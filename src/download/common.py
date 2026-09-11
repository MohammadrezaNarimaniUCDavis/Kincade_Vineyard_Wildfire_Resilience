"""Shared helpers for Phase 8 data acquisition (Kincade Multisystem Resilience).

All downloads write into PROJECT_ROOT/data/raw/... and log to outputs/logs/.
Analysis CRS: EPSG:26910 (UTM zone 10N, NAD83).
Study point (Geyserville): lon -122.78, lat 38.79.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
LOG_DIR = PROJECT_ROOT / "outputs" / "logs"
MANIFEST_PATH = PROJECT_ROOT / "data" / "data_manifest.csv"

ANALYSIS_CRS = "EPSG:26910"
WGS84 = "EPSG:4326"

STUDY_POINT = (-122.78, 38.79)  # lon, lat  (Geyserville)

# Fire event windows
PREFIRE = ("2019-09-01", "2019-10-22")
POSTFIRE = ("2019-11-10", "2019-12-15")
EVENT_WINDOW = ("2019-10-23", "2019-11-06")

for d in (DATA_RAW, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(LOG_DIR / f"{name}.log", mode="w", encoding="utf-8")
    ch = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def append_manifest(rows: list[dict]) -> None:
    """Append/replace rows in data_manifest.csv keyed by dataset_id+path."""
    import csv

    fields = ["dataset_id", "path", "source", "date", "size_bytes", "checksum_md5", "notes"]
    existing: dict[tuple, dict] = {}
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing[(r.get("dataset_id"), r.get("path"))] = r
    for r in rows:
        existing[(r.get("dataset_id"), r.get("path"))] = r
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in existing.values():
            w.writerow({k: r.get(k, "") for k in fields})


def manifest_row(dataset_id: str, path: Path, source: str, date: str = "", notes: str = "") -> dict:
    rel = str(path.relative_to(PROJECT_ROOT)) if path.exists() else str(path)
    return {
        "dataset_id": dataset_id,
        "path": rel,
        "source": source,
        "date": date or datetime.utcnow().strftime("%Y-%m-%d"),
        "size_bytes": file_size(path),
        "checksum_md5": md5(path) if path.exists() and path.is_file() else "",
        "notes": notes,
    }


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
