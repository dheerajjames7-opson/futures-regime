import pandas as pd

from futures_lab.data.rolls import detect_rolls


def _leader(symbols: list[str]) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(symbols), freq="B")
    return pd.DataFrame({"symbol": symbols, "close": 100.0, "volume": 1000},
                        index=dates)


def test_clean_roll_detected():
    leader = _leader(["ESH26"] * 5 + ["ESM26"] * 5)
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1
    assert rolls.iloc[0]["to_symbol"] == "ESM26"


def test_single_day_flicker_ignored():
    leader = _leader(["ESH26"] * 4 + ["ESM26"] + ["ESH26"] * 4 + ["ESM26"] * 5)
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 1  # the one-day flicker must not trigger a roll


def test_backward_reversion_never_rolls():
    leader = _leader(["ESM26"] * 5 + ["ESH26"] * 3 + ["ESM26"] * 3)
    rolls = detect_rolls(leader, "ES", confirm_days=2)
    assert len(rolls) == 0