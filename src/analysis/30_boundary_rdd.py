"""Fast vineyard–wildland boundary discontinuity analysis (signed-distance RDD).

Strategy: dissolve vineyard polygons intersecting fire+2km, sample edge midpoints
with a stride, then place transect points along inward normals. Avoids slow
per-segment shapely loops on the full statewide clip.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from rasterio.warp import reproject, Resampling
from scipy import stats
from shapely.geometry import LineString, Point, MultiLineString, mapping
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
LOG = OUT / "logs"
for p in (PROC, OUT / "tables", OUT / "qa", LOG, OUT / "figures" / "data"):
    p.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG / "30_boundary_rdd.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("rdd")
CRS = "EPSG:26910"
SEED = 42
rng = np.random.default_rng(SEED)


def cluster_se(X, resid, clusters):
    n, k = X.shape
    meat = np.zeros((k, k))
    for c in np.unique(clusters):
        m = clusters == c
        Xi = X[m]
        ri = resid[m][:, None]
        meat += Xi.T @ (ri @ ri.T) @ Xi
    xtx_inv = np.linalg.pinv(X.T @ X)
    G = len(np.unique(clusters))
    corr = (G / (G - 1)) * ((n - 1) / (n - k)) if G > 1 else 1.0
    cov = corr * xtx_inv @ meat @ xtx_inv
    return np.sqrt(np.clip(np.diag(cov), 0, None))


def local_linear_rdd(df, h, ycol="dnbr"):
    sub = df[(df["signed_dist_m"].abs() <= h) & np.isfinite(df[ycol])].copy()
    if len(sub) < 80:
        return {"bandwidth_m": h, "n": len(sub), "tau_vineyard": np.nan, "se_cluster": np.nan, "p": np.nan}
    x = sub["signed_dist_m"].to_numpy()
    v = sub["vineyard"].to_numpy(dtype=float)
    y = sub[ycol].to_numpy()
    X = np.column_stack([np.ones(len(x)), v, x, x * v])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    se = cluster_se(X, resid, sub["seg_id"].to_numpy())
    tau = float(beta[1])
    tstat = tau / se[1] if se[1] > 0 else np.nan
    p = float(2 * (1 - stats.norm.cdf(abs(tstat)))) if np.isfinite(tstat) else np.nan
    return {
        "bandwidth_m": h,
        "n": int(len(sub)),
        "n_segments": int(sub["seg_id"].nunique()),
        "tau_vineyard": tau,
        "se_cluster": float(se[1]),
        "t": float(tstat) if np.isfinite(tstat) else np.nan,
        "p": p,
        "mean_y_vine": float(np.nanmean(y[v == 1])),
        "mean_y_wild": float(np.nanmean(y[v == 0])),
    }


def sample_raster(arr, transform, xs, ys):
    rows, cols = rasterio.transform.rowcol(transform, xs, ys)
    rows = np.asarray(rows, dtype=int)
    cols = np.asarray(cols, dtype=int)
    out = np.full(len(xs), np.nan)
    h, w = arr.shape
    ok = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    out[ok] = arr[rows[ok], cols[ok]]
    return out


def resample_to(src, src_tf, src_crs, shape, dst_tf, dst_crs):
    dst = np.full(shape, np.nan, dtype="float32")
    reproject(
        source=src.astype("float32"),
        destination=dst,
        src_transform=src_tf,
        src_crs=src_crs,
        dst_transform=dst_tf,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
    )
    return dst


def edge_sample_points(vine_union, spacing_m=150.0, max_points=2500):
    """Sample points along vineyard exterior boundary with local inward normals."""
    boundary = vine_union.boundary
    if boundary.is_empty:
        return []
    geoms = list(boundary.geoms) if isinstance(boundary, MultiLineString) else [boundary]
    # Merge and sample by distance
    samples = []
    seg_id = 0
    for geom in geoms:
        if geom.is_empty or geom.length < spacing_m:
            continue
        # densify
        n = int(geom.length // spacing_m)
        for i in range(n):
            d0 = i * spacing_m
            d1 = min(geom.length, d0 + spacing_m)
            p0 = geom.interpolate(d0)
            p1 = geom.interpolate(d1)
            mid = geom.interpolate(0.5 * (d0 + d1))
            dx, dy = p1.x - p0.x, p1.y - p0.y
            L = np.hypot(dx, dy)
            if L < 1e-3:
                continue
            # two candidate normals
            n1x, n1y = -dy / L, dx / L
            test = Point(mid.x + n1x * 40, mid.y + n1y * 40)
            if vine_union.contains(test):
                inx, iny = n1x, n1y
            else:
                inx, iny = -n1x, -n1y
            samples.append((seg_id, mid.x, mid.y, inx, iny))
            seg_id += 1
            if seg_id >= max_points:
                return samples
    return samples


def main():
    t0 = time.time()
    log.info("Loading inputs")
    fire = gpd.read_file(RAW / "fire" / "kincade_perimeter.gpkg").to_crs(CRS)
    vines = gpd.read_file(RAW / "vineyards" / "kincade_vineyards.gpkg").to_crs(CRS)
    vines = vines[vines.geometry.is_valid & ~vines.geometry.is_empty].copy()
    vines["area_ha"] = vines.geometry.area / 10000.0
    vines = vines[vines["area_ha"] >= 0.2]

    aoi = fire.geometry.unary_union.buffer(2000)
    vines_aoi = vines[vines.intersects(aoi)].copy()
    log.info("Vineyards in AOI: %s (%.1f ha)", len(vines_aoi), vines_aoi.area.sum() / 10000)

    # Prefer fields intersecting perimeter for boundary focus, but keep AOI dissolve
    log.info("Dissolving vineyard union (this may take ~1–2 min)...")
    # Faster dissolve: use unary_union on a slightly simplified geometry
    simplified = vines_aoi.geometry.simplify(5.0, preserve_topology=True)
    vine_union = unary_union(list(simplified))
    log.info("Union done in %.1fs type=%s", time.time() - t0, vine_union.geom_type)

    samples = edge_sample_points(vine_union, spacing_m=150.0, max_points=2000)
    log.info("Edge samples: %s", len(samples))

    distances = np.array([-300, -150, -100, -60, -30, 0, 30, 60, 100, 150, 300], dtype=float)
    rows = []
    for seg_id, cx, cy, inx, iny in samples:
        for d in distances:
            rows.append(
                {
                    "seg_id": seg_id,
                    "signed_dist_m": float(d),
                    "vineyard": int(d >= 0),
                    "x": cx + inx * d,
                    "y": cy + iny * d,
                }
            )
    pts = pd.DataFrame(rows)
    gpts = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.x, pts.y), crs=CRS)

    # Rasters
    with rasterio.open(RAW / "gee" / "s2_burn_severity.tif") as src:
        dnbr = src.read(3).astype("float32")
        dnbr = np.where(np.isfinite(dnbr), dnbr, np.nan)
        dnbr_tf, dnbr_crs = src.transform, src.crs
        log.info("dNBR finite%%=%.1f mean=%.4f", 100 * np.isfinite(dnbr).mean(), np.nanmean(dnbr))

    with rasterio.open(RAW / "gee" / "dem_3dep_10m.tif") as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem = np.where(dem == src.nodata, np.nan, dem)
        dem_tf, dem_crs = src.transform, src.crs
    px, py = dem_tf.a, abs(dem_tf.e)
    gy, gx = np.gradient(dem, py, px)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    aspect = np.degrees(np.arctan2(-gx, gy))
    aspect = np.where(aspect < 0, aspect + 360, aspect)
    northness = np.cos(np.deg2rad(aspect))
    eastness = np.sin(np.deg2rad(aspect))

    elev = resample_to(dem, dem_tf, dem_crs, dnbr.shape, dnbr_tf, dnbr_crs)
    slope_r = resample_to(slope, dem_tf, dem_crs, dnbr.shape, dnbr_tf, dnbr_crs)
    north_r = resample_to(northness, dem_tf, dem_crs, dnbr.shape, dnbr_tf, dnbr_crs)
    east_r = resample_to(eastness, dem_tf, dem_crs, dnbr.shape, dnbr_tf, dnbr_crs)

    xs, ys = gpts.geometry.x.to_numpy(), gpts.geometry.y.to_numpy()
    gpts["dnbr"] = sample_raster(dnbr, dnbr_tf, xs, ys)
    gpts["elev_m"] = sample_raster(elev, dnbr_tf, xs, ys)
    gpts["slope_deg"] = sample_raster(slope_r, dnbr_tf, xs, ys)
    gpts["northness"] = sample_raster(north_r, dnbr_tf, xs, ys)
    gpts["eastness"] = sample_raster(east_r, dnbr_tf, xs, ys)
    gpts = gpts[np.isfinite(gpts["dnbr"])].copy()
    log.info("Valid transect points: %s", len(gpts))

    gpts.to_file(PROC / "boundary_transect_points.gpkg", driver="GPKG")
    gpts.drop(columns="geometry").to_csv(PROC / "boundary_transect_points.csv", index=False)
    gpts.drop(columns="geometry").to_csv(OUT / "figures" / "data" / "fig06_transect_points.csv", index=False)

    rdd_df = pd.DataFrame([local_linear_rdd(gpts, h) for h in [30, 60, 100, 150, 300]])
    rdd_df.to_csv(OUT / "tables" / "table_rdd_bandwidth.csv", index=False)
    log.info("RDD:\n%s", rdd_df.to_string(index=False))

    # Continuity
    cont_rows = []
    sub = gpts[gpts.signed_dist_m.abs() <= 100]
    for col in ["elev_m", "slope_deg", "northness", "eastness"]:
        a = sub.loc[sub.vineyard == 1, col].dropna()
        b = sub.loc[sub.vineyard == 0, col].dropna()
        if len(a) < 20 or len(b) < 20:
            continue
        t, p = stats.ttest_ind(a, b, equal_var=False)
        cont_rows.append(
            {"variable": col, "mean_vine": float(a.mean()), "mean_wild": float(b.mean()),
             "diff": float(a.mean() - b.mean()), "t": float(t), "p": float(p), "bandwidth_m": 100}
        )
    cont = pd.DataFrame(cont_rows)
    cont.to_csv(OUT / "tables" / "table_rdd_continuity.csv", index=False)

    donut = gpts[gpts.signed_dist_m.abs() >= 20]
    pd.DataFrame([local_linear_rdd(donut, h) for h in [100, 150]]).to_csv(
        OUT / "tables" / "table_rdd_donut.csv", index=False
    )

    placebo = gpts.copy()
    placebo["signed_dist_m"] = placebo["signed_dist_m"] + 100
    placebo["vineyard"] = (placebo["signed_dist_m"] >= 0).astype(int)
    pd.DataFrame([local_linear_rdd(placebo, 100)]).to_csv(
        OUT / "tables" / "table_rdd_placebo.csv", index=False
    )

    # Binned profile
    bins = np.arange(-315, 316, 30)
    gpts["bin"] = pd.cut(gpts["signed_dist_m"], bins=bins)
    binned = gpts.groupby("bin", observed=True)["dnbr"].agg(["mean", "sem", "count"]).reset_index()
    binned["signed_dist_m"] = binned["bin"].apply(lambda b: b.mid)
    binned.to_csv(OUT / "figures" / "data" / "fig06_binned_dnbr.csv", index=False)

    # Landscape pixel contrast inside perimeter
    vine_mask = features.rasterize(
        [(mapping(geom), 1) for geom in vines_aoi.geometry],
        out_shape=dnbr.shape,
        transform=dnbr_tf,
        fill=0,
        dtype="uint8",
    )
    fire_mask = features.rasterize(
        [(mapping(geom), 1) for geom in fire.geometry],
        out_shape=dnbr.shape,
        transform=dnbr_tf,
        fill=0,
        dtype="uint8",
    )
    valid = np.isfinite(dnbr) & (fire_mask == 1)
    vine_vals = dnbr[valid & (vine_mask == 1)]
    wild_vals = dnbr[valid & (vine_mask == 0)]
    vine_s = rng.choice(vine_vals, size=min(25000, vine_vals.size), replace=False)
    wild_s = rng.choice(wild_vals, size=min(25000, wild_vals.size), replace=False)
    t, p = stats.ttest_ind(vine_s, wild_s, equal_var=False)
    landscape = {
        "n_vine_pixels": int(vine_vals.size),
        "n_wild_pixels": int(wild_vals.size),
        "mean_dnbr_vine": float(np.nanmean(vine_vals)),
        "mean_dnbr_wild": float(np.nanmean(wild_vals)),
        "median_dnbr_vine": float(np.nanmedian(vine_vals)),
        "median_dnbr_wild": float(np.nanmedian(wild_vals)),
        "ttest_t": float(t),
        "ttest_p": float(p),
        "n_vineyard_fields": int(len(vines_aoi)),
        "vineyard_area_ha": float(vines_aoi.area.sum() / 10000),
        "n_edge_segments": int(len(samples)),
        "n_transect_points_valid": int(len(gpts)),
        "elapsed_s": float(time.time() - t0),
    }
    with open(OUT / "tables" / "landscape_severity_summary.json", "w", encoding="utf-8") as f:
        json.dump(landscape, f, indent=2)
    log.info("Landscape %s", landscape)

    # Mechanism: vineyard field ET vs severity using zonal on a sample of fields
    et = pd.read_csv(RAW / "gee" / "openet_vineyard_monthly.csv")
    month_cols = [c for c in et.columns if c.startswith("ET_2019_")]
    et["et_gs_mm"] = et[month_cols].sum(axis=1)
    # sample up to 1500 fields intersecting fire for speed
    vines_fire = vines_aoi[vines_aoi.intersects(fire.geometry.unary_union)].copy()
    if len(vines_fire) > 1500:
        vines_fire = vines_fire.sample(1500, random_state=SEED)
    means = []
    for _, row in vines_fire.iterrows():
        try:
            mask = features.geometry_mask(
                [mapping(row.geometry)], out_shape=dnbr.shape, transform=dnbr_tf, invert=True
            )
            vals = dnbr[mask]
            vals = vals[np.isfinite(vals)]
            means.append(float(np.mean(vals)) if vals.size else np.nan)
        except Exception:
            means.append(np.nan)
    vines_fire = vines_fire.copy()
    vines_fire["dnbr_mean"] = means
    vines_fire = vines_fire.merge(et[["vineyard_field_id", "et_gs_mm"]], on="vineyard_field_id", how="left")
    cents = vines_fire.geometry.centroid
    vines_fire["elev_m"] = sample_raster(elev, dnbr_tf, cents.x.to_numpy(), cents.y.to_numpy())
    vines_fire["slope_deg"] = sample_raster(slope_r, dnbr_tf, cents.x.to_numpy(), cents.y.to_numpy())
    vines_fire.drop(columns="geometry").to_csv(PROC / "vineyard_fields_fire_sample.csv", index=False)

    sub = vines_fire.dropna(subset=["dnbr_mean", "et_gs_mm", "elev_m", "slope_deg"])
    mech = {}
    if len(sub) > 50:
        X = np.column_stack([
            np.ones(len(sub)),
            stats.zscore(sub["et_gs_mm"]),
            stats.zscore(sub["elev_m"]),
            stats.zscore(sub["slope_deg"]),
        ])
        y = sub["dnbr_mean"].to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        n, k = X.shape
        xtx_inv = np.linalg.pinv(X.T @ X)
        meat = X.T @ np.diag(resid ** 2) @ X
        cov = (n / (n - k)) * xtx_inv @ meat @ xtx_inv
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
        mech = {
            "model": "vineyard_dnbr_on_ET_z",
            "n": int(n),
            "coef_et_z": float(beta[1]),
            "se_et": float(se[1]),
            "p_et": float(2 * (1 - stats.norm.cdf(abs(beta[1] / se[1])))),
            "coef_elev_z": float(beta[2]),
            "coef_slope_z": float(beta[3]),
        }
        pd.DataFrame([mech]).to_csv(OUT / "tables" / "table_mechanism_et.csv", index=False)
    log.info("Mechanism %s", mech)

    primary = rdd_df[rdd_df.bandwidth_m == 100].iloc[0].to_dict()
    claim = {
        "primary_tau": primary.get("tau_vineyard"),
        "se": primary.get("se_cluster"),
        "p": primary.get("p"),
        "continuity_min_p": float(cont["p"].min()) if len(cont) else None,
        "recommended_language": (
            "spatial boundary-discontinuity association"
            if (len(cont) and (cont["p"] < 0.01).any())
            else "local geographic RDD estimate (diagnostics reported)"
        ),
    }
    with open(OUT / "tables" / "rdd_claim_language.json", "w", encoding="utf-8") as f:
        json.dump(claim, f, indent=2)

    # Registry
    reg_path = OUT / "result_registry.csv"
    new_rows = pd.DataFrame([
        {"result_id": "R001", "manuscript_section": "Results 3.3", "metric": "RDD_tau_dnbr_h100",
         "value": primary.get("tau_vineyard"), "unit": "dNBR", "uncertainty": primary.get("se_cluster"),
         "dataset": "S2_dNBR+DWR_vineyards", "analysis_script": "src/analysis/30_boundary_rdd.py",
         "model": "local_linear_RDD_clusterSE", "source_output": "outputs/tables/table_rdd_bandwidth.csv",
         "timestamp": pd.Timestamp.utcnow().isoformat()},
        {"result_id": "R002", "manuscript_section": "Results 3.2", "metric": "n_vineyard_fields",
         "value": landscape["n_vineyard_fields"], "unit": "fields", "uncertainty": "",
         "dataset": "DWR_2019_crop", "analysis_script": "src/analysis/30_boundary_rdd.py",
         "model": "inventory", "source_output": "outputs/tables/landscape_severity_summary.json",
         "timestamp": pd.Timestamp.utcnow().isoformat()},
        {"result_id": "R003", "manuscript_section": "Results 3.2", "metric": "vineyard_area_ha",
         "value": landscape["vineyard_area_ha"], "unit": "ha", "uncertainty": "",
         "dataset": "DWR_2019_crop", "analysis_script": "src/analysis/30_boundary_rdd.py",
         "model": "inventory", "source_output": "outputs/tables/landscape_severity_summary.json",
         "timestamp": pd.Timestamp.utcnow().isoformat()},
        {"result_id": "R004", "manuscript_section": "Results 3.3", "metric": "mean_dnbr_vine_in_perimeter",
         "value": landscape["mean_dnbr_vine"], "unit": "dNBR", "uncertainty": "",
         "dataset": "S2_dNBR", "analysis_script": "src/analysis/30_boundary_rdd.py",
         "model": "pixel_mean", "source_output": "outputs/tables/landscape_severity_summary.json",
         "timestamp": pd.Timestamp.utcnow().isoformat()},
        {"result_id": "R005", "manuscript_section": "Results 3.3", "metric": "mean_dnbr_wild_in_perimeter",
         "value": landscape["mean_dnbr_wild"], "unit": "dNBR", "uncertainty": "",
         "dataset": "S2_dNBR", "analysis_script": "src/analysis/30_boundary_rdd.py",
         "model": "pixel_mean", "source_output": "outputs/tables/landscape_severity_summary.json",
         "timestamp": pd.Timestamp.utcnow().isoformat()},
    ])
    if reg_path.exists():
        old = pd.read_csv(reg_path)
        # replace R001-R005 if present
        old = old[~old["result_id"].isin(new_rows["result_id"])]
        pd.concat([old, new_rows], ignore_index=True).to_csv(reg_path, index=False)
    else:
        new_rows.to_csv(reg_path, index=False)

    log.info("DONE in %.1fs primary_tau=%.5f p=%s language=%s",
             time.time() - t0, primary.get("tau_vineyard"), primary.get("p"), claim["recommended_language"])


if __name__ == "__main__":
    main()
