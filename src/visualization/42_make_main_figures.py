"""Publication-quality MAIN figures — Kincade Multisystem Resilience.

Run:  conda run -n gee python src/visualization/42_make_main_figures.py
"""
from __future__ import annotations

import json
import sys
import textwrap
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from visualization import style_kincade as sk  # noqa: E402
from visualization.north_arrows import NORTH_ARROWS  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)

C = sk.COLORS
S = sk.SERIES
W = sk.WORKFLOW
FS = sk.FS
CRS = "EPSG:26910"
CM = 1 / 2.54
DATA = ROOT / "outputs" / "figures" / "data"
TAB = ROOT / "outputs" / "tables"
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

CREATED: list[str] = []
FAILED: list[str] = []

# Shared diverging colormap for dNBR (colorblind-aware, matches palette)
DNBR_CMAP = LinearSegmentedColormap.from_list(
    "kincade_dnbr",
    ["#2166AC", "#F7F7F7", "#B35806", "#8C2D04"],
    N=256,
)


def _load_json(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _read_perimeter():
    import geopandas as gpd
    return gpd.read_file(RAW / "fire" / "kincade_perimeter.gpkg").to_crs(CRS)


def _read_vineyards():
    import geopandas as gpd
    return gpd.read_file(RAW / "vineyards" / "kincade_vineyards.gpkg").to_crs(CRS)


def _read_dins():
    import geopandas as gpd
    return gpd.read_file(RAW / "dins" / "kincade_dins.gpkg").to_crs(CRS)


def _style(ax, grid=False):
    sk.style_axes(ax, grid=grid)


def _centered_panel_title(ax, letter, line1, line2=None):
    """Panel letter + title centered as one block over the axes."""
    letter = letter.strip("()")
    body = f"({letter})  {line1}" if line2 is None else f"({letter})  {line1}\n{line2}"
    ax.set_title(
        body, loc="center", fontsize=FS["size_panel_label"], fontweight="bold",
        pad=4, color=C["neutral_dark"], linespacing=1.35,
    )


def _kde_1d(vals, grid, bw=0.14):
    from scipy.stats import gaussian_kde
    v = vals[np.isfinite(vals)]
    if len(v) < 8:
        return None
    dens = gaussian_kde(v, bw_method=bw)(grid)
    return dens / (dens.max() + 1e-12)


def _draw_raincloud(ax, data, colors, rng, positions=None):
    """Half-violin (left) + box (centre) + jittered points (right)."""
    from matplotlib.patches import Rectangle

    if positions is None:
        positions = list(range(1, len(data) + 1))
    for pos, vals, c in zip(positions, data, colors):
        v = np.asarray(vals, dtype=float)
        v = v[np.isfinite(v)]
        if len(v) < 8:
            continue
        lo, hi = np.nanpercentile(v, [1, 99])
        grid = np.linspace(lo, hi, 160)
        dens = _kde_1d(v, grid, bw=0.14)
        if dens is not None:
            w = 0.38 * dens
            ax.fill_betweenx(grid, pos - w, pos, color=c, alpha=0.38, linewidth=0, zorder=2)
            ax.plot(pos - w, grid, color=c, linewidth=0.85, alpha=0.85, zorder=3)

        n_pts = min(90, len(v))
        sample = rng.choice(v, size=n_pts, replace=False)
        jitter = rng.uniform(0.06, 0.34, size=n_pts)
        ax.scatter(pos + jitter, sample, s=3.5, color=c, alpha=0.32,
                   linewidths=0, zorder=1, rasterized=True)

        q1, med, q3 = np.percentile(v, [25, 50, 75])
        iqr = q3 - q1
        whis_lo = max(v.min(), q1 - 1.5 * iqr)
        whis_hi = min(v.max(), q3 + 1.5 * iqr)
        ax.plot([pos, pos], [whis_lo, whis_hi], color=C["neutral_dark"],
                linewidth=0.75, zorder=4, solid_capstyle="round")
        ax.add_patch(Rectangle(
            (pos - 0.07, q1), 0.14, max(q3 - q1, 1e-9), facecolor=c,
            edgecolor=C["neutral_dark"], linewidth=0.7, zorder=5, alpha=1.0,
        ))
        ax.plot([pos - 0.07, pos + 0.07], [med, med], color=C["neutral_dark"],
                linewidth=1.2, zorder=6, solid_capstyle="butt")


# ------------------------------------------------------------------ Fig 01
def fig01_workflow():
    """Install external workflow infographic (outputs/figures/final/Figure_1.png)."""
    import shutil

    from PIL import Image

    src = sk.FINAL_DIR / "Figure_1.png"
    if not src.exists():
        raise FileNotFoundError(
            f"Figure 1 asset not found: {src}. Add the workflow infographic PNG there."
        )
    sk.MS_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, sk.MS_FINAL_DIR / "Figure_1.png")
    # Keep a TIFF companion for Frontiers upload sync / package builders.
    tif = sk.FINAL_DIR / "Figure_1.tif"
    Image.open(src).convert("RGB").save(
        tif, format="TIFF", compression="tiff_lzw", dpi=(300, 300)
    )
    # Remove legacy matplotlib workflow name if present.
    for legacy in (
        sk.FINAL_DIR / "Figure_01_workflow.png",
        sk.FINAL_DIR / "Figure_01_workflow.pdf",
        sk.FINAL_DIR / "Figure_01_workflow.tif",
        sk.MS_FINAL_DIR / "Figure_01_workflow.png",
        sk.MS_FINAL_DIR / "Figure_01_workflow.pdf",
        sk.MS_FINAL_DIR / "Figure_01_workflow.tif",
    ):
        if legacy.exists():
            legacy.unlink()
    print("  saved Figure_1: png+tif (external asset)")
    return {"png": str(src), "tif": str(tif)}


# ------------------------------------------------------------------ Fig 02
def fig02_study_area():
    perim = _read_perimeter()
    vines = _read_vineyards()
    dins = _read_dins()

    minx, miny, maxx, maxy = perim.total_bounds
    asp = (maxx - minx + 1200) / (maxy - miny + 1200)
    fig = plt.figure(figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.92))
    ax = sk.map_axes(fig, asp, bottom=0.14, max_height=0.80)
    ax.set_label("map")

    sk.set_extent(ax, perim, pad=800, inset_m=20)
    ax.set_facecolor("#D8D8D8")
    sk.hillshade_background(ax, alpha=0.88)

    vines.plot(ax=ax, facecolor=S["vineyard"], edgecolor="none", alpha=0.78, zorder=4)
    perim.boundary.plot(ax=ax, color=S["perimeter"], linewidth=1.4, zorder=6)

    dest = dins[dins["DAMAGE"].astype(str).str.contains("Destroyed", na=False)]
    dest.plot(ax=ax, color=S["severity"], markersize=9.0, alpha=0.92, zorder=7, linewidth=0)

    sk.map_frame(ax, crs=CRS, gis_frame=False)
    sk.clip_map_layers(ax)
    sk.add_scalebar(ax, 5.0, location="lower left")
    NORTH_ARROWS["arcgis_split"]["draw"](ax, 0.928, 0.945, 1.0)
    sk.cover_frame_overflow(fig, ax)

    handles = [
        Line2D([0], [0], color=S["perimeter"], lw=1.6, label="Kincade perimeter"),
        Patch(facecolor=S["vineyard"], edgecolor="none", label="Vineyards (2019)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=S["severity"],
               markersize=9, label="Destroyed structures (DINS)"),
    ]
    ax.legend(handles=handles, loc="upper center", ncol=3,
              bbox_to_anchor=(0.5, -0.032), borderaxespad=0.0,
              title="Map layers", title_fontsize=FS["size_label"], **sk.LEGEND_KW)
    ax.set_title("Kincade Fire study area, Sonoma County", loc="center",
                 fontsize=FS["size_panel_label"], fontweight="bold",
                 pad=8, color=C["neutral_dark"])
    return sk.save_figure(fig, "Figure_02_study_area", pad_inches=0.01)


# ------------------------------------------------------------------ Fig 03 — Sentinel-2 RGB / SWIR
def _active_scene_date() -> str | None:
    meta = RAW / "gee" / "s2_activefire_scene.json"
    if meta.exists():
        return _load_json(meta).get("date")
    hits = sorted(RAW.glob("gee/s2_activefire_rgb_*.tif"))
    return hits[-1].stem.split("_")[-1] if hits else None


