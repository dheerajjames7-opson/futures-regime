"""Checks against the real Databento cache. Skipped when data/raw is absent (CI).

Expected roll counts come from contract-month arithmetic over 2016-01 to 2026-06
(10.5 years): quarterly roots 4/yr, GC actives (G, J, M, Q, Z) 5/yr, CL 12/yr,
with a 10% tolerance for the sample edges.
"""

import numpy as np
import pandas as pd
import pytest

from futures_lab.config import ROLL_CONFIRM_DAYS, ROOTS, raw_path, roll_calendar_path
from futures_lab.data.continuous import build_continuous, load_roll_calendar, roll_gaps
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


# --- continuous contracts -----------------------------------------------------------------


@pytest.fixture(scope="module")
def committed_calendar(root):
    if not roll_calendar_path(root).exists():
        pytest.skip("roll calendar not built; run scripts/build_roll_calendar.py")
    return load_roll_calendar(root)


@pytest.fixture(scope="module")
def cont(bars, committed_calendar):
    return build_continuous(bars, committed_calendar)


def test_committed_calendar_matches_the_detector(rolls, committed_calendar):
    fresh = rolls.reset_index(drop=True)
    pd.testing.assert_frame_equal(
        fresh.astype({"from_instrument_id": "int64", "to_instrument_id": "int64"}),
        committed_calendar[fresh.columns],
        check_dtype=False,
    )


def test_continuous_covers_every_session_without_gaps(cont, leader):
    assert len(cont) == len(leader)
    assert cont.index.is_unique and cont.index.is_monotonic_increasing
    assert not cont[["open", "high", "low", "close", "volume", "adj_close"]].isna().any().any()
    assert np.isfinite(cont["ret"].to_numpy()[1:]).all()
    assert np.isfinite(cont["log_ret"].to_numpy()[1:]).all()


def test_last_segment_is_at_traded_prices(cont, committed_calendar):
    tail = cont.loc[committed_calendar["roll_date"].max() :]
    assert (tail["adjustment"] == 0).all()
    assert (tail["adj_close"] == tail["close"]).all()


def test_adjustment_is_the_suffix_sum_of_roll_gaps(cont, bars, committed_calendar):
    gaps = roll_gaps(bars, committed_calendar)
    assert cont["adjustment"].iloc[0] == pytest.approx(gaps.sum())
    step = cont["adjustment"].diff().loc[committed_calendar["roll_date"]].to_numpy()
    np.testing.assert_allclose(step, -gaps.to_numpy())


def test_every_return_is_a_single_contracts_own_return(cont, bars):
    # Held contract on session t: the shown instrument, except on roll days where it is
    # the outgoing one. Its return is close(t)/close(t-1) - 1 within that same contract.
    close = bars.reset_index().pivot(index="session", columns="instrument_id", values="close")
    own = close / close.shift(1) - 1
    held = cont["instrument_id"].shift(1).bfill().astype("int64")  # previous row's holder
    expected = own.to_numpy()[np.arange(len(cont)), close.columns.get_indexer(held)]
    got = cont["ret"].to_numpy()
    np.testing.assert_allclose(got[1:], expected[1:], rtol=1e-12, atol=1e-15)


def test_no_phantom_jump_on_roll_days(cont):
    # Roll-day returns are ordinary returns; a mis-applied gap shows up as a fat tail here.
    roll_abs = cont.loc[cont["is_roll"], "ret"].abs()
    all_abs = cont["ret"].abs().dropna()
    assert roll_abs.median() < 3 * all_abs.median()
    assert roll_abs.max() <= all_abs.quantile(0.999)
