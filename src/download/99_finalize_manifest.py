"""Scan data/raw and ensure every output file is recorded in data_manifest.csv.

Intermediate download caches (vineyards/_source extracted GDB) are skipped
except the original source zip, which is recorded for provenance.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, MANIFEST_PATH, PROJECT_ROOT, append_manifest, get_logger, manifest_row  # noqa: E402

log = get_logger("99_finalize_manifest")

SOURCE_HINTS = {
    "fire": "WFIGS/NIFC InterAgency Fire Perimeter History (ArcGIS FeatureServer)",
    "dins": "CAL FIRE POSTFIRE_MASTER_DATA_SHARE (ArcGIS FeatureServer)",
    "vineyards": "DWR i15 Statewide Crop Mapping 2019 (data.cnra.ca.gov)",
    "gee": "Google Earth Engine",
    "weather": "GEE IDAHO_EPSCOR/GRIDMET",
    "soils": "USDA NRCS SSURGO (Soil Data Access)",
}


def main() -> int:
    existing_paths = set()
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing_paths.add(r["path"].replace("/", "\\"))

    new_rows = []
    for p in sorted(DATA_RAW.rglob("*")):
        if not p.is_file():
            continue
        # skip extracted GDB cache but keep the original source zip
        parts = p.parts
        if "_source" in parts and p.suffix.lower() != ".zip":
            continue
        rel = str(p.relative_to(PROJECT_ROOT))
        if rel.replace("/", "\\") in existing_paths:
            continue
        category = p.relative_to(DATA_RAW).parts[0]
        src = SOURCE_HINTS.get(category, "see DATA_SOURCES.md")
        note = "source cache (statewide zip)" if "_source" in parts else "auto-added by finalize"
        new_rows.append(manifest_row(f"{category}_{p.stem}", p, src, notes=note))
        log.info("Adding to manifest: %s", rel)

    if new_rows:
        append_manifest(new_rows)
    log.info("Finalize complete; %d new rows added", len(new_rows))

    # Report totals
    with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total_bytes = sum(int(r["size_bytes"] or 0) for r in rows)
    log.info("Manifest now lists %d files, total %.1f MB", len(rows), total_bytes / 1e6)
    print(f"Manifest: {len(rows)} files, {total_bytes/1e6:.1f} MB total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
