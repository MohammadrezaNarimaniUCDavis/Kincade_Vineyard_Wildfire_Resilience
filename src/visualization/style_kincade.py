"""Publication figure style for Kincade — Palisades grammar, vineyard palette."""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

try:
    from visualization import style as _s

    apply_style = _s.apply_style
    panel_label = _s.panel_label
    full_frame = _s.full_frame
    lock_plot_frames = _s.lock_plot_frames
    resolve_font_family = _s.resolve_font_family
    add_cbar = _s.add_cbar
    add_scalebar = _s.add_scalebar
    add_north_arrow = _s.add_north_arrow
    map_frame = _s.map_frame
    map_axes = _s.map_axes
    hillshade_background = _s.hillshade_background
    set_extent = _s.set_extent
    clip_map_layers = _s.clip_map_layers
    cover_frame_overflow = _s.cover_frame_overflow
    ocean_overlay = _s.ocean_overlay
    W_SINGLE = _s.W_SINGLE
    W_DOUBLE = _s.W_DOUBLE
    DPI = _s.DPI
    COLORS = _s.COLORS
    PALETTES = _s.PALETTES
    FS = _s.FS
    STYLE = _s.STYLE
    ROOT = _s.ROOT
except Exception as exc:
    import yaml

    print(f"[style_kincade] fallback ({exc})")
    ROOT = Path(__file__).resolve().parents[2]
    with open(ROOT / "config" / "figure_style.yaml", encoding="utf-8") as f:
        STYLE = yaml.safe_load(f)
    CM = 1 / 2.54
    W_SINGLE = STYLE["figure"]["width_single_cm"] * CM
    W_DOUBLE = STYLE["figure"]["width_double_cm"] * CM
    DPI = STYLE["figure"]["dpi_raster"]
    COLORS = STYLE["colors"]
    PALETTES = STYLE["palettes"]
    FS = STYLE["fonts"]

    def resolve_font_family() -> str:
        from matplotlib import font_manager as fm
        for name in ("Helvetica", "Arial", "FreeSans", "DejaVu Sans"):
            if name in {f.name for f in fm.fontManager.ttflist}:
                return name
        return "sans-serif"

    def apply_style() -> None:
        fam = resolve_font_family()
        mpl.rcParams.update({
            "font.family": fam,
            "font.size": FS["size_base"],
            "axes.labelsize": FS["size_label"],
            "xtick.labelsize": FS["size_small"],
            "ytick.labelsize": FS["size_small"],
            "legend.fontsize": FS["size_small"],
            "axes.linewidth": 1.0,
            "xtick.direction": "in", "ytick.direction": "in",
            "xtick.top": True, "ytick.right": True,
            "savefig.dpi": DPI, "savefig.facecolor": "white",
            "pdf.fonttype": 42,
        })

    def full_frame(ax, twin=None) -> None:
        for s in ax.spines.values():
            s.set_visible(True)
            s.set_linewidth(1.0)

    def panel_label(ax, letter, title=None, loc="center"):
        t = f"({letter.strip('()')})  {title}" if title else f"({letter.strip('()')})"
        ax.set_title(t, loc=loc, fontsize=FS["size_panel_label"],
                     fontweight="bold", pad=8, color=COLORS["neutral_dark"])

    def lock_plot_frames(fig) -> None:
        for ax in fig.axes:
            if ax.get_label() == "colorbar":
                continue
            for s in ax.spines.values():
                s.set_visible(True)

FINAL_DIR = ROOT / "outputs" / "figures" / "final"
MS_FINAL_DIR = ROOT / "manuscript" / "figures" / "final"

# Unified series colors — use everywhere for consistency
SERIES = {
    "vineyard": COLORS["vineyard"],
    "vineyard_fill": "#7B68A6",
    "wildland": COLORS["wildland"],
    "wildland_fill": "#5AA469",
    "moisture": COLORS["moisture"],
    "moisture_fill": "#7FBFB8",
    "moisture_band": "#B8DDD8",
    "thermal": COLORS["thermal"],
    "electrical": COLORS["electrical"],
    "severity": COLORS["severity_high"],
    "severity_mid": COLORS["severity_mod"],
    "severity_light": COLORS["severity_low"],
    "smoke_heavy": COLORS["smoke"],
    "smoke_med": "#9E7BB5",
    "smoke_light": "#C9B3DC",
    "road": COLORS["road"],
    "road_major": COLORS["accent"],
    "inside": COLORS["severity_mod"],
    "outside": COLORS["wildland"],
    "regression": "#4A3728",
    "neutral": COLORS["neutral_mid"],
    "perimeter": COLORS["perimeter"],
    "hazard": COLORS["severity_high"],
    "analysis": COLORS["moisture"],
    "synthesis": COLORS["vineyard"],
}

