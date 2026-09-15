# futures-regime-lab

[![CI](https://github.com/dheerajjames7-opson/futures-regime/actions/workflows/ci.yml/badge.svg)](https://github.com/dheerajjames7-opson/futures-regime/actions/workflows/ci.yml)

Regime detection and liquidity-stress research on five CME futures (ES, ZB, CL, GC, 6E)
using Databento daily data from 2016 to mid-2026. This is a research proof-of-concept:
the deliverable is the method, its validation and its reproducibility, not features.

## Status (2026-09-15)

**Done.** Databento fetch with cost preview and parquet cache; a session-aligned loader
that strips spreads, folds UTC weekend stub bars and resolves decade-ambiguous Globex
year codes; volume-crossover roll calendars with a two-session confirmation rule, tested
against the real data (ES 42, ZB 42, CL 126, GC 53, 6E 42 rolls over 10.5 years);
difference-adjusted continuous contracts with returns that are exact through rolls.
[AUDIT.md](AUDIT.md) reviews the first three days of work and records what was broken and
how it was fixed.

**Next.** Returns, realized volatility, volume and
drawdown features; a 4-state Gaussian HMM fitted on 2016–2021 and walked forward over
2022–2025 with October 2022 held out entirely; a liquidity-stress composite (Amihud,
Corwin–Schultz, volume anomaly, drawdown depth); a three-page Streamlit demo; a
methodology note with the maths.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                # unit tests; real-data checks skip without data/raw
python scripts/estimate_cost.py       # needs DATABENTO_API_KEY in .env, see data/README.md
python scripts/fetch_data.py          # ~$7.51 of credits for the full 2016-2026 pull
python scripts/build_roll_calendar.py # writes data/processed/roll_calendar_<root>.csv
python scripts/build_continuous.py    # writes data/processed/continuous_<root>.parquet
```

## Layout

```
src/futures_lab/
  config.py            universe, sample window, paths, ROLL_CONFIRM_DAYS
  data/contracts.py    outright detection; date-aware Globex symbol parsing
  data/load.py         parquet -> clean session-aligned outright frame
  data/rolls.py        daily volume leader; roll detection; calendar builder
  data/continuous.py   difference-adjusted continuous contracts; exact returns through rolls
  features/returns.py  log returns
  models/, validation/ (empty; next phase)
scripts/               estimate_cost, fetch_data, build_roll_calendar, build_continuous
notebooks/             01 data first look, 02 roll calendar validation
data/                  raw/ (git-ignored parquet), processed/ (committed roll calendars)
docs/figures/          figures written by the notebooks
tests/                 unit tests plus real-data integrity tests (skipped when data absent)
```

## The roll rule, briefly

The front contract on a session is the outright with the highest volume. A roll is
declared when a later-dated contract has led volume for two consecutive sessions; a
single-day lead is ignored and a reversion to an earlier contract never rolls. The
confirmation length is fixed in `config.py` before any modelling and is not tuned. Both
contracts trade on the roll session, so the back-adjustment gap uses two same-day closes
and no future information.

## Continuous contracts, briefly

Difference (additive) adjustment: each roll's gap, incoming close minus outgoing close on
the roll session, is added to every earlier price, so one-session changes of the adjusted
series equal the changes a constant-contract position actually realised, roll days
included. Returns are the adjusted change divided by the previous session's traded close,
which is the held contract's own return and never involves the adjusted level as a
denominator (it is a cumulative P&L, not a price). Why this beats ratio adjustment for
this project is argued in the docstring of `src/futures_lab/data/continuous.py`. The full
data caveats are in [data/README.md](data/README.md).