def _rgb_map(ax, fp: Path, perim, ylabels: bool = True, xlabels: bool = True):
    import rasterio

    with rasterio.open(fp) as src:
        if src.count < 3:
            raise ValueError(f"expected 3-band RGB GeoTIFF, got {src.count}: {fp}")
        rgb = np.dstack([src.read(i) for i in (1, 2, 3)]).astype("float64")
        b = src.bounds
        nod = src.nodata
    if nod is not None:
        rgb[np.any(rgb == nod, axis=2)] = np.nan
    if np.isfinite(rgb).any() and np.nanmax(rgb) > 1.5:
        rgb = np.clip(rgb / 255.0, 0, 1)
    else:
        rgb = np.clip(rgb, 0, 1)
    alpha = np.where(np.all(np.isfinite(rgb), axis=2), 1.0, 0.0)
    rgba = np.dstack([np.nan_to_num(rgb, nan=0.0), alpha])
    ext = [b.left, b.right, b.bottom, b.top]
    ax.imshow(rgba, extent=ext, interpolation="bilinear", zorder=1, aspect="auto")
    sk.ocean_overlay(ax)
    perim.boundary.plot(ax=ax, color=S["perimeter"], linewidth=0.9, zorder=5)
    sk.set_extent(ax, perim, pad=400, inset_m=20)
    ax.set_label("map")
    sk.map_frame(ax, crs=CRS, ylabels=ylabels, xlabels=xlabels, gis_frame=False)
    sk.add_scalebar(ax, 4.0)


def fig03_rgb_context():
    """2×3 true color (B4/B3/B2) + SWIR false color (B12/B11/B4): pre | active | post."""
    perim = _read_perimeter()
    gee = RAW / "gee"
    active = _active_scene_date()
    if active is None:
        raise FileNotFoundError("No active-fire S2 scene; run src/download/09_s2_rgb_composites_gee.py")

    paths = {
        "pre_rgb": gee / "s2_prefire_rgb.tif",
        "pre_swir": gee / "s2_prefire_swir.tif",
        "post_rgb": gee / "s2_postfire_rgb.tif",
        "post_swir": gee / "s2_postfire_swir.tif",
        "act_rgb": gee / f"s2_activefire_rgb_{active}.tif",
        "act_swir": gee / f"s2_activefire_swir_{active}.tif",
    }
    missing = [p.name for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing RGB/SWIR GeoTIFFs: {missing}; run 09_s2_rgb_composites_gee.py")

    CM = 1 / 2.54
    fig, axes = plt.subplots(2, 3, figsize=(sk.W_DOUBLE, 12.4 * CM))
    top = [
        ("a", "True Color · Pre-fire", paths["pre_rgb"]),
        ("b", "True Color · Active fire", paths["act_rgb"]),
        ("c", "True Color · Post-fire", paths["post_rgb"]),
    ]
    bot = [
        ("d", "False color · Pre-fire", paths["pre_swir"]),
        ("e", "False color · Active fire", paths["act_swir"]),
        ("f", "False color · Post-fire", paths["post_swir"]),
    ]
    for row, panels, xlabels in ((0, top, False), (1, bot, True)):
        for col, (letter, title, fp) in enumerate(panels):
            ax = axes[row, col]
            _rgb_map(ax, fp, perim, xlabels=xlabels, ylabels=(col == 0))
            sk.panel_label(ax, letter, title)

    fig.subplots_adjust(left=0.06, right=0.98, top=0.94, bottom=0.07, wspace=0.16, hspace=0.22)
    return sk.save_figure(fig, "Figure_03_TRUE_B4B3B2_FalseB12B11B4", pad_inches=0.04)


# ------------------------------------------------------------------ Fig 04
def fig03_vineyard_water():
    df = pd.read_csv(DATA / "fig_prefire_ndmi_et.csv")
    reg = pd.read_csv(TAB / "table_prefire_ndmi_et.csv")

    def fit_row(xcol, ycol):
        r = reg[(reg.x == xcol) & (reg.y == ycol)]
        return r.iloc[0] if len(r) else None

    def panel_title(ax, letter, line1, line2=None):
        """Two-line panel titles stay inside the frame on narrow columns."""
        text = f"({letter})  {line1}" if line2 is None else f"({letter})  {line1}\n{line2}"
        ax.set_title(text, loc="center", fontsize=FS["size_panel_label"],
                     fontweight="bold", pad=8, color=C["neutral_dark"],
                     linespacing=1.25)

    fig, axes = plt.subplots(1, 3, figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.42),
                             gridspec_kw={"wspace": 0.36, "left": 0.08, "right": 0.98,
                                          "bottom": 0.16, "top": 0.78})

    # (a) NDMI vs ET
    ax = axes[0]
    ax.scatter(df.NDMI_prefire, df.ET_gs_mm, s=4, color=S["moisture"], alpha=0.22,
               edgecolors="none", rasterized=True)
    f = fit_row("NDMI_prefire", "ET_gs_mm")
    ax.set_xlabel("Pre-fire NDMI")
    ax.set_ylabel("Growing-season ET (mm)")
    _style(ax)
    if f is not None:
        x0, x1 = ax.get_xlim()
        xs = np.linspace(x0, x1, 100)
        ax.plot(xs, f.slope * xs + f.intercept, color=S["regression"], lw=1.5,
                ls=(0, (4, 2)), zorder=5)
        sk.stat_annotation(ax, f"Pearson r = {f.pearson_r:.2f}\nn = {int(f.n):,}",
                           loc="upper left")
    panel_title(ax, "a", "Canopy moisture", "vs. water use")

    # (b) NDVI vs ET
    ax = axes[1]
    ax.scatter(df.NDVI_prefire, df.ET_gs_mm, s=4, color=S["vineyard"], alpha=0.22,
               edgecolors="none", rasterized=True)
    f = fit_row("NDVI_prefire", "ET_gs_mm")
    ax.set_xlabel("Pre-fire NDVI")
    ax.set_ylabel("Growing-season ET (mm)")
    _style(ax)
    if f is not None:
        x0, x1 = ax.get_xlim()
        xs = np.linspace(x0, x1, 100)
        ax.plot(xs, f.slope * xs + f.intercept, color=S["regression"], lw=1.5,
                ls=(0, (4, 2)), zorder=5)
        sk.stat_annotation(ax, f"Pearson r = {f.pearson_r:.2f}\nn = {int(f.n):,}",
                           loc="upper left")
    panel_title(ax, "b", "Canopy vigour", "vs. water use")

    # (c) ET distribution — histogram + KDE
    ax = axes[2]
    et = df.ET_gs_mm.dropna().to_numpy()
    med = float(np.median(et))
    q25, q75 = np.percentile(et, [25, 75])
    bins = np.linspace(et.min(), et.max(), 32)
    ax.hist(et, bins=bins, color=S["moisture"], alpha=0.55,
            edgecolor="white", linewidth=0.4, zorder=2)
    # KDE scaled to count units
    from scipy.stats import gaussian_kde
    kde = gaussian_kde(et, bw_method="scott")
    xs = np.linspace(et.min(), et.max(), 240)
    bin_w = bins[1] - bins[0]
    dens = kde(xs) * len(et) * bin_w
    ax.fill_between(xs, dens, color=S["moisture"], alpha=0.22, zorder=3)
    ax.plot(xs, dens, color=S["moisture"], lw=1.6, zorder=4)
    ax.axvspan(q25, q75, color=S["moisture"], alpha=0.10, zorder=1)
    ax.axvline(med, color=S["regression"], lw=1.4, ls=(0, (4, 2)), zorder=5)
    ax.set_xlabel("Growing-season ET (mm)")
    ax.set_ylabel("Vineyard fields")
    # Leave headroom above the peak so the stats box does not sit on the KDE crest
    ax.set_ylim(0, float(dens.max()) * 1.38)
    _style(ax)
    ax.text(
        0.965, 0.955,
        f"Median = {med:.0f} mm\nIQR = {q25:.0f}–{q75:.0f}\nn = {len(et):,}",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=FS["size_small"], color=C["neutral_dark"],
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                  edgecolor="#BDBDBD", linewidth=0.6, alpha=0.96),
        zorder=10, linespacing=1.35)
    panel_title(ax, "c", "Water-use", "distribution")

    return sk.save_figure(fig, "Figure_04_vineyard_water")


