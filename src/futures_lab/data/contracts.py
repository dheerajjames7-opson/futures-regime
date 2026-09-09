"""CME Globex contract symbols: outright detection and date-aware parsing.

Databento's GLBX.MDP3 parent symbology (``ES.FUT``) returns raw Globex symbols for
every instrument under the root: outrights such as ``ESH6``, calendar spreads such as
``ESH6-ESM6``, butterflies (``CL:BF Q6-U6-V6``), crack and inter-commodity spreads
(``CL:C1 HO-CL G6``, ``CLM6-BZM6``) and user-defined strategies (``UD:ZB: TL 2584931``).
Only outrights matter for a continuous contract, so everything else is rejected here.

Globex year codes are one digit for most contracts and two digits for far-dated ones
(``CLZ30``). A one-digit code is ambiguous across decades: in the 2016-2026 sample
``ESH6`` names the March 2016 contract in early 2016 and the March 2026 contract in
2025-26, under different ``instrument_id`` values. The year is therefore resolved
relative to the date on which the symbol was observed. Because every product handled
here stops trading inside its contract month, a live contract can never carry a year
earlier than the observation year, so the one-digit code maps into the window
``[as_of.year, as_of.year + 9]``.
"""

from __future__ import annotations

import re
from datetime import date
from functools import cache

MONTH_CODES: dict[str, int] = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}


@cache
def _outright_pattern(root: str) -> re.Pattern[str]:
    return re.compile(re.escape(root) + r"([FGHJKMNQUVXZ])(\d{1,2})")


def is_outright(symbol: str, root: str) -> bool:
    """Return True if ``symbol`` is a single-contract future on ``root``.

    >>> is_outright("ESH6", "ES"), is_outright("ESH6-ESM6", "ES"), is_outright("MESH6", "ES")
    (True, False, False)
    """
    return _outright_pattern(root).fullmatch(symbol) is not None


def parse_contract(symbol: str, root: str, as_of: date) -> tuple[int, int]:
    """Return ``(year, month)`` for an outright ``symbol`` observed on ``as_of``.

    One-digit year codes resolve to the unique year in ``[as_of.year, as_of.year + 9]``
    with that final digit. Two-digit codes resolve as ``2000 + yy``. ``as_of`` may be any
    object with a ``.year`` attribute (``datetime.date``, ``pandas.Timestamp``).

    Raises ``ValueError`` for anything that is not an outright on ``root``.

    >>> parse_contract("ESH6", "ES", date(2016, 1, 4))
    (2016, 3)
    >>> parse_contract("ESH6", "ES", date(2025, 12, 1))
    (2026, 3)
    >>> parse_contract("CLZ30", "CL", date(2021, 1, 8))
    (2030, 12)
    """
    match = _outright_pattern(root).fullmatch(symbol)
    if match is None:
        raise ValueError(f"{symbol!r} is not an outright {root} future")
    month = MONTH_CODES[match.group(1)]
    code = match.group(2)
    if len(code) == 2:
        return 2000 + int(code), month
    year = as_of.year - as_of.year % 10 + int(code)
    if year < as_of.year:
        year += 10
    return year, month
