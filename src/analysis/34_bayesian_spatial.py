"""
34_bayesian_spatial.py — Landscape spatial GAM for Kincade burn severity.

Fits a penalized-spline spatial GAM (pygam LinearGAM) to explain S2 dNBR burn
severity across a 250 m regular grid inside the Kincade fire perimeter.

Spatial confounding is addressed with thin-plate-spline approximations on
normalised UTM coordinates (s(x) + s(y), 20 B-spline knots each). Covariate
terms are linear (l()):  vineyard fraction, elevation, slope, and growing-season
ET mean (OpenET Apr–Oct 2019, if available).

This model is honestly labelled "spatial GAM / penalized spline" — NOT Bayesian
(no MCMC; PyMC HSGP was not attempted because pygam performed adequately and the
grid has ~5 k cells).

Residual spatial autocorrelation: Moran's I (k = 8 KNN weights, esda).
Multicollinearity: Pearson correlation matrix saved to outputs/qa/.

Outputs
-------
outputs/tables/table_spatial_gam.csv
outputs/tables/spatial_model_summary.json
outputs/figures/data/fig07_spatial_partial.csv
outputs/qa/predictor_corr.csv
outputs/result_registry.csv      (appended)
docs/METHODS_LOG.md               (appended)
outputs/logs/34_bayesian_spatial.log
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features as rio_features
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject as rio_reproject

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parents[2]
RAW     = ROOT / "data" / "raw"
OUT     = ROOT / "outputs"
TABLES  = OUT / "tables"
FIGDATA = OUT / "figures" / "data"
QA      = OUT / "qa"
LOGDIR  = OUT / "logs"
DOCS    = ROOT / "docs"
REGISTRY = OUT / "result_registry.csv"

for _p in (TABLES, FIGDATA, QA, LOGDIR):
    _p.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE = LOGDIR / "34_bayesian_spatial.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("spatial_gam")

CRS    = "EPSG:26910"
GRID_M = 250
SEED   = 42

sys.path.insert(0, str(ROOT / "src" / "analysis"))
from analysis_common import append_registry, utcnow  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Build 250 m analysis grid masked to fire perimeter
# ══════════════════════════════════════════════════════════════════════════════

def build_grid(perim_path: Path, cell_m: int = 250):
    """Return (transform, shape, mask_2d, perim_gdf) for a regular grid."""
    perim = gpd.read_file(perim_path).to_crs(CRS)
    b = perim.total_bounds  # xmin ymin xmax ymax

    xmin = np.floor(b[0] / cell_m) * cell_m
    ymin = np.floor(b[1] / cell_m) * cell_m
    xmax = np.ceil(b[2]  / cell_m) * cell_m
    ymax = np.ceil(b[3]  / cell_m) * cell_m

    ncols = int(round((xmax - xmin) / cell_m))
    nrows = int(round((ymax - ymin) / cell_m))
    transform = from_origin(xmin, ymax, cell_m, cell_m)
    shape = (nrows, ncols)

    geoms = ((g, 1) for g in perim.geometry)
    mask = rio_features.rasterize(
        geoms, out_shape=shape, transform=transform,
        fill=0, dtype=np.uint8, all_touched=False,
    )
    n_in = int(mask.sum())
    log.info("Grid %d×%d, %d cells inside perimeter (cell=%d m)", nrows, ncols, n_in, cell_m)
    return transform, shape, mask.astype(bool), perim


# ══════════════════════════════════════════════════════════════════════════════
# 2.  Resample a single raster band to the analysis grid
# ══════════════════════════════════════════════════════════════════════════════

def resample_raster(
    src_path: Path,
    dst_transform,
    dst_shape: tuple[int, int],
    band: int = 1,
    resampling=Resampling.bilinear,
    src_nodata: float | None = None,
) -> np.ndarray:
    """Read *band* from *src_path*, reproject/resample to dst grid → 2-D float32."""
    with rasterio.open(src_path) as src:
        nd = src_nodata if src_nodata is not None else src.nodata
        dst = np.full(dst_shape, np.nan, dtype=np.float32)
        rio_reproject(
            source=rasterio.band(src, band),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=CRS,
            resampling=resampling,
            src_nodata=nd,
            dst_nodata=np.nan,
        )
    return dst


# ══════════════════════════════════════════════════════════════════════════════
# 3.  OpenET growing-season mean  (Apr–Oct = bands 1–7)
# ══════════════════════════════════════════════════════════════════════════════

def openet_gs_mean(tif_path: Path, dst_transform, dst_shape: tuple[int, int]) -> np.ndarray:
    """Mean ET across all 7 growing-season bands (Apr–Oct 2019). NoData = -9999."""
    with rasterio.open(tif_path) as src:
        n_bands = src.count
        log.info("OpenET: %d bands, shape %s, nodata %s", n_bands, src.shape, src.nodata)

    stacked = []
    for b in range(1, n_bands + 1):
        arr = resample_raster(tif_path, dst_transform, dst_shape,
                              band=b, resampling=Resampling.bilinear,
                              src_nodata=-9999.0)
        arr[arr < -100] = np.nan          # belt-and-suspenders nodata guard
        stacked.append(arr)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_et = np.nanmean(np.stack(stacked, axis=0), axis=0)

    valid = int(np.isfinite(mean_et).sum())
    log.info("ET gs-mean: min=%.1f  max=%.1f mm/month  valid cells=%d",
             float(np.nanmin(mean_et)), float(np.nanmax(mean_et)), valid)
    return mean_et


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Vineyard fraction via fine sub-grid → average
# ══════════════════════════════════════════════════════════════════════════════

def vineyard_fraction(
    vy_path: Path,
    dst_transform,
    dst_shape: tuple[int, int],
    sub_factor: int = 10,
) -> np.ndarray:
    """
    Rasterize vineyard polygons at (cell_m / sub_factor) m → average to 250 m.
    Produces a true areal fraction in [0, 1].
    """
    vy = gpd.read_file(vy_path).to_crs(CRS)
    log.info("Vineyard polygons: %d features", len(vy))

    nrows, ncols = dst_shape
    sub_rows = nrows * sub_factor
    sub_cols = ncols * sub_factor
    ox = dst_transform.c   # upper-left x
    oy = dst_transform.f   # upper-left y
    sub_res = dst_transform.a / sub_factor
    sub_transform = from_origin(ox, oy, sub_res, sub_res)

    geoms = ((g, 1) for g in vy.geometry if g is not None and not g.is_empty)
    fine = rio_features.rasterize(
        geoms,
        out_shape=(sub_rows, sub_cols),
        transform=sub_transform,
        fill=0,
        dtype=np.uint8,
    )
    frac = fine.astype(np.float32).reshape(nrows, sub_factor, ncols, sub_factor).mean(axis=(1, 3))
    log.info("Vineyard fraction: max=%.3f  mean=%.4f (all grid cells)", frac.max(), frac.mean())
    return frac


# ══════════════════════════════════════════════════════════════════════════════
# 5.  Slope from DEM (numerical gradient at 250 m)
# ══════════════════════════════════════════════════════════════════════════════

def compute_slope(elev: np.ndarray, cell_m: float = 250.0) -> np.ndarray:
    """Slope in degrees from 2-D elevation array at *cell_m* resolution."""
    safe = np.where(np.isfinite(elev), elev, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        dy, dx = np.gradient(safe, cell_m, cell_m)
    slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2))).astype(np.float32)
    slope[~np.isfinite(elev)] = np.nan
    return slope


# ══════════════════════════════════════════════════════════════════════════════
# 6.  Assemble analysis DataFrame
# ══════════════════════════════════════════════════════════════════════════════

def build_dataframe(
    transform, shape: tuple[int, int], mask: np.ndarray,
    layers: dict[str, np.ndarray],
) -> pd.DataFrame:
    rows_idx, cols_idx = np.where(mask)
    xs = transform.c + (cols_idx + 0.5) * transform.a
    ys = transform.f + (rows_idx + 0.5) * transform.e  # e < 0

    rec: dict[str, np.ndarray] = {
        "row": rows_idx, "col": cols_idx, "x_utm": xs, "y_utm": ys,
    }
    for name, arr in layers.items():
        rec[name] = arr[rows_idx, cols_idx]

    df = pd.DataFrame(rec)
    n0 = len(df)
    df = df[np.isfinite(df["dnbr"])].copy()
    log.info("Valid dNBR: %d / %d cells (%.1f%%)", len(df), n0, 100 * len(df) / max(n0, 1))
    df = df.dropna(subset=["elev", "slope"]).reset_index(drop=True)
    log.info("After dropping NaN elev/slope: %d cells", len(df))
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 7.  Moran's I on residuals
# ══════════════════════════════════════════════════════════════════════════════

def moran_residuals(df: pd.DataFrame, resid: np.ndarray, k: int = 8) -> dict:
    try:
        import libpysal
        from esda import Moran
        coords = df[["x_utm", "y_utm"]].values
        w = libpysal.weights.KNN.from_array(coords, k=k)
        w.transform = "r"
        mi = Moran(resid, w)
        log.info("Moran's I (k=%d): I=%.4f  E[I]=%.6f  p_sim=%.4f", k, mi.I, mi.EI, mi.p_sim)
        return {
            "moran_I": float(mi.I),
            "moran_EI": float(mi.EI),
            "moran_z_sim": float(mi.z_sim),
            "moran_p_sim": float(mi.p_sim),
            "k_neighbors": k,
        }
    except ImportError:
        log.info("libpysal/esda not available — Moran's I skipped")
        return {"note": "libpysal/esda not available"}
    except Exception as exc:
        log.warning("Moran's I failed: %s", exc)
        return {"note": f"Moran failed: {exc}"}


# ══════════════════════════════════════════════════════════════════════════════
# 8.  Coefficient extraction helpers
# ══════════════════════════════════════════════════════════════════════════════

def _term_n_coefs(term) -> int:
    for attr in ("n_coefs", "n_splines", "num_knots"):
        v = getattr(term, attr, None)
        if v is not None:
            return int(v)
    # Fallback: count the relevant slice via coef_indices if available
    ci = getattr(term, "coef_indices", None)
    if ci is not None:
        return len(ci)
    return 1


def extract_coef_table(
    gam, feature_order: list[str], n_spatial: int
) -> pd.DataFrame:
    """Return a coefficient table with CIs for all GAM terms."""
    from pygam import l as pygam_l

    stats = gam.statistics_
    coef  = gam.coef_

    # pygam 0.12 exposes 'se' (per-coef SE) and 'cov' (covariance matrix)
    if "se" in stats:
        has_cov = True
        se_all  = np.asarray(stats["se"])
    elif "cov" in stats:
        has_cov = True
        try:
            cov_mat = np.atleast_2d(np.asarray(stats["cov"]))
            se_all  = np.sqrt(np.abs(np.diag(cov_mat)))
        except Exception:
            has_cov = False
            se_all  = np.zeros_like(coef)
    elif "cov_params" in stats:
        has_cov = True
        try:
            cov_mat = np.atleast_2d(np.asarray(stats["cov_params"]))
            se_all  = np.sqrt(np.abs(np.diag(cov_mat)))
        except Exception:
            has_cov = False
            se_all  = np.zeros_like(coef)
    else:
        has_cov = False
        se_all  = np.zeros_like(coef)
        log.warning("No SE/cov in gam.statistics_ — CIs will be NaN")

    # p-values are per-term in pygam
    p_vals = list(stats.get("p_values", [np.nan] * len(gam.terms)))

    rows = []
    coef_offset = 0

    for i, term in enumerate(gam.terms):
        n_c = _term_n_coefs(term)
        t_coef = coef[coef_offset: coef_offset + n_c]
        tname  = type(term).__name__   # e.g. SplineTerm, LinearTerm, InterceptTerm

        feat = getattr(term, "feature", None)
        if feat is not None and feat < len(feature_order):
            fname = feature_order[feat]
        else:
            fname = "intercept" if "Intercept" in tname else f"term_{i}"

        is_linear    = "Linear" in tname
        is_intercept = "Intercept" in tname

        if is_linear or is_intercept:
            c_val  = float(t_coef[0]) if len(t_coef) > 0 else np.nan
            se_val = float(se_all[coef_offset]) if has_cov and coef_offset < len(se_all) else np.nan
            ci_lo  = c_val - 1.96 * se_val if np.isfinite(se_val) else np.nan
            ci_hi  = c_val + 1.96 * se_val if np.isfinite(se_val) else np.nan
            rows.append({
                "term": fname,
                "term_type": "intercept" if is_intercept else "linear",
                "coef": c_val, "se": se_val,
                "ci_lo_95": ci_lo, "ci_hi_95": ci_hi,
                "p_value": float(p_vals[i]) if i < len(p_vals) else np.nan,
                "edf": 1.0,
            })
        else:
            # Smooth / spline term
            rows.append({
                "term": fname,
                "term_type": "smooth_spline",
                "coef": np.nan, "se": np.nan,
                "ci_lo_95": np.nan, "ci_hi_95": np.nan,
                "p_value": float(p_vals[i]) if i < len(p_vals) else np.nan,
                "edf": float(n_c),
            })

        coef_offset += n_c

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# 9.  Partial-dependence curves for fig07
# ══════════════════════════════════════════════════════════════════════════════

def partial_dependence_df(gam, feature_order: list[str]) -> pd.DataFrame:
    frames = []
    for i, fname in enumerate(feature_order):
        try:
            XX = gam.generate_X_grid(term=i)
            pdep = gam.partial_dependence(term=i, X=XX)
            try:
                _, confi = gam.partial_dependence(term=i, X=XX, width=0.95)
                lo = confi[:, 0]
                hi = confi[:, 1]
            except Exception:
                lo = np.full(len(pdep), np.nan)
                hi = np.full(len(pdep), np.nan)

            frames.append(pd.DataFrame({
                "feature":        fname,
                "x_val":          XX[:, i] if XX.ndim > 1 else XX.ravel(),
                "partial_effect": pdep,
                "ci_lo":          lo,
                "ci_hi":          hi,
            }))
        except Exception as exc:
            log.warning("Partial dependence failed for %s: %s", fname, exc)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t0 = datetime.now(timezone.utc)
    log.info("=== 34_bayesian_spatial.py START ===")

    # ── Data paths ─────────────────────────────────────────────────────────
    perim_path  = RAW / "fire"      / "kincade_perimeter.gpkg"
    s2_path     = RAW / "gee"       / "s2_burn_severity.tif"
    dem_path    = RAW / "gee"       / "dem_3dep_10m.tif"
    openet_path = RAW / "gee"       / "openet_monthly_2019.tif"
    vy_path     = RAW / "vineyards" / "kincade_vineyards.gpkg"

    # ── 1. Grid ──────────────────────────────────────────────────────────
    log.info("--- Step 1: Build 250 m grid ---")
    transform, shape, mask, perim_gdf = build_grid(perim_path, GRID_M)
    n_perim_cells = int(mask.sum())

    # ── 2. Rasters → 250 m ───────────────────────────────────────────────
    log.info("--- Step 2: Resample rasters ---")

    log.info("S2 dNBR …")
    dnbr = resample_raster(s2_path, transform, shape, band=1)

    log.info("3DEP elevation (10 m → 250 m) …")
    elev = resample_raster(dem_path, transform, shape, band=1)

    log.info("Slope from 250 m DEM …")
    slope = compute_slope(elev, float(GRID_M))

    log.info("OpenET growing-season mean …")
    et_mean      = openet_gs_mean(openet_path, transform, shape)
    et_available = bool(np.isfinite(et_mean[mask]).sum() > 10)
    log.info("ET available: %s", et_available)

    log.info("Vineyard fraction (25 m sub-grid) …")
    vy_frac = vineyard_fraction(vy_path, transform, shape, sub_factor=10)

    # ── 3. Assemble DataFrame ─────────────────────────────────────────────
    log.info("--- Step 3: Assemble DataFrame ---")
    layers: dict[str, np.ndarray] = {
        "dnbr":         dnbr,
        "vineyard_frac": vy_frac,
        "elev":         elev,
        "slope":        slope,
    }
    if et_available:
        layers["et_mean"] = et_mean

    df = build_dataframe(transform, shape, mask, layers)
    n_valid = len(df)
    log.info("Analysis cells: %d", n_valid)

    if n_valid < 50:
        log.error("Too few valid cells (%d) — cannot fit model", n_valid)
        sys.exit(1)

    # Covariate columns (order matters for GAM term indexing)
    pred_cols = ["vineyard_frac", "elev", "slope"]
    if et_available and "et_mean" in df.columns:
        pred_cols.append("et_mean")

    df = df.dropna(subset=pred_cols).reset_index(drop=True)
    log.info("After dropping predictor NaN: %d cells", len(df))

    # ── 4. Multicollinearity ─────────────────────────────────────────────
    log.info("--- Step 4: Predictor correlation matrix ---")
    corr = df[pred_cols].corr(method="pearson")
    corr.to_csv(QA / "predictor_corr.csv")
    log.info("predictor_corr.csv saved\n%s", corr.round(3).to_string())

    # ── 5. Normalise coordinates ──────────────────────────────────────────
    x_c, x_s = df["x_utm"].mean(), df["x_utm"].std()
    y_c, y_s = df["y_utm"].mean(), df["y_utm"].std()
    df["x_norm"] = (df["x_utm"] - x_c) / x_s
    df["y_norm"] = (df["y_utm"] - y_c) / y_s
    spatial_cols  = ["x_norm", "y_norm"]
    feature_order = spatial_cols + pred_cols

    # Design matrix: [x_norm, y_norm, vineyard_frac, elev, slope, (et_mean)]
    X = df[feature_order].values.astype(np.float64)
    y = df["dnbr"].values.astype(np.float64)

    # ── 6. Fit spatial GAM ────────────────────────────────────────────────
    log.info("--- Step 5: Fit LinearGAM (n=%d) ---", len(df))
    from pygam import LinearGAM, s, l as lin

    n_sp = len(spatial_cols)
    n_pr = len(pred_cols)

    # Build term list: smooth on spatial coords, linear on predictors
    all_terms = (
        [s(i, n_splines=20, lam=0.6) for i in range(n_sp)] +
        [lin(i) for i in range(n_sp, n_sp + n_pr)]
    )
    term_expr = all_terms[0]
    for t in all_terms[1:]:
        term_expr = term_expr + t

    gam = LinearGAM(term_expr)
    gam.fit(X, y)

    pseudo_r2  = float(gam.statistics_["pseudo_r2"]["explained_deviance"])
    resid      = y - gam.predict(X)
    rmse       = float(np.sqrt(np.mean(resid**2)))
    ss_res     = float(np.sum(resid**2))
    ss_tot     = float(np.sum((y - y.mean())**2))
    r2_classic = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan

    log.info("GAM fit: pseudo-R²=%.4f  classic R²=%.4f  RMSE=%.4f",
             pseudo_r2, r2_classic, rmse)

    # ── 7. Coefficient table ──────────────────────────────────────────────
    log.info("--- Step 6: Extract coefficient table ---")
    coef_table = extract_coef_table(gam, feature_order, n_spatial=n_sp)
    coef_table.to_csv(TABLES / "table_spatial_gam.csv", index=False)
    log.info("table_spatial_gam.csv:\n%s", coef_table.to_string(index=False))

    # ── 8. Moran's I ──────────────────────────────────────────────────────
    log.info("--- Step 7: Moran's I on residuals ---")
    moran_res = moran_residuals(df, resid, k=8)

    # ── 9. Partial dependence ─────────────────────────────────────────────
    log.info("--- Step 8: Partial dependence curves ---")
    pd_df = partial_dependence_df(gam, feature_order)
    if len(pd_df) > 0:
        pd_df.to_csv(FIGDATA / "fig07_spatial_partial.csv", index=False)
        log.info("fig07_spatial_partial.csv: %d rows", len(pd_df))

    # ── 10. Summary JSON ──────────────────────────────────────────────────
    lin_coefs: dict[str, dict] = {}
    for _, row in coef_table.iterrows():
        if row["term_type"] == "linear":
            lin_coefs[row["term"]] = {
                "coef":     float(row["coef"])     if pd.notna(row["coef"])     else None,
                "se":       float(row["se"])       if pd.notna(row["se"])       else None,
                "ci_lo_95": float(row["ci_lo_95"]) if pd.notna(row["ci_lo_95"]) else None,
                "ci_hi_95": float(row["ci_hi_95"]) if pd.notna(row["ci_hi_95"]) else None,
                "p_value":  float(row["p_value"])  if pd.notna(row["p_value"])  else None,
            }

    summary = {
        "model":             "spatial_gam_penalized_spline",
        "label":             "Spatial GAM / penalized spline (pygam LinearGAM)",
        "n_perim_cells":     n_perim_cells,
        "n_analysis_cells":  len(df),
        "grid_m":            GRID_M,
        "response":          "S2 dNBR",
        "spatial_smooth":    "s(x_norm, n_splines=20) + s(y_norm, n_splines=20)",
        "covariates":        pred_cols,
        "pseudo_r2_expl_dev": pseudo_r2,
        "r2_classic":        round(r2_classic, 6),
        "rmse_dnbr":         round(rmse, 6),
        "linear_coefficients": lin_coefs,
        "moran_residuals":   moran_res,
        "et_available":      et_available,
        "timestamp":         utcnow(),
        "crs":               CRS,
    }
    with open(TABLES / "spatial_model_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("spatial_model_summary.json saved")

    # ── 11. Result registry ───────────────────────────────────────────────
    reg_rows = [
        {
            "result_id": "R060",
            "manuscript_section": "4 · Landscape spatial model",
            "metric": "pseudo_R2_explained_deviance",
            "value": round(pseudo_r2, 4),
            "unit": "proportion",
            "uncertainty": "",
            "dataset": "S2 dNBR / 3DEP DEM / DWR-2019 vineyards / OpenET",
            "analysis_script": "src/analysis/34_bayesian_spatial.py",
            "model": "LinearGAM penalized spline (pygam 0.12.0)",
            "source_output": "outputs/tables/spatial_model_summary.json",
        },
        {
            "result_id": "R061",
            "manuscript_section": "4 · Landscape spatial model",
            "metric": "r2_classic",
            "value": round(r2_classic, 4),
            "unit": "proportion",
            "uncertainty": "",
            "dataset": "S2 dNBR",
            "analysis_script": "src/analysis/34_bayesian_spatial.py",
            "model": "LinearGAM penalized spline",
            "source_output": "outputs/tables/spatial_model_summary.json",
        },
        {
            "result_id": "R062",
            "manuscript_section": "4 · Landscape spatial model",
            "metric": "rmse_dnbr",
            "value": round(rmse, 4),
            "unit": "dNBR units",
            "uncertainty": "",
            "dataset": "S2 dNBR",
            "analysis_script": "src/analysis/34_bayesian_spatial.py",
            "model": "LinearGAM penalized spline",
            "source_output": "outputs/tables/spatial_model_summary.json",
        },
        {
            "result_id": "R063",
            "manuscript_section": "4 · Landscape spatial model",
            "metric": "n_grid_cells_analysis",
            "value": len(df),
            "unit": "cells",
            "uncertainty": "",
            "dataset": "250 m grid inside Kincade perimeter",
            "analysis_script": "src/analysis/34_bayesian_spatial.py",
            "model": "",
            "source_output": "outputs/tables/spatial_model_summary.json",
        },
    ]

    if "moran_I" in moran_res:
        reg_rows.append({
            "result_id": "R064",
            "manuscript_section": "4 · Landscape spatial model",
            "metric": "moran_I_residuals",
            "value": round(moran_res["moran_I"], 4),
            "unit": "Moran I",
            "uncertainty": f"p_sim={moran_res['moran_p_sim']:.4f}",
            "dataset": "GAM residuals",
            "analysis_script": "src/analysis/34_bayesian_spatial.py",
            "model": "KNN-8 spatial weights (libpysal/esda)",
            "source_output": "outputs/tables/spatial_model_summary.json",
        })

    rid = 65
    for pname, pinfo in lin_coefs.items():
        ci_str = ""
        if pinfo["ci_lo_95"] is not None and pinfo["ci_hi_95"] is not None:
            ci_str = f"95% CI [{pinfo['ci_lo_95']:.5f}, {pinfo['ci_hi_95']:.5f}]"
        reg_rows.append({
            "result_id": f"R0{rid}",
            "manuscript_section": "4 · Landscape spatial model",
            "metric": f"coef_{pname}",
            "value": round(pinfo["coef"], 6) if pinfo["coef"] is not None else "N/A",
            "unit": "dNBR per unit predictor",
            "uncertainty": ci_str,
            "dataset": "spatial GAM",
            "analysis_script": "src/analysis/34_bayesian_spatial.py",
            "model": "LinearGAM penalized spline",
            "source_output": "outputs/tables/table_spatial_gam.csv",
        })
        rid += 1

    append_registry(reg_rows)
    log.info("Appended %d rows to result_registry.csv", len(reg_rows))

    # ── 12. METHODS_LOG append ─────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()

    coef_bullet_lines = []
    for pname, pinfo in lin_coefs.items():
        c  = f"{pinfo['coef']:.5f}" if pinfo["coef"] is not None else "N/A"
        ci = (f"[{pinfo['ci_lo_95']:.5f}, {pinfo['ci_hi_95']:.5f}]"
              if pinfo["ci_lo_95"] is not None else "N/A")
        p  = f"{pinfo['p_value']:.3e}" if pinfo["p_value"] is not None else "N/A"
        coef_bullet_lines.append(f"  - `{pname}`: b = {c}, 95% CI {ci}, p = {p}")

    smooth_bullet_lines = []
    for _, row in coef_table.iterrows():
        if row["term_type"] == "smooth_spline":
            p_s = f"{row['p_value']:.3e}" if pd.notna(row["p_value"]) else "N/A"
            smooth_bullet_lines.append(
                f"  - `{row['term']}` (penalized spline, 20 knots): p = {p_s}"
            )

    if "moran_I" in moran_res:
        moran_line = (
            f"  Moran's I on residuals (k=8 KNN): **I = {moran_res['moran_I']:.4f}**, "
            f"p_sim = {moran_res['moran_p_sim']:.4f}"
        )
    else:
        moran_line = f"  Moran's I: {moran_res.get('note', 'N/A')}"

    log_entry = f"""
