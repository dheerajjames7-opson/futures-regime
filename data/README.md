# Data

Raw data is NOT committed to this repository (Databento license terms,
and reproducibility is via script, not via committed binaries).

## Rebuilding the raw data

1. Sign up at databento.com and place your key in `.env` as DATABENTO_API_KEY
2. Run `python scripts/estimate_cost.py` to preview credit usage
3. Run `python scripts/fetch_data.py`

## Contents

| File | Source | Symbology | Schema | Range |
|---|---|---|---|---|
| es_ohlcv_1d.parquet | GLBX.MDP3 | ES.FUT (parent) | ohlcv-1d | 2016 to 2026 |
| zb_ohlcv_1d.parquet | GLBX.MDP3 | ZB.FUT (parent) | ohlcv-1d | 2016 to 2026 |
| cl_ohlcv_1d.parquet | GLBX.MDP3 | CL.FUT (parent) | ohlcv-1d | 2016 to 2026 |
| gc_ohlcv_1d.parquet | GLBX.MDP3 | GC.FUT (parent) | ohlcv-1d | 2016 to 2026 |
| 6e_ohlcv_1d.parquet | GLBX.MDP3 | 6E.FUT (parent) | ohlcv-1d | 2016 to 2026 |

Individual contracts are pulled deliberately (not pre-built continuous
series) — continuous contract construction with explicit roll rules is
implemented in `src/futures_lab/data/` and documented in docs/methodology.md.

Total credit cost of a full pull: ~$X.XX (fill in your actual number).