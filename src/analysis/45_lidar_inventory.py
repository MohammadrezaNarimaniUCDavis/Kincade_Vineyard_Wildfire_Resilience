"""LiDAR / 3-D structure data inventory for the Kincade AOI (feasibility check).

Queries public catalogs WITHOUT credentials:
  1. OpenTopography catalog API (otCatalog) - lidar point-cloud datasets.
  2. USGS The National Map (TNM) Access API - 3DEP Lidar Point Cloud (LPC),
     1m DEM, and OPR products intersecting the AOI.
  3. GEE - GEDI L2A canopy-height shot counts inside the fire perimeter
     (spaceborne lidar coverage; GEE access is already authenticated).

If a 3DEP DEM cloud-optimized GeoTIFF with a public download URL is found, a
small window is read via /vsicurl and saved (no credentials, no full-tile
download). GEDI direct granule download (NASA Earthdata) is documented as a
credential blocker; GEE-hosted GEDI is usable now.

Outputs
-------
- data/raw/lidar/lidar_inventory.json
- data/raw/lidar/sample_3dep_dem.tif        (only if a public COG tile is found)
- outputs/tables/lidar_inventory_summary.json
- appends rows to outputs/result_registry.csv
Docs updated separately: docs/SENSOR_FEASIBILITY.md, docs/CREDENTIAL_BLOCKERS.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_common import (  # noqa: E402
    CRS,
    RAW,
    TABLES,
    WGS84,
    append_registry,
    get_logger,
)

log = get_logger("45_lidar_inventory")
SCRIPT = "src/analysis/45_lidar_inventory.py"
LIDAR_DIR = RAW / "lidar"
LIDAR_DIR.mkdir(parents=True, exist_ok=True)

# AOI bbox (WGS84), from the fire perimeter + buffer
BBOX = None  # set in main from perimeter


def aoi_bbox():
    fire = gpd.read_file(RAW / "fire" / "kincade_perimeter.gpkg").to_crs(CRS)
    minx, miny, maxx, maxy = fire.geometry.buffer(5000).total_bounds
    box = gpd.GeoSeries.from_wkt(
        [f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"],
        crs=CRS).to_crs(WGS84)
    return list(box.total_bounds)  # [minx,miny,maxx,maxy] lonlat


def query_opentopography(bbox):
    u = "https://portal.opentopography.org/API/otCatalog"
    params = {"productFormat": "PointCloud", "detail": "true", "outputFormat": "json",
              "include_federated": "true", "minx": bbox[0], "miny": bbox[1],
              "maxx": bbox[2], "maxy": bbox[3]}
    out = []
    try:
        r = requests.get(u, params=params, timeout=120)
        log.info("OpenTopography catalog HTTP %s (%d bytes)", r.status_code, len(r.content))
        if r.status_code == 200:
            for e in r.json().get("Datasets", []):
                d = e.get("Dataset", {})
                out.append({
                    "name": d.get("name"),
                    "id": d.get("alternateName") or d.get("identifier", {}).get("value")
                    if isinstance(d.get("identifier"), dict) else d.get("alternateName"),
                    "temporal": d.get("temporalCoverage"),
                    "product_available": d.get("productAvailable"),
                    "host": (d.get("provider") or {}).get("name") if isinstance(d.get("provider"), dict) else None,
                    "doi": d.get("identifier", {}).get("value") if isinstance(d.get("identifier"), dict) else None,
                })
    except Exception as ex:  # noqa: BLE001
        log.warning("OpenTopography query failed: %s", ex)
    return out


def query_tnm(bbox, datasets):
    u = "https://tnmaccess.nationalmap.gov/api/v1/products"
    results = {}
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    for label, ds in datasets.items():
        try:
            params = {"bbox": bbox_str, "datasets": ds, "prodFormats": "", "max": 50, "outputFormat": "JSON"}
            r = requests.get(u, params=params, timeout=120)
            log.info("TNM '%s' HTTP %s (%d bytes)", label, r.status_code, len(r.content))
            items = []
            if r.status_code == 200:
                j = r.json()
                for it in j.get("items", []):
                    items.append({
                        "title": it.get("title"),
                        "pubDate": it.get("publicationDate"),
                        "format": it.get("format"),
                        "sizeInBytes": it.get("sizeInBytes"),
                        "downloadURL": it.get("downloadURL") or (it.get("urls") or {}).get("TIFF"),
                        "boundingBox": it.get("boundingBox"),
                    })
                results[label] = {"total": j.get("total", len(items)), "items": items}
            else:
                results[label] = {"total": 0, "items": [], "http": r.status_code}
        except Exception as ex:  # noqa: BLE001
            log.warning("TNM '%s' query failed: %s", label, ex)
            results[label] = {"error": str(ex)}
    return results


def try_sample_dem(tnm_results):
    """Read a small window from a public 3DEP DEM COG (no credentials)."""
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    for label in ("3dep_1m_dem", "3dep_dem_10m"):
        block = tnm_results.get(label, {})
        for it in block.get("items", []):
            url = it.get("downloadURL")
            if not url or not str(url).lower().endswith(".tif"):
                continue
            try:
                vsi = f"/vsicurl/{url}"
                with rasterio.open(vsi) as src:
                    w = min(512, src.width)
                    h = min(512, src.height)
                    col0 = max(0, src.width // 2 - w // 2)
                    row0 = max(0, src.height // 2 - h // 2)
                    win = Window(col0, row0, w, h)
                    arr = src.read(1, window=win)
                    prof = src.profile.copy()
                    prof.update(width=w, height=h,
                                transform=src.window_transform(win),
                                compress="deflate")
                out = LIDAR_DIR / "sample_3dep_dem.tif"
                with rasterio.open(out, "w", **prof) as dst:
                    dst.write(arr, 1)
                log.info("Downloaded sample 3DEP DEM window %dx%d from %s", w, h, url)
                return {"path": str(out.relative_to(RAW.parent.parent)),
                        "source_url": url, "window_px": [w, h],
                        "valid_min": float(np.nanmin(arr)), "valid_max": float(np.nanmax(arr))}
            except Exception as ex:  # noqa: BLE001
                log.warning("Sample DEM read failed for %s: %s", url, ex)
    return None


def gedi_shot_count():
    """Count GEDI L2A shots inside the fire perimeter via GEE (spaceborne lidar)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "download"))
        from gee_utils import init_ee  # noqa: E402
        import ee
        init_ee()
        fire = gpd.read_file(RAW / "fire" / "kincade_perimeter.gpkg").to_crs(WGS84)
        geom = fire.geometry.unary_union
        region = ee.Geometry(geom.__geo_interface__)
        col = (ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")
               .filterBounds(region)
               .filterDate("2019-04-01", "2023-01-01"))
        n_images = col.size().getInfo()
        # count valid rh98 pixels in perimeter (proxy for shot density)
        if n_images > 0:
            mosaic = col.select("rh98").mosaic()
            cnt = mosaic.reduceRegion(
                reducer=ee.Reducer.count(), geometry=region, scale=25, maxPixels=1e9).get("rh98")
            n_shots = cnt.getInfo()
        else:
            n_shots = 0
        return {"gee_collection": "LARSE/GEDI/GEDI02_A_002_MONTHLY",
                "n_monthly_images_over_perimeter": int(n_images),
                "n_valid_rh98_pixels_in_perimeter_25m": int(n_shots) if n_shots else 0,
                "window": ["2019-04-01", "2023-01-01"]}
    except Exception as ex:  # noqa: BLE001
        log.warning("GEDI GEE query failed: %s", ex)
        return {"error": str(ex)}


