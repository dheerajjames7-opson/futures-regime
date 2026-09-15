# Data

Raw Databento files are **not committed** (licence terms; reproducibility is via
script). The processed roll calendars **are committed**: they are small, derived, and let
a reviewer without a Databento key see exactly what the roll rule produced.

## Rebuilding

1. Create a Databento account and put the key in `.env` at the repo root as
   `DATABENTO_API_KEY=...` (the file is git-ignored).
2. `python scripts/estimate_cost.py` previews credit usage without downloading.
3. `python scripts/fetch_data.py` downloads and caches; files already present are skipped.
4. `python scripts/build_roll_calendar.py` writes `data/processed/roll_calendar_<root>.csv`.

Measured cost of the full pull on 2026-09-09: **$7.51** (ES 0.20, ZB 0.10, CL 5.88,
GC 0.94, 6E 0.38). CL dominates because parent symbology returns every calendar spread,
butterfly and crack spread under the root; 3,363 of CL's 3,499 symbols are not outrights.

## Raw files (`data/raw/`, git-ignored)

| File | Dataset | Symbology | Schema | Range | Rows |
|---|---|---|---|---|---|
| es_ohlcv_1d.parquet | GLBX.MDP3 | ES.FUT (parent) | ohlcv-1d | 2016-01-03 to 2026-06-30 | 20,206 |
| zb_ohlcv_1d.parquet | GLBX.MDP3 | ZB.FUT (parent) | ohlcv-1d | same | 10,350 |
| cl_ohlcv_1d.parquet | GLBX.MDP3 | CL.FUT (parent) | ohlcv-1d | same | 593,497 |
| gc_ohlcv_1d.parquet | GLBX.MDP3 | GC.FUT (parent) | ohlcv-1d | same | 95,181 |
| 6e_ohlcv_1d.parquet | GLBX.MDP3 | 6E.FUT (parent) | ohlcv-1d | same | 38,091 |

Individual contracts are pulled deliberately rather than a vendor continuous series, so
that the roll rule and the back-adjustment are explicit, testable code.

Four properties of the raw files matter and are handled in `futures_lab.data.load`:

- **The index is not unique.** `ts_event` is shared by every instrument trading that day.
- **Spreads and strategies are included** (`ESH6-ESM6`, `CL:BF Q6-U6-V6`,
  `UD:ZB: TL 2584931`). Only outrights are kept.
- **Bars are UTC days, not CME sessions.** The Sunday 17:00 CT Globex open creates a
  one-hour Sunday bar every week (540 per root). They are folded into Monday's session.
  Weekday bars still close at 00:00 UTC, one to two hours after the next session opens,
  so `close` is the last trade before 18:00/19:00 CT, not the CME settlement. After
  folding there are about 260 sessions a year, not 252, because Globex runs abbreviated
  sessions on most US holidays; those are real, low-volume sessions and are kept.
- **Year codes are one digit and repeat across decades.** `ESH6` is March 2016 in early
  2016 and March 2026 in 2025-26. Each row's contract is resolved from its session date
  against the product's last-trading-day rule (CL stops trading in the month *before* the
  contract month and is listed ten years out, so `CLM9` printing on 2019-06-20 is June
  2029). The loader raises if instruments and contracts do not map one-to-one.

`futures_lab.data.load.load_outrights(root)` returns one row per (instrument, session)
with columns `instrument_id, symbol, contract_year, contract_month, open, high, low,
close, volume`, indexed by tz-naive session date.

## Processed files (`data/processed/`, committed)

`roll_calendar_<root>.csv`, one row per confirmed roll:

| Column | Meaning |
|---|---|
| `crossover_date` | first session on which the new contract out-traded the incumbent |
| `roll_date` | session on which the lead had lasted `ROLL_CONFIRM_DAYS` (= 2) sessions; the continuous series switches here |
| `from_symbol`, `to_symbol` | Globex symbols |
| `from_instrument_id`, `to_instrument_id` | Databento instrument ids, unambiguous across decades |

Counts over 2016-01 to 2026-06: ES 42, ZB 42, CL 126, GC 53, 6E 42. Contract-month
arithmetic over 10.5 years predicts 42 / 42 / 126 / 52 / 42.

## Continuous contracts (`data/processed/continuous_<root>.parquet`, git-ignored)

Built by `python scripts/build_continuous.py` from the raw cache and the committed roll
calendars. Not committed because the series is a rearrangement of licensed Databento
prices. One row per session:

| Column | Meaning |
|---|---|
| `instrument_id`, `symbol` | contract held at the close (incoming contract from `roll_date` on) |
| `open`, `high`, `low`, `close`, `volume` | that contract at traded prices |
| `volume_all` | summed volume of every outright that session |
| `adjustment` | additive shift: sum of the gaps of all later rolls; zero from the last roll on |
| `adj_open` .. `adj_close` | traded prices plus `adjustment` (difference-adjusted series) |
| `is_roll` | True on `roll_date` sessions |
| `ret`, `log_ret` | `adj_close.diff() / close.shift(1)` and `log1p` of it: the return of the contract actually held, exact through rolls |

The gap of a roll is the incoming close minus the outgoing close on `roll_date`. The
position holds the outgoing contract through that session and rolls at its close, so the
`roll_date` row's return is the outgoing contract's. The adjusted level is a cumulative
P&L, not a price: never divide by it or take its log (for CL it drifts far from the
traded level). The reasons for difference rather than ratio adjustment are in the module
docstring of `futures_lab.data.continuous`.
