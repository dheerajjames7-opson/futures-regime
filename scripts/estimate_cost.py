"""Preview the Databento credit cost of the full pull without downloading anything.

Usage: python scripts/estimate_cost.py
"""

from __future__ import annotations

import databento as db

from futures_lab.config import DATASET, END, ROOTS, SCHEMA, START, databento_api_key


def main() -> None:
    client = db.Historical(databento_api_key())
    total = 0.0
    for root in ROOTS:
        cost = client.metadata.get_cost(
            dataset=DATASET,
            symbols=[f"{root}.FUT"],
            stype_in="parent",
            schema=SCHEMA,
            start=START,
            end=END,
        )
        print(f"{root}: ${cost:.4f}")
        total += cost
    print(f"\nTotal estimated cost: ${total:.4f}")


if __name__ == "__main__":
    main()
