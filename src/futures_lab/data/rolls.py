"""Volume-crossover roll calendar.

The front contract on a session is the outright with the highest volume. A roll is
declared when a later-dated contract has out-traded the incumbent on ``confirm_days``
consecutive sessions; the confirmation rule filters single-day flickers, which occur
around expiry and on days when spread activity distorts outright volume. A day on which
the incumbent or an earlier-dated contract leads breaks the streak. Reversions to an
earlier contract never roll.

``crossover_date`` is the first session of the confirming streak and ``roll_date`` the
last, so ``roll_date`` lags the crossover by ``confirm_days - 1`` sessions. Downstream
code switches to the new contract on ``roll_date``. Both contracts trade that session,
so a back-adjustment gap taken from their same-day closes uses no future information.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from futures_lab.config import ROLL_CONFIRM_DAYS
from futures_lab.data.contracts import parse_contract
from futures_lab.data.load import load_outrights

ROLL_COLUMNS = [
    "roll_date",
    "crossover_date",
    "from_symbol",
    "to_symbol",
    "from_instrument_id",
    "to_instrument_id",
]


def daily_volume_leader(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per session: the outright with the highest volume.

    ``df`` is a session-indexed frame such as ``load_outrights`` returns; the index is
    expected to repeat (several contracts per session). Selection is positional, so a
    repeated index is handled correctly. Ties go to the first row in input order.
    """
    if df.empty:
        return df.iloc[0:0]
    d = df.reset_index()
    session_col = d.columns[0]
    pos = d.groupby(session_col, sort=True)["volume"].idxmax()
    return d.loc[pos].set_index(session_col)


def detect_rolls(
    leader: pd.DataFrame, root: str, confirm_days: int = ROLL_CONFIRM_DAYS
) -> pd.DataFrame:
    """Detect rolls in a one-row-per-session ``leader`` frame.

    Requires a datetime index and a ``symbol`` column; ``instrument_id`` is carried
    through when present. Contract order is resolved per row from symbol and session
    date, so one-digit year codes are handled across decades. Always returns the
    ``ROLL_COLUMNS`` schema, empty when no roll occurs.
    """
    if confirm_days < 1:
        raise ValueError("confirm_days must be at least 1")
    if leader.empty:
        return pd.DataFrame(columns=ROLL_COLUMNS)

    dates = list(leader.index)
    symbols = list(leader["symbol"])
    ids = list(leader["instrument_id"]) if "instrument_id" in leader else [pd.NA] * len(dates)
    keys = [parse_contract(s, root, d) for s, d in zip(symbols, dates, strict=True)]

    current_sym, current_key, current_id = symbols[0], keys[0], ids[0]
    streak_sym, streak, streak_start = None, 0, None
    rolls: list[dict[str, object]] = []

    for day, sym, key, iid in zip(dates, symbols, keys, ids, strict=True):
        if sym == current_sym or key <= current_key:
            streak_sym, streak = None, 0
            continue
        if sym == streak_sym:
            streak += 1
        else:
            streak_sym, streak, streak_start = sym, 1, day
        if streak >= confirm_days:
            rolls.append(
                {
                    "roll_date": day,
                    "crossover_date": streak_start,
                    "from_symbol": current_sym,
                    "to_symbol": sym,
                    "from_instrument_id": current_id,
                    "to_instrument_id": iid,
                }
            )
            current_sym, current_key, current_id = sym, key, iid
            streak_sym, streak = None, 0

    return pd.DataFrame(rolls, columns=ROLL_COLUMNS)


def build_roll_calendar(
    root: str, confirm_days: int = ROLL_CONFIRM_DAYS, raw_dir: Path | None = None
) -> pd.DataFrame:
    """Load, select the daily volume leader and detect rolls for one root."""
    bars = load_outrights(root, raw_dir)
    return detect_rolls(daily_volume_leader(bars), root, confirm_days)
