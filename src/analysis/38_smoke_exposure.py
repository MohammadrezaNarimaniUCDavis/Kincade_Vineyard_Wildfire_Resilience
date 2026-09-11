"""Potential smoke exposure over Kincade-area vineyards (NOAA HMS smoke polygons).

Downloads daily NOAA/NESDIS Hazard Mapping System (HMS) smoke polygon
shapefiles for 2019-10-23 .. 2019-11-10 and intersects them with the DWR
vineyard fields to quantify *potential* atmospheric smoke exposure (overhead
smoke plumes detected from GOES/polar imagery). This is an exposure proxy only
and is NOT a measure of smoke taint or in-berry volatile phenols.

Source: https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/
Attributes: Satellite, Start, End, Density (Light/Medium/Heavy).

Outputs
-------
- data/raw/smoke/hms_smoke_YYYYMMDD.zip                    (raw daily archives)
- data/processed/vineyard_smoke_days.csv                   (per-field exposure)
- outputs/tables/smoke_vineyard_summary.json               (headline numbers)
- outputs/tables/table_smoke_daily.csv                     (daily coverage)
- outputs/figures/data/fig_smoke_daily_coverage.csv        (figure data)
- appends rows to outputs/result_registry.csv
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_common import (  # noqa: E402
    CRS,
    FIGDATA,
    PROC,
    RAW,
    TABLES,
    append_registry,
    get_logger,
)

log = get_logger("38_smoke_exposure")
SCRIPT = "src/analysis/38_smoke_exposure.py"
SMOKE_DIR = RAW / "smoke"
SMOKE_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile"
START = date(2019, 10, 23)
END = date(2019, 11, 10)
DENSITY_WEIGHT = {"Light": 1, "Medium": 2, "Heavy": 3}


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def download_day(d: date) -> Path | None:
    fn = f"hms_smoke{d:%Y%m%d}.zip"
    out = SMOKE_DIR / fn
    if out.exists() and out.stat().st_size > 500:
        return out
    url = f"{BASE}/{d:%Y}/{d:%m}/{fn}"
    try:
        r = requests.get(url, timeout=180)
        if r.status_code == 200 and r.content[:2] == b"PK":
            out.write_bytes(r.content)
            return out
        log.warning("Day %s: HTTP %s (%d bytes)", d, r.status_code, len(r.content))
    except Exception as e:  # noqa: BLE001
        log.warning("Day %s download failed: %s", d, e)
    return None


def read_smoke(zip_path: Path) -> gpd.GeoDataFrame | None:
    try:
        g = gpd.read_file(f"zip://{zip_path.as_posix()}")
    except Exception as e:  # noqa: BLE001
        log.warning("Read failed %s: %s", zip_path.name, e)
        return None
    if g.empty:
        return None
    if g.crs is None:
        g = g.set_crs("EPSG:4326")
    g = g[g.geometry.notna() & g.geometry.is_valid | ~g.geometry.is_valid].copy()
    g["geometry"] = g.geometry.buffer(0)
    g = g[~g.geometry.is_empty].copy()
    if "Density" not in g.columns:
        g["Density"] = "Light"
    g["dens_w"] = g["Density"].map(DENSITY_WEIGHT).fillna(1).astype(int)
    return g


def main() -> int:
    vy = gpd.read_file(RAW / "vineyards" / "kincade_vineyards.gpkg").to_crs(CRS)
    vy = vy[vy.geometry.is_valid & ~vy.geometry.is_empty].copy()
    if "area_ha" not in vy.columns:
        vy["area_ha"] = vy.geometry.area / 10000.0
    vy = vy[["vineyard_field_id", "area_ha", "geometry"]].copy()
    aoi = vy.geometry.union_all() if hasattr(vy.geometry, "union_all") else vy.geometry.unary_union
    aoi_gdf = gpd.GeoDataFrame(geometry=[aoi], crs=CRS).to_crs("EPSG:4326")
    total_area_ha = float(vy["area_ha"].sum())

    per_field_days = {vid: 0 for vid in vy["vineyard_field_id"]}
    per_field_wdays = {vid: 0 for vid in vy["vineyard_field_id"]}
    per_field_maxdens = {vid: 0 for vid in vy["vineyard_field_id"]}
    daily_rows = []
    days_with_data = 0

    for d in daterange(START, END):
        zp = download_day(d)
        if zp is None:
            daily_rows.append({"date": d.isoformat(), "status": "missing",
                               "n_smoke_polys_aoi": 0, "vineyard_ha_under_smoke": 0.0,
                               "max_density": ""})
            continue
        g = read_smoke(zp)
        if g is None:
            daily_rows.append({"date": d.isoformat(), "status": "empty",
                               "n_smoke_polys_aoi": 0, "vineyard_ha_under_smoke": 0.0,
                               "max_density": ""})
            continue
        # keep only smoke polygons intersecting the vineyard footprint bbox region
        g_aoi = g[g.intersects(aoi_gdf.iloc[0].geometry)].copy()
        if g_aoi.empty:
            daily_rows.append({"date": d.isoformat(), "status": "no_overlap",
                               "n_smoke_polys_aoi": 0, "vineyard_ha_under_smoke": 0.0,
                               "max_density": ""})
            continue
        days_with_data += 1
        g_aoi = g_aoi.to_crs(CRS)
        # spatial join: which fields intersect which smoke polygons today
        sj = gpd.sjoin(vy, g_aoi[["dens_w", "Density", "geometry"]], how="inner", predicate="intersects")
        if sj.empty:
            daily_rows.append({"date": d.isoformat(), "status": "no_field_overlap",
                               "n_smoke_polys_aoi": int(len(g_aoi)),
                               "vineyard_ha_under_smoke": 0.0, "max_density": ""})
            continue
        fld_dens = sj.groupby("vineyard_field_id")["dens_w"].max()
        exposed_ids = fld_dens.index.tolist()
        exposed_ha = float(vy.loc[vy["vineyard_field_id"].isin(exposed_ids), "area_ha"].sum())
        for vid, w in fld_dens.items():
            per_field_days[vid] += 1
            per_field_wdays[vid] += int(w)
            per_field_maxdens[vid] = max(per_field_maxdens[vid], int(w))
        max_dw = int(fld_dens.max())
        max_dens_label = next((k for k, v in DENSITY_WEIGHT.items() if v == max_dw), "")
        daily_rows.append({"date": d.isoformat(), "status": "ok",
                           "n_smoke_polys_aoi": int(len(g_aoi)),
                           "vineyard_ha_under_smoke": round(exposed_ha, 2),
                           "max_density": max_dens_label})
        log.info("%s: %d smoke polys over AOI, %.0f vineyard ha exposed (max %s)",
                 d, len(g_aoi), exposed_ha, max_dens_label)

    daily_df = pd.DataFrame(daily_rows)
    daily_df.to_csv(TABLES / "table_smoke_daily.csv", index=False)
    daily_df.to_csv(FIGDATA / "fig_smoke_daily_coverage.csv", index=False)

    field_df = pd.DataFrame({
        "vineyard_field_id": list(per_field_days.keys()),
        "smoke_days": list(per_field_days.values()),
        "smoke_density_weighted_days": list(per_field_wdays.values()),
        "max_density_weight": list(per_field_maxdens.values()),
    }).merge(vy[["vineyard_field_id", "area_ha"]], on="vineyard_field_id", how="left")
    field_df["ha_smoke_days"] = field_df["area_ha"] * field_df["smoke_days"]
    field_df.to_csv(PROC / "vineyard_smoke_days.csv", index=False)

    total_ha_smoke_days = float(field_df["ha_smoke_days"].sum())
    mean_smoke_days = float(field_df["smoke_days"].mean())
    max_smoke_days = int(field_df["smoke_days"].max())
    n_fields_any = int((field_df["smoke_days"] > 0).sum())

    summary = {
        "exposure_type": "POTENTIAL atmospheric smoke exposure (overhead HMS smoke plumes); NOT smoke taint",
        "source": "NOAA/NESDIS HMS Smoke Polygons (GOES + polar), daily shapefiles",
        "window": {"start": START.isoformat(), "end": END.isoformat(),
                   "n_days_requested": (END - START).days + 1,
                   "n_days_with_smoke_over_aoi": days_with_data},
        "n_vineyard_fields": int(len(vy)),
        "total_vineyard_area_ha": round(total_area_ha, 1),
        "n_fields_with_any_smoke_day": n_fields_any,
        "mean_smoke_days_per_field": round(mean_smoke_days, 2),
        "max_smoke_days_per_field": max_smoke_days,
        "total_hectare_smoke_days": round(total_ha_smoke_days, 1),
        "density_weights": DENSITY_WEIGHT,
        "caveats": [
            "HMS smoke polygons indicate overhead smoke detected in satellite imagery; "
            "they do not measure ground-level PM2.5 or grape smoke taint.",
            "Plume polygons are regional and analyst-drawn; a field flagged as exposed on a day "
            "means smoke was overhead at some point that day.",
        ],
    }
    with open(TABLES / "smoke_vineyard_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Smoke summary: %s", json.dumps({k: summary[k] for k in
             ["n_fields_with_any_smoke_day", "mean_smoke_days_per_field",
              "max_smoke_days_per_field", "total_hectare_smoke_days"]}))

    reg = [
        {"result_id": "R020", "manuscript_section": "Results 3.4",
         "metric": "mean_potential_smoke_days_per_vineyard", "value": round(mean_smoke_days, 2),
         "unit": "days", "uncertainty": "",
         "dataset": "NOAA_HMS_smoke", "analysis_script": SCRIPT,
         "model": "daily_polygon_intersection",
         "source_output": "outputs/tables/smoke_vineyard_summary.json"},
        {"result_id": "R021", "manuscript_section": "Results 3.4",
         "metric": "total_vineyard_hectare_smoke_days", "value": round(total_ha_smoke_days, 1),
         "unit": "ha-days", "uncertainty": "",
         "dataset": "NOAA_HMS_smoke", "analysis_script": SCRIPT,
         "model": "daily_polygon_intersection",
         "source_output": "outputs/tables/smoke_vineyard_summary.json"},
        {"result_id": "R022", "manuscript_section": "Results 3.4",
         "metric": "n_days_smoke_over_aoi", "value": days_with_data,
         "unit": "days", "uncertainty": "",
         "dataset": "NOAA_HMS_smoke", "analysis_script": SCRIPT,
         "model": "daily_polygon_intersection",
         "source_output": "outputs/tables/smoke_vineyard_summary.json"},
    ]
    append_registry(reg)

    print(json.dumps(summary, indent=2))
    print(daily_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
