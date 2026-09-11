"""OpenET monthly ensemble ET for the Kincade study area (growing season 2019).

Primary asset: projects/openet/assets/ensemble/conus/gridmet/monthly/v2_1
Fallback (public GEE catalog): OpenET/ENSEMBLE/CONUS/GRIDMET/MONTHLY/v2_0
Exports a monthly ET GeoTIFF (one band per month) and samples mean ET per
vineyard field to CSV. If neither is accessible, documents the blocker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, append_manifest, get_logger, manifest_row, save_json  # noqa: E402
from gee_utils import aoi_from_perimeter, download_tiled, init_ee  # noqa: E402

log = get_logger("06_openet_gee")
OUT = DATA_RAW / "gee"
OUT.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    "projects/openet/assets/ensemble/conus/gridmet/monthly/v2_1",
    "OpenET/ENSEMBLE/CONUS/GRIDMET/MONTHLY/v2_0",
    "projects/openet/assets/ensemble/conus/gridmet/monthly/v2_0",
]
MONTHS = [f"2019-{m:02d}-01" for m in range(4, 11)]  # Apr..Oct growing season
ET_BAND_CANDIDATES = ["et_ensemble_mad", "et_ensemble_mean", "et"]


def resolve_collection(ee):
    for asset in CANDIDATES:
        try:
            col = ee.ImageCollection(asset).filterDate("2019-01-01", "2020-01-01")
            n = col.size().getInfo()
            log.info("Asset %s -> %d images in 2019", asset, n)
            if n > 0:
                first = ee.Image(col.first())
                bands = first.bandNames().getInfo()
                band = next((b for b in ET_BAND_CANDIDATES if b in bands), bands[0])
                log.info("Using band '%s' (available: %s)", band, bands)
                return col, asset, band
        except Exception as e:  # noqa: BLE001
            log.warning("Asset %s not accessible: %s", asset, e)
    return None, None, None


def main() -> int:
    ee = init_ee()
    region, bounds_utm = aoi_from_perimeter(buffer_m=5000)

    col, asset, band = resolve_collection(ee)
    if col is None:
        msg = "OpenET ensemble asset not accessible with current credentials."
        log.error(msg)
        save_json({"status": "unavailable", "candidates": CANDIDATES, "note": msg},
                  OUT / "openet_summary.json")
        return 2

    # Build a monthly multiband image (one band per growing-season month)
    monthly_imgs = []
    band_names = []
    for start in MONTHS:
        yr, mo, _ = start.split("-")
        end = f"{yr}-{int(mo)+1:02d}-01" if int(mo) < 12 else f"{int(yr)+1}-01-01"
        m_img = col.filterDate(start, end).select(band).mean().rename(f"ET_{yr}_{mo}")
        monthly_imgs.append(m_img)
        band_names.append(f"ET_{yr}_{mo}")

    stack = monthly_imgs[0]
    for im in monthly_imgs[1:]:
        stack = stack.addBands(im)
    stack = stack.toFloat().clip(region)

    out_tif = OUT / "openet_monthly_2019.tif"
    # 7 monthly bands (float32) -> keep tiles small to stay under the 48 MB
    # getDownloadURL request limit.
    if out_tif.exists() and out_tif.stat().st_size > 1_000_000:
        log.info("OpenET GeoTIFF already exists (%d bytes); skipping re-download", out_tif.stat().st_size)
    else:
        download_tiled(stack, bounds_utm, scale=30, out_path=out_tif, crs="EPSG:26910",
                       band_names=band_names, max_px=900, logger=log)
    append_manifest([
        manifest_row("openet_monthly_2019", out_tif, f"GEE {asset}",
                     notes=f"Monthly ET (mm) Apr-Oct 2019, band {band} @30m; bands={band_names}"),
    ])

    # Zonal mean ET per vineyard field
    vy_path = DATA_RAW / "vineyards" / "kincade_vineyards.gpkg"
    sample_csv = OUT / "openet_vineyard_monthly.csv"
    try:
        vy = gpd.read_file(vy_path)[["vineyard_field_id", "geometry"]].to_crs("EPSG:4326")
        # EE rejects 3D coords; drop Z from the DWR MultiPolygon Z geometries.
        try:
            from shapely import force_2d
            vy["geometry"] = vy.geometry.apply(force_2d)
        except Exception:  # noqa: BLE001
            from shapely.ops import transform as shp_transform
            vy["geometry"] = vy.geometry.apply(
                lambda g: shp_transform(lambda *c: c[:2], g))
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry(g.__geo_interface__), {"vineyard_field_id": vid})
            for vid, g in zip(vy["vineyard_field_id"], vy.geometry)
        ]) if len(vy) <= 5000 else None
        if fc is not None:
            sampled = stack.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30)
            rows = sampled.getInfo()["features"]
            import csv
            keys = ["vineyard_field_id"] + band_names
            with open(sample_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                for feat in rows:
                    p = feat["properties"]
                    w.writerow({k: p.get(k, "") for k in keys})
            log.info("Wrote zonal ET for %d vineyard fields", len(rows))
            append_manifest([
                manifest_row("openet_vineyard_monthly", sample_csv, f"GEE {asset}",
                             notes="Zonal mean monthly ET per vineyard field"),
            ])
    except Exception as e:  # noqa: BLE001
        log.exception("Zonal ET sampling failed: %s", e)

    summary = {"asset": asset, "band": band, "months": MONTHS, "bands": band_names,
               "tif": str(out_tif)}
    save_json(summary, OUT / "openet_summary.json")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
