"""North arrow library — official-style symbols in assets/north_arrows/.

Set the style in config/figure_style.yaml:

    maps:
      north_arrow_style: usgs_classic   # or any name from list_north_arrows()

Generate a selection preview:

    python src/visualization/north_arrows.py
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, PathPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath
from svg.path import CubicBezier, Line, QuadraticBezier, parse_path
from svg.path.path import Close

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets" / "north_arrows"

DrawFn = Callable


def _edge(ax):
    from visualization.style import COLORS, FS
    return COLORS["neutral_dark"], FS


def _axes_y_scale(ax) -> float:
    """Correct transAxes y-units so symbols keep true SVG aspect on map axes."""
    bbox = ax.get_position()
    return bbox.width / bbox.height


def _svg_path_to_mpl(d: str, offset: tuple[float, float] = (0.0, 0.0)) -> MplPath:
    tx, ty = offset
    verts: list[tuple[float, float]] = []
    codes: list[int] = []
    prev_end: tuple[float, float] | None = None
    for seg in parse_path(d):
        start = (seg.start.real + tx, seg.start.imag + ty)
        if prev_end is None or start != prev_end:
            verts.append(start)
            codes.append(MplPath.MOVETO)
        if isinstance(seg, Line):
            end = (seg.end.real + tx, seg.end.imag + ty)
            verts.append(end)
            codes.append(MplPath.LINETO)
            prev_end = end
        elif isinstance(seg, CubicBezier):
            for p in (seg.control1, seg.control2, seg.end):
                verts.append((p.real + tx, p.imag + ty))
                codes.append(MplPath.CURVE4)
            prev_end = (seg.end.real + tx, seg.end.imag + ty)
        elif isinstance(seg, QuadraticBezier):
            for p in (seg.control, seg.end):
                verts.append((p.real + tx, p.imag + ty))
                codes.append(MplPath.CURVE3)
            prev_end = (seg.end.real + tx, seg.end.imag + ty)
        elif isinstance(seg, Close):
            codes.append(MplPath.CLOSEPOLY)
            verts.append(verts[-1])
    return MplPath(verts, codes)


def _place_mpl_path(ax, path: MplPath, cx: float, cy: float, height_frac: float) -> MplPath:
    """Map path vertices into axes coords; flip SVG y so north points up."""
    sy = _axes_y_scale(ax)
    verts = path.vertices
    xmin, ymin = verts.min(axis=0)
    xmax, ymax = verts.max(axis=0)
    xctr = (xmin + xmax) / 2
    bh = ymax - ymin
    s = height_frac / bh
    new = np.column_stack([
        cx + (verts[:, 0] - xctr) * s * sy,
        cy + (ymax - verts[:, 1]) * s,
    ])
    return MplPath(new, path.codes)


def _load_svg_path(svg_path: Path) -> tuple[str, tuple[float, float]]:
    root = ET.parse(svg_path).getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}
    g = root.find(".//svg:g", ns)
    tx, ty = 0.0, 0.0
    if g is not None:
        transform = g.get("transform", "")
        if "translate" in transform:
            parts = transform.replace("translate(", "").replace(")", "").replace(",", " ").split()
            tx, ty = float(parts[0]), float(parts[1])
    path_el = root.find(".//svg:path", ns)
    if path_el is None:
        raise ValueError(f"No path in {svg_path}")
    return path_el.get("d"), (tx, ty)


def _draw_svg_file(ax, svg_path: Path, cx: float, cy: float, scale: float,
                   height_frac: float = 0.095) -> None:
    edge, _ = _edge(ax)
    d, offset = _load_svg_path(svg_path)
    path = _place_mpl_path(ax, _svg_path_to_mpl(d, offset), cx, cy, height_frac * scale)
    ax.add_patch(PathPatch(
        path, facecolor=edge, edgecolor=edge, linewidth=0,
        transform=ax.transAxes, zorder=650, clip_on=False,
    ))


def _usgs_classic(ax, cx, cy, scale):
    edge, FS = _edge(ax)
    h, w, stem = 0.044 * scale, 0.020 * scale, 0.016 * scale
    y0 = cy - h - stem
    ax.plot([cx, cx], [y0, y0 + stem], transform=ax.transAxes, color=edge,
            linewidth=1.0, zorder=650, clip_on=False)
    ax.add_patch(Polygon(
        [(cx, y0 + stem + h), (cx - w / 2, y0 + stem), (cx + w / 2, y0 + stem)],
        closed=True, transform=ax.transAxes, facecolor=edge, edgecolor=edge,
        linewidth=0.5, zorder=651, clip_on=False))
    ax.text(cx, y0 + stem + h + 0.006, "N", transform=ax.transAxes,
            ha="center", va="bottom", fontsize=FS["size_label"],
            fontweight="bold", color=edge, zorder=652, clip_on=False)


def _arcgis_split(ax, cx, cy, scale):
    """Match assets/north_arrows/arcgis_split.svg (isotropic scaling)."""
    edge, FS = _edge(ax)
    sy = _axes_y_scale(ax)
    s = 0.00155 * scale
    y_n = cy

    def p(x, y):
        return cx + (x - 24) * s, y_n + (58 - y) * s * sy

    left = [p(24, 6), p(6, 36), p(24, 28)]
    right = [p(24, 6), p(24, 28), p(42, 36)]
    kw = dict(transform=ax.transAxes, linewidth=0.55, zorder=650, clip_on=False)
    ax.add_patch(Polygon(left, closed=True, facecolor="white", edgecolor=edge, **kw))
    ax.add_patch(Polygon(right, closed=True, facecolor=edge, edgecolor=edge, **kw))
    ax.text(*p(24, 55), "N", transform=ax.transAxes, ha="center", va="center",
            fontsize=max(10.0, FS["size_label"] * 1.55 * scale), fontweight="bold",
            color=edge, zorder=652, clip_on=False)


def _north_arrow_2(ax, cx, cy, scale):
    """OpenClipart split north arrow from assets/north_arrows/north-arrow-2.svg."""
    _draw_svg_file(ax, ASSETS / "north-arrow-2.svg", cx, cy, scale, height_frac=0.10)


def _compass_cardinal(ax, cx, cy, scale):
    edge, FS = _edge(ax)
    r = 0.026 * scale
    pad = 0.006 * scale
    ax.add_patch(Circle((cx, cy), r, transform=ax.transAxes, facecolor="white",
                        edgecolor=edge, linewidth=0.65, alpha=0.94,
                        zorder=650, clip_on=False))
    ah, aw = r * 0.72, r * 0.26
    ax.add_patch(Polygon([(cx, cy + ah), (cx - aw, cy - ah * 0.15), (cx + aw, cy - ah * 0.15)],
                         closed=True, transform=ax.transAxes, facecolor=edge,
                         edgecolor=edge, linewidth=0.35, zorder=651, clip_on=False))
    fs = FS["size_small"] * 0.92
    for text, x, y, ha, va, fw in (
        ("N", cx, cy + r + pad, "center", "bottom", "bold"),
        ("S", cx, cy - r - pad, "center", "top", "normal"),
        ("E", cx + r + pad, cy, "left", "center", "normal"),
        ("W", cx - r - pad, cy, "right", "center", "normal"),
    ):
        ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va,
                fontsize=FS["size_label"] * 0.82 if text == "N" else fs,
                fontweight=fw, color=edge, zorder=652, clip_on=False)


def _iso_simple(ax, cx, cy, scale):
    edge, FS = _edge(ax)
    h, w = 0.048 * scale, 0.024 * scale
    y0 = cy - h
    ax.add_patch(Polygon([(cx, y0 + h), (cx - w / 2, y0), (cx + w / 2, y0)],
                         closed=True, transform=ax.transAxes, facecolor=edge,
                         edgecolor=edge, linewidth=0.5, zorder=651, clip_on=False))
    ax.text(cx, y0 + h + 0.006, "N", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=FS["size_label"], fontweight="bold", color=edge, zorder=652, clip_on=False)


def _os_uk(ax, cx, cy, scale):
    edge, FS = _edge(ax)
    r = 0.028 * scale
    ax.add_patch(Circle((cx, cy), r, transform=ax.transAxes, facecolor="none",
                        edgecolor=edge, linewidth=0.65, zorder=650, clip_on=False))
    ax.plot([cx, cx], [cy - r * 0.15, cy + r * 0.85], transform=ax.transAxes,
            color=edge, linewidth=1.1, zorder=651, clip_on=False)
    ah, aw = r * 0.35, r * 0.22
    ax.add_patch(Polygon([(cx, cy + r * 0.95), (cx - aw, cy + r * 0.55),
                          (cx + aw, cy + r * 0.55)],
                         closed=True, transform=ax.transAxes, facecolor=edge,
                         edgecolor=edge, linewidth=0.4, zorder=652, clip_on=False))
    ax.text(cx, cy - r - 0.005, "N", transform=ax.transAxes, ha="center", va="top",
            fontsize=FS["size_label"] * 0.85, fontweight="bold", color=edge, zorder=653, clip_on=False)


def _esri_arrow(ax, cx, cy, scale):
    edge, FS = _edge(ax)
    h, w, shaft = 0.050 * scale, 0.022 * scale, 0.028 * scale
    y0 = cy - h - shaft
    y_head = y0 + shaft
    ax.add_patch(Rectangle((cx - w * 0.18, y0), w * 0.36, shaft, transform=ax.transAxes,
                           facecolor=edge, edgecolor=edge, linewidth=0.4, zorder=650, clip_on=False))
    ax.add_patch(Polygon([(cx, y_head + h), (cx - w, y_head + h * 0.35), (cx, y_head)],
                         closed=True, transform=ax.transAxes, facecolor=edge, edgecolor=edge,
                         linewidth=0.4, zorder=651, clip_on=False))
    ax.add_patch(Polygon([(cx, y_head + h), (cx, y_head), (cx + w, y_head + h * 0.35)],
                         closed=True, transform=ax.transAxes, facecolor=edge, edgecolor=edge,
                         linewidth=0.4, zorder=651, clip_on=False))
    ax.text(cx, y0 - 0.004, "N", transform=ax.transAxes, ha="center", va="top",
            fontsize=FS["size_label"] * 0.85, fontweight="bold", color=edge, zorder=652, clip_on=False)


def _qgis_default(ax, cx, cy, scale):
    edge, FS = _edge(ax)
    h, w = 0.046 * scale, 0.024 * scale
    y0 = cy - h
    ax.add_patch(Polygon([(cx, y0 + h), (cx - w, y0 + h * 0.25), (cx, y0 + h * 0.55),
                          (cx + w, y0 + h * 0.25)],
                         closed=True, transform=ax.transAxes, facecolor=edge,
                         edgecolor=edge, linewidth=0.5, zorder=651, clip_on=False))
    ax.text(cx, y0 - 0.004, "N", transform=ax.transAxes, ha="center", va="top",
            fontsize=FS["size_label"], fontweight="bold", color=edge, zorder=652, clip_on=False)


NORTH_ARROWS: dict[str, dict] = {
    "usgs_classic": {
        "label": "USGS classic (triangle + stem)",
        "svg": "usgs_classic.svg",
        "draw": _usgs_classic,
    },
    "arcgis_split": {
        "label": "ArcGIS split chevron",
        "svg": "arcgis_split.svg",
        "draw": _arcgis_split,
    },
    "north_arrow_2": {
        "label": "OpenClipart split arrow + N",
        "svg": "north-arrow-2.svg",
        "draw": _north_arrow_2,
    },
    "compass_cardinal": {
        "label": "Compass rose (N/S/E/W)",
        "svg": "compass_cardinal.svg",
        "draw": _compass_cardinal,
    },
    "iso_simple": {
        "label": "ISO simple triangle",
        "svg": "iso_simple.svg",
        "draw": _iso_simple,
    },
    "os_uk": {
        "label": "Ordnance Survey (circle + barb)",
        "svg": "os_uk.svg",
        "draw": _os_uk,
    },
    "esri_arrow": {
        "label": "Esri layout arrow",
        "svg": "esri_arrow.svg",
        "draw": _esri_arrow,
    },
    "qgis_default": {
        "label": "QGIS default",
        "svg": "qgis_default.svg",
        "draw": _qgis_default,
    },
}

_LOCATIONS = {
    "upper right": (0.928, 0.898),
    "upper left": (0.072, 0.898),
}


def list_north_arrows() -> list[str]:
    return list(NORTH_ARROWS)


def add_north_arrow(ax, style: str = "usgs_classic", location: str = "upper right",
                    scale: float = 1.0) -> None:
    """Draw a north arrow on *ax* using a named style from assets/north_arrows/."""
    if style not in NORTH_ARROWS:
        opts = ", ".join(NORTH_ARROWS)
        raise ValueError(f"Unknown north arrow {style!r}. Choose from: {opts}")
    cx, cy = _LOCATIONS.get(location, _LOCATIONS["upper right"])
    NORTH_ARROWS[style]["draw"](ax, cx, cy, scale)


def make_preview(out: Path | None = None) -> Path:
    """Render all north-arrow styles on one sheet for selection."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from visualization.style import CM, W_DOUBLE, apply_style, full_frame

    apply_style()
    styles = list(NORTH_ARROWS)
    ncols = 4
    nrows = (len(styles) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(W_DOUBLE, 6.5 * nrows * CM))
    axes = axes.flatten() if nrows > 1 else ([axes] if ncols == 1 else axes.flatten())

    for ax, name in zip(axes, styles):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.axis("off")
        info = NORTH_ARROWS[name]
        add_north_arrow(ax, style=name, location="upper right", scale=1.35)
        ax.set_xlim(0.78, 1.02)
        ax.set_ylim(0.82, 1.02)
        ax.text(0.02, 0.06, name, transform=ax.transAxes, fontsize=7, fontweight="bold")
        ax.text(0.02, 0.0, info["label"], transform=ax.transAxes, fontsize=6, color="#555555")
        full_frame(ax)

    for ax in axes[len(styles):]:
        ax.axis("off")

    fig.suptitle("North arrow styles — set maps.north_arrow_style in config/figure_style.yaml",
                 fontsize=9, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out = out or ASSETS / "preview_all.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out}")
    return out


if __name__ == "__main__":
    make_preview()