# ------------------------------------------------------------------ Fig 05
def fig04_structure_context():
    s = _load_json(TAB / "lidar_inventory_summary.json")
    years = []
    for d in s["opentopography_datasets"]:
        try:
            years.append(int(str(d.get("temporal", ""))[:4]))
        except Exception:
            pass
    yr_series = pd.Series(years).value_counts().sort_index()
    x_years = yr_series.index.astype(int).to_numpy()
    y_counts = yr_series.values.astype(float)

    # Shared vineyard-purple sequence (light → dark) for both panels
    vine = np.array(matplotlib.colors.to_rgb(S["vineyard"]))
    def vine_shade(t: float):
        """t in [0,1]: mix white → vineyard purple."""
        t = float(np.clip(t, 0, 1))
        return tuple(vine * t + (1.0 - t) * np.array([0.92, 0.90, 0.95]))

    fig, axes = plt.subplots(1, 2, figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.42),
                             gridspec_kw={"wspace": 0.38, "left": 0.09, "right": 0.97,
                                          "bottom": 0.16, "top": 0.82})

    def frame_on_top(ax):
        """Redraw full frame above bars — bars stay flush with axes."""
        ax.set_axisbelow(True)
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_zorder(30)
            sp.set_linewidth(1.15)
            sp.set_color(C["neutral_dark"])
        # Explicit edge lines so the contact edge stays black over bar fills
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        kw = dict(color=C["neutral_dark"], lw=1.15, zorder=31, clip_on=False,
                  solid_capstyle="projecting")
        ax.plot([x0, x1], [y0, y0], **kw)  # bottom
        ax.plot([x0, x1], [y1, y1], **kw)  # top
        ax.plot([x0, x0], [y0, y1], **kw)  # left
        ax.plot([x1, x1], [y0, y1], **kw)  # right

    # (a) Continuous-time bar timeline — single cohesive color
    ax = axes[0]
    ax.axvline(2019, color=C["neutral_mid"], lw=1.0, ls=(0, (4, 2)), zorder=2)
    ax.text(2019.25, max(y_counts) + 0.55, "Kincade 2019",
            ha="left", va="bottom", fontsize=FS["size_small"] - 0.5,
            color=C["neutral_mid"], zorder=4)
    ax.bar(x_years, y_counts, width=0.85, color=vine_shade(0.72),
           edgecolor="white", linewidth=0.45, zorder=3, clip_on=True)
    ax.set_xlim(2001.5, 2024.5)
    ax.set_ylim(0, max(y_counts) + 1.35)
    ax.set_xticks([2004, 2008, 2012, 2016, 2020, 2024])
    ax.set_xlabel("Campaign start year")
    ax.set_ylabel("OpenTopography datasets")
    ax.yaxis.get_major_locator().set_params(integer=True)
    sk.stat_annotation(
        ax, f"n = {s['n_opentopography_pointcloud_datasets']} products",
        loc="upper left", pad=0.05)
    _style(ax)
    frame_on_top(ax)
    sk.panel_label(ax, "a", "Airborne lidar inventory")

    # (b) Horizontal bars — ordered purple shades; GEDI box inside (bottom right)
    ax = axes[1]
    tnm = s["tnm_counts"]
    rows = [
        ("10 m DEM", tnm["3dep_dem_10m"]),
        ("1 m DEM", tnm["3dep_1m_dem"]),
        ("OPR", tnm["3dep_opr"]),
        ("3DEP LPC", tnm["3dep_lpc"]),
    ]  # ascending
    labels = [r[0] for r in rows]
    vals = np.array([r[1] for r in rows], dtype=float)
    ypos = np.arange(len(rows))
    shades = [vine_shade(0.35 + 0.55 * i / (len(rows) - 1)) for i in range(len(rows))]
    ax.barh(ypos, vals, height=0.48, color=shades, edgecolor="white",
            linewidth=0.45, log=True, zorder=3, clip_on=True)
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Tile count (log scale)")
    ax.set_xlim(1, max(vals) * 3.2)
    ax.set_ylim(-1.05, len(rows) - 0.0)
    for y, v in zip(ypos, vals):
        ax.text(v * 1.08, y, f"{int(v):,}", va="center", ha="left",
                fontsize=FS["size_small"], color=C["neutral_dark"], zorder=4)
    g = s["gedi"]
    sk.stat_annotation(
        ax,
        f"GEDI L2A: {g['n_valid_rh98_pixels_in_perimeter_25m']:,} RH98 px\n"
        f"({g['n_monthly_images_over_perimeter']} monthly scenes)",
        loc="lower right", pad=0.05,
    )
    _style(ax)
    frame_on_top(ax)
    sk.panel_label(ax, "b", "USGS 3DEP tile inventory")

    return sk.save_figure(fig, "Figure_05_structure_context")


# ------------------------------------------------------------------ Fig 05
def fig05_weather():
    df = pd.read_csv(RAW / "weather" / "gridmet_aoi_mean_daily.csv", parse_dates=["date"])
    ign = pd.Timestamp("2019-10-23")
    t0, t1 = pd.Timestamp("2019-10-10"), pd.Timestamp("2019-11-06")
    df = df[(df.date >= t0) & (df.date <= t1)].copy()
    if df.empty:
        raise FileNotFoundError(
            "No gridMET rows for 10 Oct–6 Nov 2019; re-run src/download/07_gridmet.py"
        )
    if df.date.min() > ign - pd.Timedelta(days=3):
        raise FileNotFoundError(
            "gridMET CSV lacks pre-ignition lead-in; re-run src/download/07_gridmet.py"
        )

    xlo = df.date.min() - pd.Timedelta(hours=12)
    xhi = df.date.max() + pd.Timedelta(hours=12)
    leg_kw = {**sk.LEGEND_KW, "labelspacing": 0.45}
    vpd_color = S["severity"]
    ign_color = S["thermal"]

    fig, axes = plt.subplots(
        2, 1, figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.60),
        sharex=True,
        gridspec_kw={"hspace": 0.28, "left": 0.11, "right": 0.84, "bottom": 0.11, "top": 0.915},
    )

    def _ignition_line(ax):
        ax.axvline(ign, color=ign_color, lw=1.2, ls=(0, (5, 3)), zorder=2)

    ax = axes[0]
    ax.fill_between(
        df.date, df.rmin, df.rmax, color=S["moisture_band"], alpha=0.55,
        zorder=1, linewidth=0,
    )
    l_rh_min, = ax.plot(
        df.date, df.rmin, color=S["moisture"], lw=1.5, marker="o", ms=3.5,
        markerfacecolor="white", markeredgewidth=0.8, markeredgecolor=S["moisture"], zorder=3,
    )
    l_rh_max, = ax.plot(
        df.date, df.rmax, color=S["moisture"], lw=1.0, ls=(0, (3, 2)), alpha=0.5, zorder=2,
    )
    ax.set_ylabel("Relative humidity (%)", color=S["moisture"])
    ax.tick_params(axis="y", labelcolor=S["moisture"])
    ax.set_ylim(0, 100)
    axb = ax.twinx()
    l_vpd, = axb.plot(
        df.date, df.vpd, color=vpd_color, lw=1.5, marker="o", ms=3.5,
        markerfacecolor="white", markeredgewidth=0.8, markeredgecolor=vpd_color, zorder=3,
    )
    vpd_top = max(3.2, df.vpd.max() * 1.12)
    axb.set_ylabel("VPD (kPa)", color=vpd_color)
    axb.set_ylim(0, vpd_top)
    axb.yaxis.set_major_locator(MaxNLocator(nbins=5))
    axb.tick_params(
        axis="y", colors=vpd_color, labelcolor=vpd_color,
        right=True, labelright=True, left=False, labelleft=False,
    )
    _style(ax, grid=True)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", right=False, labelright=False)
    sk.full_frame(ax, twin=axb)
    _ignition_line(ax)
    _centered_panel_title(ax, "a", "Fire weather: humidity and vapour-pressure deficit")
    ax.legend(
        [
            Patch(facecolor=S["moisture_band"], edgecolor="none", alpha=0.55),
            l_rh_min, l_vpd,
        ],
        ["RH range (min–max)", "RH minimum", "VPD"],
        loc="upper right", bbox_to_anchor=(1.0, 1.0), ncol=1, **leg_kw,
    )

    ax = axes[1]
    wind_color = S["vineyard"]
    l_w, = ax.plot(
        df.date, df.vs, color=wind_color, lw=1.5, marker="o", ms=3.5,
        markerfacecolor="white", markeredgewidth=0.8, markeredgecolor=wind_color, zorder=3,
    )
    peak_idx = df.vs.idxmax()
    peak_day = df.loc[peak_idx, "date"]
    peak_val = df.loc[peak_idx, "vs"]
    ax.scatter([peak_day], [peak_val], s=36, color=wind_color, edgecolors="white",
               linewidths=0.8, zorder=5)
    ax.annotate(
        f"Peak wind\n{peak_val:.1f} m s$^{{-1}}$",
        xy=(peak_day, peak_val), xytext=(-20, -14), textcoords="offset points",
        ha="right", va="top", fontsize=FS["size_small"] - 0.5, color=C["neutral_dark"],
        arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.8, shrinkA=2, shrinkB=2),
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#CCCCCC", alpha=0.95),
        zorder=6,
    )
    ax.set_ylabel("Wind speed (m s$^{-1}$)")
    ax.set_xlabel("Date (2019)")
    ax.set_ylim(max(0, df.vs.min() - 0.6), df.vs.max() * 1.10)
    _ignition_line(ax)
    _style(ax, grid=True)
    _centered_panel_title(ax, "b", "Offshore wind forcing (gridMET AOI mean)")
    l_ign = Line2D([0], [0], color=ign_color, lw=1.2, ls=(0, (5, 3)))
    ax.legend(
        [l_w, l_ign],
        ["10 m wind speed", "Ignition (23 Oct 2019)"],
        loc="upper right", bbox_to_anchor=(1.0, 1.0), **leg_kw,
    )

    for a in axes:
        a.set_xlim(xlo, xhi)
        a.margins(x=0)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.xaxis.set_minor_locator(mdates.DayLocator())
    return sk.save_figure(fig, "Figure_06_weather_electrical")


