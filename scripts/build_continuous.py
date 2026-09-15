"""Build difference-adjusted continuous contracts for every root.

Usage: python scripts/build_continuous.py [--force]

Cache-first like the other scripts: an existing data/processed/continuous_<root>.parquet is
kept unless --force is given (needed after the roll rule or the raw data changes). Requires
the raw parquet cache and the roll calendars from scripts/build_roll_calendar.py. Output is
git-ignored: it is a rearrangement of licensed Databento prices.
"""

from __future__ import annotations

import argparse

import numpy as np

from futures_lab.config import PROCESSED_DIR, ROOTS, continuous_path
from futures_lab.data.continuous import build_continuous_for_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--force", action="store_true", help="rebuild even if cached")
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for root in ROOTS:
        out = continuous_path(root)
        if out.exists() and not args.force:
            print(f"{root}: cached ({out})")
            continue
        cont = build_continuous_for_root(root)
        cont.to_parquet(out)
        ret = cont["ret"].to_numpy(dtype=float)[1:]
        print(
            f"{root}: {len(cont):5d} sessions, {int(cont['is_roll'].sum()):3d} rolls, "
            f"adj_close [{cont['adj_close'].min():9.2f}, {cont['adj_close'].max():9.2f}], "
            f"close min {cont['close'].min():8.2f}, max |ret| {np.abs(ret).max():.1%}, "
            f"non-finite returns {int((~np.isfinite(ret)).sum())} -> {out.name}"
        )


if __name__ == "__main__":
    main()
