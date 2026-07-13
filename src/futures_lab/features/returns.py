import numpy as np
import pandas as pd


def log_returns(prices: pd.Series) -> pd.Series:
    """Compute log returns from a price series.

    Raises ValueError if prices contain non-positive values,
    which would indicate corrupted futures data.
    """
    if (prices <= 0).any():
        raise ValueError("Price series contains non-positive values")
    return np.log(prices / prices.shift(1)).dropna()