"""Build volume-crossover roll calendars for every root and write them to data/processed.

Usage: python scripts/build_roll_calendar.py
Requires the raw parquet cache (see data/README.md).
"""

from __future__ import annotations

from futures_lab.config import PROCESSED_DIR, ROLL_CONFIRM_DAYS, ROOTS
from futures_lab.data.rolls import build_roll_calendar


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for root in ROOTS:
        rolls = build_roll_calendar(root, confirm_days=ROLL_CONFIRM_DAYS)
        out = PROCESSED_DIR / f"roll_calendar_{root.lower()}.csv"
        rolls.to_csv(out, index=False, date_format="%Y-%m-%d")
        first = rolls["roll_date"].min().date() if len(rolls) else None
        last = rolls["roll_date"].max().date() if len(rolls) else None
        print(f"{root}: {len(rolls):3d} rolls  {first} -> {last}  -> {out}")


if __name__ == "__main__":
    main()
