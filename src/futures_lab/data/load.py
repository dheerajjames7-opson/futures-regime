"""Load cached Databento daily bars into a clean, session-aligned outright frame.

Three properties of the raw parquet are wrong for our purpose and are fixed here.

1. Parent symbology (``ES.FUT``) includes calendar spreads, butterflies, inter-commodity
   spreads and user-defined strategies. Keep outrights only.
2. ``ohlcv-1d`` bars are cut on UTC days, not CME sessions. The Sunday 17:00 CT Globex
   open therefore yields a one-hour Sunday bar (540 per root in 2016-2026, under 1% of
   volume), inflating the calendar to ~311 "days" a year. Weekend bars are folded into
   the following session. Bars still close at 00:00 UTC, one to two hours after the next
   session opens, so ``close`` is the last trade before 18:00/19:00 CT, not the CME
   settlement. That is acceptable for daily-frequency regime work and is documented.
3. One-digit Globex year codes repeat across decades (``ESH6`` in 2016 and in 2026).
   Each row's contract year is resolved from its session date, and the loader checks
   that every ``instrument_id`` resolves to exactly one contract.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from futures_lab.config import raw_path
from futures_lab.data.contracts import outright_pattern, parse_contract

OUTRIGHT_COLUMNS = [
    "instrument_id",
    "symbol",
    "contract_year",
    "contract_month",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


def load_raw(root: str, raw_dir: Path | None = None) -> pd.DataFrame:
    """Read the cached Databento parquet for ``root`` exactly as fetched."""
    path = raw_path(root, raw_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/fetch_data.py` (see data/README.md)."
        )
    return pd.read_parquet(path)


def filter_outrights(df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Keep rows whose ``symbol`` is a single-contract future on ``root``."""
    mask = df["symbol"].str.fullmatch(outright_pattern(root).pattern)
    return df[mask.fillna(False).to_numpy(dtype=bool)]


def to_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Fold weekend UTC bars into the following session; index by tz-naive session date.

    Saturday bars (none observed, handled for safety) move forward two days and Sunday
    bars one day. Bars sharing an ``instrument_id`` and session are aggregated with
    first open, max high, min low, last close and summed volume.
    """
    d = df.reset_index()
    ts = d["ts_event"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    session = ts.dt.normalize()
    dow = session.dt.dayofweek.to_numpy()
    shift_days = np.where(dow == 6, 1, np.where(dow == 5, 2, 0))
    d["session"] = session + pd.to_timedelta(shift_days, unit="D")
    d = d.sort_values(["instrument_id", "ts_event"], kind="stable")
    agg = (
        d.groupby(["instrument_id", "symbol", "session"], sort=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    return agg.set_index("session").sort_index(kind="stable")


def add_contract_keys(df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Add ``contract_year`` and ``contract_month`` resolved per row from symbol and session."""
    sessions = df.index.date
    symbols = df["symbol"].to_numpy()
    years = np.empty(len(df), dtype=np.int64)
    months = np.empty(len(df), dtype=np.int64)
    for i, (sym, day) in enumerate(zip(symbols, sessions, strict=True)):
        years[i], months[i] = parse_contract(sym, root, day)
    out = df.copy()
    out["contract_year"] = years
    out["contract_month"] = months
    return out


def check_integrity(df: pd.DataFrame) -> None:
    """Raise unless instruments and contracts map one-to-one and sessions do not repeat.

    Both directions are checked: an instrument that resolves to two contracts means the
    year rule mis-dated some of its rows; two instruments resolving to one contract means
    a relisted symbol was confused with its predecessor.
    """
    per_inst = df.groupby("instrument_id")[["contract_year", "contract_month"]].nunique()
    bad = per_inst[(per_inst > 1).any(axis=1)]
    if len(bad):
        raise ValueError(
            "instrument_id resolved to more than one contract (year-code ambiguity): "
            f"{bad.index.tolist()[:10]}"
        )
    per_contract = df.groupby(["contract_year", "contract_month"])["instrument_id"].nunique()
    clash = per_contract[per_contract > 1]
    if len(clash):
        raise ValueError(
            f"several instrument_ids resolved to the same contract: {clash.index.tolist()[:10]}"
        )
    dup = int(df.reset_index().duplicated(["instrument_id", "session"]).sum())
    if dup:
        raise ValueError(f"{dup} duplicated (instrument_id, session) rows after folding")


def load_outrights(root: str, raw_dir: Path | None = None) -> pd.DataFrame:
    """Clean outright bars for ``root``: one row per (instrument, session).

    Index: ``session`` (tz-naive, midnight, no weekends). Columns: ``OUTRIGHT_COLUMNS``.
    """
    df = load_raw(root, raw_dir)
    df = filter_outrights(df, root)
    df = to_sessions(df)
    df = add_contract_keys(df, root)
    check_integrity(df)
    return df[OUTRIGHT_COLUMNS]