def main() -> int:
    bbox = aoi_bbox()
    log.info("AOI bbox (WGS84): %s", bbox)

    ot = query_opentopography(bbox)
    tnm_datasets = {
        "3dep_lpc": "Lidar Point Cloud (LPC)",
        "3dep_1m_dem": "Digital Elevation Model (DEM) 1 meter",
        "3dep_opr": "Original Product Resolution (OPR) Digital Elevation Model (DEM)",
        "3dep_dem_10m": "National Elevation Dataset (NED) 1/3 arc-second",
    }
    tnm = query_tnm(bbox, tnm_datasets)
    sample = try_sample_dem(tnm)
    gedi = gedi_shot_count()

    inventory = {
        "aoi_bbox_wgs84": bbox,
        "query_date": "2026-08-27",
        "opentopography_pointcloud_datasets": ot,
        "usgs_tnm": {k: {"total": v.get("total"),
                         "titles": [i.get("title") for i in v.get("items", [])][:20]}
                     for k, v in tnm.items()},
        "usgs_tnm_full": tnm,
        "sample_dem_download": sample,
        "gedi_gee": gedi,
    }
    with open(LIDAR_DIR / "lidar_inventory.json", "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)

    summary = {
        "n_opentopography_pointcloud_datasets": len(ot),
        "opentopography_datasets": [{"name": d["name"], "temporal": d["temporal"]} for d in ot],
        "tnm_counts": {k: v.get("total") for k, v in tnm.items()},
        "sample_dem_downloaded": bool(sample),
        "gedi": gedi,
    }
    with open(TABLES / "lidar_inventory_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("LiDAR inventory summary: %s", json.dumps(summary))

    reg = [
        {"result_id": "R050", "manuscript_section": "Methods 2.x / Data availability",
         "metric": "n_opentopography_lidar_datasets_AOI", "value": len(ot),
         "unit": "datasets", "uncertainty": "", "dataset": "OpenTopography_catalog",
         "analysis_script": SCRIPT, "model": "catalog_query",
         "source_output": "data/raw/lidar/lidar_inventory.json"},
        {"result_id": "R051", "manuscript_section": "Methods 2.x / Data availability",
         "metric": "n_3DEP_LPC_products_AOI", "value": tnm.get("3dep_lpc", {}).get("total", 0),
         "unit": "products", "uncertainty": "", "dataset": "USGS_TNM_3DEP",
         "analysis_script": SCRIPT, "model": "catalog_query",
         "source_output": "data/raw/lidar/lidar_inventory.json"},
    ]
    if isinstance(gedi, dict) and "n_valid_rh98_pixels_in_perimeter_25m" in gedi:
        reg.append({"result_id": "R052", "manuscript_section": "Methods 2.x / Data availability",
                    "metric": "GEDI_rh98_valid_pixels_in_perimeter",
                    "value": gedi["n_valid_rh98_pixels_in_perimeter_25m"],
                    "unit": "pixels_25m", "uncertainty": "", "dataset": "GEE_LARSE_GEDI_L2A",
                    "analysis_script": SCRIPT, "model": "reduceRegion_count",
                    "source_output": "data/raw/lidar/lidar_inventory.json"})
    append_registry(reg)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
