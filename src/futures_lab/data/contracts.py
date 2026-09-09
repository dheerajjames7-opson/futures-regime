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
relative to the date on which the symbol was observed: the contract is the earliest
one with that year digit that had not yet stopped trading on the observation date.

The expiry test needs product knowledge. ES, ZB, GC and 6E stop trading inside the
contract month, so the end of that month is a safe bound. CL stops trading three
business days before the 25th calendar day of the month *before* the contract month
(CME rule 200.01), and CME lists CL ten years out, so the June 2029 contract is
relisted as ``CLM9`` within weeks of the June 2019 contract expiring. The sample
contains exactly this: instrument 323547 (``CLM9``) prints on 2019-06-20 and again in
2025-26, and both are June 2029.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
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

# Roots whose last trading day is in the month before the contract month.
PRIOR_MONTH_EXPIRY: frozenset[str] = frozenset({"CL"})


@cache
def outright_pattern(root: str) -> re.Pattern[str]:
    """Compiled regex matching an outright on ``root``: root, month code, 1-2 year digits."""
    return re.compile(re.escape(root) + r"([FGHJKMNQUVXZ])(\d{1,2})")


def is_outright(symbol: str, root: str) -> bool:
    """Return True if ``symbol`` is a single-contract future on ``root``.

    >>> is_outright("ESH6", "ES"), is_outright("ESH6-ESM6", "ES"), is_outright("MESH6", "ES")
    (True, False, False)
    """
    return outright_pattern(root).fullmatch(symbol) is not None


def last_trade_bound(root: str, year: int, month: int) -> date:
    """Latest date on which contract ``(year, month)`` of ``root`` can still trade.

    CL: three business days before the 25th of the prior month, weekends only (holidays
    ignored). Ignoring holidays can only make this bound later than the true last trade
    date, so a live contract is never mistaken for an expired one. Everything else: the
    last calendar day of the contract month.

    >>> last_trade_bound("CL", 2020, 5)  # CLK0 actually expired 2020-04-21
    datetime.date(2020, 4, 21)
    >>> last_trade_bound("ES", 2016, 3)
    datetime.date(2016, 3, 31)
    """
    if root in PRIOR_MONTH_EXPIRY:
        y, m = (year, month - 1) if month > 1 else (year - 1, 12)
        d = date(y, m, 25)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        remaining = 3
        while remaining:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                remaining -= 1
        return d
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_contract(symbol: str, root: str, as_of: date) -> tuple[int, int]:
    """Return ``(year, month)`` for an outright ``symbol`` observed on ``as_of``.

    A one-digit year code resolves to the earliest year with that final digit, in the
    decade of ``as_of`` or the next, whose contract had not stopped trading by ``as_of``
    (see ``last_trade_bound``). Two-digit codes resolve as ``2000 + yy``. ``as_of`` may be
    a ``datetime.date`` or anything with ``year``, ``month`` and ``day`` attributes, such
    as ``pandas.Timestamp``.

    Raises ``ValueError`` for anything that is not an outright on ``root``.

    >>> parse_contract("ESH6", "ES", date(2016, 1, 4))
    (2016, 3)
    >>> parse_contract("ESH6", "ES", date(2025, 12, 1))
    (2026, 3)
    >>> parse_contract("CLM9", "CL", date(2019, 6, 20))  # June 2019 expired 2019-05-21
    (2029, 6)
    >>> parse_contract("CLZ30", "CL", date(2021, 1, 8))
    (2030, 12)
    """
    match = outright_pattern(root).fullmatch(symbol)
    if match is None:
        raise ValueError(f"{symbol!r} is not an outright {root} future")
    month = MONTH_CODES[match.group(1)]
    code = match.group(2)
    if len(code) == 2:
        return 2000 + int(code), month
    observed = date(as_of.year, as_of.month, as_of.day)
    year = observed.year - observed.year % 10 + int(code)
    if last_trade_bound(root, year, month) < observed:
        year += 10
    return year, month