# ------------------------------------------------------------------ Fig 06
def fig06_boundary_rdd():
    binned = pd.read_csv(DATA / "fig06_binned_dnbr.csv")
    pts = pd.read_csv(DATA / "fig06_transect_points.csv")
    bw = pd.read_csv(TAB / "table_rdd_bandwidth.csv")
    claim = _load_json(TAB / "rdd_claim_language.json")
    perim = _read_perimeter()
    vines = _read_vineyards()
    tau = float(claim["primary_tau"])

    fig = plt.figure(figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.52))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 0.95, 1.15], wspace=0.38,
                          left=0.07, right=0.97, bottom=0.14, top=0.88)

    # ---- (a) severity profile: side shading, color-coded bins, jump callout
    ax = fig.add_subplot(gs[0, 0])
    d = binned.sort_values("signed_dist_m").copy()
    wild = d[d.signed_dist_m < 0]
    vine = d[d.signed_dist_m > 0]
    x_lo, x_hi = d.signed_dist_m.min() - 20, d.signed_dist_m.max() + 20
    ax.axvspan(x_lo, 0, color=S["wildland"], alpha=0.08, zorder=0)
    ax.axvspan(0, x_hi, color=S["vineyard"], alpha=0.08, zorder=0)
    ax.axvline(0, color=C["neutral_dark"], lw=1.0, ls=(0, (5, 3)), zorder=2)
    ax.text(0.28, 0.07, "← Wildland", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=FS["size_small"] - 0.5, color=S["wildland"], fontweight="medium",
            clip_on=False, zorder=9)
    ax.text(0.72, 0.07, "Vineyard →", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=FS["size_small"] - 0.5, color=S["vineyard"], fontweight="medium",
            clip_on=False, zorder=9)

    fit_ends = {}
    for sub, col, side in ((wild, S["wildland"], "Wildland"),
                           (vine, S["vineyard"], "Vineyard")):
        ax.errorbar(sub.signed_dist_m, sub["mean"], yerr=sub["sem"], fmt="o", ms=5.0,
                    color=col, ecolor=col, elinewidth=0.8, alpha=0.85,
                    capsize=2.5, capthick=0.7, zorder=5, markeredgecolor="white",
                    markeredgewidth=0.5)
        if len(sub) >= 2:
            m, b0 = np.polyfit(sub.signed_dist_m, sub["mean"], 1)
            if side == "Wildland":
                xs = np.linspace(sub.signed_dist_m.min(), 0, 40)
            else:
                xs = np.linspace(0, sub.signed_dist_m.max(), 40)
            ax.plot(xs, m * xs + b0, color=col, lw=2.0, label=side, zorder=4,
                    solid_capstyle="round")
            fit_ends[side] = float(b0)

    if "Wildland" in fit_ends and "Vineyard" in fit_ends:
        y_w, y_v = fit_ends["Wildland"], fit_ends["Vineyard"]
        y_lo_j, y_hi_j = (y_w, y_v) if y_v >= y_w else (y_v, y_w)
        _jump = dict(arrowstyle="<->", mutation_scale=14)
        ax.annotate(
            "", xy=(-14, y_hi_j), xytext=(-14, y_lo_j),
            arrowprops=dict(**_jump, color="white", lw=3.2), zorder=6,
        )
        ax.annotate(
            "", xy=(-14, y_hi_j), xytext=(-14, y_lo_j),
            arrowprops=dict(**_jump, color="#111111", lw=1.7), zorder=7,
        )
        ax.text(
            -102, 0.5 * (y_w + y_v), "Boundary\ncontrast",
            ha="center", va="center", fontsize=FS["size_small"] - 0.5,
            color=C["neutral_dark"], linespacing=1.1,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor="#CCCCCC", alpha=0.95), zorder=8,
        )

    ax.set_xlim(x_lo, x_hi)
    ax.set_xlabel("Signed distance to vineyard boundary (m)")
    ax.set_ylabel("Mean dNBR")
    _style(ax, grid=True)
    ax.legend(loc="upper left", fontsize=FS["size_small"], **sk.LEGEND_KW)
    _centered_panel_title(ax, "a", "Severity profile", "at vineyard–wildland edges")

    # ---- (b) bandwidth sensitivity
    ax = fig.add_subplot(gs[0, 1])
    ci = 1.96 * bw.se_cluster
    y_lo = float((bw.tau_vineyard - ci).min()) - 0.005
    y_hi = float((bw.tau_vineyard + ci).max()) + 0.005
    ax.axhspan(min(y_lo, 0), 0, color=S["vineyard"], alpha=0.10, zorder=0)
    ax.axhline(0, color=C["neutral_dark"], lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.fill_between(bw.bandwidth_m, bw.tau_vineyard - ci, bw.tau_vineyard + ci,
                     color=S["severity"], alpha=0.12, zorder=2, linewidth=0)
    ax.plot(bw.bandwidth_m, bw.tau_vineyard, color=S["severity"], lw=1.6, zorder=3)
    ax.errorbar(bw.bandwidth_m, bw.tau_vineyard, yerr=ci, fmt="s", ms=5.5,
                color=S["severity"], ecolor="#888888", capsize=3, lw=0,
                elinewidth=0.9, markerfacecolor="white", markeredgewidth=1.1, zorder=4)
    _ann_box = dict(boxstyle="round,pad=0.2", facecolor="white",
                    edgecolor="#CCCCCC", alpha=0.92)
    primary = bw[bw.bandwidth_m == 100]
    if len(primary):
        ax.scatter(primary.bandwidth_m, primary.tau_vineyard, s=70, marker="s",
                   color=S["severity"], edgecolors="white", linewidths=1.0, zorder=6)
        ax.axvline(100, color=S["severity"], lw=0.9, ls=(0, (3, 2)), alpha=0.65, zorder=2)
        ax.text(
            78, y_hi - 0.012, "Primary\nbandwidth", rotation=90,
            ha="center", va="top", fontsize=FS["size_small"] - 0.5,
            color=S["severity"], fontweight="medium", linespacing=1.1,
            bbox=_ann_box, zorder=8,
        )
    ax.text(
        200, 0.0015, "Lower severity\nin vineyards",
        ha="center", va="bottom", fontsize=FS["size_small"] - 0.5,
        color=S["vineyard"], fontweight="medium", linespacing=1.1,
        bbox=_ann_box, zorder=8,
    )
    sk.stat_annotation(ax, f"Primary (100 m)\nτ = {tau:.3f}\np < 1×10$^{{-7}}$",
                       loc="upper right")
    ax.set_xlabel("Bandwidth (m)")
    ax.set_ylabel(r"$\tau$ (vineyard − wildland)")
    ax.set_ylim(y_lo, y_hi)
    _style(ax, grid=True)
    _centered_panel_title(ax, "b", "Bandwidth", "sensitivity")

    # ---- (c) map: full study extent (Fig 02 axes), extra west pad for transect samples
    ax = fig.add_subplot(gs[0, 2])
    ax.set_label("map")
    ax.set_facecolor("#D8D8D8")
    sk.hillshade_background(ax, alpha=0.88)
    vine_edge = "#8B72A8"
    vines.plot(ax=ax, facecolor=S["vineyard"], edgecolor=vine_edge, linewidth=0.25,
               alpha=0.78, zorder=3)
    sub = pts.dropna(subset=["dnbr"])
    out = sub[sub.vineyard == 0]
    inn = sub[sub.vineyard == 1]
    ax.scatter(out.x, out.y, c=out.dnbr, cmap=DNBR_CMAP, s=3.5,
               vmin=0, vmax=0.55, alpha=0.75, zorder=5, edgecolors="none",
               rasterized=True)
    sc = ax.scatter(inn.x, inn.y, c=inn.dnbr, cmap=DNBR_CMAP, s=3.5,
                    vmin=0, vmax=0.55, alpha=0.85, zorder=6, edgecolors="none",
                    rasterized=True)
    perim.boundary.plot(ax=ax, color=S["perimeter"], lw=1.35, zorder=7)

    pminx, pminy, pmaxx, pmaxy = perim.total_bounds
    pad_l, pad_r, pad_y = 2200, 800, 900
    minx = min(float(pminx) - pad_l, float(sub.x.min()) - 500)
    maxx = float(pmaxx) + pad_r
    miny = min(float(pminy) - pad_y, float(sub.y.min()) - 500)
    maxy = max(float(pmaxy) + pad_y, float(sub.y.max()) + 500)
    from visualization import style as _st
    _st._ensure_hillshade()
    left, right, bottom, top = _st._HS["ext"]
    x0, x1 = max(minx, left), min(maxx, right)
    y0, y1 = max(miny, bottom), min(maxy, top)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_autoscale_on(False)

    sk.map_frame(ax, crs=CRS, gis_frame=False)
    sk.clip_map_layers(ax)
    sk.add_scalebar(ax, 5.0, location="lower left")
    sk.add_cbar(sc, ax, "dNBR")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    handles = [
        Line2D([0], [0], color=S["perimeter"], lw=1.5, label="Fire perimeter"),
        Patch(facecolor=S["vineyard"], edgecolor=vine_edge, linewidth=0.5,
              alpha=0.78, label="Vineyards"),
    ]
    leg = ax.legend(handles=handles, loc="upper right", bbox_to_anchor=(1.0, 1.0),
                    fontsize=FS["size_small"] - 0.5, **sk.LEGEND_KW)
    leg.set_zorder(1000)
    if leg.get_frame() is not None:
        leg.get_frame().set_zorder(1000)
    _centered_panel_title(ax, "c", "Transect sample", "locations")

    return sk.save_figure(fig, "Figure_07_boundary_rdd")


# ------------------------------------------------------------------ Fig 07
def fig07_mechanisms():
    fields = pd.read_csv(PROC / "vineyard_fields_fire_sample.csv")
    mech = pd.read_csv(TAB / "table_mechanism_et.csv")
    cont = pd.read_csv(TAB / "table_rdd_continuity.csv")
    land = _load_json(TAB / "landscape_severity_summary.json")
    pts = pd.read_csv(DATA / "fig06_transect_points.csv")

    _ann_box = dict(boxstyle="round,pad=0.35", facecolor="white",
                    edgecolor="#BDBDBD", linewidth=0.6, alpha=0.96)
    _reg_kw = dict(color=S["regression"], lw=1.5, ls=(0, (4, 2)), zorder=5)

    fig, axes = plt.subplots(1, 3, figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.42),
                             gridspec_kw={"wspace": 0.48, "left": 0.08, "right": 0.98,
                                          "bottom": 0.16, "top": 0.81})

    # ---- (a) vineyard water use vs. burn severity
    ax = axes[0]
    f = fields.dropna(subset=["et_gs_mm", "dnbr_mean"])
    ax.scatter(f.et_gs_mm, f.dnbr_mean, s=5, color=S["vineyard"], alpha=0.42,
               edgecolors="none", rasterized=True, zorder=2)
    ax.set_xlabel("Growing-season ET (mm)")
    ax.set_ylabel("Field-mean dNBR")
    _style(ax)
    if len(f) >= 2:
        m, b0 = np.polyfit(f.et_gs_mm, f.dnbr_mean, 1)
        x0, x1 = ax.get_xlim()
        xs = np.linspace(x0, x1, 100)
        ax.plot(xs, m * xs + b0, **_reg_kw)
    beta = mech.iloc[0]
    ax.text(
        0.96, 0.06,
        f"$\\beta$(ET$_z$) = {beta.coef_et_z:.3f}\n"
        f"$n$ = {int(beta.n):,}\n$p$ < 0.001",
        transform=ax.transAxes, ha="right", va="bottom",
        fontsize=FS["size_small"], color=C["neutral_dark"],
        bbox=_ann_box, zorder=10, linespacing=1.35,
    )
    _centered_panel_title(ax, "a", "Water use", "vs. severity (vineyards)")

    # ---- (b) severity distributions by land cover (raincloud)
    ax = axes[1]
    grp = pts.dropna(subset=["dnbr"])
    wild_vals = grp[grp.vineyard == 0].dnbr.values
    vine_vals = grp[grp.vineyard == 1].dnbr.values
    data = [wild_vals, vine_vals]
    cols = [S["wildland"], S["vineyard"]]
    rng = np.random.default_rng(42)
    _draw_raincloud(ax, data, cols, rng, positions=[1, 2])
    vals = np.concatenate(data)
    lo, hi = np.nanpercentile(vals, [1, 99])
    pad = 0.06 * (hi - lo + 1e-9)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Wildland", "Vineyard"])
    ax.set_ylabel("dNBR (boundary transects)")
    ax.set_xlim(0.45, 2.75)
    ax.text(
        0.96, 0.96,
        f"Landscape means\nwild {land['mean_dnbr_wild']:.2f}  |  "
        f"vine {land['mean_dnbr_vine']:.2f}",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=FS["size_small"], color=C["neutral_dark"],
        bbox=_ann_box, zorder=10, linespacing=1.35,
    )
    _style(ax)
    _centered_panel_title(ax, "b", "Severity", "by land cover")

    # ---- (c) covariate balance at the RDD boundary
    ax = axes[2]
    order = cont.iloc[::-1].copy()
    _var_labels = {
        "elev_m": "Elev. (m)",
        "slope_deg": "Slope (°)",
        "northness": "Northness",
        "eastness": "Eastness",
    }
    order["label"] = order.variable.map(_var_labels).fillna(order.variable)
    ypos = np.arange(len(order))
    x_abs = float(order["diff"].abs().max()) * 1.18
    ax.axvspan(-x_abs, 0, color=S["wildland"], alpha=0.08, zorder=0)
    ax.axvspan(0, x_abs, color=S["vineyard"], alpha=0.08, zorder=0)
    ax.axvline(0, color=C["neutral_dark"], lw=0.9, ls=(0, (4, 3)), zorder=1)
    slope_yi = None
    slope_diff = None
    for yi, (_, row) in enumerate(order.iterrows()):
        sig = row.p < 0.05
        diff = row["diff"]
        if sig:
            ax.barh(
                yi, diff, height=0.52, color=S["severity"], alpha=0.88,
                edgecolor="white", linewidth=0.6, zorder=3,
            )
            if row.variable == "slope_deg":
                slope_yi, slope_diff = yi, diff
        else:
            ax.barh(
                yi, diff, height=0.52, color="#ECECEC", alpha=0.95,
                edgecolor="#AAAAAA", linewidth=0.8, zorder=2,
            )
            ax.scatter(
                [diff], [yi], s=28, facecolors="white", edgecolors="#888888",
                linewidths=0.9, zorder=4,
            )
    if slope_yi is not None:
        ax.text(
            slope_diff * 0.52, slope_yi, "Slope fails\ncontinuity",
            ha="center", va="center", fontsize=FS["size_small"] - 0.5,
            color="white", fontweight="medium", linespacing=1.2, zorder=5,
        )
    ax.set_yticks(ypos)
    ax.set_yticklabels(order.label)
    ax.tick_params(axis="y", pad=6)
    ax.set_xlabel("Vineyard − wildland difference")
    ax.set_xlim(-x_abs, x_abs)
    ax.text(
        0.96, 0.06,
        "Filled: $p$ < 0.05\nOpen: $p$ ≥ 0.05",
        transform=ax.transAxes, ha="right", va="bottom",
        fontsize=FS["size_small"], color=C["neutral_dark"],
        bbox=_ann_box, zorder=10, linespacing=1.35,
    )
    _style(ax)
    _centered_panel_title(ax, "c", "Covariate balance", "at boundary")

    return sk.save_figure(fig, "Figure_08_mechanisms")


