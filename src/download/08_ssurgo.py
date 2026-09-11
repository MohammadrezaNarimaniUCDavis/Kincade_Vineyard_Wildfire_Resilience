"""SSURGO soils for the Kincade AOI via USDA NRCS Soil Data Access (SDA).

Spatial mapunit polygons (mupolygon) intersecting the perimeter+5km bbox are
retrieved as WKT, then joined to aggregated attributes (muaggatt) and mapunit
names. Saves GeoPackage + GeoJSON to data/raw/soils/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely import wkt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, WGS84, append_manifest, get_logger, manifest_row, save_json  # noqa: E402

log = get_logger("08_ssurgo")
OUT = DATA_RAW / "soils"
OUT.mkdir(parents=True, exist_ok=True)

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
PERIM = DATA_RAW / "fire" / "kincade_perimeter.gpkg"
BUFFER_M = 5000


def sda_query(sql: str) -> pd.DataFrame:
    body = {"query": sql, "format": "JSON+COLUMNNAME"}
    r = requests.post(SDA_URL, json=body, timeout=300)
    r.raise_for_status()
    js = r.json()
    if "Table" not in js:
        raise RuntimeError(f"SDA returned no Table: {str(js)[:300]}")
    table = js["Table"]
    cols = table[0]
    return pd.DataFrame(table[1:], columns=cols)


def main() -> int:
    perim = gpd.read_file(PERIM).to_crs("EPSG:26910")
    minx, miny, maxx, maxy = perim.buffer(BUFFER_M).total_bounds
    box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"
    ], crs="EPSG:26910").to_crs(WGS84)
    b = box.total_bounds
    aoi_wkt = (
        f"POLYGON(({b[0]} {b[1]},{b[2]} {b[1]},{b[2]} {b[3]},{b[0]} {b[3]},{b[0]} {b[1]}))"
    )
    log.info("AOI bbox WGS84: %s", b.tolist())

    # 1) Spatial: mapunit polygons intersecting the AOI bbox
    spatial_sql = (
        "SELECT mukey, mupolygonkey, mupolygongeo.STAsText() AS geom "
        "FROM mupolygon "
        f"WHERE mupolygongeo.STIntersects(geometry::STGeomFromText('{aoi_wkt}', 4326)) = 1"
    )
    log.info("Querying SDA mupolygon (spatial)...")
    poly_df = sda_query(spatial_sql)
    log.info("Retrieved %d mapunit polygons", len(poly_df))
    if poly_df.empty:
        save_json({"status": "no_polygons", "bbox": b.tolist()}, OUT / "ssurgo_summary.json")
        return 1

    poly_df["geometry"] = poly_df["geom"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(poly_df.drop(columns=["geom"]), geometry="geometry", crs=WGS84)

    # 2) Attributes: muaggatt (aggregated) + mapunit name for these mukeys
    mukeys = sorted(set(gdf["mukey"].astype(str)))
    mukey_list = ",".join(f"'{m}'" for m in mukeys)
    attr_sql = (
        "SELECT m.mukey, mu.muname, m.drclassdcd AS drainage_class, "
        "m.aws0100wta AS awc_0_100cm, m.aws0150wta AS awc_0_150cm, "
        "m.slopegraddcp AS slope_pct, m.hydgrpdcd AS hydrologic_group, "
        "m.flodfreqdcd AS flooding_freq, m.brockdepmin AS bedrock_depth_min "
        "FROM muaggatt m INNER JOIN mapunit mu ON m.mukey = mu.mukey "
        f"WHERE m.mukey IN ({mukey_list})"
    )
    log.info("Querying SDA muaggatt (attributes) for %d mukeys...", len(mukeys))
    attr_df = sda_query(attr_sql)
    log.info("Retrieved %d attribute rows", len(attr_df))

    gdf["mukey"] = gdf["mukey"].astype(str)
    attr_df["mukey"] = attr_df["mukey"].astype(str)
    gdf = gdf.merge(attr_df, on="mukey", how="left")

    # Clip precisely to buffered perimeter
    buf = gpd.GeoDataFrame(geometry=perim.buffer(BUFFER_M), crs="EPSG:26910").to_crs(WGS84)
    union = buf.union_all() if hasattr(buf, "union_all") else buf.unary_union
    gdf = gdf[gdf.intersects(union)].copy()

    gpkg = OUT / "kincade_ssurgo.gpkg"
    geojson = OUT / "kincade_ssurgo.geojson"
    gdf.to_file(gpkg, driver="GPKG", layer="ssurgo")
    gdf.to_file(geojson, driver="GeoJSON")

    summary = {
        "source": SDA_URL,
        "survey": "USDA NRCS SSURGO via Soil Data Access",
        "n_polygons": int(len(gdf)),
        "n_mapunits": int(gdf["mukey"].nunique()),
        "attributes": [c for c in gdf.columns if c != "geometry"],
        "aoi_bbox_wgs84": b.tolist(),
    }
    save_json(summary, OUT / "ssurgo_summary.json")
    log.info("SSURGO: %d polygons, %d mapunits", len(gdf), gdf["mukey"].nunique())

    append_manifest([
        manifest_row("ssurgo_gpkg", gpkg, SDA_URL, notes="SSURGO mapunits Kincade+5km"),
        manifest_row("ssurgo_geojson", geojson, SDA_URL, notes="SSURGO mapunits Kincade+5km"),
        manifest_row("ssurgo_summary", OUT / "ssurgo_summary.json", SDA_URL),
    ])
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
