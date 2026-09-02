import pandas as pd
from futures_lab.data.contracts import sort_key

def daily_volume_leader(df: pd.DataFrame, root: str) -> pd.DataFrame:
    
    idx = df.groupby(df.index.date)["volume"].idxmax()
    leader = df.loc[idx, ["symbol", "close", "volume"]].copy()
    leader.index = pd.to_datetime(leader.index.date)
    return leader

def detect_rolls(leader: pd.DataFrame, root: str, confirm_days: int = 2) -> pd.DataFrame:
    
    rolls = []
    current = leader["symbol"].iloc[0]
    streak_symbol, streak = None, 0

    for date, sym in leader["symbol"].items():
        if sym == current:
            streak_symbol, streak = None, 0
            continue
        if sort_key(sym, root) <= sort_key(current, root):
            continue  # backward reversion: noise
        if sym == streak_symbol:
            streak += 1
        else:
            streak_symbol, streak = sym, 1
        if streak >= confirm_days:
            rolls.append({"roll_date": date, "from_symbol": current, "to_symbol": sym})
            current = sym
            streak_symbol, streak = None, 0

    return pd.DataFrame(rolls)