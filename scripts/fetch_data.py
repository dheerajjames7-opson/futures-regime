import os
from pathlib import Path

import databento as db
from dotenv import load_dotenv

load_dotenv()

ROOTS = ["ES", "ZB", "CL", "GC", "6E"]
START = "2016-01-01"
END = "2026-07-01"
RAW_DIR = Path("data/raw")


def fetch_root(client: db.Historical, root: str) -> Path:
    out_path = RAW_DIR / f"{root.lower()}_ohlcv_1d.parquet"
    if out_path.exists():
        print(f"{root}: cached ({out_path})")
        return out_path

    print(f"{root}: fetching from Databento...")
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=[f"{root}.FUT"],
        stype_in="parent",
        schema="ohlcv-1d",
        start=START,
        end=END,
    )
    df = data.to_df()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"{root}: saved {len(df):,} rows -> {out_path}")
    return out_path


def main() -> None:
    client = db.Historical(os.environ["DATABENTO_API_KEY"])
    for root in ROOTS:
        fetch_root(client, root)


if __name__ == "__main__":
    main()