# ------------------------------------------------------------------ Fig 08
def fig08_transport():
    acc = pd.read_csv(DATA / "fig_vineyard_access.csv")
    net = _load_json(TAB / "table_network_metrics.json")

    _ann_box = dict(boxstyle="round,pad=0.35", facecolor="white",
                    edgecolor="#BDBDBD", linewidth=0.6, alpha=0.96)

    fig, axes = plt.subplots(1, 3, figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.42),
                             gridspec_kw={"wspace": 0.48, "left": 0.08, "right": 0.98,
                                          "bottom": 0.16, "top": 0.81})

    # ---- (a) vineyard road access ECDF
    ax = axes[0]
    series = (
        ("dist_nearest_node_m", "Any road node", S["road"]),
        ("dist_major_road_m", "Major road", S["road_major"]),
    )
    for col, lab, color in series:
        v = np.sort(acc[col].dropna().values) / 1000.0
        y = np.arange(1, len(v) + 1) / len(v)
        ax.plot(v, y, lw=1.8, color=color, label=lab, solid_capstyle="round")
    ax.set_xlabel("Distance from vineyard centroid (km)")
    ax.set_ylabel("Cumulative fraction of fields")
    ax.set_xlim(0, np.percentile(acc.dist_major_road_m / 1000.0, 97))
    ax.set_ylim(0, 1.02)
    _style(ax)
    ax.legend(loc="lower right", fontsize=FS["size_small"] - 0.5, **sk.LEGEND_KW)
    _centered_panel_title(ax, "a", "Vineyard road access (ECDF)")

    # ---- (b) access by fire exposure (raincloud)
    ax = axes[1]
    inside = acc[acc.in_perimeter == 1].dist_major_road_m.dropna() / 1000.0
    outside = acc[acc.in_perimeter == 0].dist_major_road_m.dropna() / 1000.0
    data = [outside.values, inside.values]
    cols = [S["wildland"], S["thermal"]]
    rng = np.random.default_rng(42)
    _draw_raincloud(ax, data, cols, rng, positions=[1, 2])
    vals = np.concatenate(data)
    lo, hi = np.nanpercentile(vals, [1, 99])
    pad = 0.06 * (hi - lo + 1e-9)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xticks([1, 2])
    ax.set_xticklabels([f"Outside fire\n($n$={len(outside):,})",
                        f"Inside fire\n($n$={len(inside):,})"])
    ax.set_ylabel("Distance to major road (km)")
    ax.set_xlim(0.45, 2.75)
    ax.text(
        0.04, 0.96,
        f"Medians:\noutside {outside.median():.2f} km\n"
        f"inside {inside.median():.2f} km",
        transform=ax.transAxes, ha="left", va="top",
        fontsize=FS["size_small"], color=C["neutral_dark"],
        bbox=_ann_box, zorder=10, linespacing=1.35,
    )
    _style(ax)
    _centered_panel_title(ax, "b", "Access by fire exposure")

    # ---- (c) road-network summary
    ax = axes[2]
    km_total = net["total_road_length_km"]
    km_major = net["major_road_length_km"]
    dead_pct = net["frac_deadend_nodes"] * 100
    bar_w = 0.58
    bar_x_len = [0.0, 1.45]
    bar_x_dead = 3.05
    div_x = 2.22
    x_lo, x_hi = -0.65, 3.75
    y_hi = km_total * 1.08

    ax.axvspan(x_lo, div_x, color=S["road"], alpha=0.10, zorder=0)
    ax.axvspan(div_x, x_hi, color=S["road_major"], alpha=0.10, zorder=0)
    ax.axvline(div_x, color=C["neutral_dark"], lw=0.9, ls=(0, (5, 3)), zorder=1)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(0, y_hi)

    bar_specs = (
        (bar_x_len[0], km_total, S["neutral"], C["neutral_dark"], f"{km_total:,.0f} km"),
        (bar_x_len[1], km_major, S["thermal"], "#A84312", f"{km_major:,.0f} km"),
    )
    for xpos, height, fc, ec, label in bar_specs:
        ax.bar(xpos, height, width=bar_w, color=fc, edgecolor=ec,
               linewidth=0.8, alpha=0.92, zorder=3)
        ax.text(xpos, height * 0.50, label, ha="center", va="center", rotation=90,
                fontsize=FS["size_small"], color="white", fontweight="medium", zorder=4)
    ax.set_xticks([*bar_x_len, bar_x_dead])
    ax.set_xticklabels(["Total road\nlength", "Major road\nlength", "Dead-end\nshare"])
    ax.set_ylabel("Length (km)")
    _style(ax)

    ax2 = ax.twinx()
    ax2.bar(bar_x_dead, dead_pct, width=bar_w, color=S["road_major"],
            edgecolor="#3D2E28", linewidth=0.8, alpha=0.92, zorder=3)
    ax2.text(bar_x_dead, dead_pct * 0.50, f"{dead_pct:.0f}%", ha="center", va="center",
             rotation=90, fontsize=FS["size_small"], color="white",
             fontweight="medium", zorder=4)
    ax2.set_ylabel("Dead-end nodes (%)", color=S["road_major"])
    ax2.tick_params(axis="y", labelcolor=S["road_major"])
    ax2.set_ylim(0, max(60, dead_pct * 1.55))
    ax2.set_xlim(x_lo, x_hi)
    sk.full_frame(ax, twin=ax2)

    ax.text(
        0.96, 0.96,
        f"{net['n_nodes']:,} nodes\n"
        f"{net['n_edges']:,} edges\n"
        "OSM drive network\n"
        "(Oct 2019)",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=FS["size_small"] - 0.5, color=C["neutral_dark"],
        bbox=_ann_box, zorder=10, linespacing=1.25,
    )
    _centered_panel_title(ax, "c", "Road-network summary")

    return sk.save_figure(fig, "Figure_09_transport")


