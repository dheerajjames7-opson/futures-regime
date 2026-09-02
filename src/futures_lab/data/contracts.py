MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}


def parse_contract(symbol: str, root: str) -> tuple[int, int]:
    suffix = symbol[len(root):]
    month_code, year_digits = suffix[0], suffix[1:]
    if month_code not in MONTH_CODES:
        raise ValueError(f"Unknown month code in {symbol!r}")
    month = MONTH_CODES[month_code]
    y = int(year_digits)
    if len(year_digits) == 1:
        year = 2020 + y if y <= 6 else 2010 + y
    else:
        year = 2000 + y
    return year, month


def sort_key(symbol: str, root: str) -> tuple[int, int]:
    return parse_contract(symbol, root)