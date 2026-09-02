import pytest

from futures_lab.data.contracts import parse_contract

def test_parse_standard_contract():
    assert parse_contract("ESH26", "ES") == (2026, 3)

def test_parse_numeric_root():
    assert parse_contract("6EZ25", "6E") == (2025, 12)

def test_reject_bad_month_code():
    with pytest.raises(ValueError):
        parse_contract("ESA26", "ES")