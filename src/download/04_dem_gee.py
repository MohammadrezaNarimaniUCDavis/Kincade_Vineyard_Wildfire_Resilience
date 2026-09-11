"""Export USGS 3DEP 10 m DEM for the Kincade study area via GEE -> GeoTIFF."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_RAW, append_manifest, get_logger, manifest_row, save_json  # noqa: E402
from gee_utils import aoi_from_perimeter, download_tiled, init_ee  # noqa: E402

log = get_logger("04_dem_gee")
OUT = DATA_RAW / "gee"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ee = init_ee()
    region, bounds_utm = aoi_from_perimeter(buffer_m=5000)
    log.info("AOI UTM bounds: %s", bounds_utm)

    dem = ee.Image("USGS/3DEP/10m").select("elevation").clip(region)
    out = OUT / "dem_3dep_10m.tif"
    download_tiled(dem, bounds_utm, scale=10, out_path=out, crs="EPSG:26910", logger=log)

    append_manifest([
        manifest_row("dem_3dep_10m", out, "GEE USGS/3DEP/10m",
                     notes="10 m DEM, EPSG:26910, Kincade+5km AOI"),
    ])
    summary = {"asset": "USGS/3DEP/10m", "scale_m": 10, "crs": "EPSG:26910",
               "bounds_utm": bounds_utm, "path": str(out)}
    save_json(summary, OUT / "dem_summary.json")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
