"""Difference-adjusted ("back-adjusted") continuous contracts.

Why difference adjustment rather than ratio adjustment
-----------------------------------------------------
A futures position is a number of contracts, N. Its P&L over a session is N times the
multiplier times the change in that contract's price. Rolling exits N contracts of the
expiring month and enters N of the next: N is unchanged and no cash changes hands, so the
P&L history of the position is the concatenation of per-contract price *changes*.
Difference adjustment builds the one series whose one-session change equals that realised
change on every session, roll sessions included. Each roll's gap (incoming close minus
outgoing close on the roll session) is added to every earlier price, so the discontinuity
disappears and the most recent contract is left at traded prices.

Ratio adjustment multiplies history by the cumulative product of roll ratios instead. It
preserves the percentage returns of a position that rebalances its contract count at every
roll to keep notional constant, which is a trading policy rather than the instrument, and
it rescales historical point moves: over 126 CL rolls through alternating contango and
backwardation the cumulative ratio drifts well away from one, so a 2016 daily range is
reported at a different scale than it traded. Realised volatility in points, drawdown in
points, Amihud's |change| per unit of volume, and the Corwin-Schultz range estimator
(which needs consecutive sessions' highs and lows in one price basis) all need the
additive frame. Difference adjustment gives those and exact returns from one table.

Its cost is that the adjusted level is a cumulative P&L, not a price. Far from the present
it drifts from the traded level and for CL it can cross zero, so it must never be a
denominator or the argument of a log. Returns here are therefore the adjusted change
divided by the previous session's *unadjusted* front-month close. That equals the simple
return of the contract actually held, which is also what ratio adjustment would report,
so the return-based model loses nothing. Use the ``ret`` and ``log_ret`` columns; do not
call ``pct_change`` on ``adj_close``.

Conventions
-----------
Shared with ``futures_lab.data.rolls``: the position holds the outgoing contract through
the ``roll_date`` session and rolls at its close. Hence the gap is the difference of the
two contracts' closes on ``roll_date``; from ``roll_date`` onward the unadjusted OHLCV
columns are the incoming contract's; and the ``roll_date`` row's return is the outgoing
contract's own return for that session. Both contracts trade on ``roll_date`` by
construction of the calendar, so no future information is used. Under this convention
``adj_close.diff() / close.shift(1)`` is exact on every row, which is why the switch is
made on ``roll_date`` and not the session after.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from futures_lab.config import continuous_path, roll_calendar_path
from futures_lab.data.load import load_outrights
from futures_lab.data.rolls import ROLL_COLUMNS

CONTINUOUS_COLUMNS = [
    "instrument_id",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "volume_all",
    "adjustment",
    "adj_open",
    "adj_high",
    "adj_low",
    "adj_close",
    "is_roll",
    "ret",
    "log_ret",
]

PRICE_COLUMNS = ["open", "high", "low", "close"]


def validate_calendar(calendar: pd.DataFrame) -> pd.DataFrame:
    """Return the calendar sorted by ``roll_date`` after checking it forms a single chain."""
    missing = [c for c in ROLL_COLUMNS if c not in calendar.columns]
    if missing:
        raise ValueError(f"roll calendar is missing columns {missing}")
    if calendar.empty:
        raise ValueError("roll calendar has no rolls; the active contract cannot be inferred")
    cal = calendar.sort_values("roll_date").reset_index(drop=True)
    cal["roll_date"] = pd.to_datetime(cal["roll_date"])
    if not cal["roll_date"].is_unique:
        raise ValueError("roll calendar has repeated roll dates")
    outgoing = cal["from_instrument_id"].to_numpy()[1:]
    incoming = cal["to_instrument_id"].to_numpy()[:-1]
    if not np.array_equal(outgoing, incoming):
        raise ValueError(
            "roll calendar chain is broken: each roll's from_instrument_id must equal the "
            "previous roll's to_instrument_id"
        )
    return cal


def load_roll_calendar(root: str, processed_dir: Path | None = None) -> pd.DataFrame:
    """Read the ``roll_calendar_<root>.csv`` that ``scripts/build_roll_calendar.py`` writes."""
    path = roll_calendar_path(root, processed_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python scripts/build_roll_calendar.py`.")
    cal = pd.read_csv(path, parse_dates=["roll_date", "crossover_date"])
    return validate_calendar(cal)


def active_instruments(sessions: pd.DatetimeIndex, calendar: pd.DataFrame) -> pd.Series:
    """Instrument held at the close of each session: the incoming contract from ``roll_date`` on."""
    cal = validate_calendar(calendar)
    roll_dates = cal["roll_date"].to_numpy(dtype="datetime64[ns]")
    n_rolled = np.searchsorted(roll_dates, sessions.to_numpy(dtype="datetime64[ns]"), side="right")
    chain = np.concatenate(
        ([cal["from_instrument_id"].iloc[0]], cal["to_instrument_id"].to_numpy())
    ).astype("int64")
    return pd.Series(chain[n_rolled], index=sessions, name="instrument_id")


def roll_gaps(bars: pd.DataFrame, calendar: pd.DataFrame) -> pd.Series:
    """Additive gap of each roll: incoming close minus outgoing close on ``roll_date``.

    Raises if either contract has no bar on its roll date; the gap is undefined then and a
    silent fallback would hide a calendar or data problem.
    """
    cal = validate_calendar(calendar)
    close = bars.reset_index().set_index(["session", "instrument_id"])["close"]
    close.index = close.index.set_levels(close.index.levels[1].astype("int64"), level=1)
    outgoing = pd.MultiIndex.from_arrays(
        [cal["roll_date"], cal["from_instrument_id"].astype("int64")]
    )
    incoming = pd.MultiIndex.from_arrays(
        [cal["roll_date"], cal["to_instrument_id"].astype("int64")]
    )
    old = close.reindex(outgoing).to_numpy(dtype=float)
    new = close.reindex(incoming).to_numpy(dtype=float)
    bad = np.isnan(old) | np.isnan(new)
    if bad.any():
        rows = cal.loc[bad, ["roll_date", "from_symbol", "to_symbol"]].head(5)
        raise ValueError(
            f"no close for both contracts on roll date(s):\n{rows.to_string(index=False)}"
        )
    return pd.Series(new - old, index=cal.index, name="gap")


def build_continuous(bars: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Difference-adjusted continuous series from per-contract bars and a roll calendar.

    ``bars`` is the frame ``load_outrights`` returns (session index, one row per instrument
    and session). ``calendar`` has the ``ROLL_COLUMNS`` schema. The result has one row per
    session and the ``CONTINUOUS_COLUMNS``:

    - ``instrument_id``, ``symbol``, ``open``..``volume``: the contract held at the close,
      at traded prices; ``volume_all`` is the summed volume of every outright that session.
    - ``adjustment``: the additive shift applied to that session, i.e. the sum of the gaps
      of all rolls that happen *after* it; zero from the last roll onward.
    - ``adj_open``..``adj_close``: traded prices plus ``adjustment``.
    - ``is_roll``: True on ``roll_date`` sessions.
    - ``ret``: ``adj_close.diff() / close.shift(1)``, the simple return of the contract held
      during the session. ``log_ret = log1p(ret)``.
    """
    cal = validate_calendar(calendar)
    bars = bars.assign(instrument_id=bars["instrument_id"].astype("int64"))
    sessions = bars.index.unique().sort_values()
    active = active_instruments(sessions, cal)

    keyed = bars.reset_index().set_index(["session", "instrument_id"])
    wanted = pd.MultiIndex.from_arrays(
        [sessions, active.to_numpy()], names=["session", "instrument_id"]
    )
    rows = keyed.reindex(wanted)
    missing = rows["close"].isna().to_numpy()
    if missing.any():
        first = [(s.date(), int(i)) for s, i in wanted[missing][:3]]
        raise ValueError(
            f"{int(missing.sum())} session(s) where the active contract has no bar, first: {first}"
        )

    out = rows.reset_index(level="instrument_id")[
        ["instrument_id", "symbol", *PRICE_COLUMNS, "volume"]
    ]
    out["volume_all"] = bars.groupby(level=0)["volume"].sum().reindex(sessions).to_numpy()

    # Back-adjustment proper. gaps[k] is roll k's (incoming - outgoing) close difference on
    # its roll date. A session that has seen n_rolled rolls so far must be shifted by the
    # gaps of every *later* roll, so its adjustment is the suffix sum gaps[n_rolled:]. The
    # shift is additive and identical for open, high, low and close, which keeps each
    # session's range in points intact and puts consecutive sessions on one price basis
    # across a roll. Because the shift is a constant within a segment and changes by exactly
    # gaps[k] at roll k, the one-session change of adj_close on the roll date collapses to
    # the outgoing contract's own change (see module docstring), so returns are undistorted.
    gaps = roll_gaps(bars, cal).to_numpy(dtype=float)
    roll_dates = cal["roll_date"].to_numpy(dtype="datetime64[ns]")
    n_rolled = np.searchsorted(roll_dates, sessions.to_numpy(dtype="datetime64[ns]"), side="right")
    suffix_sums = np.concatenate((np.cumsum(gaps[::-1])[::-1], [0.0]))
    adjustment = suffix_sums[n_rolled]

    out["adjustment"] = adjustment
    for col in PRICE_COLUMNS:
        out[f"adj_{col}"] = out[col].to_numpy(dtype=float) + adjustment
    out["is_roll"] = out.index.isin(cal["roll_date"])

    # Divide by the previous *traded* close, never by adj_close: the adjusted level is a
    # cumulative P&L and can be arbitrarily far from the traded price, or negative (CL).
    out["ret"] = out["adj_close"].diff() / out["close"].shift(1)
    out["log_ret"] = np.log1p(out["ret"])
    out.index.name = "session"
    return out[CONTINUOUS_COLUMNS]


def build_continuous_for_root(
    root: str, raw_dir: Path | None = None, processed_dir: Path | None = None
) -> pd.DataFrame:
    """Load bars and the committed roll calendar for ``root`` and build the continuous series."""
    return build_continuous(load_outrights(root, raw_dir), load_roll_calendar(root, processed_dir))


def load_continuous(root: str, processed_dir: Path | None = None) -> pd.DataFrame:
    """Read the ``continuous_<root>.parquet`` that ``scripts/build_continuous.py`` writes."""
    path = continuous_path(root, processed_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python scripts/build_continuous.py`.")
    return pd.read_parquet(path)
