#!/usr/bin/env python
"""End-to-end pipeline orchestrator for the Kincade Multisystem Resilience study.

Lists and (optionally) runs every stage of the workflow in order, from raw-data
acquisition through analysis, figures, tables, references, and manuscript build.
All stages read parameters from ``config/project.yaml`` and write to ``data/`` and
``outputs/``; quantitative results are appended to ``outputs/result_registry.csv``.

Usage (from the project root, with the ``gee`` conda environment):
    conda run -n gee python src/pipeline/run_all.py --list
    conda run -n gee python src/pipeline/run_all.py --dry-run
    conda run -n gee python src/pipeline/run_all.py --only analysis
    conda run -n gee python src/pipeline/run_all.py            # run everything

Notes:
    * Data-acquisition stages require an authenticated Google Earth Engine session
      and network access; they are idempotent and safe to re-run.
    * The manuscript build stage requires pandoc (and a LaTeX engine for PDF).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (group, human label, command as list). "python" resolves to the current interpreter.
PY = sys.executable

STAGES: list[tuple[str, str, list[str]]] = [
    # --- 1. Data acquisition (Google Earth Engine + agency APIs) ---
    ("download", "Fire perimeter (WFIGS/NIFC)", [PY, "src/download/01_fire_perimeter.py"]),
    ("download", "Structure damage (CAL FIRE DINS)", [PY, "src/download/02_dins.py"]),
    ("download", "Vineyards (DWR i15 2019)", [PY, "src/download/03_vineyards.py"]),
    ("download", "DEM (USGS 3DEP 10 m)", [PY, "src/download/04_dem_gee.py"]),
    ("download", "Burn severity (S2 + Landsat-8)", [PY, "src/download/05_burn_severity_gee.py"]),
    ("download", "S2 RGB/SWIR context composites", [PY, "src/download/09_s2_rgb_composites_gee.py"]),
    ("download", "Evapotranspiration (OpenET)", [PY, "src/download/06_openet_gee.py"]),
    ("download", "Fire weather (gridMET)", [PY, "src/download/07_gridmet.py"]),
    ("download", "Soils (SSURGO)", [PY, "src/download/08_ssurgo.py"]),
    ("download", "Finalize data manifest", [PY, "src/download/99_finalize_manifest.py"]),
    # --- 2. Analysis modules ---
    ("analysis", "Pre-fire water status (NDMI/NDVI vs ET/AWC)", [PY, "src/analysis/25_prefire_ndmi_et.py"]),
    ("analysis", "Boundary discontinuity (RDD) + severity contrast", [PY, "src/analysis/30_boundary_rdd.py"]),
    ("analysis", "Landscape severity drivers (spatial GAM)", [PY, "src/analysis/34_bayesian_spatial.py"]),
    ("analysis", "Transport network structure", [PY, "src/analysis/36_transport_network.py"]),
    ("analysis", "Potential smoke exposure", [PY, "src/analysis/38_smoke_exposure.py"]),
    ("analysis", "NDVI recovery trajectories", [PY, "src/analysis/40_recovery.py"]),
    ("analysis", "3-D structure / lidar inventory", [PY, "src/analysis/45_lidar_inventory.py"]),
    # --- 3. Figures and tables ---
    ("figures", "Main figures (Figure_01..Figure_10)", [PY, "src/visualization/42_make_main_figures.py"]),
    ("tables", "Analysis CSV tables", [PY, "scripts/build_csvs.py"]),
    ("tables", "Manuscript Tables 1-4 (CSV/XLSX)", [PY, "scripts/build_manuscript_tables.py"]),
    # --- 4. References ---
    ("references", "Build/verify references.bib", [PY, "scripts/build_bib.py"]),
    # --- 5. Manuscript build (requires pandoc; PDF requires LaTeX) ---
    ("manuscript", "Build manuscript docx/tex/pdf", ["pandoc", "--version"]),
]

GROUP_ORDER = ["download", "analysis", "figures", "tables", "references", "manuscript"]


def list_stages() -> None:
    print("Pipeline stages (in execution order):\n")
    n = 0
    for group in GROUP_ORDER:
        print(f"[{group}]")
        for g, label, cmd in STAGES:
            if g == group:
                n += 1
                print(f"  {n:2d}. {label}\n      $ {' '.join(cmd)}")
        print()
    print("Manuscript build is documented in docs/REPRODUCIBILITY.md (pandoc commands).")


def run(only: str | None, dry_run: bool) -> int:
    failures: list[str] = []
    for group, label, cmd in STAGES:
        if only and group != only:
            continue
        print(f"\n=== [{group}] {label} ===")
        print("    $", " ".join(cmd))
        if dry_run:
            continue
        t0 = time.time()
        try:
            subprocess.run(cmd, cwd=str(ROOT), check=True)
            print(f"    done in {time.time() - t0:.1f}s")
        except subprocess.CalledProcessError as exc:
            print(f"    FAILED (exit {exc.returncode})")
            failures.append(label)
    if failures:
        print("\nStages that failed:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nAll requested stages completed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Kincade Multisystem Resilience pipeline orchestrator")
    ap.add_argument("--list", action="store_true", help="list stages and exit")
    ap.add_argument("--dry-run", action="store_true", help="print commands without executing")
    ap.add_argument(
        "--only",
        choices=GROUP_ORDER,
        help="run only one stage group (download/analysis/figures/tables/references/manuscript)",
    )
    args = ap.parse_args()
    if args.list:
        list_stages()
        return 0
    return run(args.only, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