# ------------------------------------------------------------------ Fig 09
def _fig10_panel_a(ax, smoke, smk):
    """Panel (a): density-colored lollipop chart of vineyard smoke exposure."""
    dens_col = {"Heavy": S["smoke_heavy"], "Medium": S["smoke_med"], "Light": S["smoke_light"]}
    present = [k for k in dens_col if (smoke.max_density == k).any()]
    sm = smoke.loc[smoke.vineyard_ha_under_smoke > 0].copy()
    n_smoke = smk["window"]["n_days_with_smoke_over_aoi"]
    n_tot = smk["window"]["n_days_requested"]
    xmax = float(smoke.vineyard_ha_under_smoke.max())

    for dens_name, color in dens_col.items():
        sub = sm[sm.max_density == dens_name]
        if sub.empty:
            continue
        for _, row in sub.iterrows():
            ax.plot(
                [row.date, row.date], [0, row.vineyard_ha_under_smoke],
                color=color, lw=2.0, solid_capstyle="round", zorder=3, alpha=0.85,
            )
        ax.scatter(
            sub.date, sub.vineyard_ha_under_smoke,
            s=42, color=color, edgecolors="white", linewidths=0.8, zorder=5,
        )

    ax.set_ylabel("Vineyard area under smoke (ha)")
    ax.set_xlabel("Date (2019)")
    ax.set_xticks([
        pd.Timestamp("2019-10-23"),
        pd.Timestamp("2019-10-30"),
        pd.Timestamp("2019-11-06"),
    ])
    ax.set_xticklabels(["Oct 23", "Oct 30", "Nov 06"])
    ax.set_xlim(pd.Timestamp("2019-10-22"), pd.Timestamp("2019-11-08"))
    # Headroom above all lollipops so the legend sits clear of data
    ax.set_ylim(0, xmax * 1.38)

    handles = [Patch(facecolor=dens_col[k], edgecolor="white", linewidth=0.4, label=k)
               for k in present]
    leg = ax.legend(
        handles=handles,
        loc="upper right",
        bbox_to_anchor=(0.98, 0.98),
        title=f"{n_smoke} of {n_tot}\ndays with\nsmoke",
        fontsize=FS["size_small"] - 0.5,
        title_fontsize=FS["size_small"] - 0.5,
        borderpad=0.45,
        labelspacing=0.35,
        handletextpad=0.4,
        **{k: v for k, v in sk.LEGEND_KW.items()
           if k not in ("borderpad", "labelspacing", "handletextpad")},
    )
    if leg.get_title() is not None:
        leg.get_title().set_multialignment("left")
        leg.get_title().set_linespacing(1.25)
    _style(ax)
    _centered_panel_title(ax, "a", "Potential smoke exposure", "(not smoke taint)")


