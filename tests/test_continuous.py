"""Synthetic contracts with hand-computed expectations around rolls.

Sessions are the business days 2016-03-07 (d1) through 2016-03-16 (d8). Contract A is
instrument 1, B is 2, C is 3. Roll dates are given directly, as the calendar would.
"""

import numpy as np
import pandas as pd
import pytest

from futures_lab.data.continuous import (
    CONTINUOUS_COLUMNS,
    active_instruments,
    build_continuous,
    build_continuous_for_root,
    load_continuous,
    load_roll_calendar,
    roll_gaps,
    validate_calendar,
)

D = pd.bdate_range("2016-03-07", periods=8)
IDS = {"A": 1, "B": 2, "C": 3}


def _bars(contracts: dict[str, dict[int, float]]) -> pd.DataFrame:
    """Bars from ``{symbol: {session_number: close}}``; OHL are fixed offsets from close."""
    rows = [
        {
            "session": D[i - 1],
            "instrument_id": IDS[sym],
            "symbol": sym,
            "open": close - 1.0,
            "high": close + 2.0,
            "low": close - 3.0,
            "close": close,
            "volume": 100 * IDS[sym],
        }
        for sym, closes in contracts.items()
        for i, close in closes.items()
    ]
    return pd.DataFrame(rows).set_index("session").sort_index(kind="stable")


def _calendar(rolls: list[tuple[int, str, str]]) -> pd.DataFrame:
    """Calendar from ``[(roll_session_number, from_symbol, to_symbol)]``."""
    return pd.DataFrame(
        [
            {
                "roll_date": D[i - 1],
                "crossover_date": D[i - 2],
                "from_symbol": a,
                "to_symbol": b,
                "from_instrument_id": IDS[a],
                "to_instrument_id": IDS[b],
            }
            for i, a, b in rolls
        ]
    )


# One roll. A: 100, 102, 101, 103 (d1-d4). B: 106, 105, 108, 110, 111 (d2-d6). Roll on d4.
ONE_ROLL_BARS = _bars(
    {"A": {1: 100, 2: 102, 3: 101, 4: 103}, "B": {2: 106, 3: 105, 4: 108, 5: 110, 6: 111}}
)
ONE_ROLL_CAL = _calendar([(4, "A", "B")])


def test_one_roll_levels_by_hand():
    out = build_continuous(ONE_ROLL_BARS, ONE_ROLL_CAL)
    assert list(out.columns) == CONTINUOUS_COLUMNS
    assert list(out.index) == list(D[:6])
    assert list(out["symbol"]) == ["A", "A", "A", "B", "B", "B"]
    assert list(out["close"]) == [100, 102, 101, 108, 110, 111]
    # gap = B(d4) - A(d4) = 108 - 103 = 5, applied to every session before d4
    assert list(out["adjustment"]) == [5, 5, 5, 0, 0, 0]
    assert list(out["adj_close"]) == [105, 107, 106, 108, 110, 111]
    assert list(out["is_roll"]) == [False, False, False, True, False, False]


def test_one_roll_returns_by_hand():
    out = build_continuous(ONE_ROLL_BARS, ONE_ROLL_CAL)
    expected = [np.nan, 2 / 100, -1 / 102, 2 / 101, 2 / 108, 1 / 110]
    np.testing.assert_allclose(out["ret"].to_numpy(), expected, rtol=1e-12)
    np.testing.assert_allclose(out["log_ret"].to_numpy(), np.log1p(expected), rtol=1e-12)


def test_roll_day_return_is_the_outgoing_contracts_own_return():
    out = build_continuous(ONE_ROLL_BARS, ONE_ROLL_CAL)
    roll_ret = out.loc[D[3], "ret"]
    assert roll_ret == pytest.approx(103 / 101 - 1)  # A held through d4, rolled at the close
    naive = 108 / 101 - 1  # what splicing raw closes would report: a 6.9% phantom jump
    assert roll_ret != pytest.approx(naive)


