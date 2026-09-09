"""Fetch daily OHLCV for every root from Databento and cache it as parquet.

Usage: python scripts/fetch_data.py

Pulls ``ROOT.FUT`` parent symbology, which returns every instrument under the root
(outrights plus calendar spreads and strategies); outright filtering happens later in
``futures_lab.data.load``. Files already in ``data/raw`` are never re-downloaded. Run
``scripts/estimate_cost.py`` first to preview the credit cost.
"""

from __future__ import annotations

from pathlib import Path

import databento as db

from futures_lab.config import DATASET, END, ROOTS, SCHEMA, START, databento_api_key, raw_path


def fetch_root(client: db.Historical, root: str) -> Path:
    out_path = raw_path(root)
    if out_path.exists():
        print(f"{root}: cached ({out_path})")
        return out_path

    print(f"{root}: fetching from Databento...")
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[f"{root}.FUT"],
        stype_in="parent",
        schema=SCHEMA,
        start=START,
        end=END,
    )
    df = data.to_df()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"{root}: saved {len(df):,} rows -> {out_path}")
    return out_path


def main() -> None:
    client = db.Historical(databento_api_key())
    for root in ROOTS:
        fetch_root(client, root)


if __name__ == "__main__":
    main()
