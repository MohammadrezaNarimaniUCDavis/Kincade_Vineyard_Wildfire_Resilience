"""Shared publication figure style for GIScience & Remote Sensing.

All figures use the same typeface, sizes, full four-sided frames, outside
panel letters, lat/lon ticks on maps, and colorbars matched to axis height.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
with open(ROOT / "config" / "figure_style.yaml", "r", encoding="utf-8") as f:
    STYLE = yaml.safe_load(f)

CM = 1 / 2.54
W_SINGLE = STYLE["figure"]["width_single_cm"] * CM
W_DOUBLE = STYLE["figure"]["width_double_cm"] * CM
DPI = STYLE["figure"]["dpi_raster"]
COLORS = STYLE["colors"]
PALETTES = STYLE["palettes"]
FS = STYLE["fonts"]

DAMAGE_COLORS = {
    "No Damage": COLORS["no_damage"],
    "Affected (>0-10%)": COLORS["affected"],
    "Minor (10-25%)": COLORS["minor"],
    "Major (25-50%)": COLORS["major"],
    "Destroyed (>50%)": COLORS["destroyed"],
}

DAMAGE_SHORT = ["No damage", "Affected", "Minor", "Major", "Destroyed"]

_HS: dict = {}
_FW: dict = {}  # LANDFIRE fuel water mask (panel c reference)
FUEL_WATER_COLOR = "#D9E8F2"
_RESOLVED_FONT: str | None = None


def resolve_font_family() -> str:
    """Helvetica if installed; else bundled FreeSans; else Arial / DejaVu."""
    global _RESOLVED_FONT
    if _RESOLVED_FONT:
        return _RESOLVED_FONT
    from matplotlib import font_manager as fm

    fonts_dir = ROOT / "assets" / "fonts"
    if fonts_dir.is_dir():
        for fp in sorted(fonts_dir.glob("*.ttf")):
            try:
                fm.fontManager.addfont(str(fp))
            except (OSError, RuntimeError, ValueError):
                pass
    available = {f.name for f in fm.fontManager.ttflist}
    preferred = FS.get("family", "Helvetica")
    for name in (preferred, "Helvetica", "FreeSans", "Arial", "DejaVu Sans"):
        if name in available:
            _RESOLVED_FONT = name
            break
    else:
        _RESOLVED_FONT = "sans-serif"
    return _RESOLVED_FONT


def apply_style() -> None:
    ln = STYLE["lines"]
    family = resolve_font_family()
    mpl.rcParams.update({
        "font.family": family,
        "font.sans-serif": [family, "Helvetica", "FreeSans", "Arial", "DejaVu Sans"],
        "font.size": FS["size_base"],
        "axes.labelsize": FS["size_label"],
        "axes.titlesize": FS["size_title"],
        "xtick.labelsize": FS["size_small"],
        "ytick.labelsize": FS["size_small"],
        "legend.fontsize": FS["size_small"],
        "legend.title_fontsize": FS.get("size_legend_title", FS["size_label"]),
        "axes.linewidth": 1.0,
        "lines.linewidth": ln["line_width"],
        "grid.alpha": ln["grid_alpha"],
        "axes.grid": False,
        "axes.unicode_minus": False,
        "axes.spines.top": True,
        "axes.spines.right": True,
        "axes.spines.bottom": True,
        "axes.spines.left": True,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "axes.xmargin": 0.02,
        "axes.ymargin": 0.04,
        "figure.dpi": 120,
        "savefig.dpi": DPI,
        "savefig.facecolor": "white",
        "legend.frameon": True,
        "legend.edgecolor": "#BDBDBD",
        "legend.fancybox": False,
        "legend.framealpha": 1.0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "mathtext.fontset": "custom",
        "mathtext.rm": family,
        "mathtext.it": family,
        "mathtext.bf": family,
    })


def full_frame(ax, twin=None) -> None:
    """Draw all four spines; optional twin y-axis keeps a closed rectangle."""
    lw = STYLE["lines"]["axes_linewidth"]
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_linewidth(lw)
        s.set_color(COLORS["neutral_dark"])
    ax.tick_params(which="both", direction="in", top=True,
                   right=(twin is None), length=3.0, width=0.7)
    if twin is None:
        return
    for s in twin.spines.values():
        s.set_visible(True)
        s.set_linewidth(lw)
        s.set_color(COLORS["neutral_dark"])
    twin.spines["left"].set_visible(False)
    twin.spines["bottom"].set_visible(False)
    ax.spines["right"].set_visible(False)
    twin.tick_params(which="both", direction="in", right=True, left=False,
                     top=True, bottom=False, length=3.0, width=0.7)


def panel_label(ax, letter: str, title: str | None = None,
                loc: str = "center") -> None:
    """Place panel letter + title centered above the axes."""
    letter = letter.strip("()")
    text = f"({letter})" if not title else f"({letter})  {title}"
    ax.set_title(
        text, loc=loc, fontsize=FS["size_panel_label"],
        fontweight="bold", pad=6, color=COLORS["neutral_dark"],
    )


def add_cbar(mappable, ax, label: str, orientation: str = "vertical"):
    """Colorbar whose long side matches the axes frame."""
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    divider = make_axes_locatable(ax)
    if orientation == "vertical":
        cax = divider.append_axes("right", size="4.6%", pad=0.12)
    else:
        cax = divider.append_axes("bottom", size="5%", pad=0.40)
    cax.set_label("colorbar")
    cb = ax.figure.colorbar(mappable, cax=cax, orientation=orientation)
    cb.set_label(label, size=FS["size_label"])
    cb.ax.tick_params(labelsize=FS["size_small"], length=2.5, width=0.6,
                      direction="in")
    cb.outline.set_linewidth(0.7)
    cb.outline.set_edgecolor(COLORS["neutral_dark"])
    return cb


def lock_plot_frames(fig) -> None:
    """Force a closed four-sided frame on every data axis."""
    lw = STYLE["lines"]["axes_linewidth"]
    for ax in fig.axes:
        if ax.get_label() in {"colorbar", "inset"}:
            continue
        # Preserve twin-axis spine layout.
        if not ax.spines["left"].get_visible():
            for side in ("top", "right", "bottom"):
                ax.spines[side].set_visible(True)
                ax.spines[side].set_linewidth(lw)
            continue
        if not ax.spines["right"].get_visible() and ax.spines["left"].get_visible():
            for side in ("top", "left", "bottom"):
                ax.spines[side].set_visible(True)
                ax.spines[side].set_linewidth(lw)
            ax.tick_params(which="major", direction="in", top=True, right=False,
                           bottom=True, left=True, length=3.0, width=0.7)
            continue
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(lw)
            spine.set_color(COLORS["neutral_dark"])
        if ax.get_label() != "map":
            ax.tick_params(which="major", direction="in", top=True, right=True,
                           bottom=True, left=True, length=3.0, width=0.7,
                           labeltop=False, labelright=False)


def add_scalebar(ax, length_km: float = 4.0, location: str = "lower left") -> None:
    from matplotlib_scalebar.scalebar import ScaleBar
    family = resolve_font_family()
    ax.add_artist(ScaleBar(
        1.0, units="m", fixed_value=length_km, fixed_units="km",
        location=location, box_alpha=1.0, border_pad=0.15, sep=0.6,
        scale_loc="top", color=COLORS["neutral_dark"],
        box_color="white", rotation="horizontal-only",
        font_properties={"size": FS["size_small"], "family": family},
        pad=0.4,
    ))


def _nice_ticks(vmin: float, vmax: float, n: int = 3) -> np.ndarray:
    span = max(vmax - vmin, 1e-9)
    raw = span / max(n, 1)
    mag = 10 ** np.floor(np.log10(raw))
    step = mag
    for m in (1.0, 2.0, 5.0, 10.0):
        if m * mag >= raw * 0.55:
            step = m * mag
            break
    start = np.ceil((vmin + 0.08 * span) / step) * step
    stop = np.floor((vmax - 0.08 * span) / step) * step
    ticks = np.arange(start, stop + step * 0.5, step)
    if len(ticks) < 2:
        ticks = np.linspace(vmin + 0.2 * span, vmax - 0.2 * span, 2)
    return ticks


def _regular_ticks(vmin: float, vmax: float, steps: tuple[float, ...]) -> np.ndarray:
    """Degree ticks at fixed intervals spanning the full map extent."""
    for step in steps:
        start = np.floor(vmin / step + 1e-9) * step
        ticks = np.arange(start, vmax + step * 0.25, step)
        ticks = ticks[(ticks >= vmin - 1e-9) & (ticks <= vmax + 1e-9)]
        if 3 <= len(ticks) <= 7:
            dec = max(0, int(round(-np.log10(step))))
            return np.round(ticks, dec)
    return np.round(np.linspace(vmin, vmax, 4), 2)


def add_latlon_ticks(ax, crs: str, n_ticks: int = 4) -> None:
    """Longitude / latitude labels at regular intervals across the map frame."""
    from pyproj import Transformer
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    corners = [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]
    lons, lats = zip(*[to_ll.transform(x, y) for x, y in corners])
    lon_ticks = _regular_ticks(min(lons), max(lons), (0.05, 0.02, 0.1, 0.01))
    lat_ticks = _regular_ticks(min(lats), max(lats), (0.02, 0.01, 0.05, 0.005))
    mean_lat = float(np.mean(lats))
    mean_lon = float(np.mean(lons))
    xticks = [to_xy.transform(lon, mean_lat)[0] for lon in lon_ticks]
    yticks = [to_xy.transform(mean_lon, lat)[1] for lat in lat_ticks]
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"{abs(lon):.1f}°W" for lon in lon_ticks],
                       fontsize=FS["size_small"])
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{lat:.2f}°N" for lat in lat_ticks],
                       fontsize=FS["size_small"])
    ax.tick_params(axis="both", which="both", direction="in", length=3.5,
                   width=0.7, top=True, right=True, bottom=True, left=True,
                   labelsize=FS["size_small"], pad=2)


def add_gis_graticule_frame(ax, crs: str) -> None:
    """GIS-style neatline graticule: labels and ticks on all four sides."""
    from pyproj import Transformer
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    corners = [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]
    lons, lats = zip(*[to_ll.transform(x, y) for x, y in corners])
    lon_vals = _regular_ticks(min(lons), max(lons), (0.05, 0.02, 0.1))
    lat_vals = _regular_ticks(min(lats), max(lats), (0.02, 0.01, 0.05))
    mean_lat = float(np.mean(lats))
    mean_lon = float(np.mean(lons))
    xticks = [to_xy.transform(lon, mean_lat)[0] for lon in lon_vals]
    yticks = [to_xy.transform(mean_lon, lat)[1] for lat in lat_vals]
    ax.set_xticks(xticks)
    ax.set_yticks(yticks)
    ax.set_xticklabels([f"{abs(lon):.2f}°W" for lon in lon_vals],
                       fontsize=FS["size_small"])
    ax.set_yticklabels([f"{lat:.2f}°N" for lat in lat_vals],
                       fontsize=FS["size_small"])
    ax.tick_params(axis="both", which="major", direction="in",
                   top=True, bottom=True, left=True, right=True,
                   labeltop=False, labelbottom=True, labelleft=True, labelright=False,
                   length=5.5, width=0.85, pad=2.5, labelsize=FS["size_small"])
    if len(lon_vals) >= 2:
        lon_half = float(lon_vals[1] - lon_vals[0]) / 2
        lon_minor = np.arange(lon_vals[0] - lon_half, lon_vals[-1] + lon_half, lon_half)
        lon_minor = lon_minor[(lon_minor >= min(lons)) & (lon_minor <= max(lons))]
        xminor = [to_xy.transform(lon, mean_lat)[0] for lon in lon_minor
                  if not any(np.isclose(lon, v) for v in lon_vals)]
        ax.set_xticks(xminor, minor=True)
    if len(lat_vals) >= 2:
        lat_half = float(lat_vals[1] - lat_vals[0]) / 2
        lat_minor = np.arange(lat_vals[0] - lat_half, lat_vals[-1] + lat_half, lat_half)
        lat_minor = lat_minor[(lat_minor >= min(lats)) & (lat_minor <= max(lats))]
        yminor = [to_xy.transform(mean_lon, lat)[1] for lat in lat_minor
                  if not any(np.isclose(lat, v) for v in lat_vals)]
        ax.set_yticks(yminor, minor=True)
    ax.tick_params(axis="both", which="minor", direction="in",
                   top=True, bottom=True, left=True, right=True,
                   length=3.0, width=0.55)


def add_north_arrow(ax, location: str = "upper right", style: str | None = None,
                    scale: float = 1.0) -> None:
    """Draw a north arrow; style from config maps.north_arrow_style unless overridden."""
    from visualization.north_arrows import add_north_arrow as _draw
    if style is None:
        style = STYLE.get("maps", {}).get("north_arrow_style", "usgs_classic")
    _draw(ax, style=style, location=location, scale=scale)


def map_axes(fig, data_aspect: float, left: float = 0.09, bottom: float = 0.13,
             max_width: float = 0.88, max_height: float = 0.82):
    """Add a map axes whose box matches geographic aspect (no inner gaps)."""
    fw, fh = fig.get_size_inches()
    target_wh = data_aspect * fh / fw
    if max_width / max_height > target_wh:
        w, h = max_height * target_wh, max_height
    else:
        w, h = max_width, max_width / target_wh
    return fig.add_axes([left, bottom, w, h])


def _fill_map_frame(ax) -> None:
    """Keep the current map limits; ensure raster fills the frame (no letterboxing)."""
    ax.set_autoscale_on(False)
    ax.margins(0)
    ax.set_aspect("auto")


def map_frame(ax, crs: str | None = None, ylabels: bool = True,
              xlabels: bool = True, equal: bool = True,
              gis_frame: bool = False) -> None:
    """Closed map frame; map data fills the box without stretching geography."""
    lw = STYLE["lines"]["axes_linewidth"]
    ax.set_facecolor("white" if gis_frame else "#D8D8D8")
    ax.margins(0)
    if equal:
        _fill_map_frame(ax)
    else:
        ax.set_aspect("auto")
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_linewidth(lw)
        s.set_color(COLORS["neutral_dark"])
        s.set_zorder(1000)
    ax.set_clip_on(True)
    if crs:
        if gis_frame:
            add_gis_graticule_frame(ax, crs)
        else:
            add_latlon_ticks(ax, crs)
            ax.tick_params(labeltop=False, labelright=False)
        if not ylabels:
            ax.set_yticklabels([])
            ax.tick_params(labelleft=False, labelright=False)
        if not xlabels:
            ax.set_xticklabels([])
            ax.tick_params(labeltop=False, labelbottom=False)
    else:
        ax.set_xticks([])
        ax.set_yticks([])


def clip_map_layers(ax) -> None:
    """Force raster/vector map layers to clip at the axes patch (neatline)."""
    patch = ax.patch
    for artist in list(ax.images) + list(ax.collections) + list(ax.lines):
        if artist.get_clip_on():
            artist.set_clip_path(patch)


def cover_frame_overflow(fig, ax, width: float = 0.004) -> None:
    """White strips just outside the neatline to hide sub-pixel raster bleed.

    Only top/right (no tick labels on those sides for GIS frames).
    """
    from matplotlib.patches import Rectangle
    pos = ax.get_position()
    strips = [
        (pos.x0 - width, pos.y1, pos.width + 2 * width, width),   # top
        (pos.x1, pos.y0, width, pos.height + width),              # right
    ]
    for x, y, w, h in strips:
        fig.add_artist(Rectangle(
            (x, y), w, h, transform=fig.transFigure, facecolor="white",
            edgecolor="none", zorder=20, clip_on=False,
        ))


def set_extent(ax, gdf, pad: float = 600, inset_m: float = 0.0) -> None:
    """Set map limits to the study view, clipped to DEM coverage (no empty frame).

    inset_m pulls limits inward (meters) to hide single-pixel export/frame seams.
    """
    minx, miny, maxx, maxy = (float(v) for v in gdf.total_bounds)
    minx, maxx = minx - pad, maxx + pad
    miny, maxy = miny - pad, maxy + pad
    _ensure_hillshade()
    left, right, bottom, top = _HS["ext"]
    x0, x1 = max(minx, left), min(maxx, right)
    y0, y1 = max(miny, bottom), min(maxy, top)
    if inset_m > 0:
        x0, x1 = x0 + inset_m, x1 - inset_m
        y0, y1 = y0 + inset_m, y1 - inset_m
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_autoscale_on(False)


def _ensure_hillshade() -> None:
    import rasterio
    from matplotlib.colors import LightSource

    if "hs" in _HS:
        return
    fp = ROOT / "data" / "raw" / "gee" / "dem_3dep_10m.tif"
    with rasterio.open(fp) as src:
        dem = src.read(1).astype("float64")
        b = src.bounds
    dem[dem < -100] = np.nan
    ls = LightSource(azdeg=315, altdeg=45)
    filled = np.nan_to_num(dem, nan=0.0)
    _HS["hs"] = ls.hillshade(filled, vert_exag=1.5, dx=10, dy=10)
    _HS["ocean"] = np.where(filled <= 0.5, 1.0, np.nan)
    _HS["ext"] = [b.left, b.right, b.bottom, b.top]


def hillshade_background(ax, alpha: float = 0.88, vmin: float = 0.12,
                         vmax: float = 0.98) -> list[float]:
    """Shared 10 m hillshade + ocean mask (cached)."""
    from matplotlib.colors import ListedColormap
    _ensure_hillshade()
    ax.imshow(_HS["hs"], cmap="Greys_r", extent=_HS["ext"], alpha=alpha,
              zorder=0, vmin=vmin, vmax=vmax, interpolation="bilinear",
              aspect="auto", clip_on=True)
    ax.imshow(_HS["ocean"], cmap=ListedColormap([COLORS["water"]]),
              extent=_HS["ext"], zorder=1, interpolation="nearest",
              aspect="auto", clip_on=True)
    return _HS["ext"]


def ocean_overlay(ax, zorder: int = 4) -> None:
    from matplotlib.colors import ListedColormap
    _ensure_hillshade()
    ax.imshow(_HS["ocean"], cmap=ListedColormap([COLORS["water"]]),
              extent=_HS["ext"], zorder=zorder, interpolation="nearest", aspect="auto")


def _ensure_fuel_water() -> None:
    import rasterio
    if "mask" in _FW:
        return
    fp = ROOT / "data" / "raw" / "landfire" / "lf2024_fbfm40.tif"
    with rasterio.open(fp) as src:
        fb = src.read(1)
        b = src.bounds
    _FW["mask"] = np.where(np.isin(fb, [98, 99]), 1.0, np.nan)
    _FW["ext"] = [b.left, b.right, b.bottom, b.top]


def fuel_water_overlay(ax, zorder: int = 3) -> None:
    """Paint LANDFIRE water (fuel codes 98/99) — same as panel c in Figure 3."""
    from matplotlib.colors import ListedColormap
    _ensure_fuel_water()
    ax.imshow(_FW["mask"], cmap=ListedColormap([FUEL_WATER_COLOR]),
              extent=_FW["ext"], zorder=zorder, interpolation="nearest", aspect="auto")


def save_figure(fig, name: str, formats=("pdf", "png"), pad_inches: float = 0.04) -> None:
    lock_plot_frames(fig)
    outdir = ROOT / "outputs" / "figures"
    outdir.mkdir(parents=True, exist_ok=True)
    msdir = ROOT / "manuscript" / "figures"
    msdir.mkdir(parents=True, exist_ok=True)
    for ext in formats:
        dest = outdir / f"{name}.{ext}"
        fig.savefig(dest, bbox_inches="tight", pad_inches=pad_inches,
                    facecolor="white", dpi=DPI if ext == "png" else DPI)
        shutil.copy2(dest, msdir / f"{name}.{ext}")
    plt.close(fig)
    print(f"saved {name} ({', '.join(formats)})")
