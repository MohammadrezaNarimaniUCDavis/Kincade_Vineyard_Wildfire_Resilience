"""Download DINS (Damage Inspection) points for the Kincade fire.

Source: CAL FIRE POSTFIRE_MASTER_DATA_SHARE FeatureServer.
Filters to Kincade incident; falls back to spatial filter by perimeter bbox.
Saves GeoJSON + GeoPackage to data/raw/dins/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, WGS84, append_manifest, get_logger, manifest_row, save_json  # noqa: E402

log = get_logger("02_dins")
OUT = DATA_RAW / "dins"
OUT.mkdir(parents=True, exist_ok=True)

DINS_URL = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0"
PERIM_SUMMARY = DATA_RAW / "fire" / "kincade_perimeter_summary.json"


def query_all(where: str) -> list[dict]:
    """Paginate through ArcGIS query results."""
    feats: list[dict] = []
    offset = 0
    page = 2000
    while True:
        params = {
            "where": where,
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": page,
        }
        r = requests.get(DINS_URL + "/query", params=params, timeout=180)
        r.raise_for_status()
        data = r.json()
        batch = data.get("features", [])
        feats.extend(batch)
        log.info("WHERE %s offset=%d -> %d (total %d)", where[:50], offset, len(batch), len(feats))
        if len(batch) < page:
            break
        offset += page
    return feats


def main() -> int:
    # Discover incident-name field
    where_clauses = [
        "UPPER(INCIDENTNAME) LIKE '%KINCADE%'",
        "UPPER(INCIDENT_NAME) LIKE '%KINCADE%'",
        "UPPER(\"* Incident Name\") LIKE '%KINCADE%'",
        "UPPER(INCIDENTNU) LIKE '%KINCADE%'",
    ]
    feats: list[dict] = []
    used_where = ""
    for wc in where_clauses:
        try:
            feats = query_all(wc)
            if feats:
                used_where = wc
                break
        except Exception as e:  # noqa: BLE001
            log.warning("WHERE %s failed: %s", wc, e)

    if not feats:
        # Fallback: spatial query using perimeter bbox
        log.warning("Name-based query returned nothing; trying spatial bbox filter")
        with open(PERIM_SUMMARY, encoding="utf-8") as f:
            b = json.load(f)["bounds_wgs84_minx_miny_maxx_maxy"]
        params = {
            "geometry": f"{b[0]},{b[1]},{b[2]},{b[3]}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "where": "1=1",
        }
        r = requests.get(DINS_URL + "/query", params=params, timeout=180)
        r.raise_for_status()
        feats = r.json().get("features", [])
        used_where = "spatial bbox (perimeter)"
        log.info("Spatial bbox query -> %d features", len(feats))

    if not feats:
        log.error("No DINS features found for Kincade")
        save_json({"status": "no_features", "where_tried": where_clauses}, OUT / "dins_summary.json")
        return 1

    gdf = gpd.GeoDataFrame.from_features(feats, crs=WGS84)
    log.info("DINS features: %d, columns=%s", len(gdf), list(gdf.columns)[:25])

    gpkg = OUT / "kincade_dins.gpkg"
    geojson = OUT / "kincade_dins.geojson"
    gdf.to_file(gpkg, driver="GPKG", layer="kincade_dins")
    gdf.to_file(geojson, driver="GeoJSON")

    # Damage class breakdown
    dmg_col = next((c for c in gdf.columns if "damage" in c.lower()), None)
    breakdown = gdf[dmg_col].value_counts().to_dict() if dmg_col else {}
    summary = {
        "source_url": DINS_URL,
        "where": used_where,
        "n_points": int(len(gdf)),
        "damage_field": dmg_col,
        "damage_breakdown": {str(k): int(v) for k, v in breakdown.items()},
        "columns": list(gdf.columns),
    }
    save_json(summary, OUT / "dins_summary.json")
    log.info("Damage breakdown: %s", breakdown)

    append_manifest([
        manifest_row("dins_points_gpkg", gpkg, DINS_URL, notes="Kincade DINS damage points"),
        manifest_row("dins_points_geojson", geojson, DINS_URL, notes="Kincade DINS damage points"),
        manifest_row("dins_summary", OUT / "dins_summary.json", DINS_URL),
    ])
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