def fig09_smoke_recovery():
    smoke = pd.read_csv(TAB / "table_smoke_daily.csv", parse_dates=["date"])
    traj = pd.read_csv(DATA / "fig_recovery_trajectory.csv")
    traj = traj[traj.year.between(2018, 2021)]
    tests = pd.read_csv(TAB / "table_recovery_tests.csv")
    smk = _load_json(TAB / "smoke_vineyard_summary.json")

    _ann_box = dict(boxstyle="round,pad=0.35", facecolor="white",
                    edgecolor="#BDBDBD", linewidth=0.6, alpha=0.96)

    fig, axes = plt.subplots(1, 3, figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.42),
                             gridspec_kw={"wspace": 0.70, "left": 0.07, "right": 0.985,
                                          "bottom": 0.16, "top": 0.81})

    # ---- (a) lollipop
    _fig10_panel_a(axes[0], smoke, smk)

    # ---- (b) NDVI recovery trajectory
    ax = axes[1]
    series = (
        ("outside", S["wildland"], "Outside perimeter"),
        ("inside", S["thermal"], "Inside perimeter"),
    )
    for grp, color, lab in series:
        g = traj[traj.group == grp].sort_values("year")
        ax.fill_between(
            g.year, g.mean_ndvi - g.sem_ndvi, g.mean_ndvi + g.sem_ndvi,
            color=color, alpha=0.16, zorder=2,
        )
        ax.plot(
            g.year, g.mean_ndvi, "-", lw=1.8, color=color, label=lab,
            solid_capstyle="round", zorder=3,
        )
        ax.plot(
            g.year, g.mean_ndvi, "o", ms=5.5, color=color,
            markerfacecolor="white", markeredgewidth=1.35, zorder=4,
        )
    ax.axvspan(2018.85, 2019.15, color=S["thermal"], alpha=0.12, zorder=0)
    y0, y1 = float(traj.mean_ndvi.min()), float(traj.mean_ndvi.max())
    ypad = 0.06 * (y1 - y0)
    ax.set_ylim(y0 - ypad, y1 + ypad * 1.45)
    from matplotlib.transforms import blended_transform_factory
    # Fire at ~72% axes height (data x, axes y) — clear of lower-left legend
    ax.text(
        2019, 0.72, "Fire",
        transform=blended_transform_factory(ax.transData, ax.transAxes),
        ha="center", va="center",
        fontsize=FS["size_small"], color=S["thermal"], fontweight="medium",
        zorder=6,
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Mean growing-season NDVI")
    years = sorted(traj.year.unique())
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], rotation=0)
    if len(years) >= 6:
        ax.tick_params(axis="x", labelsize=FS["size_small"] - 0.5)
    ax.legend(loc="lower left", fontsize=FS["size_small"] - 0.5, **sk.LEGEND_KW)
    _style(ax)
    _centered_panel_title(ax, "b", "Vegetation recovery", "trajectory")

    # ---- (c) recovery deficit
    ax = axes[2]
    order = ["NDVI_2020", "NDVI_2021", "recov_2020_ratio", "recov_2021_ratio"]
    nice = {
        "NDVI_2020": "NDVI (2020)",
        "NDVI_2021": "NDVI (2021)",
        "recov_2020_ratio": "Recov. ratio (2020)",
        "recov_2021_ratio": "Recov. ratio (2021)",
    }
    t = tests.set_index("variable").loc[order].reset_index()
    t["lab"] = t.variable.map(nice)
    ypos = np.arange(len(t))
    diffs = t.diff_in_minus_out.to_numpy(dtype=float)
    x_lo = float(diffs.min()) * 1.22
    x_hi = max(0.008, float(np.abs(diffs).max()) * 0.28)

    ax.axvspan(x_lo, 0, color=S["severity"], alpha=0.11, zorder=0)
    ax.axvspan(0, x_hi, color=S["wildland"], alpha=0.10, zorder=0)
    ax.axvline(0, color=C["neutral_dark"], lw=0.9, ls=(0, (4, 3)), zorder=1)

    for yi, row in t.iterrows():
        diff = float(row.diff_in_minus_out)
        ax.barh(
            yi, diff, height=0.55, color=S["severity"], alpha=0.90,
            edgecolor="white", linewidth=0.6, zorder=3,
        )
        ax.text(
            diff * 0.52, yi, f"{diff:.3f}", ha="center", va="center",
            fontsize=FS["size_small"] - 0.5, color="white",
            fontweight="medium", zorder=5,
        )
    ax.set_yticks(ypos)
    ax.set_yticklabels(t.lab)
    ax.tick_params(axis="y", pad=5)
    ax.set_xlabel("Inside − outside (Δ)")
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(-0.55, len(t) - 0.45)
    ax.text(
        0.04, 0.06,
        "All differences\n$p$ < 0.05",
        transform=ax.transAxes, ha="left", va="bottom",
        fontsize=FS["size_small"], color=C["neutral_dark"],
        bbox=_ann_box, zorder=10, linespacing=1.35,
    )
    _style(ax)
    _centered_panel_title(ax, "c", "Recovery deficit", "inside perimeter")

    return sk.save_figure(fig, "Figure_10_smoke_recovery")


# ------------------------------------------------------------------ Fig 11 evidence synthesis
def _fmt_p(p: float) -> str:
    if p == 0 or p < 1e-3:
        return "p < 0.001"
    if p < 0.01:
        return f"p = {p:.3f}"
    return f"p = {p:.2f}"


# Ordinal planning attention (bar length only). Labels avoid "Low/Med/High"
# so they are not confused with evidence-class wording in the legend.
_IMPORTANCE = {
    "high": (0.90, "Primary"),
    "medium": (0.62, "Secondary"),
    "support": (0.40, "Supporting"),
}


def _synthesis_data():
    """Eight evidence domains in the previous scorecard visual grammar (4 columns).

    Colors encode the *evidence class* of the Signal column (favorable / mixed /
    adverse), not the salience bar length. Salience is ordinal attention only.
    """
    land = _load_json(TAB / "landscape_severity_summary.json")
    claim = _load_json(TAB / "rdd_claim_language.json")
    net = _load_json(TAB / "table_network_metrics.json")
    smk = _load_json(TAB / "smoke_vineyard_summary.json")
    gam = _load_json(TAB / "spatial_model_summary.json")
    rec = pd.read_csv(TAB / "table_recovery_group_means.csv")
    reg = pd.read_csv(TAB / "table_prefire_ndmi_et.csv")
    ndmi_et = reg[(reg.x == "NDMI_prefire") & (reg.y == "ET_gs_mm")].iloc[0]
    ndvi_et = reg[(reg.x == "NDVI_prefire") & (reg.y == "ET_gs_mm")].iloc[0]
    ri = rec[rec.group == "inside"].iloc[0]
    ro = rec[rec.group == "outside"].iloc[0]

    vine_d = float(land["mean_dnbr_vine"])
    wild_d = float(land["mean_dnbr_wild"])
    tau = float(claim["primary_tau"])
    road_m = float(net["vineyard_access"]["median_dist_major_road_m"])
    dead_frac = float(net["frac_deadend_nodes"])
    mean_smoke_days = float(smk["mean_smoke_days_per_field"])
    rec_in = float(ri.mean_recov_2021_ratio)
    rec_out = float(ro.mean_recov_2021_ratio)
    vf = float(gam["linear_coefficients"]["vineyard_frac"]["coef"])
    moran = float(gam["moran_residuals"]["moran_I"])

    # Evidence-class colors (same Kincade scorecard grammar).
    GOOD, MIX, POOR = S["wildland"], S["severity_mid"], S["severity"]

    def _row(system, indicator, metric, detail, signal, color, importance):
        fill, label = _IMPORTANCE[importance]
        return dict(
            system=system, indicator=indicator, metric=metric, detail=detail,
            signal=signal, color=color, importance_fill=fill, importance_label=label,
        )

    rows = [
        _row(
            "Canopy–water",
            "Pre-fire NDMI–ET & NDVI–ET coupling",
            f"NDMI–ET r={ndmi_et.pearson_r:.3f}; NDVI–ET r={ndvi_et.pearson_r:.3f}",
            "Canopy tracked water use; irrigation unobserved.",
            "Coherent field signal", GOOD, "medium",
        ),
        _row(
            "Landscape severity",
            "Vineyard vs. wildland dNBR",
            f"dNBR {vine_d:.3f} vine vs {wild_d:.3f} wildland",
            "Descriptive contrast; not calibrated damage.",
            "Weaker spectral impact", GOOD, "high",
        ),
        _row(
            "Boundary",
            "Discontinuity (100 m bandwidth)",
            f"τ = {tau:.4f} at 100 m",
            "Slope/donut/placebo fail causal claim.",
            "Mixed / scale dependent", MIX, "medium",
        ),
        _row(
            "Spatial model",
            "Conditional vineyard-fraction association",
            f"β={vf:+.3f}; residual Moran I={moran:.3f}",
            "Sign reversal; residual structure remains.",
            "Mixed / unresolved", MIX, "medium",
        ),
        _row(
            "Transport",
            "Median distance to major road",
            f"{road_m:.0f} m; {100 * dead_frac:.1f}% dead-end nodes",
            "Connected network; dead ends cut redundancy.",
            "Access with fragility", MIX, "medium",
        ),
        _row(
            "Smoke",
            "HMS overhead plume days",
            f"All fields; mean {mean_smoke_days:.2f} smoke-days",
            "Plume proxy only; not PM2.5 or smoke taint.",
            "Persistent exposure", POOR, "high",
        ),
        _row(
            "Recovery",
            "NDVI recovery ratio 2021",
            f"{rec_in:.3f} inside vs {rec_out:.3f} outside",
            "Greenness deficit through year 2; not yield.",
            "Persistent deficit", POOR, "high",
        ),
        _row(
            "3-D fuels",
            "Airborne lidar readiness",
            "No dedicated 2019 airborne lidar collect",
            "Lidar/GEDI = context, not event-day fuels.",
            "Critical data gap", POOR, "support",
        ),
    ]
    return rows, (GOOD, MIX, POOR)


def _synthesis_legend(ax, good, mix, poor):
    """Draw legend as an in-panel strip just under the last row (no floating gap)."""
    y0, h = 0.008, 0.028
    ax.add_patch(FancyBboxPatch(
        (0.12, y0), 0.76, h, boxstyle="round,pad=0.004,rounding_size=0.006",
        facecolor="#FAFAFA", edgecolor="#DDD8E4", linewidth=0.55, zorder=2,
    ))
    items = [
        (good, "Favorable / coherent signal"),
        (mix, "Mixed / context-dependent"),
        (poor, "Adverse / data-limited"),
    ]
    xs = [0.16, 0.40, 0.64]
    for x, (col, lab) in zip(xs, items):
        ax.add_patch(Rectangle((x, y0 + h * 0.28), 0.018, h * 0.44,
                               facecolor=col, edgecolor="none", zorder=3))
        ax.text(x + 0.026, y0 + h * 0.50, lab, va="center", ha="left",
                fontsize=FS["size_small"] - 0.55, color=C["neutral_dark"], zorder=3)


