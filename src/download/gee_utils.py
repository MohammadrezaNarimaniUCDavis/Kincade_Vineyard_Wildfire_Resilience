"""GEE helpers: initialize EE and download images locally as GeoTIFF.

Large images are tiled through ee.Image.getDownloadURL (GEO_TIFF) and merged
with rasterio, so no Google Drive export is required.
"""
from __future__ import annotations

import io
import math
import sys
import zipfile
from pathlib import Path

import ee
import numpy as np
import rasterio
import requests
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, get_logger  # noqa: E402


def init_ee():
    try:
        ee.Initialize()
    except Exception:  # noqa: BLE001
        ee.Initialize(opt_url="https://earthengine-highvolume.googleapis.com")
    return ee


def aoi_from_perimeter(buffer_m: float = 5000):
    """Return (ee.Geometry region in EPSG:26910 coords via 4326, bounds_utm).

    We buffer the Kincade perimeter bbox and return an ee.Geometry rectangle in
    EPSG:4326 plus the UTM (EPSG:26910) bounds used as the export grid.
    """
    import geopandas as gpd

    perim = gpd.read_file(DATA_RAW / "fire" / "kincade_perimeter.gpkg").to_crs("EPSG:26910")
    minx, miny, maxx, maxy = perim.total_bounds
    minx -= buffer_m
    miny -= buffer_m
    maxx += buffer_m
    maxy += buffer_m
    bounds_utm = (minx, miny, maxx, maxy)
    # Convert to 4326 for ee.Geometry.Rectangle
    box_utm = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries.from_wkt([
            f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"
        ]),
        crs="EPSG:26910",
    )
    b4326 = box_utm.to_crs("EPSG:4326").total_bounds
    region = ee.Geometry.Rectangle([b4326[0], b4326[1], b4326[2], b4326[3]], proj="EPSG:4326", geodesic=False)
    return region, bounds_utm


def _fetch_tile_bytes(image, rect, scale, crs):
    url = image.getDownloadURL({"scale": scale, "crs": crs, "region": rect, "format": "GEO_TIFF"})
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    content = r.content
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            name = [n for n in z.namelist() if n.lower().endswith(".tif")][0]
            return z.read(name)
    return content


def download_tiled(image, bounds_utm, scale, out_path: Path, crs="EPSG:26910",
                   max_px=2048, nodata=-9999.0, band_names=None, logger=None):
    """Download an ee.Image over a UTM bbox to a single GeoTIFF via tiling.

    Tiles are assembled deterministically into a preallocated array (no
    rasterio.merge) so masked/float rasters composite correctly. The output
    grid is anchored to bounds_utm/scale; each tile is fetched over its exact
    pixel window and slotted into place.
    """
    log = logger or get_logger("gee_download")
    minx, miny, maxx, maxy = bounds_utm
    width = int(round((maxx - minx) / scale))
    height = int(round((maxy - miny) / scale))
    nx = int(math.ceil(width / max_px))
    ny = int(math.ceil(height / max_px))
    tile_w = int(math.ceil(width / nx))
    tile_h = int(math.ceil(height / ny))
    log.info("Downloading %s: %dx%d px @ %dm -> %dx%d tiles", out_path.name, width, height, scale, nx, ny)

    transform = from_origin(minx, maxy, scale, scale)
    out_arr = None
    count = None
    descriptions = band_names

    tile_no = 0
    for j in range(ny):
        for i in range(nx):
            tile_no += 1
            col0 = i * tile_w
            row0 = j * tile_h
            col1 = min(col0 + tile_w, width)
            row1 = min(row0 + tile_h, height)
            tx0 = minx + col0 * scale
            tx1 = minx + col1 * scale
            ty1 = maxy - row0 * scale
            ty0 = maxy - row1 * scale
            rect = ee.Geometry.Rectangle([tx0, ty0, tx1, ty1], proj=crs, geodesic=False)
            data = _fetch_tile_bytes(image, rect, scale, crs)
            with rasterio.MemoryFile(data) as mf, mf.open() as src:
                arr = src.read().astype("float32")
                if descriptions is None:
                    descriptions = list(src.descriptions)
                src_nodata = src.nodata
            if out_arr is None:
                count = arr.shape[0]
                out_arr = np.full((count, height, width), nodata, dtype="float32")
            # normalise EE nodata / non-finite to our nodata
            arr = np.where(np.isfinite(arr), arr, nodata)
            if src_nodata is not None and np.isfinite(src_nodata):
                arr = np.where(arr == np.float32(src_nodata), nodata, arr)
            h = min(arr.shape[1], row1 - row0)
            w = min(arr.shape[2], col1 - col0)
            out_arr[:, row0:row0 + h, col0:col0 + w] = arr[:, :h, :w]
            log.info("  tile %d/%d done (%d bytes, tile px %dx%d)", tile_no, nx * ny, len(data), w, h)

    meta = {
        "driver": "GTiff", "height": height, "width": width, "count": count,
        "dtype": "float32", "crs": crs, "transform": transform,
        "nodata": nodata, "compress": "deflate",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(out_arr)
        if descriptions and all(descriptions):
            dst.descriptions = tuple(descriptions[:count])
    log.info("Wrote %s (%d bytes)", out_path, out_path.stat().st_size)
    return out_path