# Workflow column tints (light bg + dark edge text)
WORKFLOW = {
    "hazard": ("#F5E6E0", COLORS["severity_high"]),
    "exposed": ("#EDE8F4", COLORS["vineyard"]),
    "analysis": ("#E3F0EE", COLORS["moisture"]),
    "synthesis": ("#EDE8F4", COLORS["vineyard"]),
}

LEGEND_KW = dict(
    frameon=True, fancybox=False, framealpha=1.0,
    edgecolor="#BDBDBD", borderpad=0.5, handletextpad=0.45,
    columnspacing=0.9, handlelength=1.6,
)


def style_axes(ax, grid: bool = False) -> None:
    """Apply full frame + inward ticks."""
    lw = STYLE["lines"]["axes_linewidth"]
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_linewidth(lw)
        s.set_color(COLORS["neutral_dark"])
    ax.tick_params(which="both", direction="in", top=True, right=True,
                   length=3.0, width=0.7, labelsize=FS["size_small"])
    ax.grid(grid, alpha=STYLE["lines"]["grid_alpha"], linewidth=0.5)
    ax.set_axisbelow(True)


def stat_annotation(ax, text: str, loc: str = "upper left", pad: float = 0.04) -> None:
    """Place stats in a clean white box, away from dense data."""
    anchors = {
        "upper left": (pad, 1 - pad, "left", "top"),
        "upper right": (1 - pad, 1 - pad, "right", "top"),
        "lower left": (pad, pad, "left", "bottom"),
        "lower right": (1 - pad, pad, "right", "bottom"),
    }
    x, y, ha, va = anchors.get(loc, anchors["upper left"])
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va,
            fontsize=FS["size_small"], color=COLORS["neutral_dark"],
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                      edgecolor="#BDBDBD", linewidth=0.6, alpha=0.96),
            zorder=10, linespacing=1.35)


def fig_legend(fig, handles, labels, ncol: int = 3, y: float = 0.02, title: str | None = None):
    """Figure-level legend below panels — avoids covering data."""
    leg = fig.legend(handles, labels, loc="lower center", ncol=ncol,
                     bbox_to_anchor=(0.5, y), **LEGEND_KW,
                     title=title, title_fontsize=FS.get("size_legend_title", FS["size_label"]))
    return leg


def save_figure(fig, name: str, tif: bool = True, pad_inches: float = 0.04) -> dict:
    try:
        lock_plot_frames(fig)
    except Exception:
        pass
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    MS_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    pdf = FINAL_DIR / f"{name}.pdf"
    fig.savefig(pdf, bbox_inches="tight", pad_inches=pad_inches, facecolor="white")
    written["pdf"] = str(pdf)

    png = FINAL_DIR / f"{name}.png"
    fig.savefig(png, bbox_inches="tight", pad_inches=pad_inches,
                facecolor="white", dpi=DPI)
    written["png"] = str(png)

    if tif:
        tifp = FINAL_DIR / f"{name}.tif"
        fig.savefig(tifp, bbox_inches="tight", pad_inches=pad_inches,
                    facecolor="white", dpi=DPI,
                    pil_kwargs={"compression": "tiff_lzw"})
        _ensure_rgb_tiff(tifp)
        written["tif"] = str(tifp)

    import shutil
    shutil.copy2(png, MS_FINAL_DIR / f"{name}.png")
    plt.close(fig)
    print(f"  saved {name}: {', '.join(written.keys())}")
    return written


def _ensure_rgb_tiff(path: Path) -> None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            if im.mode != "RGB":
                im.convert("RGB").save(path, format="TIFF",
                                       compression="tiff_lzw", dpi=(DPI, DPI))
    except Exception as exc:
        print(f"  [warn] RGB TIFF {path.name}: {exc}")