def _draw_evidence_synthesis(ax, rows):
    """Scorecard layout: 4 columns; colors = evidence class; bars = attention."""
    CARD_X, CARD_W = 0.010, 0.980
    CARD_RIGHT = CARD_X + CARD_W
    X_LABEL = 0.028
    X_BAR, W_BAR = 0.245, 0.220
    X_METRIC = 0.485
    X_CHIP, W_CHIP = 0.820, 0.145
    # Hard right edge for metric text (clear gap before Signal pills)
    METRIC_RIGHT = X_CHIP - 0.030

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    n = len(rows)
    hdr_y = 0.955
    top = 0.930
    gap = 0.010
    # Small breath between last row and legend (legend top ≈ 0.036)
    bottom = 0.052
    h = (top - bottom - gap * (n - 1)) / n
    fs = FS["size_small"]
    fs_s = fs - 0.55

    ax.text(X_LABEL, hdr_y, "System / indicator", fontsize=fs_s, fontweight="bold",
            color=C["neutral_mid"])
    ax.text(X_BAR + W_BAR / 2, hdr_y, "Planning attention", ha="center",
            fontsize=fs_s, fontweight="bold", color=C["neutral_mid"])
    ax.text(X_METRIC, hdr_y, "Key metric / context", fontsize=fs_s, fontweight="bold",
            color=C["neutral_mid"])
    ax.text(X_CHIP + W_CHIP / 2, hdr_y, "Signal", ha="center", fontsize=fs_s,
            fontweight="bold", color=C["neutral_mid"])

    for i, row in enumerate(rows):
        y0 = top - (i + 1) * h - i * gap
        tc = row["color"]
        bg = "#FAFAFA" if i % 2 else "#F7F7F7"

        for z0, z1, col in (
            (0.0, 0.40, S["severity"]),
            (0.40, 0.68, S["severity_mid"]),
            (0.68, 1.0, S["wildland"]),
        ):
            ax.add_patch(Rectangle(
                (X_BAR + z0 * W_BAR, y0), (z1 - z0) * W_BAR, h,
                facecolor=col, alpha=0.06, edgecolor="none", zorder=0,
            ))

        # Solid fill first (guarantees the row closes on the right)
        ax.add_patch(Rectangle(
            (CARD_X, y0), CARD_W, h,
            facecolor=bg, edgecolor="none", zorder=1,
        ))

        ax.text(X_LABEL + 0.010, y0 + h * 0.70, row["system"], va="center", ha="left",
                fontsize=fs, fontweight="bold", color=C["neutral_dark"], zorder=3)
        ax.text(X_LABEL + 0.010, y0 + h * 0.28,
                textwrap.fill(row["indicator"], width=24),
                va="center", ha="left", fontsize=fs_s, color="#5A5A5A",
                linespacing=1.15, zorder=3)

        track_h = h * 0.32
        track_y = y0 + h * 0.50
        cap = track_h / 2
        ax.add_patch(FancyBboxPatch(
            (X_BAR, track_y), W_BAR, track_h,
            boxstyle=f"round,pad=0,rounding_size={cap}",
            facecolor="#E4E4E4", edgecolor="none", zorder=2))
        fill_w = max(row["importance_fill"] * W_BAR, 0.012)
        ax.add_patch(FancyBboxPatch(
            (X_BAR, track_y), fill_w, track_h,
            boxstyle=f"round,pad=0,rounding_size={cap}",
            facecolor=tc, edgecolor="white", linewidth=0.7, alpha=0.94, zorder=3))
        if fill_w > W_BAR * 0.30:
            ax.text(X_BAR + fill_w - 0.006, track_y + track_h / 2, row["importance_label"],
                    ha="right", va="center", fontsize=fs_s - 0.15, color="white",
                    fontweight="bold", zorder=4)
        else:
            ax.text(X_BAR + fill_w + 0.006, track_y + track_h / 2, row["importance_label"],
                    ha="left", va="center", fontsize=fs_s - 0.15, color=tc,
                    fontweight="bold", zorder=4)

        lbl_y = y0 + h * 0.14
        axis_y = y0 + h * 0.28
        tick_up = h * 0.020
        ax.plot([X_BAR, X_BAR + W_BAR], [axis_y, axis_y],
                color="#C8C8C8", lw=0.5, zorder=2, clip_on=True)
        for xv, xl in ((0.0, "less"), (1.0, "more")):
            tx = X_BAR + xv * W_BAR
            ax.plot([tx, tx], [axis_y, axis_y + tick_up],
                    color="#C8C8C8", lw=0.5, zorder=2, clip_on=True)
            ax.text(tx, lbl_y, xl, ha="center", va="center",
                    fontsize=fs_s - 0.6, color=C["neutral_mid"], clip_on=True,
                    style="italic")

        # Single-line metric + detail, hard-clipped so they never enter Signal
        metric_clip = Rectangle(
            (X_METRIC, y0 + 0.004), METRIC_RIGHT - X_METRIC, h - 0.008,
            transform=ax.transData,
        )
        t_metric = ax.text(
            X_METRIC + 0.004, y0 + h * 0.68, row["metric"],
            va="center", ha="left", fontsize=fs - 0.25, color=C["neutral_dark"],
            zorder=3, clip_on=True,
        )
        t_metric.set_clip_path(metric_clip)
        t_detail = ax.text(
            X_METRIC + 0.004, y0 + h * 0.32, row["detail"],
            va="center", ha="left", fontsize=fs_s - 0.25, color="#666666",
            zorder=3, clip_on=True,
        )
        t_detail.set_clip_path(metric_clip)
        # Wipe only the gap before Signal (stay well inside the card)
        ax.add_patch(Rectangle(
            (METRIC_RIGHT, y0 + 0.004), X_CHIP - METRIC_RIGHT, h - 0.008,
            facecolor=bg, edgecolor="none", zorder=4.5,
        ))

        chip_h = h * 0.54
        chip_y = y0 + h * 0.23
        ax.add_patch(FancyBboxPatch(
            (X_CHIP, chip_y), W_CHIP, chip_h,
            boxstyle="round,pad=0.012,rounding_size=0.012",
            facecolor=tc, edgecolor="none", zorder=5))
        ax.text(X_CHIP + W_CHIP / 2, y0 + h * 0.50,
                textwrap.fill(row["signal"], width=13),
                ha="center", va="center", fontsize=fs_s, color="white",
                fontweight="bold", zorder=6, linespacing=1.08)
        # Closed border on top of row content
        ax.add_patch(FancyBboxPatch(
            (CARD_X, y0), CARD_W, h, boxstyle="round,pad=0.002,rounding_size=0.008",
            facecolor="none", edgecolor="#DDD8E4", linewidth=0.75, zorder=7))
        # Left accent bar above the frame so it is never covered
        ax.add_patch(FancyBboxPatch(
            (CARD_X, y0), 0.010, h, boxstyle="round,pad=0.004,rounding_size=0.008",
            facecolor=tc, edgecolor="none", zorder=8))


def fig10_synthesis(save_name: str = "Figure_11_synthesis"):
    """Figure 11 — evidence synthesis styled like the previous scorecard."""
    rows, (good, mix, poor) = _synthesis_data()
    fig, ax = plt.subplots(figsize=(sk.W_DOUBLE, sk.W_DOUBLE * 0.70))
    fig.subplots_adjust(top=0.93, bottom=0.015, left=0.035, right=0.985)
    _draw_evidence_synthesis(ax, rows)
    _synthesis_legend(ax, good, mix, poor)
    fig.suptitle(
        "Evidence synthesis for vineyard wildfire resilience",
        fontsize=FS["size_panel_label"], fontweight="bold",
        color=C["neutral_dark"], y=0.968,
    )
    return sk.save_figure(fig, save_name, pad_inches=0.008)


FIGURES = [
    ("Figure 01 workflow", fig01_workflow),
    ("Figure 02 study area", fig02_study_area),
    ("Figure 03 S2 RGB/SWIR context", fig03_rgb_context),
    ("Figure 04 vineyard water", fig03_vineyard_water),
    ("Figure 05 structure context", fig04_structure_context),
    ("Figure 06 weather + electrical", fig05_weather),
    ("Figure 07 boundary RDD", fig06_boundary_rdd),
    ("Figure 08 mechanisms", fig07_mechanisms),
    ("Figure 09 transport", fig08_transport),
    ("Figure 10 smoke + recovery", fig09_smoke_recovery),
    ("Figure 11 synthesis", fig10_synthesis),
]


def main():
    sk.apply_style()
    print(f"Font: {sk.resolve_font_family()}")
    print(f"Output: {sk.FINAL_DIR}")
    for name, fn in FIGURES:
        try:
            print(f"[build] {name}")
            fn()
            CREATED.append(name)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            FAILED.append(f"{name}: {exc}")
    print(f"\nCreated: {len(CREATED)} | Failed: {len(FAILED)}")
        for f in FAILED:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
