"""Download the Kincade (2019) fire perimeter.

Primary source: WFIGS Interagency Perimeters (ArcGIS FeatureServer).
Fallback: NIFC WFIGS Interagency Fire Perimeter History and CAL FIRE FRAP.
Outputs GeoJSON + GeoPackage to data/raw/fire/ and records key attributes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DATA_RAW,
    WGS84,
    append_manifest,
    get_logger,
    manifest_row,
    save_json,
)

log = get_logger("01_fire_perimeter")
OUT = DATA_RAW / "fire"
OUT.mkdir(parents=True, exist_ok=True)

WFIGS_URLS = [
    # Current interagency perimeters (as specified)
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters/FeatureServer/0",
    # WFIGS Interagency Perimeters — historical / full
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0",
]
# NIFC historical perimeters (good for 2019 events)
NIFC_HISTORY = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0"


def query_arcgis(base_url: str, where: str) -> dict | None:
    params = {
        "where": where,
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "returnGeometry": "true",
    }
    try:
        r = requests.get(base_url + "/query", params=params, timeout=120)
        r.raise_for_status()
        data = r.json()
        feats = data.get("features", [])
        log.info("Query %s WHERE %s -> %d features", base_url.split("/services/")[-1][:40], where, len(feats))
        if feats:
            return data
    except Exception as e:  # noqa: BLE001
        log.warning("Query failed for %s: %s", base_url, e)
    return None


def try_sources() -> tuple[dict | None, str]:
    # WHERE clauses to try across services (field names differ between layers)
    where_clauses = [
        "UPPER(poly_IncidentName) LIKE '%KINCADE%'",
        "UPPER(IncidentName) LIKE '%KINCADE%'",
        "UPPER(attr_IncidentName) LIKE '%KINCADE%'",
        "UPPER(FIRE_NAME) LIKE '%KINCADE%'",
        "UPPER(INCIDENT) LIKE '%KINCADE%'",
    ]
    for url in WFIGS_URLS + [NIFC_HISTORY]:
        for wc in where_clauses:
            data = query_arcgis(url, wc)
            if data:
                return data, url
    return None, ""


def try_calfire() -> tuple[dict | None, str]:
    """CAL FIRE FRAP historical fire perimeters (fire20_1 / current)."""
    calfire_urls = [
        "https://egis.fire.ca.gov/arcgis/rest/services/FRAP/firep22_1/MapServer/0",
        "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Fire_Perimeters/FeatureServer/0",
        "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Fire_Perimeters_all/FeatureServer/0",
    ]
    for url in calfire_urls:
        for wc in ["UPPER(FIRE_NAME) LIKE '%KINCADE%'", "UPPER(INCIDENT) LIKE '%KINCADE%'"]:
            data = query_arcgis(url, wc)
            if data:
                # filter to 2019
                feats = [
                    f for f in data["features"]
                    if str(f["properties"].get("YEAR_", f["properties"].get("YEAR", "2019"))) in ("2019", "2019.0")
                ] or data["features"]
                data["features"] = feats
                return data, url
    return None, ""


def main() -> int:
    data, source_url = try_sources()
    used_source = source_url
    if data is None:
        log.warning("WFIGS/NIFC failed; trying CAL FIRE FRAP")
        data, source_url = try_calfire()
        used_source = source_url
    if data is None:
        log.error("All fire perimeter sources failed")
        return 1

    gdf = gpd.GeoDataFrame.from_features(data["features"], crs=WGS84)
    log.info("Loaded %d features, columns=%s", len(gdf), list(gdf.columns)[:20])

    # If multiple, dissolve to a single Kincade perimeter (largest area)
    gdf = gdf[~gdf.geometry.isna()].copy()
    gdf["_area"] = gdf.to_crs("EPSG:26910").geometry.area
    gdf = gdf.sort_values("_area", ascending=False)

    gpkg = OUT / "kincade_perimeter.gpkg"
    geojson = OUT / "kincade_perimeter.geojson"
    gdf.drop(columns=["_area"]).to_file(gpkg, driver="GPKG", layer="kincade_perimeter")
    gdf.drop(columns=["_area"]).to_file(geojson, driver="GeoJSON")

    # Compute summary attributes
    diss = gdf.dissolve().to_crs("EPSG:26910")
    acres = float(diss.geometry.area.iloc[0]) / 4046.8564224
    bounds_wgs = gdf.total_bounds.tolist()
    # find a date-like and acres field
    props = gdf.iloc[0].drop(labels=["geometry", "_area"], errors="ignore").to_dict()
    date_fields = {k: v for k, v in props.items() if any(t in k.lower() for t in ["date", "ignit", "discover", "fired", "alarm"])}
    acre_fields = {k: v for k, v in props.items() if "acre" in k.lower() or "gisacres" in k.lower()}

    summary = {
        "source_url": used_source,
        "n_features": int(len(gdf)),
        "computed_acres_utm10": round(acres, 1),
        "reported_acre_fields": acre_fields,
        "candidate_date_fields": {k: str(v) for k, v in date_fields.items()},
        "bounds_wgs84_minx_miny_maxx_maxy": bounds_wgs,
        "columns": list(gdf.columns),
    }
    save_json(summary, OUT / "kincade_perimeter_summary.json")
    log.info("Summary: acres~%.0f bounds=%s", acres, bounds_wgs)
    log.info("Date fields: %s", date_fields)
    log.info("Acre fields: %s", acre_fields)

    append_manifest([
        manifest_row("fire_perimeter_gpkg", gpkg, used_source, notes="Kincade 2019 perimeter"),
        manifest_row("fire_perimeter_geojson", geojson, used_source, notes="Kincade 2019 perimeter"),
        manifest_row("fire_perimeter_summary", OUT / "kincade_perimeter_summary.json", used_source),
    ])
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
