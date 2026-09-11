"""Shared helpers for Kincade Multisystem Resilience analysis modules.

Provides project paths, logging, a Google Earth Engine initializer (reusing the
download-layer helpers), and an idempotent appender for the cross-module
result registry (outputs/result_registry.csv).

Analysis CRS: EPSG:26910 (UTM zone 10N, NAD83).
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
TABLES = OUT / "tables"
FIGDATA = OUT / "figures" / "data"
QA = OUT / "qa"
LOGDIR = OUT / "logs"
DOCS = ROOT / "docs"
REGISTRY = OUT / "result_registry.csv"

CRS = "EPSG:26910"
WGS84 = "EPSG:4326"

# Fire event windows (mirrors src/download/common.py)
PREFIRE = ("2019-09-01", "2019-10-22")
POSTFIRE = ("2019-11-10", "2019-12-15")
EVENT_WINDOW = ("2019-10-23", "2019-11-06")

REGISTRY_FIELDS = [
    "result_id",
    "manuscript_section",
    "metric",
    "value",
    "unit",
    "uncertainty",
    "dataset",
    "analysis_script",
    "model",
    "source_output",
    "timestamp",
]

for _p in (PROC, TABLES, FIGDATA, QA, LOGDIR):
    _p.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(LOGDIR / f"{name}.log", mode="w", encoding="utf-8")
    ch = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_ee():
    """Initialize Earth Engine, reusing the download-layer helper."""
    sys.path.insert(0, str(ROOT / "src" / "download"))
    from gee_utils import init_ee as _init  # noqa: E402

    return _init()


def append_registry(rows: list[dict]) -> Path:
    """Append rows to outputs/result_registry.csv (create if missing).

    Rows are keyed by result_id: an incoming row replaces any existing row with
    the same result_id (keep-last), so re-running a module updates rather than
    duplicates its results. Other modules' rows are preserved.
    """
    for r in rows:
        r.setdefault("timestamp", utcnow())
        for k in REGISTRY_FIELDS:
            r.setdefault(k, "")
    new = pd.DataFrame(rows)[REGISTRY_FIELDS]
    if REGISTRY.exists():
        old = pd.read_csv(REGISTRY)
        for k in REGISTRY_FIELDS:
            if k not in old.columns:
                old[k] = ""
        old = old[REGISTRY_FIELDS]
        combined = pd.concat([old, new], ignore_index=True)
        combined = combined.drop_duplicates(subset="result_id", keep="last")
    else:
        combined = new
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(REGISTRY, index=False)
    return REGISTRY
