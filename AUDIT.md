# Audit of Days 1–3 (repo state at commit `ad630aa`)

Audit date: 2026-09-09. Scope: every tracked file plus the five parquet files in
`data/raw/` (present locally, git-ignored). All numbers below were measured on those
files; nothing is estimated.

## Verdict in one paragraph

The skeleton and the fetch pipeline are sound, but nothing downstream of the fetch
currently works: the project file is invalid TOML, so `pip install`, `pytest` and `ruff`
all abort before running, and CI has been red since 2026-08-03. The roll pipeline has
three independent bugs (duplicate-index selection, spread symbols, decade-ambiguous year
codes), any one of which alone would make the roll calendar wrong. Existing tests pass
only symbol shapes that never appear in the data. None of this is hard to fix, and the
fixes below are small, but a reviewer who runs `pytest` first would stop reading.

## Findings, by severity

| # | Severity | Area | Finding | Status |
|---|----------|------|---------|--------|
| 1 | Blocker | Build/CI | `pyproject.toml` lines 36–38 are three bare strings outside any table. `tomllib`, pip, pytest and ruff all fail to parse it. Introduced in `f60cb7f` (2026-08-03); CI red since. | Fixed |
| 2 | Blocker | Roll detection | `daily_volume_leader` returns every row, not one per day. `idxmax()` returns the timestamp label; the index is not unique (all contracts share a day's `ts_event`), so `df.loc[idx]` selects all rows for those days. ES: 20,206 rows returned for 3,266 days. | Fixed |
| 3 | Blocker | Roll detection | Spreads and user-defined strategies are not filtered. `parse_contract("ESH6-ESU6")` raises `ValueError` on `int("6-ESU6")`; `detect_rolls` crashes on the fourth row of ES. Spreads are also the day's top-volume instrument on 102 ZB days and 68 6E days, so filtering is required, not cosmetic. | Fixed |
| 4 | Blocker | Contract parsing | Year codes are single-digit in the data (`ESH6`, not `ESH26`). `parse_contract` maps digit ≤6 to 202x and >6 to 201x with no date context, so `ESZ6` (Dec 2016) parses as 2026 and every 2017–2025 contract sorts "backward". With spreads pre-filtered, the existing detector finds 3 rolls for ES, 3 ZB, 10 CL, 4 GC, 3 6E, all frozen by Oct 2016. The same string maps to two instruments: `ESH6` is instrument 49705 (Jan–Mar 2016) and 42140878 (Jan 2025–Mar 2026). | Fixed |
| 5 | Major | Contract parsing | CL carries two-digit year codes for far-dated contracts (`CLZ30`…`CLZ36`, `CLM31`; 16 symbols). The parser must accept both forms. Current code happens to handle two digits; the fix must keep that. | Fixed |
| 6 | Major | Data hygiene | Databento `ohlcv-1d` bars are UTC-day aligned, not CME-session aligned. Each root has 540 Sunday bars (the 17:00–18:00 CT Globex open), giving ~311 "days" per year instead of ~252. Sunday bars hold 0.3–0.7% of volume. Left in, they inflate realized-vol day counts and produce a spike in Amihud (abs return over volume) every week. | Fixed |
| 7 | Major | Tests | `test_contracts.py` and `test_rolls.py` use `ESH26`, `6EZ25`, `ESM26`, forms absent from the data. No test covers single-digit years, decade rollover (`ESZ9` to `ESH0`), spreads, `daily_volume_leader`, duplicate indices, or empty results. Coverage was green on a broken module. | Fixed |
| 8 | Major | Notebooks | Notebook 02's stored outputs are an `ImportError` and a `NameError` (run before `detect_rolls` existed). Notebook 01 cell 2 has five bare expressions of which only the last displays. Notebook 02 writes to `docs/figures/`, which does not exist. | Fixed |
| 9 | Major | Docs | `README.md` is a CI badge and nothing else. `data/README.md` says "~$X.XX (fill in your actual number)" and links to a `docs/methodology.md` that does not exist. | Partly fixed (see plan) |
| 10 | Minor | Build | `arch` (GARCH) is a dependency; GARCH is explicitly out of scope. `statsmodels` is unused. `python-dotenv` and `pyarrow` are used but sat in the broken lines, so `pip install -e .` would not install them. CI commit says "ruff and pytest" but the workflow only runs pytest. | Fixed |
| 11 | Minor | Roll detection | `detect_rolls` on an empty leader raises `IndexError` at `iloc[0]`; with no rolls it returns a frame with no columns, so `rolls["roll_date"]` fails downstream. `root` parameter of `daily_volume_leader` is unused. `roll_date` is the confirmation day, not the first crossover day, which is a valid choice but undocumented. | Fixed |
| 12 | Minor | Scripts | `RAW_DIR = Path("data/raw")` is CWD-relative; `os.environ["DATABENTO_API_KEY"]` gives a bare `KeyError`; `ROOTS`, `START`, `END` duplicated across two scripts. | Fixed |
| 13 | Minor | Style | `rolls.py` has whitespace-only lines, one blank line between top-level defs, unsorted import groups, no docstrings. Would fail `ruff` once ruff can run. | Fixed |
| 14 | Cosmetic | Git | Commit `ad630aa` is titled "Contracts and rollbacks" (it adds roll detection, not rollbacks). `f60cb7f` and `851e67a` are the same change committed twice around a merge. History is pushed, so left alone. | Not fixed (intentional) |

## What exists versus the intended scope

| Scope item | State | Notes |
|---|---|---|
| 1 Data layer | Fetch done, loader missing | `scripts/fetch_data.py` pulls `ROOT.FUT` parent symbology for 2016-01-01 to 2026-07-01 and caches parquet. Correct choice; parent symbology necessarily includes spreads, so filtering belongs in a loader, which did not exist. |
| 2 Roll detection | Written, non-functional | See findings 2–4. |
| 3 Continuous contracts | Not started | |
| 4 Features | `log_returns` only | Correct but trivial. Rejects non-positive prices, which matters for CL (see design notes). |
| 5–8 HMM, validation, liquidity, app | Not started | Empty `models/` and `validation/` packages. |
| 9 Docs | Not started | |
| 10 Tests, CI, repro | Tests exist but weak; CI red; no repro script | |

## Data-dependent checks (measured)

All five files share: index `ts_event` (UTC, non-unique), columns `rtype, publisher_id,
instrument_id, open, high, low, close, volume, symbol`, no nulls, range 2016-01-03 to
2026-06-30.

| Root | Rows | Distinct symbols | Outright symbols | Outright instrument_ids | Symbols with >1 instrument_id | Non-outright kinds present |
|---|---|---|---|---|---|---|
| ES | 20,206 | 187 | 40 | 45 | 5 | calendar spreads |
| ZB | 10,350 | 343 | 40 | 44 | 4 | calendar spreads, `UD:ZB: TL …` user-defined |
| CL | 593,497 | 3,499 | 136 (120 one-digit + 16 two-digit year) | 179 | 43 | calendar spreads, `CL:BF` butterflies, `CL:C1` cracks, CL–BZ and CL–MCL inter-commodity |
| GC | 95,181 | 1,219 | 120 | 153 | 33 | calendar spreads |
| 6E | 38,091 | 600 | 118 | 126 | 8 | calendar spreads |

Symbols with more than one `instrument_id` are the decade collisions from finding 4. The
gap between outright symbols and outright instrument_ids is exactly the number of
contracts whose year code repeated inside the 2016–2026 window.

Days on which a non-outright had the highest volume: ES 16, ZB 102, CL 10, GC 6, 6E 68.
These cluster at roll time (for example `ZBM6-ZBU6` on 2016-05-25, 26 and 27), which is
precisely when the leader logic must be right.

Roll counts from the existing code with spreads pre-filtered so it does not crash:
ES 3, ZB 3, CL 10, GC 4, 6E 3. Expected over 2016-01 to 2026-06: ES, ZB and 6E about 42
(quarterly), GC about 52 (G, J, M, Q, Z actives), CL about 126 (monthly). Post-fix counts
are in the verification section at the end of this file.

CL April 2020: `CLK0` closed at −2.67 in the 2020-04-20 UTC bar (the −37.63 settlement
occurred inside that bar; the UTC close is the last trade before 19:00 CDT). `CLM0` had
already been the volume leader since 2020-04-16, so a volume-crossover calendar with a
two-day confirmation rolls on 2020-04-17 and the continuous series never touches the
negative print. This needs a test and a sentence in the methodology.

`.env` is git-ignored and does not appear anywhere in history. The Databento key is not
leaked.

## Test-coverage gaps in existing modules

- `contracts.py`: no test with a one-digit year; no decade rollover; no spread or
  user-defined symbol rejection; no `sort_key` test; no two-digit CL test with an
  observation date.
- `rolls.py`: `daily_volume_leader` has no test at all. `detect_rolls` has no test with a
  duplicate-timestamp input, a decade boundary, `confirm_days=1`, an empty input, a
  zero-roll output schema, or a multi-contract day where a spread out-volumes the front.
- `returns.py`: no test for index alignment or interior NaN.
- Scripts: untested by design (network). Fine.

## Things that would embarrass the author in front of a quant reviewer

1. `pytest` does not run. It is the first thing a reviewer tries.
2. A roll calendar with 3 rolls in ten years, produced silently once the crash is patched.
3. Tests written against `ESH26`-style symbols while the data says `ESH6`. Signals the
   tests were not written against the data.
4. Sunday bars treated as trading days. Signals unfamiliarity with how Databento daily
   bars are cut.
5. A README with only a badge, and a data README with a "$X.XX" placeholder.
6. Notebook outputs that are tracebacks.
7. A GARCH library in the dependencies of a project whose brief says no GARCH.

## Fix plan (each a separate commit, in this order)

1. `build`: repair `pyproject.toml`; move `databento`, `python-dotenv`, `pyarrow` into
   dependencies; drop `arch` and `statsmodels`; add `ruff check` to CI; test on 3.11 and
   3.12.
2. `fix(contracts)`: date-aware `parse_contract(symbol, root, as_of)` resolving one-digit
   years into the window `[as_of.year, as_of.year + 9]`; accept two-digit years; an
   `is_outright()` filter; tests against the real symbol shapes.
3. `fix(data)`: new `load.py` (read parquet, keep outrights, fold Sunday UTC stub bars
   into the following session, tidy columns); `daily_volume_leader` selecting one row per
   session by position; `detect_rolls` comparing stored `(year, month)` keys, handling
   empty input and returning a fixed schema; docstrings; tests including duplicate index,
   spread-out-volumes-front, decade boundary, and the CL April 2020 case.
4. `fix(scripts)`: repo-root-relative paths, shared config module, clear error on a
   missing key.
5. `docs`: honest `data/README.md` with the measured cost; re-executed notebooks;
   `docs/figures/` created.

The research-note README and `docs/methodology.md` (scope item 9) are deferred to the docs
phase because they describe modules that do not exist yet. The placeholder text is removed
now.

## Design notes for the modules not yet built (surfaced by this audit)

- **Back-adjustment and CL.** Additive back-adjustment over about 126 CL rolls accumulates
  the roll gaps; in extended backwardation the shifted history can approach or cross zero,
  which breaks `log_returns`. Compute returns by splicing per-contract log returns at the
  roll date (equivalent to ratio adjustment) and keep the additive back-adjusted level only
  for plotting. Test that the CL return series has no NaN or inf in April 2020.
- **UTC bar alignment.** Even after folding Sundays, each weekday bar closes at 00:00 UTC
  (18:00 or 19:00 CT), one to two hours after the next Globex session opens, so `close` is
  not the CME settlement. Acceptable for daily regime work; state it in the methodology.
- **Roll date semantics.** `roll_date` is the day on which the new contract has led volume
  for `confirm_days` consecutive sessions. The continuous series should switch to the new
  contract from `roll_date` onward and take the adjustment from both contracts' closes on
  that day. Both contracts trade that day, so there is no look-ahead.
- **October 2022 holdout.** Roll dates in October 2022 must come from the same rule with
  no parameter tuned on that month. The rule has one parameter (`confirm_days=2`), fixed
  before any modelling; record that in the methodology.

## Post-fix verification

Filled in after the fix commits (see bottom of file).
