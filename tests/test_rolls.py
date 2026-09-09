import pandas as pd
import pytest

from futures_lab.data.rolls import ROLL_COLUMNS, daily_volume_leader, detect_rolls

# Symbols are real Globex shapes (one-digit year codes) with dates in the matching year.


def _leader(symbols: list[str], start: str) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(symbols))
    ids = {s: i + 1 for i, s in enumerate(dict.fromkeys(symbols))}
    return pd.DataFrame(
        {
            "symbol": symbols,
            "instrument_id": [ids[s] for s in symbols],
            "close": 100.0,
            "volume": 1000,
        },
        index=dates,
    )


def test_clean_roll_detected_with_dates_and_ids():
    leader = _leader(["ESH6"] * 5 + ["ESM6"] * 5, "2016-03-07")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert list(rolls.columns) == ROLL_COLUMNS
    assert len(rolls) == 1
    r = rolls.iloc[0]
    assert (r["from_symbol"], r["to_symbol"]) == ("ESH6", "ESM6")
    assert r["crossover_date"] == leader.index[5]
    assert r["roll_date"] == leader.index[6]
    assert (r["from_instrument_id"], r["to_instrument_id"]) == (1, 2)


def test_single_day_flicker_ignored():
    leader = _leader(["ESH6"] * 4 + ["ESM6"] + ["ESH6"] * 4 + ["ESM6"] * 5, "2016-03-01")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1
    assert rolls.iloc[0]["roll_date"] == leader.index[10]


def test_backward_reversion_never_rolls():
    leader = _leader(["ESM6"] * 5 + ["ESH6"] * 3 + ["ESM6"] * 3, "2016-03-14")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert rolls.empty
    assert list(rolls.columns) == ROLL_COLUMNS


def test_backward_day_breaks_the_confirmation_streak():
    # ESU6 leads on day 3, an earlier contract interrupts on day 4, ESU6 leads days 5-6.
    # The streak must restart on day 5, so the roll confirms on day 6, not day 5.
    leader = _leader(["ESM6"] * 3 + ["ESU6", "ESH6", "ESU6", "ESU6"], "2016-06-06")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1
    assert rolls.iloc[0]["crossover_date"] == leader.index[5]
    assert rolls.iloc[0]["roll_date"] == leader.index[6]


def test_decade_boundary_rolls_forward():
    leader = _leader(["ESZ9"] * 3 + ["ESH0"] * 3, "2019-12-09")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1
    assert rolls.iloc[0]["to_symbol"] == "ESH0"


def test_same_symbol_string_in_a_later_decade_is_a_forward_roll():
    # ESH6 in Dec 2025 is March 2026, later than ESZ5; the old parser called it 2026 vs 2015.
    leader = _leader(["ESZ5"] * 3 + ["ESH6"] * 3, "2025-12-08")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1
    assert rolls.iloc[0]["to_symbol"] == "ESH6"


def test_skipping_a_contract_is_allowed():
    leader = _leader(["CLK0"] * 3 + ["CLN0"] * 3, "2020-04-13")
    rolls = detect_rolls(leader, "CL", confirm_days=2)
    assert len(rolls) == 1
    assert (rolls.iloc[0]["from_symbol"], rolls.iloc[0]["to_symbol"]) == ("CLK0", "CLN0")


def test_confirm_days_one_rolls_on_the_crossover_day():
    leader = _leader(["ESH6"] * 2 + ["ESM6"], "2016-03-14")
    rolls = detect_rolls(leader, "ES", confirm_days=1)
    assert len(rolls) == 1
    assert rolls.iloc[0]["roll_date"] == rolls.iloc[0]["crossover_date"] == leader.index[2]


def test_confirm_days_must_be_positive():
    with pytest.raises(ValueError):
        detect_rolls(_leader(["ESH6"], "2016-01-04"), "ES", confirm_days=0)


def test_empty_leader_returns_schema():
    rolls = detect_rolls(_leader([], "2016-01-04"), "ES")
    assert rolls.empty
    assert list(rolls.columns) == ROLL_COLUMNS


def test_leader_without_instrument_id_column_still_works():
    leader = _leader(["ESH6"] * 3 + ["ESM6"] * 3, "2016-03-07").drop(columns="instrument_id")
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1
    assert pd.isna(rolls.iloc[0]["from_instrument_id"])


def _bars(rows: list[tuple[str, str, int, int]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["session", "symbol", "instrument_id", "volume"])
    df["session"] = pd.to_datetime(df["session"])
    df["close"] = 100.0
    return df.set_index("session")


def test_daily_volume_leader_picks_one_row_per_session_on_repeated_index():
    # The original implementation used label-based .loc on a non-unique index and
    # returned every row. Three sessions, two contracts each, must give three rows.
    bars = _bars(
        [
            ("2016-03-08", "ESH6", 1, 1_000_000),
            ("2016-03-08", "ESM6", 2, 50_000),
            ("2016-03-09", "ESH6", 1, 900_000),
            ("2016-03-09", "ESM6", 2, 800_000),
            ("2016-03-10", "ESH6", 1, 400_000),
            ("2016-03-10", "ESM6", 2, 1_200_000),
        ]
    )
    leader = daily_volume_leader(bars)
    assert len(leader) == 3
    assert leader.index.is_unique
    assert list(leader["symbol"]) == ["ESH6", "ESH6", "ESM6"]
    assert list(leader["volume"]) == [1_000_000, 900_000, 1_200_000]


def test_daily_volume_leader_on_empty_input():
    empty = _bars([]).iloc[0:0]
    assert daily_volume_leader(empty).empty


def test_leader_then_detect_end_to_end():
    bars = _bars(
        [
            ("2016-03-08", "ESH6", 1, 1_000_000),
            ("2016-03-08", "ESM6", 2, 50_000),
            ("2016-03-09", "ESH6", 1, 900_000),
            ("2016-03-09", "ESM6", 2, 950_000),
            ("2016-03-10", "ESH6", 1, 400_000),
            ("2016-03-10", "ESM6", 2, 1_200_000),
            ("2016-03-11", "ESH6", 1, 100_000),
            ("2016-03-11", "ESM6", 2, 1_500_000),
        ]
    )
    rolls = detect_rolls(daily_volume_leader(bars), "ES", confirm_days=2)
    assert len(rolls) == 1
    assert rolls.iloc[0]["crossover_date"] == pd.Timestamp("2016-03-09")
    assert rolls.iloc[0]["roll_date"] == pd.Timestamp("2016-03-10")
