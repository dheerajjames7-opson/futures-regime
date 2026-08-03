import os

import databento as db
from dotenv import load_dotenv

load_dotenv()

ROOTS = ["ES", "ZB", "CL", "GC", "6E"]
START = "2016-01-01"
END = "2026-07-01"

client = db.Historical(os.environ["DATABENTO_API_KEY"])

total = 0.0
for root in ROOTS:
    cost = client.metadata.get_cost(
        dataset="GLBX.MDP3",
        symbols=[f"{root}.FUT"],
        stype_in="parent",
        schema="ohlcv-1d",
        start=START,
        end=END,
    )
    print(f"{root}: ${cost:.4f}")
    total += cost

print(f"\nTotal estimated cost: ${total:.4f}")