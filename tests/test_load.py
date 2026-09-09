import pandas as pd
import pytest

from futures_lab.data.load import (
    OUTRIGHT_COLUMNS,
    add_contract_keys,
    check_integrity,
    filter_outrights,
    load_outrights,
    to_sessions,
)

RawRow = tuple[str, int, str, float, float, float, float, int]


def _raw(rows: list[RawRow]) -> pd.DataFrame:
    """Frame shaped like Databento's ohlcv-1d parquet (tz-aware UTC index, repeated)."""
    cols = ["ts_event", "instrument_id", "symbol", "open", "high", "low", "close", "volume"]
    df = pd.DataFrame(rows, columns=cols)
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["rtype"] = 35
    df["publisher_id"] = 1
    return df.set_index("ts_event")


def test_filter_outrights_drops_spreads_and_strategies():
    df = _raw(
        [
            ("2016-01-04", 1, "ESH6", 2038.0, 2040.0, 1990.0, 2012.5, 2_208_553),
            ("2016-01-04", 2, "ESH6-ESU6", -13.2, -13.2, -13.3, -13.2, 599),
            ("2016-01-04", 3, "UD:ZB: TL 2584931", 0.0, 0.0, 0.0, 0.0, 10),
            ("2016-01-04", 4, "MESH6", 2038.0, 2040.0, 1990.0, 2012.5, 5),
        ]
    )
    out = filter_outrights(df, "ES")
    assert list(out["symbol"]) == ["ESH6"]


def test_to_sessions_folds_sunday_stub_into_monday():
    # Real ESH6 numbers: the Sunday 2016-01-03 UTC bar is the 17:00-18:00 CT Globex open.
    df = _raw(
        [
            ("2016-01-03", 1, "ESH6", 2037.75, 2043.5, 2037.5, 2040.25, 10_915),
            ("2016-01-04", 1, "ESH6", 2038.0, 2040.0, 1990.0, 2012.5, 2_208_553),
            ("2016-01-05", 1, "ESH6", 2012.0, 2020.0, 2000.0, 2015.0, 1_900_000),
        ]
    )
    out = to_sessions(df)
    assert out.index.tz is None
    assert list(out.index) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]
    monday = out.iloc[0]
    assert monday["open"] == 2037.75  # Sunday's open
    assert monday["high"] == 2043.5  # Sunday's high
    assert monday["low"] == 1990.0
    assert monday["close"] == 2012.5  # Monday's close
    assert monday["volume"] == 10_915 + 2_208_553
    assert out.iloc[1]["volume"] == 1_900_000  # Tuesday untouched


def test_to_sessions_keeps_instruments_separate():
    df = _raw(
        [
            ("2016-01-03", 1, "ESH6", 1.0, 1.0, 1.0, 1.0, 10),
            ("2016-01-04", 1, "ESH6", 1.0, 1.0, 1.0, 1.0, 100),
            ("2016-01-03", 2, "ESM6", 1.0, 1.0, 1.0, 1.0, 1),
            ("2016-01-04", 2, "ESM6", 1.0, 1.0, 1.0, 1.0, 5),
        ]
    )
    out = to_sessions(df)
    assert len(out) == 2
    assert sorted(out["volume"]) == [6, 110]


def test_add_contract_keys_separates_decade_twins():
    df = to_sessions(
        _raw(
            [
                ("2016-01-04", 49705, "ESH6", 1.0, 1.0, 1.0, 1.0, 10),
                ("2026-01-05", 42140878, "ESH6", 1.0, 1.0, 1.0, 1.0, 10),
                ("2016-01-04", 7, "ESZ5", 1.0, 1.0, 1.0, 1.0, 10),
            ]
        )
    )
    out = add_contract_keys(df, "ES").sort_values("instrument_id")
    pairs = zip(out["contract_year"], out["contract_month"], strict=True)
    keyed = dict(zip(out["instrument_id"], pairs, strict=True))
    assert keyed[49705] == (2016, 3)
    assert keyed[42140878] == (2026, 3)
    assert keyed[7] == (2025, 12)


def test_check_integrity_rejects_instrument_spanning_decades():
    df = add_contract_keys(
        to_sessions(
            _raw(
                [
                    ("2016-01-04", 1, "ESH6", 1.0, 1.0, 1.0, 1.0, 10),
                    ("2026-01-05", 1, "ESH6", 1.0, 1.0, 1.0, 1.0, 10),
                ]
            )
        ),
        "ES",
    )
    with pytest.raises(ValueError, match="more than one contract"):
        check_integrity(df)


def test_check_integrity_rejects_two_instruments_for_one_contract():
    df = pd.DataFrame(
        {
            "instrument_id": [1, 2],
            "symbol": ["ESH6", "ESH6"],
            "contract_year": [2016, 2016],
            "contract_month": [3, 3],
        },
        index=pd.DatetimeIndex(["2016-01-04", "2016-01-05"], name="session"),
    )
    with pytest.raises(ValueError, match="same contract"):
        check_integrity(df)


def test_check_integrity_rejects_duplicate_instrument_session():
    df = pd.DataFrame(
        {
            "instrument_id": [1, 1],
            "symbol": ["ESH6", "ESH6"],
            "contract_year": [2016, 2016],
            "contract_month": [3, 3],
        },
        index=pd.DatetimeIndex(["2016-01-04", "2016-01-04"], name="session"),
    )
    with pytest.raises(ValueError, match="duplicated"):
        check_integrity(df)


def test_load_outrights_end_to_end(tmp_path):
    raw = _raw(
        [
            ("2016-01-03", 1, "ESH6", 2037.75, 2043.5, 2037.5, 2040.25, 10_915),
            ("2016-01-04", 1, "ESH6", 2038.0, 2040.0, 1990.0, 2012.5, 2_208_553),
            ("2016-01-04", 2, "ESM6", 2032.5, 2036.0, 2032.5, 2032.5, 16),
            ("2016-01-04", 3, "ESH6-ESM6", -5.0, -5.0, -5.0, -5.0, 900_000),
        ]
    )
    raw.to_parquet(tmp_path / "es_ohlcv_1d.parquet")
    out = load_outrights("ES", raw_dir=tmp_path)
    assert list(out.columns) == OUTRIGHT_COLUMNS
    assert list(out.index) == [pd.Timestamp("2016-01-04")] * 2
    assert set(out["symbol"]) == {"ESH6", "ESM6"}
    assert out.loc[out["symbol"] == "ESH6", "volume"].iloc[0] == 10_915 + 2_208_553


def test_load_outrights_missing_file_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_data"):
        load_outrights("ES", raw_dir=tmp_path)
