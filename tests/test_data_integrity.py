"""Checks against the real Databento cache. Skipped when data/raw is absent (CI).

Expected roll counts come from contract-month arithmetic over 2016-01 to 2026-06
(10.5 years): quarterly roots 4/yr, GC actives (G, J, M, Q, Z) 5/yr, CL 12/yr,
with a 10% tolerance for the sample edges.
"""

import pandas as pd
import pytest

from futures_lab.config import ROLL_CONFIRM_DAYS, ROOTS, raw_path
from futures_lab.data.contracts import parse_contract
from futures_lab.data.load import load_outrights
from futures_lab.data.rolls import daily_volume_leader, detect_rolls

pytestmark = pytest.mark.skipif(
    not all(raw_path(r).exists() for r in ROOTS),
    reason="raw Databento parquet not present (git-ignored); run scripts/fetch_data.py",
)

EXPECTED_ROLLS = {
    "ES": (38, 46),
    "ZB": (38, 46),
    "6E": (38, 46),
    "GC": (47, 58),
    "CL": (113, 139),
}


@pytest.fixture(scope="module", params=ROOTS)
def root(request):
    return request.param


@pytest.fixture(scope="module")
def bars(root):
    return load_outrights(root)


@pytest.fixture(scope="module")
def leader(bars):
    return daily_volume_leader(bars)


@pytest.fixture(scope="module")
def rolls(leader, root):
    return detect_rolls(leader, root, confirm_days=ROLL_CONFIRM_DAYS)


def test_no_weekend_sessions(bars):
    assert not bars.index.dayofweek.isin([5, 6]).any()


def test_sessions_per_year_plausible(leader):
    counts = leader.groupby(leader.index.year).size()
    full_years = counts.loc[2017:2025]
    assert full_years.between(240, 265).all(), full_years.to_dict()


def test_one_row_per_instrument_session(bars):
    assert not bars.reset_index().duplicated(["instrument_id", "session"]).any()


def test_roll_count_plausible(rolls, root):
    lo, hi = EXPECTED_ROLLS[root]
    assert lo <= len(rolls) <= hi, f"{root}: {len(rolls)} rolls"


def test_rolls_strictly_forward_in_time_and_contract(rolls, root):
    assert rolls["roll_date"].is_monotonic_increasing
    assert rolls["roll_date"].is_unique
    pairs = zip(rolls["to_symbol"], rolls["roll_date"], strict=True)
    keys = [parse_contract(s, root, d) for s, d in pairs]
    assert all(a < b for a, b in zip(keys, keys[1:], strict=False))


def test_roll_lag_equals_confirmation_rule(rolls, leader):
    pos = pd.Series(range(len(leader)), index=leader.index)
    lag = pos.loc[rolls["roll_date"]].to_numpy() - pos.loc[rolls["crossover_date"]].to_numpy()
    assert (lag == ROLL_CONFIRM_DAYS - 1).all()


def test_cl_front_never_prints_negative(leader, root):
    if root != "CL":
        pytest.skip("CL only")
    assert leader["close"].min() > 0
    # CLK0 settled at -37.63 on 2020-04-20; the volume leader had already moved to CLM0.
    assert leader.loc["2020-04-20", "symbol"] == "CLM0"