def test_adjusted_change_on_roll_day_equals_outgoing_change():
    out = build_continuous(ONE_ROLL_BARS, ONE_ROLL_CAL)
    assert out["adj_close"].diff().loc[D[3]] == pytest.approx(103 - 101)


# Two rolls. A: d1-d4; B: d3-d7; C: d5-d8. Rolls on d4 (A->B) and d7 (B->C).
TWO_ROLL_BARS = _bars(
    {
        "A": {1: 100, 2: 102, 3: 101, 4: 103},
        "B": {3: 105, 4: 108, 5: 110, 6: 109, 7: 112},
        "C": {5: 120, 6: 118, 7: 121, 8: 123},
    }
)
TWO_ROLL_CAL = _calendar([(4, "A", "B"), (7, "B", "C")])


def test_two_rolls_propagate_gaps_backward_cumulatively():
    out = build_continuous(TWO_ROLL_BARS, TWO_ROLL_CAL)
    # gap1 = 108 - 103 = 5 on d4; gap2 = 121 - 112 = 9 on d7
    assert list(out["adjustment"]) == [14, 14, 14, 9, 9, 9, 0, 0]
    assert list(out["adj_close"]) == [114, 116, 115, 117, 119, 118, 121, 123]
    assert list(out["symbol"]) == ["A", "A", "A", "B", "B", "B", "C", "C"]
    assert out["adj_close"].diff().loc[D[3]] == pytest.approx(103 - 101)  # A's move on d4
    assert out["adj_close"].diff().loc[D[6]] == pytest.approx(112 - 109)  # B's move on d7
    assert out.loc[D[6], "ret"] == pytest.approx(112 / 109 - 1)
    assert out.loc[D[7], "ret"] == pytest.approx(123 / 121 - 1)


def test_two_rolls_gaps_and_unsorted_calendar():
    gaps = roll_gaps(TWO_ROLL_BARS, TWO_ROLL_CAL)
    assert list(gaps) == [5, 9]
    reversed_cal = TWO_ROLL_CAL.iloc[::-1].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        build_continuous(TWO_ROLL_BARS, reversed_cal), build_continuous(TWO_ROLL_BARS, TWO_ROLL_CAL)
    )


def test_all_four_prices_shift_by_the_same_amount_and_last_segment_is_untouched():
    out = build_continuous(TWO_ROLL_BARS, TWO_ROLL_CAL)
    for col in ["open", "high", "low", "close"]:
        np.testing.assert_allclose(out[f"adj_{col}"] - out[col], out["adjustment"])
    last = out.loc[D[6] :]
    for col in ["open", "high", "low", "close"]:
        assert (last[f"adj_{col}"] == last[col]).all()
    # ranges in points are preserved by construction
    np.testing.assert_allclose(out["adj_high"] - out["adj_low"], out["high"] - out["low"])


def test_volume_columns():
    out = build_continuous(TWO_ROLL_BARS, TWO_ROLL_CAL)
    assert list(out["volume"]) == [100, 100, 100, 200, 200, 200, 300, 300]
    # d3: A+B; d5, d6: B+C; d7: B+C; d8: C only
    assert list(out["volume_all"]) == [100, 100, 300, 300, 500, 500, 500, 300]


def test_negative_adjusted_level_leaves_returns_exact():
    # A: 4 -> 6; B: 1 -> 1.1; roll on d2. gap = 1 - 6 = -5, so A's d1 level becomes -1.
    bars = _bars({"A": {1: 4, 2: 6}, "B": {2: 1, 3: 1.1}})
    out = build_continuous(bars, _calendar([(2, "A", "B")]))
    assert list(out["adj_close"]) == pytest.approx([-1, 1, 1.1])
    np.testing.assert_allclose(out["ret"].to_numpy()[1:], [6 / 4 - 1, 1.1 / 1 - 1])
    assert np.isfinite(out["ret"].to_numpy()[1:]).all()
    # pct_change on the adjusted level would report -200% here; that is why it is never used
    assert out["adj_close"].pct_change().iloc[1] == pytest.approx(-2.0)


