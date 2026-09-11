"""Vineyard NDVI recovery trajectories inside vs outside the Kincade perimeter.

Builds month-matched growing-season (Apr 1 - Sep 30) Sentinel-2 median NDVI
composites for 2018, 2019 (prefire baseline), 2020 and 2021, samples field-mean
NDVI per DWR vineyard field
(one multiband reduceRegions per batch), flags each field inside vs outside
the fire perimeter, and estimates recovery trajectories (post-fire NDVI
relative to the 2019 prefire baseline) for the two groups.

Outputs
-------
- data/processed/vineyard_ndvi_recovery.csv           (per-field yearly NDVI)
- outputs/tables/table_recovery_group_means.csv       (group x year means)
- outputs/tables/table_recovery_tests.csv             (inside vs outside tests)
- outputs/tables/recovery_summary.json
- outputs/figures/data/fig_recovery_trajectory.csv    (figure data)
- appends rows to outputs/result_registry.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_common import (  # noqa: E402
    CRS,
    FIGDATA,
    PROC,
    RAW,
    TABLES,
    WGS84,
    append_registry,
    get_logger,
    init_ee,
)

log = get_logger("40_recovery")
SCRIPT = "src/analysis/40_recovery.py"
BATCH = 800
YEARS = [2018, 2019, 2020, 2021]
GS = ("-04-01", "-09-30")  # month-matched Apr 1 .. Sep 30


def year_ndvi(ee, region, year):
    def mask(img):
        scl = img.select("SCL")
        good = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        return img.updateMask(good).divide(10000)

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(f"{year}{GS[0]}", f"{year}{GS[1]}")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
        .map(mask)
    )
    n = col.size().getInfo()
    ndvi = col.map(lambda i: i.normalizedDifference(["B8", "B4"]).rename(f"NDVI_{year}")).median()
    return ndvi, n


def _fc_from_gdf(ee, gdf):
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(geom.__geo_interface__), {"vineyard_field_id": vid})
        for vid, geom in zip(gdf["vineyard_field_id"], gdf.geometry)
    ])


def main() -> int:
    ee = init_ee()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "download"))
    from gee_utils import aoi_from_perimeter  # noqa: E402

    region, _ = aoi_from_perimeter(buffer_m=5000)

    stack = None
    n_scenes = {}
    band_names = []
    for y in YEARS:
        ndvi, n = year_ndvi(ee, region, y)
        n_scenes[y] = n
        band_names.append(f"NDVI_{y}")
        stack = ndvi if stack is None else stack.addBands(ndvi)
        log.info("Year %d: %d S2 scenes (Apr-Sep, <60%% cloud)", y, n)

    vy = gpd.read_file(RAW / "vineyards" / "kincade_vineyards.gpkg").to_crs(CRS)
    vy = vy[vy.geometry.is_valid & ~vy.geometry.is_empty].copy()
    if "area_ha" not in vy.columns:
        vy["area_ha"] = vy.geometry.area / 10000.0

    fire = gpd.read_file(RAW / "fire" / "kincade_perimeter.gpkg").to_crs(CRS)
    fire_u = fire.geometry.union_all() if hasattr(fire.geometry, "union_all") else fire.geometry.unary_union
    vy["in_perimeter"] = vy.geometry.intersects(fire_u).astype(int)

    vy4326 = vy[["vineyard_field_id", "geometry"]].to_crs(WGS84).copy()
    try:
        from shapely import force_2d
        vy4326["geometry"] = vy4326.geometry.apply(force_2d)
    except Exception:  # noqa: BLE001
        from shapely.ops import transform as shp_transform
        vy4326["geometry"] = vy4326.geometry.apply(lambda g: shp_transform(lambda *c: c[:2], g))

    rows = []
    nrec = len(vy4326)
    for start in range(0, nrec, BATCH):
        chunk = vy4326.iloc[start:start + BATCH]
        fc = _fc_from_gdf(ee, chunk)
        sampled = stack.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=20)
        for f in sampled.getInfo()["features"]:
            p = f["properties"]
            rows.append({"vineyard_field_id": p.get("vineyard_field_id"),
                         **{b: p.get(b) for b in band_names}})
        log.info("  reduced fields %d..%d", start, min(start + BATCH, nrec))

    ndvi_df = pd.DataFrame(rows).merge(
        vy[["vineyard_field_id", "area_ha", "in_perimeter"]], on="vineyard_field_id", how="left")

    # recovery ratios relative to 2019 prefire baseline
    base = ndvi_df["NDVI_2019"].replace(0, np.nan)
    ndvi_df["recov_2020_ratio"] = ndvi_df["NDVI_2020"] / base
    ndvi_df["recov_2021_ratio"] = ndvi_df["NDVI_2021"] / base
    ndvi_df["drop_2019_2020"] = ndvi_df["NDVI_2020"] - ndvi_df["NDVI_2019"]
    ndvi_df["drop_2019_2021"] = ndvi_df["NDVI_2021"] - ndvi_df["NDVI_2019"]
    ndvi_df.to_csv(PROC / "vineyard_ndvi_recovery.csv", index=False)
    log.info("Wrote per-field recovery table for %d fields", len(ndvi_df))

    # group means
    grp_rows = []
    for grp, label in [(1, "inside"), (0, "outside")]:
        sub = ndvi_df[ndvi_df["in_perimeter"] == grp]
        rec = {"group": label, "n_fields": int(len(sub)),
               "area_ha": round(float(sub["area_ha"].sum()), 1)}
        for b in band_names:
            rec[f"mean_{b}"] = float(pd.to_numeric(sub[b], errors="coerce").mean())
        rec["mean_recov_2020_ratio"] = float(sub["recov_2020_ratio"].mean())
        rec["mean_recov_2021_ratio"] = float(sub["recov_2021_ratio"].mean())
        grp_rows.append(rec)
    grp_df = pd.DataFrame(grp_rows)
    grp_df.to_csv(TABLES / "table_recovery_group_means.csv", index=False)

    # figure data (long form)
    fig_rows = []
    for grp, label in [(1, "inside"), (0, "outside")]:
        sub = ndvi_df[ndvi_df["in_perimeter"] == grp]
        for y in YEARS:
            v = pd.to_numeric(sub[f"NDVI_{y}"], errors="coerce")
            fig_rows.append({"group": label, "year": y,
                             "mean_ndvi": float(v.mean()),
                             "sem_ndvi": float(v.sem()),
                             "n": int(v.notna().sum())})
    fig_df = pd.DataFrame(fig_rows)
    fig_df.to_csv(FIGDATA / "fig_recovery_trajectory.csv", index=False)

    # inside vs outside tests
    inside = ndvi_df[ndvi_df["in_perimeter"] == 1]
    outside = ndvi_df[ndvi_df["in_perimeter"] == 0]
    test_rows = []
    for col in ["NDVI_2019", "NDVI_2020", "NDVI_2021",
                "drop_2019_2020", "drop_2019_2021",
                "recov_2020_ratio", "recov_2021_ratio"]:
        a = pd.to_numeric(inside[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        b = pd.to_numeric(outside[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if len(a) < 10 or len(b) < 10:
            continue
        t, p = stats.ttest_ind(a, b, equal_var=False)
        test_rows.append({"variable": col, "n_inside": int(len(a)), "n_outside": int(len(b)),
                          "mean_inside": float(a.mean()), "mean_outside": float(b.mean()),
                          "diff_in_minus_out": float(a.mean() - b.mean()),
                          "welch_t": float(t), "p_value": float(p)})
    test_df = pd.DataFrame(test_rows)
    test_df.to_csv(TABLES / "table_recovery_tests.csv", index=False)

    summary = {
        "growing_season_window": "Apr 1 - Sep 30 (month-matched)",
        "years": YEARS,
        "baseline_year": 2019,
        "n_s2_scenes_by_year": n_scenes,
        "n_fields_total": int(len(ndvi_df)),
        "n_inside": int(len(inside)),
        "n_outside": int(len(outside)),
        "group_means": grp_rows,
        "inside_vs_outside_tests": test_rows,
        "note": "2019 Apr-Sep is fully prefire (Kincade ignition 2019-10-23); "
                "2020 and 2021 are post-fire recovery seasons.",
    }
    with open(TABLES / "recovery_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Recovery group means:\n%s", grp_df.to_string(index=False))
    log.info("Recovery tests:\n%s", test_df.to_string(index=False))

    reg = []
    d2020 = next((r for r in test_rows if r["variable"] == "drop_2019_2020"), None)
    if d2020:
        reg.append({"result_id": "R030", "manuscript_section": "Results 3.5",
                    "metric": "NDVI_drop_2019to2020_inside", "value": round(d2020["mean_inside"], 4),
                    "unit": "NDVI", "uncertainty": "",
                    "dataset": "S2_NDVI_recovery", "analysis_script": SCRIPT,
                    "model": "field_mean_composite",
                    "source_output": "outputs/tables/table_recovery_tests.csv"})
        reg.append({"result_id": "R031", "manuscript_section": "Results 3.5",
                    "metric": "NDVI_drop_2019to2020_outside", "value": round(d2020["mean_outside"], 4),
                    "unit": "NDVI", "uncertainty": d2020["p_value"],
                    "dataset": "S2_NDVI_recovery", "analysis_script": SCRIPT,
                    "model": "field_mean_composite",
                    "source_output": "outputs/tables/table_recovery_tests.csv"})
    r2021 = next((r for r in test_rows if r["variable"] == "recov_2021_ratio"), None)
    if r2021:
        reg.append({"result_id": "R032", "manuscript_section": "Results 3.5",
                    "metric": "recovery_ratio_2021_inside", "value": round(r2021["mean_inside"], 4),
                    "unit": "ratio", "uncertainty": r2021["p_value"],
                    "dataset": "S2_NDVI_recovery", "analysis_script": SCRIPT,
                    "model": "NDVI2021/NDVI2019",
                    "source_output": "outputs/tables/table_recovery_tests.csv"})
        reg.append({"result_id": "R033", "manuscript_section": "Results 3.5",
                    "metric": "recovery_ratio_2021_outside", "value": round(r2021["mean_outside"], 4),
                    "unit": "ratio", "uncertainty": "",
                    "dataset": "S2_NDVI_recovery", "analysis_script": SCRIPT,
                    "model": "NDVI2021/NDVI2019",
                    "source_output": "outputs/tables/table_recovery_tests.csv"})
    append_registry(reg)

    print(json.dumps({k: summary[k] for k in
          ["years", "n_s2_scenes_by_year", "n_inside", "n_outside"]}, indent=2))
    print(grp_df.to_string(index=False))
    print(test_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
