"""Extract vineyard field polygons from DWR 2019 Statewide Crop Mapping.

The live MapServer/FeatureServer endpoints are frequently offline. We first try
the FeatureServer; if unavailable we download the official 2019 statewide
Geodatabase from data.cnra.ca.gov and extract vineyards locally.
Vineyard class in this dataset: CLASS2 = 'V'.
Clips to Kincade perimeter + 5 km buffer, assigns vineyard_field_id.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, WGS84, append_manifest, get_logger, manifest_row, save_json  # noqa: E402

log = get_logger("03_vineyards")
OUT = DATA_RAW / "vineyards"
OUT.mkdir(parents=True, exist_ok=True)
SRC = OUT / "_source"
SRC.mkdir(parents=True, exist_ok=True)

FS = "https://gis.water.ca.gov/arcgis/rest/services/Planning/i15_Crop_Mapping_2019/FeatureServer/0"
GDB_ZIP_URL = (
    "https://data.cnra.ca.gov/dataset/6c3d65e3-35bb-49e1-a51e-49d5a2cf09a9/"
    "resource/519a6ac2-77f5-4da6-85f3-ada74d7eddee/download/i15_crop_mapping_2019_gdb.zip"
)
PERIM = DATA_RAW / "fire" / "kincade_perimeter.gpkg"
BUFFER_M = 5000


def query_page(bbox, where, offset, page=1000):
    params = {
        "where": where,
        "geometry": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "returnGeometry": "true",
        "resultOffset": offset,
        "resultRecordCount": page,
    }
    r = requests.get(FS + "/query", params=params, timeout=180)
    r.raise_for_status()
    return r.json().get("features", [])


def fetch_all(bbox, where):
    feats, offset, page = [], 0, 1000
    while True:
        batch = query_page(bbox, where, offset, page)
        feats.extend(batch)
        log.info("WHERE %s offset=%d -> %d (total %d)", where[:30], offset, len(batch), len(feats))
        if len(batch) < page:
            break
        offset += page
    return feats


def from_featureserver(bbox):
    for wc in ["CLASS2='V'", "UPPER(CLASS2)='V'"]:
        try:
            feats = fetch_all(bbox, wc)
            if feats:
                gdf = gpd.GeoDataFrame.from_features(feats, crs=WGS84).to_crs("EPSG:26910")
                return gdf, wc, FS
        except Exception as e:  # noqa: BLE001
            log.warning("FeatureServer WHERE %s failed: %s", wc, e)
    return None, "", ""


def download_gdb() -> Path:
    zip_path = SRC / "i15_crop_mapping_2019_gdb.zip"
    if not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
        log.info("Downloading DWR 2019 crop mapping GDB (~86 MB)...")
        with requests.get(GDB_ZIP_URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        log.info("Downloaded %d bytes", zip_path.stat().st_size)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(SRC)
    gdbs = list(SRC.glob("**/*.gdb"))
    if not gdbs:
        raise RuntimeError("No .gdb found after extraction")
    log.info("Extracted GDB: %s", gdbs[0])
    return gdbs[0]


def from_gdb(bbox_wgs):
    gdb = download_gdb()
    import pyogrio

    layers = pyogrio.list_layers(gdb)
    log.info("GDB layers: %s", layers.tolist() if hasattr(layers, "tolist") else layers)
    layer_name = layers[0][0]
    info = pyogrio.read_info(gdb, layer=layer_name)
    src_crs = info.get("crs")
    log.info("Layer %s CRS=%s fields=%s", layer_name, src_crs, list(info.get("fields", []))[:20])
    # transform AOI bbox to the dataset CRS for a fast bbox read
    aoi_wgs = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries.from_wkt([
            f"POLYGON(({bbox_wgs[0]} {bbox_wgs[1]},{bbox_wgs[2]} {bbox_wgs[1]},"
            f"{bbox_wgs[2]} {bbox_wgs[3]},{bbox_wgs[0]} {bbox_wgs[3]},{bbox_wgs[0]} {bbox_wgs[1]}))"
        ]),
        crs=WGS84,
    )
    aoi_src = aoi_wgs.to_crs(src_crs)
    b = aoi_src.total_bounds
    # SYMB_CLASS holds a clean vineyard code 'V' (CLASS2 values are space-padded).
    # Combining the attribute filter with a bbox keeps the read fast and avoids
    # loading very large statewide multipolygons.
    vy = pyogrio.read_dataframe(
        gdb, layer=layer_name, where="SYMB_CLASS = 'V'", bbox=tuple(b),
    )
    log.info("Read %d vineyard polys within AOI bbox from GDB", len(vy))
    # trim space-padded code columns for tidiness
    for c in vy.columns:
        if vy[c].dtype == object:
            try:
                vy[c] = vy[c].str.strip()
            except Exception:  # noqa: BLE001
                pass
    return vy.to_crs("EPSG:26910"), "SYMB_CLASS='V'", GDB_ZIP_URL


def main() -> int:
    perim = gpd.read_file(PERIM).to_crs("EPSG:26910")
    buffered = perim.buffer(BUFFER_M)
    buf_gdf = gpd.GeoDataFrame(geometry=buffered, crs="EPSG:26910")
    bbox = buf_gdf.to_crs(WGS84).total_bounds.tolist()
    log.info("AOI bbox (perimeter+5km) WGS84: %s", bbox)

    gdf, used_where, source = from_featureserver(bbox)
    if gdf is None or gdf.empty:
        log.warning("FeatureServer unavailable; falling back to official GDB download")
        gdf, used_where, source = from_gdb(bbox)

    if gdf is None or gdf.empty:
        log.error("No vineyard features obtained")
        save_json({"status": "no_features", "bbox": bbox}, OUT / "vineyards_summary.json")
        return 1

    # Precise clip to buffered perimeter
    clip_union = buf_gdf.union_all() if hasattr(buf_gdf, "union_all") else buf_gdf.unary_union
    gdf = gdf[gdf.intersects(clip_union)].copy()
    gdf["geometry"] = gdf.geometry.intersection(clip_union)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()

    gdf = gdf.reset_index(drop=True)
    gdf["vineyard_field_id"] = ["VYD_%05d" % i for i in range(1, len(gdf) + 1)]
    gdf["area_ha"] = gdf.geometry.area / 10000.0

    gpkg = OUT / "kincade_vineyards.gpkg"
    geojson = OUT / "kincade_vineyards.geojson"
    gdf.to_file(gpkg, driver="GPKG", layer="vineyards")
    gdf.to_crs(WGS84).to_file(geojson, driver="GeoJSON")

    summary = {
        "source_url": source,
        "where": used_where,
        "buffer_m": BUFFER_M,
        "n_fields": int(len(gdf)),
        "total_area_ha": round(float(gdf["area_ha"].sum()), 1),
        "crs": "EPSG:26910",
        "columns": list(gdf.columns),
        "aoi_bbox_wgs84": bbox,
    }
    save_json(summary, OUT / "vineyards_summary.json")
    log.info("Vineyards: %d fields, %.1f ha", len(gdf), gdf["area_ha"].sum())

    append_manifest([
        manifest_row("vineyards_gpkg", gpkg, source, notes="DWR 2019 vineyards clipped to Kincade+5km"),
        manifest_row("vineyards_geojson", geojson, source, notes="DWR 2019 vineyards clipped to Kincade+5km"),
        manifest_row("vineyards_summary", OUT / "vineyards_summary.json", source),
    ])
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