def test_active_instruments_switch_on_roll_date():
    active = active_instruments(D, TWO_ROLL_CAL)
    assert list(active) == [1, 1, 1, 2, 2, 2, 3, 3]


def test_missing_close_on_roll_date_raises():
    bars = ONE_ROLL_BARS.drop(index=D[3])  # removes both A's and B's d4 rows
    bars = pd.concat([bars, _bars({"B": {4: 108}})]).sort_index(kind="stable")  # restore B only
    with pytest.raises(ValueError, match="no close for both contracts"):
        build_continuous(bars, ONE_ROLL_CAL)


def test_active_contract_without_a_bar_raises():
    bars = ONE_ROLL_BARS.drop(index=D[4])  # B has no d5 row, but B is active on d5
    bars = pd.concat([bars, _bars({"A": {5: 104}})]).sort_index(kind="stable")
    with pytest.raises(ValueError, match="active contract has no bar"):
        build_continuous(bars, ONE_ROLL_CAL)


def test_calendar_validation():
    with pytest.raises(ValueError, match="no rolls"):
        validate_calendar(ONE_ROLL_CAL.iloc[0:0])
    broken = _calendar([(4, "A", "B"), (7, "A", "C")])  # second roll should leave B
    with pytest.raises(ValueError, match="chain is broken"):
        validate_calendar(broken)
    dup = _calendar([(4, "A", "B"), (4, "B", "C")])
    with pytest.raises(ValueError, match="repeated roll dates"):
        validate_calendar(dup)
    with pytest.raises(ValueError, match="missing columns"):
        validate_calendar(ONE_ROLL_CAL.drop(columns="to_instrument_id"))


def test_calendar_csv_round_trip_and_end_to_end(tmp_path):
    # Raw parquet in Databento shape (tz-aware, repeated ts_event), calendar as the build
    # script writes it, then the same entry point the build script uses.
    raw = TWO_ROLL_BARS.reset_index().rename(columns={"session": "ts_event"})
    raw["ts_event"] = raw["ts_event"].dt.tz_localize("UTC")
    raw["symbol"] = raw["symbol"].map({"A": "ESH6", "B": "ESM6", "C": "ESU6"})
    raw["rtype"], raw["publisher_id"] = 35, 1
    raw.set_index("ts_event").to_parquet(tmp_path / "es_ohlcv_1d.parquet")
    cal = TWO_ROLL_CAL.copy()
    cal["from_symbol"] = cal["from_symbol"].map({"A": "ESH6", "B": "ESM6"})
    cal["to_symbol"] = cal["to_symbol"].map({"B": "ESM6", "C": "ESU6"})
    cal.to_csv(tmp_path / "roll_calendar_es.csv", index=False, date_format="%Y-%m-%d")

    loaded = load_roll_calendar("ES", processed_dir=tmp_path)
    assert loaded["roll_date"].dtype.kind == "M"
    assert list(loaded["roll_date"]) == [D[3], D[6]]

    out = build_continuous_for_root("ES", raw_dir=tmp_path, processed_dir=tmp_path)
    assert list(out["adj_close"]) == [114, 116, 115, 117, 119, 118, 121, 123]
    assert list(out["symbol"]) == ["ESH6"] * 3 + ["ESM6"] * 3 + ["ESU6"] * 2

    out.to_parquet(tmp_path / "continuous_es.parquet")
    pd.testing.assert_frame_equal(load_continuous("ES", processed_dir=tmp_path), out)


def test_missing_file_messages(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_roll_calendar"):
        load_roll_calendar("ES", processed_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="build_continuous"):
        load_continuous("ES", processed_dir=tmp_path)
