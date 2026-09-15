"""Project-wide constants: instrument universe, sample window, data locations."""

from __future__ import annotations

import os
from pathlib import Path

# Resolved from this file so scripts work from any working directory (editable install).
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

ROOTS: tuple[str, ...] = ("ES", "ZB", "CL", "GC", "6E")
DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1d"
START = "2016-01-01"
END = "2026-07-01"

# Consecutive sessions a later contract must lead volume before we roll. Fixed here,
# before any modelling, and never tuned on the October 2022 holdout.
ROLL_CONFIRM_DAYS = 2


def raw_path(root: str, raw_dir: Path | None = None) -> Path:
    """Parquet cache location for one root, e.g. ``data/raw/es_ohlcv_1d.parquet``."""
    return (raw_dir or RAW_DIR) / f"{root.lower()}_ohlcv_1d.parquet"


def roll_calendar_path(root: str, processed_dir: Path | None = None) -> Path:
    """Roll calendar CSV for one root, e.g. ``data/processed/roll_calendar_es.csv``."""
    return (processed_dir or PROCESSED_DIR) / f"roll_calendar_{root.lower()}.csv"


def continuous_path(root: str, processed_dir: Path | None = None) -> Path:
    """Continuous-contract parquet for one root, e.g. ``data/processed/continuous_es.parquet``."""
    return (processed_dir or PROCESSED_DIR) / f"continuous_{root.lower()}.parquet"


def databento_api_key() -> str:
    """Read ``DATABENTO_API_KEY`` from ``<repo>/.env`` or the environment."""
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY is not set. Put it in <repo>/.env or the environment; "
            "see data/README.md."
        )
    return key
