"""Run the audited Kincade vineyard wildfire resilience pipeline.

Usage:
    python run_pipeline.py
    python run_pipeline.py --from 25
    python run_pipeline.py --only 42
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STAGES = [
    (1, "src/download/01_fire_perimeter.py"),
    (2, "src/download/02_dins.py"),
    (3, "src/download/03_vineyards.py"),
    (4, "src/download/04_dem_gee.py"),
    (5, "src/download/05_burn_severity_gee.py"),
    (6, "src/download/06_openet_gee.py"),
    (7, "src/download/07_gridmet.py"),
    (8, "src/download/08_ssurgo.py"),
    (9, "src/download/09_s2_rgb_composites_gee.py"),
    (99, "src/download/99_finalize_manifest.py"),
    (25, "src/analysis/25_prefire_ndmi_et.py"),
    (30, "src/analysis/30_boundary_rdd.py"),
    (34, "src/analysis/34_bayesian_spatial.py"),
    (36, "src/analysis/36_transport_network.py"),
    (38, "src/analysis/38_smoke_exposure.py"),
    (40, "src/analysis/40_recovery.py"),
    (45, "src/analysis/45_lidar_inventory.py"),
    (42, "src/visualization/42_make_main_figures.py"),
    (50, "scripts/build_csvs.py"),
    (51, "scripts/build_manuscript_tables.py"),
]
ORDER = [n for n, _ in STAGES]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", type=int, default=None)
    ap.add_argument("--only", type=int, default=None)
    args = ap.parse_args()
    stage_map = dict(STAGES)
    if args.only is not None:
        to_run = [args.only]
    elif args.start is not None:
        to_run = ORDER[ORDER.index(args.start) :]
    else:
        to_run = list(ORDER)

    for n in to_run:
        script = stage_map[n]
        print(f"\n=== stage {n}: {script} ===")
        t0 = time.time()
        rc = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT).returncode
        print(f"=== stage {n} done in {time.time() - t0:.1f}s (rc={rc}) ===")
        if rc != 0:
            sys.exit(rc)


if __name__ == "__main__":
    main()
