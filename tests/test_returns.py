import numpy as np
import pandas as pd
import pytest

from futures_lab.features.returns import log_returns


def test_log_returns_basic():
    prices = pd.Series([100.0, 105.0, 102.0])
    result = log_returns(prices)
    assert len(result) == 2
    assert np.isclose(result.iloc[0], np.log(105 / 100))


def test_log_returns_rejects_negative_prices():
    prices = pd.Series([100.0, -5.0, 102.0])
    with pytest.raises(ValueError):
        log_returns(prices)