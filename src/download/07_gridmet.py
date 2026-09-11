"""gridMET daily fire-weather for the Kincade event window (Oct 23 - Nov 6 2019).

Source: GEE IDAHO_EPSCOR/GRIDMET (~4 km daily).
Outputs:
  - Point time series CSV at the Geyserville study point (all key variables).
  - AOI-mean daily time series CSV.
  - Multiband GeoTIFF of daily max wind speed (vs) over the AOI (band per day).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DATA_RAW,
    EVENT_WINDOW,
    STUDY_POINT,
    append_manifest,
    get_logger,
    manifest_row,
    save_json,
)
from gee_utils import aoi_from_perimeter, download_tiled, init_ee  # noqa: E402

log = get_logger("07_gridmet")
OUT = DATA_RAW / "weather"
OUT.mkdir(parents=True, exist_ok=True)

VARS = ["tmmn", "tmmx", "rmin", "rmax", "vs", "th", "pr", "sph", "vpd", "erc", "bi", "fm100", "fm1000", "etr"]
# Event window inclusive of Nov 6; filterDate end is exclusive.
# Lead-in from 10 Oct gives pre-ignition fire-weather context in Figure 06.
WEATHER_START = "2019-10-10"
START, END = WEATHER_START, "2019-11-07"


def main() -> int:
    ee = init_ee()
    region, bounds_utm = aoi_from_perimeter(buffer_m=5000)
    pt = ee.Geometry.Point(list(STUDY_POINT))

    col = (
        ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
        .filterDate(START, END)
        .select(VARS)
    )
    n = col.size().getInfo()
    log.info("gridMET images in window %s..%s: %d", START, END, n)

    # ---- Point time series via getRegion ----
    arr = col.getRegion(pt, scale=4000).getInfo()
    header = arr[0]
    rows = arr[1:]
    pt_csv = OUT / "gridmet_point_geyserville.csv"
    with open(pt_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in sorted(rows, key=lambda x: x[3]):
            w.writerow(r)
    log.info("Wrote point time series (%d days) -> %s", len(rows), pt_csv.name)

    # ---- AOI-mean daily time series ----
    def daily_mean(img):
        stats = img.reduceRegion(ee.Reducer.mean(), region, 4000, maxPixels=1e9)
        return ee.Feature(None, stats.set("date", img.date().format("YYYY-MM-dd")))

    feats = col.map(daily_mean).getInfo()["features"]
    aoi_csv = OUT / "gridmet_aoi_mean_daily.csv"
    keys = ["date"] + VARS
    with open(aoi_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for ft in sorted(feats, key=lambda x: x["properties"].get("date", "")):
            w.writerow({k: ft["properties"].get(k, "") for k in keys})
    log.info("Wrote AOI-mean daily time series -> %s", aoi_csv.name)

    # ---- Daily wind speed (vs) GeoTIFF, band per day ----
    imgs = col.select("vs").toList(n)
    stack = None
    band_names = []
    for i in range(n):
        im = ee.Image(imgs.get(i))
        date = im.date().format("YYYYMMdd").getInfo()
        b = im.rename(f"vs_{date}")
        band_names.append(f"vs_{date}")
        stack = b if stack is None else stack.addBands(b)
    stack = stack.toFloat().clip(region)
    wind_tif = OUT / "gridmet_wind_daily.tif"
    download_tiled(stack, bounds_utm, scale=4000, out_path=wind_tif, crs="EPSG:26910",
                   band_names=band_names, logger=log)

    append_manifest([
        manifest_row("gridmet_point_geyserville", pt_csv, "GEE IDAHO_EPSCOR/GRIDMET",
                     notes="Daily fire-weather at study point, event window"),
        manifest_row("gridmet_aoi_mean_daily", aoi_csv, "GEE IDAHO_EPSCOR/GRIDMET",
                     notes="AOI-mean daily fire-weather, event window"),
        manifest_row("gridmet_wind_daily", wind_tif, "GEE IDAHO_EPSCOR/GRIDMET",
                     notes="Daily max wind speed (vs, m/s) raster stack @4km"),
    ])
    summary = {"vars": VARS, "window": [START, END], "n_days": n,
               "point": STUDY_POINT, "files": [pt_csv.name, aoi_csv.name, wind_tif.name]}
    save_json(summary, OUT / "gridmet_summary.json")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
