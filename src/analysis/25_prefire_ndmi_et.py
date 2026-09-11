"""Prefire Sentinel-2 NDMI / NDVI per vineyard field and links to ET and soil AWC.

Steps
-----
1. Build a cloud-masked Sentinel-2 SR median composite for the prefire window
   (2019-09-01 .. 2019-10-22) and derive NDMI = (B8-B11)/(B8+B11) and
   NDVI = (B8-B4)/(B8+B4).
2. Zonal-mean NDMI/NDVI per DWR vineyard field via ee.Image.reduceRegions
   (batched to keep each getInfo call small).
3. Join OpenET growing-season ET (sum of monthly Apr-Oct 2019) and SSURGO
   available water capacity (AWC, centroid join) to each field.
4. Relate prefire NDMI to OpenET GS ET and to soil AWC (correlations + OLS).

Outputs
-------
- data/processed/prefire_ndmi_ndvi_vineyard.csv          (per-field indices)
- data/processed/vineyard_prefire_water_status.csv       (indices+ET+AWC join)
- outputs/tables/table_prefire_ndmi_et.csv               (regression/corr table)
- outputs/tables/prefire_ndmi_et_summary.json            (summary stats)
- outputs/figures/data/fig_prefire_ndmi_et.csv           (scatter figure data)
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
    PREFIRE,
    PROC,
    RAW,
    TABLES,
    WGS84,
    append_registry,
    get_logger,
    init_ee,
)

log = get_logger("25_prefire_ndmi_et")
SCRIPT = "src/analysis/25_prefire_ndmi_et.py"
BATCH = 800


def s2_prefire_indices(ee, region):
    """Median NDMI/NDVI composite over the prefire window."""

    def mask(img):
        scl = img.select("SCL")
        good = (
            scl.neq(3)  # cloud shadow
            .And(scl.neq(8))  # cloud medium prob
            .And(scl.neq(9))  # cloud high prob
            .And(scl.neq(10))  # thin cirrus
            .And(scl.neq(11))  # snow/ice
        )
        return img.updateMask(good).divide(10000)

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(PREFIRE[0], PREFIRE[1])
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
        .map(mask)
    )
    n = col.size().getInfo()
    log.info("Prefire S2 scenes (%s..%s, <60%% cloud): %d", PREFIRE[0], PREFIRE[1], n)

    def add_idx(img):
        ndmi = img.normalizedDifference(["B8", "B11"]).rename("NDMI")
        ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
        return img.addBands([ndmi, ndvi])

    comp = col.map(add_idx).select(["NDMI", "NDVI"]).median()
    return comp, n


def _fc_from_gdf(ee, gdf):
    feats = []
    for vid, geom in zip(gdf["vineyard_field_id"], gdf.geometry):
        feats.append(ee.Feature(ee.Geometry(geom.__geo_interface__), {"vineyard_field_id": vid}))
    return ee.FeatureCollection(feats)


def zonal_indices(ee, comp, vy4326):
    """Batched reduceRegions mean of NDMI/NDVI per vineyard field."""
    rows = []
    n = len(vy4326)
    for start in range(0, n, BATCH):
        chunk = vy4326.iloc[start:start + BATCH]
        fc = _fc_from_gdf(ee, chunk)
        sampled = comp.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=20)
        feats = sampled.getInfo()["features"]
        for f in feats:
            p = f["properties"]
            rows.append({
                "vineyard_field_id": p.get("vineyard_field_id"),
                "NDMI_prefire": p.get("NDMI"),
                "NDVI_prefire": p.get("NDVI"),
            })
        log.info("  reduced fields %d..%d (%d returned)", start, min(start + BATCH, n), len(feats))
    return pd.DataFrame(rows)


def join_awc(vy_utm: gpd.GeoDataFrame) -> pd.DataFrame:
    """Centroid join of SSURGO AWC (0-100 cm, 0-150 cm) to each vineyard field."""
    soils = gpd.read_file(RAW / "soils" / "kincade_ssurgo.gpkg").to_crs(CRS)
    for c in ("awc_0_100cm", "awc_0_150cm"):
        soils[c] = pd.to_numeric(soils[c], errors="coerce")
    soils = soils[["awc_0_100cm", "awc_0_150cm", "muname", "drainage_class", "geometry"]]
    cent = vy_utm.copy()
    cent["geometry"] = cent.geometry.centroid
    joined = gpd.sjoin(cent, soils, how="left", predicate="within")
    joined = joined.drop_duplicates(subset="vineyard_field_id", keep="first")
    return joined[["vineyard_field_id", "awc_0_100cm", "awc_0_150cm", "muname", "drainage_class"]]


def openet_gs(et_csv: Path) -> pd.DataFrame:
    et = pd.read_csv(et_csv)
    month_cols = [c for c in et.columns if c.startswith("ET_2019_")]
    et["ET_gs_mm"] = et[month_cols].sum(axis=1, min_count=1)
    return et[["vineyard_field_id", "ET_gs_mm"]]


def ols_report(df, xcol, ycol):
    sub = df[[xcol, ycol]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 30:
        return None
    x = sub[xcol].values.astype(float)
    y = sub[ycol].values.astype(float)
    slope, intercept, r, p, se = stats.linregress(x, y)
    rho, prho = stats.spearmanr(x, y)
    return {
        "x": xcol,
        "y": ycol,
        "n": int(len(sub)),
        "slope": float(slope),
        "intercept": float(intercept),
        "pearson_r": float(r),
        "pearson_r2": float(r**2),
        "p_value": float(p),
        "slope_se": float(se),
        "spearman_rho": float(rho),
        "spearman_p": float(prho),
    }


def main() -> int:
    ee = init_ee()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "download"))
    from gee_utils import aoi_from_perimeter  # noqa: E402

    region, _ = aoi_from_perimeter(buffer_m=5000)
    comp, n_scenes = s2_prefire_indices(ee, region)

    vy_utm = gpd.read_file(RAW / "vineyards" / "kincade_vineyards.gpkg").to_crs(CRS)
    vy_utm = vy_utm[vy_utm.geometry.is_valid & ~vy_utm.geometry.is_empty].copy()
    if "area_ha" not in vy_utm.columns:
        vy_utm["area_ha"] = vy_utm.geometry.area / 10000.0

    vy4326 = vy_utm[["vineyard_field_id", "geometry"]].to_crs(WGS84).copy()
    try:
        from shapely import force_2d
        vy4326["geometry"] = vy4326.geometry.apply(force_2d)
    except Exception:  # noqa: BLE001
        from shapely.ops import transform as shp_transform
        vy4326["geometry"] = vy4326.geometry.apply(lambda g: shp_transform(lambda *c: c[:2], g))

    idx_df = zonal_indices(ee, comp, vy4326)
    idx_df = idx_df.merge(vy_utm[["vineyard_field_id", "area_ha"]], on="vineyard_field_id", how="left")
    idx_df.to_csv(PROC / "prefire_ndmi_ndvi_vineyard.csv", index=False)
    log.info("Wrote per-field NDMI/NDVI for %d fields", len(idx_df))

    awc = join_awc(vy_utm)
    et_gs = openet_gs(RAW / "gee" / "openet_vineyard_monthly.csv")
    merged = idx_df.merge(et_gs, on="vineyard_field_id", how="left").merge(awc, on="vineyard_field_id", how="left")
    merged.to_csv(PROC / "vineyard_prefire_water_status.csv", index=False)

    fig_cols = ["vineyard_field_id", "NDMI_prefire", "NDVI_prefire", "ET_gs_mm",
                "awc_0_100cm", "awc_0_150cm", "area_ha"]
    merged[fig_cols].to_csv(FIGDATA / "fig_prefire_ndmi_et.csv", index=False)

    reports = []
    for xcol, ycol in [
        ("NDMI_prefire", "ET_gs_mm"),
        ("NDVI_prefire", "ET_gs_mm"),
        ("awc_0_100cm", "ET_gs_mm"),
        ("awc_0_100cm", "NDMI_prefire"),
        ("awc_0_150cm", "NDMI_prefire"),
    ]:
        r = ols_report(merged, xcol, ycol)
        if r:
            reports.append(r)
    rep_df = pd.DataFrame(reports)
    rep_df.to_csv(TABLES / "table_prefire_ndmi_et.csv", index=False)

    def _mean(col):
        v = pd.to_numeric(merged[col], errors="coerce")
        return float(v.mean()) if v.notna().any() else None

    def _std(col):
        v = pd.to_numeric(merged[col], errors="coerce")
        return float(v.std()) if v.notna().any() else None

    summary = {
        "prefire_window": PREFIRE,
        "n_s2_scenes": n_scenes,
        "n_fields_total": int(len(merged)),
        "n_fields_with_ndmi": int(merged["NDMI_prefire"].notna().sum()),
        "n_fields_with_et": int(merged["ET_gs_mm"].notna().sum()),
        "n_fields_with_awc": int(pd.to_numeric(merged["awc_0_100cm"], errors="coerce").notna().sum()),
        "mean_NDMI_prefire": _mean("NDMI_prefire"),
        "sd_NDMI_prefire": _std("NDMI_prefire"),
        "mean_NDVI_prefire": _mean("NDVI_prefire"),
        "mean_ET_gs_mm": _mean("ET_gs_mm"),
        "mean_awc_0_100cm": _mean("awc_0_100cm"),
        "relationships": reports,
    }
    with open(TABLES / "prefire_ndmi_et_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Summary: %s", json.dumps({k: v for k, v in summary.items() if k != "relationships"}))

    reg = [
        {"result_id": "R010", "manuscript_section": "Results 3.1",
         "metric": "mean_prefire_NDMI_vineyard", "value": summary["mean_NDMI_prefire"],
         "unit": "index", "uncertainty": summary["sd_NDMI_prefire"],
         "dataset": "S2_SR_HARMONIZED_prefire", "analysis_script": SCRIPT,
         "model": "zonal_median_composite",
         "source_output": "outputs/tables/prefire_ndmi_et_summary.json"},
        {"result_id": "R011", "manuscript_section": "Results 3.1",
         "metric": "mean_prefire_NDVI_vineyard", "value": summary["mean_NDVI_prefire"],
         "unit": "index", "uncertainty": "",
         "dataset": "S2_SR_HARMONIZED_prefire", "analysis_script": SCRIPT,
         "model": "zonal_median_composite",
         "source_output": "outputs/tables/prefire_ndmi_et_summary.json"},
    ]
    ndmi_et = next((r for r in reports if r["x"] == "NDMI_prefire" and r["y"] == "ET_gs_mm"), None)
    if ndmi_et:
        reg.append({
            "result_id": "R012", "manuscript_section": "Results 3.1",
            "metric": "pearson_r_NDMI_vs_ETgs", "value": ndmi_et["pearson_r"],
            "unit": "r", "uncertainty": ndmi_et["p_value"],
            "dataset": "S2_NDMI+OpenET", "analysis_script": SCRIPT,
            "model": "OLS_linregress",
            "source_output": "outputs/tables/table_prefire_ndmi_et.csv"})
    awc_ndmi = next((r for r in reports if r["x"] == "awc_0_100cm" and r["y"] == "NDMI_prefire"), None)
    if awc_ndmi:
        reg.append({
            "result_id": "R013", "manuscript_section": "Results 3.1",
            "metric": "pearson_r_AWC_vs_NDMI", "value": awc_ndmi["pearson_r"],
            "unit": "r", "uncertainty": awc_ndmi["p_value"],
            "dataset": "SSURGO_AWC+S2_NDMI", "analysis_script": SCRIPT,
            "model": "OLS_linregress",
            "source_output": "outputs/tables/table_prefire_ndmi_et.csv"})
    append_registry(reg)

    print(json.dumps({k: v for k, v in summary.items() if k != "relationships"}, indent=2))
    print("Relationships:")
    print(rep_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
