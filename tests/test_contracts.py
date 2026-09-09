from datetime import date

import pandas as pd
import pytest

from futures_lab.data.contracts import is_outright, parse_contract

# Symbol shapes below are taken from data/raw/*.parquet, not invented.


@pytest.mark.parametrize(
    ("symbol", "root", "as_of", "expected"),
    [
        ("ESH6", "ES", date(2016, 1, 4), (2016, 3)),  # instrument 49705
        ("ESH6", "ES", date(2025, 12, 1), (2026, 3)),  # instrument 42140878, same string
        ("ESZ6", "ES", date(2016, 9, 12), (2016, 12)),
        ("ESH7", "ES", date(2016, 12, 12), (2017, 3)),
        ("ESZ9", "ES", date(2019, 12, 2), (2019, 12)),
        ("ESH0", "ES", date(2019, 12, 2), (2020, 3)),  # decade rollover
        ("CLZ5", "CL", date(2016, 1, 4), (2025, 12)),  # far-dated, one digit
        ("CLK0", "CL", date(2020, 4, 20), (2020, 5)),
        ("CLZ30", "CL", date(2021, 1, 8), (2030, 12)),  # two-digit year code
        ("CLM31", "CL", date(2026, 6, 29), (2031, 6)),
        ("GCQ1", "GC", date(2021, 7, 28), (2021, 8)),
        ("6EZ5", "6E", date(2025, 9, 1), (2025, 12)),  # numeric root
        ("ZBU6", "ZB", date(2026, 6, 30), (2026, 9)),
    ],
)
def test_parse_real_symbol_shapes(symbol, root, as_of, expected):
    assert parse_contract(symbol, root, as_of) == expected


def test_decade_boundary_orders_correctly():
    as_of = date(2019, 12, 2)
    assert parse_contract("ESZ9", "ES", as_of) < parse_contract("ESH0", "ES", as_of)


def test_year_never_precedes_observation_year():
    for digit in range(10):
        year, _ = parse_contract(f"ESH{digit}", "ES", date(2023, 6, 1))
        assert 2023 <= year <= 2032


def test_accepts_pandas_timestamp():
    ts = pd.Timestamp("2016-01-03 00:00:00+00:00")
    assert parse_contract("ESH6", "ES", ts) == (2016, 3)


@pytest.mark.parametrize(
    ("symbol", "root"),
    [
        ("ESH6-ESU6", "ES"),  # calendar spread
        ("CL:BF Q6-U6-V6", "CL"),  # butterfly
        ("CL:C1 HO-CL G6", "CL"),  # crack spread
        ("CLM6-BZM6", "CL"),  # inter-commodity
        ("UD:ZB: TL 2584931", "ZB"),  # user-defined strategy
        ("MESH6", "ES"),  # different root
        ("ESA6", "ES"),  # bad month code
        ("ESH", "ES"),  # missing year
        ("ESH123", "ES"),  # too many year digits
        ("esh6", "ES"),  # case matters on Globex
    ],
)
def test_rejects_non_outrights(symbol, root):
    assert not is_outright(symbol, root)
    with pytest.raises(ValueError):
        parse_contract(symbol, root, date(2016, 1, 4))


def test_is_outright_accepts_both_year_code_lengths():
    assert is_outright("CLZ6", "CL")
    assert is_outright("CLZ30", "CL")
    assert is_outright("6EH6", "6E")