### 34 · Landscape spatial GAM — burn severity drivers (`src/analysis/34_bayesian_spatial.py`)
- **Data/method:** 250 m regular grid (EPSG:26910) inside Kincade perimeter
  (`rasterize`, `all_touched=False`). Response: S2 dNBR (`s2_burn_severity.tif`, Band 1).
  Predictors rasterized/resampled to 250 m:
  - Vineyard fraction — DWR-2019 polygons rasterized at 25 m, averaged to 250 m (true areal fraction).
  - Elevation — 3DEP 10 m DEM (`dem_3dep_10m.tif`, bilinear resample).
  - Slope (°) — numerical gradient of 250 m DEM (`np.gradient`, Euclidean norm).
  - ET mean (mm/month) — mean of OpenET Apr–Oct 2019 bands (7 months); available = {et_available}.
  Model: `pygam.LinearGAM` with penalized B-splines on normalised UTM coordinates
  (20 knots per axis, λ = 0.6) + linear terms for covariates.
  **Honestly labelled "spatial GAM / penalized spline" — not Bayesian.**
  Moran's I (k = 8 KNN, `libpysal`/`esda`) on residuals to assess residual autocorrelation.
- **Grid:** {shape[0]}×{shape[1]} total cells ({n_perim_cells} inside perimeter); {len(df)} with valid data.
- **Spatial smooth terms (x_norm, y_norm):**
{chr(10).join(smooth_bullet_lines) if smooth_bullet_lines else "  (see table_spatial_gam.csv)"}
- **Linear covariate terms (b, 95% CI, p-value from GAM statistics):**
{chr(10).join(coef_bullet_lines) if coef_bullet_lines else "  (see table_spatial_gam.csv)"}
- **Fit metrics:** pseudo-R² (explained deviance) = **{pseudo_r2:.4f}**; classic R² = {r2_classic:.4f}; RMSE = {rmse:.4f} dNBR units.
- **Spatial autocorrelation:** {moran_line}
- **Multicollinearity:** Pearson correlation matrix → `outputs/qa/predictor_corr.csv`.
- **Outputs:** `outputs/tables/table_spatial_gam.csv`, `outputs/tables/spatial_model_summary.json`,
  `outputs/figures/data/fig07_spatial_partial.csv`, `outputs/qa/predictor_corr.csv`.
