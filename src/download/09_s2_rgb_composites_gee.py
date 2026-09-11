"""Export Sentinel-2 true-color (B4/B3/B2) and SWIR false-color (B12/B11/B4).

Products (data/raw/gee/):
  s2_prefire_rgb.tif / s2_prefire_swir.tif
  s2_postfire_rgb.tif / s2_postfire_swir.tif
  s2_activefire_rgb_YYYYMMDD.tif / s2_activefire_swir_YYYYMMDD.tif
  s2_activefire_scene.json  — selected during-fire scene metadata

Run:  conda run -n gee python src/download/09_s2_rgb_composites_gee.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import ee

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DATA_RAW, EVENT_WINDOW, PREFIRE, POSTFIRE,
    append_manifest, get_logger, manifest_row, save_json,
)
from gee_utils import aoi_from_perimeter, download_tiled, init_ee  # noqa: E402

log = get_logger("s2_rgb")
OUT = DATA_RAW / "gee"

S2 = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD = "COPERNICUS/S2_CLOUD_PROBABILITY"
CLOUD_THR = 40
MAX_ACTIVE_CLOUD = 85.0

RGB_VIS = dict(bands=["R", "G", "B"], min=0.02, max=0.35, gamma=1.0)
SWIR_VIS = dict(bands=["SWIR2", "SWIR1", "Red"], min=0.0, max=0.35, gamma=1.0)


def s2_masked(region, start: str, end: str, bands: list[str]):
    s2 = (
        ee.ImageCollection(S2)
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 90))
    )
    prob = ee.ImageCollection(S2_CLOUD).filterBounds(region).filterDate(start, end)
    joined = ee.Join.saveFirst("cloud_prob").apply(
        primary=s2,
        secondary=prob,
        condition=ee.Filter.equals(leftField="system:index", rightField="system:index"),
    )

    def mask(img):
        img = ee.Image(img)
        cp = ee.Image(img.get("cloud_prob")).select("probability")
        scl = img.select("SCL")
        good = (
            cp.lt(CLOUD_THR)
            .And(scl.neq(3))
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10))
            .And(scl.neq(11))
        )
        return img.updateMask(good).divide(10000).select(bands)

    return ee.ImageCollection(joined).map(mask)


def list_active_scenes(region) -> list[dict]:
    start, end = EVENT_WINDOW
    coll = (
        ee.ImageCollection(S2)
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 95))
        .sort("system:time_start")
    )
    info = coll.reduceColumns(
        ee.Reducer.toList(3),
        ["system:index", "system:time_start", "CLOUDY_PIXEL_PERCENTAGE"],
    ).get("list").getInfo()
    rows = []
    for sid, t_ms, cloud in info:
        if cloud > MAX_ACTIVE_CLOUD:
            continue
        day = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y%m%d")
        rows.append({"id": sid, "date": day, "cloud": float(cloud), "t_ms": t_ms})
    return rows


def group_scenes_by_date(scenes: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in scenes:
        out.setdefault(s["date"], []).append(s)
    return out


def pick_active_day(scenes: list[dict]) -> dict | None:
    """Pick event-window date with best tile coverage and low cloud."""
    if not scenes:
        return None
    by_date = group_scenes_by_date(scenes)
    ranked: list[tuple] = []
    for date, group in by_date.items():
        mean_cloud = sum(s["cloud"] for s in group) / len(group)
        date_rank = {d: i for i, d in enumerate(
            ("20191027", "20191028", "20191025", "20191023", "20191030", "20191031")
        )}.get(date, 99)
        ranked.append((date_rank, -len(group), mean_cloud, date, group))
    ranked.sort()
    _, _, mean_cloud, date, group = ranked[0]
    return {
        "date": date,
        "ids": [s["id"] for s in group],
        "cloud": mean_cloud,
        "n_tiles": len(group),
    }


def export_window(region, bounds, tag: str, start: str, end: str, force: bool = False):
    rgb = (
        s2_masked(region, start, end, ["B4", "B3", "B2"])
        .median()
        .rename(["R", "G", "B"])
        .visualize(**RGB_VIS)
    )
    swir = (
        s2_masked(region, start, end, ["B12", "B11", "B4"])
        .median()
        .rename(["SWIR2", "SWIR1", "Red"])
        .visualize(**SWIR_VIS)
    )
    for img, name, note in (
        (rgb, f"s2_{tag}_rgb", "B4/B3/B2 median true color"),
        (swir, f"s2_{tag}_swir", "B12/B11/B4 median SWIR false color"),
    ):
        fp = OUT / f"{name}.tif"
        if fp.exists() and not force:
            log.info("cached %s", fp.name)
            continue
        download_tiled(img, bounds, 10, fp, band_names=["R", "G", "B"] if "rgb" in name else ["SWIR2", "SWIR1", "Red"], logger=log)
        append_manifest([manifest_row(
            f"D09_{tag}_{'rgb' if 'rgb' in name else 'swir'}", fp,
            "Copernicus S2 SR Harmonized via GEE", f"{start}..{end}", note,
        )])


def export_active(region, bounds, day: dict, force: bool = True):
    ids = day["ids"]
    base = (
        ee.ImageCollection(S2)
        .filter(ee.Filter.inList("system:index", ids))
        .mosaic()
        .divide(10000)
    )
    rgb = base.select(["B4", "B3", "B2"]).rename(["R", "G", "B"]).visualize(**RGB_VIS)
    swir = base.select(["B12", "B11", "B4"]).rename(["SWIR2", "SWIR1", "Red"]).visualize(**SWIR_VIS)
    d = day["date"]
    log.info(
        "active mosaic %s: %d granules, mean cloud=%.1f%% (unmasked, smoke retained)",
        d, day["n_tiles"], day["cloud"],
    )
    for img, kind in ((rgb, "rgb"), (swir, "swir")):
        fp = OUT / f"s2_activefire_{kind}_{d}.tif"
        if fp.exists() and not force:
            continue
        bands = ["R", "G", "B"] if kind == "rgb" else ["SWIR2", "SWIR1", "Red"]
        download_tiled(img, bounds, 10, fp, band_names=bands, logger=log)
        append_manifest([manifest_row(
            f"D09_active_{kind}", fp, "Copernicus S2 SR Harmonized via GEE", d,
            f"Mosaic {day['n_tiles']} granules; smoke retained",
        )])
    save_json({**day, "note": "unmasked active-fire mosaic"}, OUT / "s2_activefire_scene.json")
    for kind in ("rgb", "swir"):
        src = OUT / f"s2_activefire_{kind}_{d}.tif"
        if src.exists():
            shutil.copy2(src, OUT / f"s2_duringfire_{kind}.tif")


def main():
    init_ee()
    region, bounds = aoi_from_perimeter(buffer_m=800)
    OUT.mkdir(parents=True, exist_ok=True)

    export_window(region, bounds, "prefire", *PREFIRE, force=False)
    export_window(region, bounds, "postfire", *POSTFIRE, force=False)

    scenes = list_active_scenes(region)
    log.info("Found %d usable during-fire S2 scenes", len(scenes))
    pick = pick_active_day(scenes)
    if pick is None:
        log.warning("No during-fire S2 scene under cloud threshold — active panels skipped")
    else:
        log.info("Selected active day: %s (%d granules, mean cloud %.1f%%)",
                 pick["date"], pick["n_tiles"], pick["cloud"])
        export_active(region, bounds, pick, force=True)

    save_json({"prefire": PREFIRE, "postfire": POSTFIRE, "event": EVENT_WINDOW,
               "scenes": scenes, "selected": pick}, OUT / "s2_rgb_export_meta.json")
    log.info("S2 RGB/SWIR export complete")


if __name__ == "__main__":
    main()
