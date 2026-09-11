"""Compute Sentinel-2 and Landsat-8 burn severity (NBR, dNBR, RdNBR) for Kincade.

Sentinel-2 SR (harmonized): pre/post NBR, dNBR, RdNBR at 20 m.
Landsat-8 C2 L2: pre/post NBR, dNBR at 30 m (independent comparison).
Windows:
  prefire  2019-09-01 .. 2019-10-22
  postfire 2019-11-10 .. 2019-12-15
Outputs GeoTIFF to data/raw/gee/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DATA_RAW,
    POSTFIRE,
    PREFIRE,
    append_manifest,
    get_logger,
    manifest_row,
    save_json,
)
from gee_utils import aoi_from_perimeter, download_tiled, init_ee  # noqa: E402

log = get_logger("05_burn_severity_gee")
OUT = DATA_RAW / "gee"
OUT.mkdir(parents=True, exist_ok=True)


def s2_masked(ee, region, start, end):
    def mask(img):
        scl = img.select("SCL")
        # keep vegetation(4), bare(5), water(6), unclassified(7); drop clouds/shadow/cirrus
        good = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        return img.updateMask(good).divide(10000)

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
        .map(mask)
    )
    return col


def s2_nbr(col):
    # NBR = (B8 - B12) / (B8 + B12)
    return col.map(lambda i: i.normalizedDifference(["B8", "B12"]).rename("NBR")).median()


def landsat_masked(ee, region, start, end):
    def mask(img):
        qa = img.select("QA_PIXEL")
        # bits 3 (cloud) and 4 (cloud shadow)
        cloud = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        optical = img.select("SR_B.").multiply(0.0000275).add(-0.2)
        return optical.updateMask(cloud).copyProperties(img, ["system:time_start"])

    col = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUD_COVER", 60))
        .map(mask)
    )
    return col


def landsat_nbr(col):
    # NBR = (SR_B5 - SR_B7) / (SR_B5 + SR_B7)
    return col.map(lambda i: i.normalizedDifference(["SR_B5", "SR_B7"]).rename("NBR")).median()


def main() -> int:
    ee = init_ee()
    region, bounds_utm = aoi_from_perimeter(buffer_m=5000)
    log.info("AOI UTM bounds: %s", bounds_utm)

    results = {}

    # ---------- Sentinel-2 ----------
    try:
        s2_pre = s2_masked(ee, region, *PREFIRE)
        s2_post = s2_masked(ee, region, *POSTFIRE)
        log.info("S2 pre images: %s, post images: %s",
                 s2_pre.size().getInfo(), s2_post.size().getInfo())
        nbr_pre = s2_nbr(s2_pre)
        nbr_post = s2_nbr(s2_post)
        dnbr = nbr_pre.subtract(nbr_post).rename("dNBR")
        # RdNBR = dNBR / sqrt(abs(preNBR)); guard small denom
        denom = nbr_pre.abs().sqrt().max(0.001)
        rdnbr = dnbr.divide(denom).rename("RdNBR")
        s2_stack = (
            nbr_pre.rename("NBR_pre")
            .addBands(nbr_post.rename("NBR_post"))
            .addBands(dnbr)
            .addBands(rdnbr)
            .toFloat()
            .clip(region)
        )
        out_s2 = OUT / "s2_burn_severity.tif"
        download_tiled(s2_stack, bounds_utm, scale=20, out_path=out_s2, crs="EPSG:26910",
                       band_names=["NBR_pre", "NBR_post", "dNBR", "RdNBR"], logger=log)
        append_manifest([
            manifest_row("s2_burn_severity", out_s2, "GEE COPERNICUS/S2_SR_HARMONIZED",
                         notes="Bands: NBR_pre,NBR_post,dNBR,RdNBR @20m"),
        ])
        results["sentinel2"] = {"path": str(out_s2), "bands": ["NBR_pre", "NBR_post", "dNBR", "RdNBR"],
                                 "scale_m": 20}
    except Exception as e:  # noqa: BLE001
        log.exception("Sentinel-2 burn severity failed: %s", e)
        results["sentinel2"] = {"error": str(e)}

    # ---------- Landsat-8 ----------
    try:
        l8_pre = landsat_masked(ee, region, *PREFIRE)
        l8_post = landsat_masked(ee, region, *POSTFIRE)
        log.info("L8 pre images: %s, post images: %s",
                 l8_pre.size().getInfo(), l8_post.size().getInfo())
        lnbr_pre = landsat_nbr(l8_pre)
        lnbr_post = landsat_nbr(l8_post)
        ldnbr = lnbr_pre.subtract(lnbr_post).rename("dNBR")
        l8_stack = (
            lnbr_pre.rename("NBR_pre")
            .addBands(lnbr_post.rename("NBR_post"))
            .addBands(ldnbr)
            .toFloat()
            .clip(region)
        )
        out_l8 = OUT / "landsat8_burn_severity.tif"
        download_tiled(l8_stack, bounds_utm, scale=30, out_path=out_l8, crs="EPSG:26910",
                       band_names=["NBR_pre", "NBR_post", "dNBR"], logger=log)
        append_manifest([
            manifest_row("landsat8_burn_severity", out_l8, "GEE LANDSAT/LC08/C02/T1_L2",
                         notes="Bands: NBR_pre,NBR_post,dNBR @30m"),
        ])
        results["landsat8"] = {"path": str(out_l8), "bands": ["NBR_pre", "NBR_post", "dNBR"], "scale_m": 30}
    except Exception as e:  # noqa: BLE001
        log.exception("Landsat-8 burn severity failed: %s", e)
        results["landsat8"] = {"error": str(e)}

    results["windows"] = {"prefire": PREFIRE, "postfire": POSTFIRE}
    save_json(results, OUT / "burn_severity_summary.json")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