- *Runtime: {elapsed:.0f} s.*

"""
    log_path = DOCS / "METHODS_LOG.md"
    if log_path.exists():
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        log.info("Appended to METHODS_LOG.md")
    else:
        log.warning("METHODS_LOG.md not found at %s", log_path)

    # ── Print summary ─────────────────────────────────────────────────────
    sep = "=" * 65
    print(f"\n{sep}")
    print("  SPATIAL GAM RESULTS — Kincade Burn Severity")
    print(sep)
    print(f"  Grid cells analysed      : {len(df):,}")
    print(f"  Pseudo-R² (expl. deviance): {pseudo_r2:.4f}")
    print(f"  Classic R²               : {r2_classic:.4f}")
    print(f"  RMSE (dNBR)              : {rmse:.4f}")
    print()
    print("  Linear covariate coefficients (b  95%-CI  p-value):")
    for pname, pinfo in lin_coefs.items():
        c  = f"{pinfo['coef']:+.5f}" if pinfo["coef"] is not None else "    N/A"
        ci = (f"[{pinfo['ci_lo_95']:+.5f}, {pinfo['ci_hi_95']:+.5f}]"
              if pinfo["ci_lo_95"] is not None else "N/A")
        p  = f"{pinfo['p_value']:.3e}" if pinfo["p_value"] is not None else "N/A"
        print(f"    {pname:<16s}: b={c}  CI {ci}  p={p}")
    print()
    if "moran_I" in moran_res:
        print(f"  Moran's I residuals (k=8): I={moran_res['moran_I']:.4f}"
              f"  p_sim={moran_res['moran_p_sim']:.4f}")
    else:
        print(f"  Moran's I: {moran_res.get('note', 'N/A')}")
    print()
    print("  Predictor correlation matrix (absolute max off-diagonal):")
    off_diag = corr.values.copy()
    np.fill_diagonal(off_diag, 0)
    print(f"    max |r| = {np.abs(off_diag).max():.3f}")
    print(sep + "\n")

    log.info("=== 34_bayesian_spatial.py DONE (%.0f s) ===", elapsed)


if __name__ == "__main__":
    main()
