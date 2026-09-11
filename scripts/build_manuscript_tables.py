#!/usr/bin/env python
"""Build the four main manuscript tables for the Kincade Multisystem Resilience paper.

Every value below is transcribed from real pipeline outputs under ``outputs/`` and
``data/`` (see ``outputs/result_registry.csv`` and the per-analysis JSON/CSV
summaries). No numbers are invented here. The script writes one CSV per table plus
a combined XLSX workbook (one sheet per table) into ``outputs/tables/``.

Run:
    conda run -n gee python scripts/build_manuscript_tables.py
"""
from __future__ import annotations

import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
TABLES.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Table 1 — Datasets and provenance
# ---------------------------------------------------------------------------
table1 = pd.DataFrame(
    [
        {
            "Dataset": "Fire perimeter (Kincade 2019)",
            "Source / product": "WFIGS/NIFC InterAgency Fire Perimeter History",
            "Native resolution / unit": "Vector polygon",
            "Temporal coverage": "2019 incident",
            "Role in analysis": "Study-area definition; inside/outside masks (77,762 GIS acres)",
        },
        {
            "Dataset": "Structure damage (DINS)",
            "Source / product": "CAL FIRE POSTFIRE_MASTER_DATA_SHARE",
            "Native resolution / unit": "Point (per structure)",
            "Temporal coverage": "Post-fire 2019 survey",
            "Role in analysis": "Community exposure context (1,568 inspected; 374 destroyed)",
        },
        {
            "Dataset": "Vineyard fields",
            "Source / product": "DWR i15 Statewide Crop Mapping 2019 (SYMB_CLASS = V)",
            "Native resolution / unit": "Vector polygon",
            "Temporal coverage": "2019 growing season",
            "Role in analysis": "Agricultural exposure unit (4,581 fields / 8,813.2 ha in AOI)",
        },
        {
            "Dataset": "Digital elevation model",
            "Source / product": "USGS 3DEP 10 m (Google Earth Engine)",
            "Native resolution / unit": "10 m raster",
            "Temporal coverage": "Static",
            "Role in analysis": "Elevation, slope, aspect covariates; hillshade basemap",
        },
        {
            "Dataset": "Burn severity (dNBR)",
            "Source / product": "Sentinel-2 SR Harmonized; Landsat-8 C2 L2 (cross-check)",
            "Native resolution / unit": "20 m (S2) / 30 m (L8)",
            "Temporal coverage": "Pre 2019-09-01/10-22; post 2019-11-10/12-15",
            "Role in analysis": "Primary outcome (dNBR = NBR_pre - NBR_post)",
        },
        {
            "Dataset": "Evapotranspiration",
            "Source / product": "OpenET ensemble (CONUS gridMET monthly v2.1)",
            "Native resolution / unit": "30 m monthly (mm)",
            "Temporal coverage": "Apr-Oct 2019",
            "Role in analysis": "Pre-fire water-use / canopy status covariate & outcome",
        },
        {
            "Dataset": "Surface reflectance indices",
            "Source / product": "Sentinel-2 SR Harmonized (NDMI, NDVI)",
            "Native resolution / unit": "20 m",
            "Temporal coverage": "2018-2021 growing seasons",
            "Role in analysis": "Pre-fire moisture/vigour; NDVI recovery trajectories",
        },
        {
            "Dataset": "Fire weather",
            "Source / product": "gridMET (IDAHO_EPSCOR/GRIDMET)",
            "Native resolution / unit": "~4 km daily",
            "Temporal coverage": "2019-10-23 to 11-06",
            "Role in analysis": "RH, VPD, wind context for event onset",
        },
        {
            "Dataset": "Soils",
            "Source / product": "USDA NRCS SSURGO (Soil Data Access)",
            "Native resolution / unit": "Map-unit polygon",
            "Temporal coverage": "Static",
            "Role in analysis": "Available water capacity (AWC) covariate",
        },
        {
            "Dataset": "Smoke plumes",
            "Source / product": "NOAA/NESDIS HMS smoke polygons (GOES + polar)",
            "Native resolution / unit": "Daily analyst polygon",
            "Temporal coverage": "2019-10-23 to 11-10",
            "Role in analysis": "Potential overhead smoke exposure (not taint)",
        },
        {
            "Dataset": "Road network",
            "Source / product": "OpenStreetMap (Overpass snapshot [date:2019-10-23])",
            "Native resolution / unit": "Vector graph",
            "Temporal coverage": "2019-10-23",
            "Role in analysis": "Transport access & topology (geometry only)",
        },
        {
            "Dataset": "3-D structure inventory",
            "Source / product": "OpenTopography; USGS 3DEP LPC/TNM; GEDI L2A (GEE)",
            "Native resolution / unit": "Point cloud / 25 m footprint",
            "Temporal coverage": "2003-2024 (airborne); 2019-2023 (GEDI)",
            "Role in analysis": "Structural-data feasibility context (no event-day fuels)",
        },
        {
            "Dataset": "Ignition & regulatory record",
            "Source / product": "CAL FIRE cause release; CPUC SED investigation & Resolution SED-6",
            "Native resolution / unit": "Document",
            "Temporal coverage": "2020-2021",
            "Role in analysis": "Documented PG&E electrical initiation (cited, not re-derived)",
        },
    ]
)


# ---------------------------------------------------------------------------
# Table 2 — Research questions, units, models, and claim boundaries
# ---------------------------------------------------------------------------
table2 = pd.DataFrame(
    [
        {
            "Subsystem": "Pre-fire water status",
            "Question": "Does pre-fire canopy moisture/vigour track field water use?",
            "Analysis unit": "Vineyard field (n=4,581)",
            "Model / statistic": "OLS + Spearman (NDMI/NDVI vs OpenET ET; AWC)",
            "Claim boundary": "Association only; ET is water use, not metered irrigation",
        },
        {
            "Subsystem": "Landscape burn severity",
            "Question": "Do vineyards burn at lower severity than wildland?",
            "Analysis unit": "20 m dNBR pixel (vine vs wild in perimeter)",
            "Model / statistic": "Pixel means/medians; Welch t-test",
            "Claim boundary": "Descriptive landscape contrast; unconditional",
        },
        {
            "Subsystem": "Boundary discontinuity",
            "Question": "Does severity change discontinuously at the vine-wild edge?",
            "Analysis unit": "Boundary transect point (n=2,000 segments)",
            "Model / statistic": "Local-linear RDD, cluster-robust SE by segment",
            "Claim boundary": "Spatial boundary-discontinuity association, NOT causal RDD (continuity fails)",
        },
        {
            "Subsystem": "Severity drivers",
            "Question": "What landscape covariates covary with severity?",
            "Analysis unit": "250 m grid cell (n=5,097)",
            "Model / statistic": "Spatial GAM (penalized spline) + Moran's I",
            "Claim boundary": "Conditional association; residual autocorrelation remains",
        },
        {
            "Subsystem": "Within-vineyard mechanism",
            "Question": "Is field ET associated with field dNBR?",
            "Analysis unit": "Vineyard field (n=1,206)",
            "Model / statistic": "Standardized OLS (dNBR on ET_z, elev_z, slope_z)",
            "Claim boundary": "Spectral/biomass association; ET does not 'increase fire'",
        },
        {
            "Subsystem": "Smoke exposure",
            "Question": "How much potential overhead smoke did vineyards receive?",
            "Analysis unit": "Vineyard field-day",
            "Model / statistic": "Daily HMS polygon intersection",
            "Claim boundary": "Atmospheric exposure proxy; NOT ground PM2.5 or smoke taint",
        },
        {
            "Subsystem": "Transport access",
            "Question": "How well connected are vineyards to the road network?",
            "Analysis unit": "Vineyard centroid; network node/edge",
            "Model / statistic": "osmnx graph metrics; nearest-distance joins",
            "Claim boundary": "Geometry/topology only; no traffic volumes or evacuation sim",
        },
        {
            "Subsystem": "Vegetation recovery",
            "Question": "Do inside-perimeter vineyards recover more slowly?",
            "Analysis unit": "Vineyard field (1,327 in / 3,254 out)",
            "Model / statistic": "Month-matched NDVI ratios; Welch t-tests",
            "Claim boundary": "Greenness recovery; not yield or wine quality",
        },
    ]
)


# ---------------------------------------------------------------------------
# Table 3 — Main quantitative results
# ---------------------------------------------------------------------------
table3 = pd.DataFrame(
    [
        {"Metric": "Vineyard fields in download AOI (5 km)", "Value": "4,581", "Unit": "fields", "Uncertainty / test": "-", "Source": "vineyards_summary.json"},
        {"Metric": "Vineyard area in download AOI (5 km)", "Value": "8,813.2", "Unit": "ha", "Uncertainty / test": "-", "Source": "vineyards_summary.json"},
        {"Metric": "Vineyard fields in analysis AOI (fire+2 km)", "Value": "2,622", "Unit": "fields", "Uncertainty / test": "-", "Source": "landscape_severity_summary.json"},
        {"Metric": "Vineyard area in analysis AOI (fire+2 km)", "Value": "5,798.3", "Unit": "ha", "Uncertainty / test": "-", "Source": "landscape_severity_summary.json"},
        {"Metric": "Mean dNBR, vineyard (in perimeter)", "Value": "0.130", "Unit": "dNBR", "Uncertainty / test": "median 0.127", "Source": "landscape_severity_summary.json"},
        {"Metric": "Mean dNBR, wildland (in perimeter)", "Value": "0.337", "Unit": "dNBR", "Uncertainty / test": "median 0.284; t=-109.5, p<1e-300", "Source": "landscape_severity_summary.json"},
        {"Metric": "Boundary contrast tau (h=100 m, primary)", "Value": "-0.0166", "Unit": "dNBR", "Uncertainty / test": "SE 0.0031; p=6.0e-8", "Source": "table_rdd_bandwidth.csv"},
        {"Metric": "Pre-fire NDMI (vineyard mean)", "Value": "0.015", "Unit": "index", "Uncertainty / test": "SD 0.077", "Source": "prefire_ndmi_et_summary.json"},
        {"Metric": "Pre-fire NDVI (vineyard mean)", "Value": "0.439", "Unit": "index", "Uncertainty / test": "-", "Source": "prefire_ndmi_et_summary.json"},
        {"Metric": "Growing-season ET (vineyard mean)", "Value": "470.3", "Unit": "mm", "Uncertainty / test": "-", "Source": "prefire_ndmi_et_summary.json"},
        {"Metric": "NDMI-ET correlation", "Value": "0.567", "Unit": "Pearson r", "Uncertainty / test": "p<1e-300", "Source": "table_prefire_ndmi_et.csv"},
        {"Metric": "NDVI-ET correlation", "Value": "0.639", "Unit": "Pearson r", "Uncertainty / test": "p<1e-300", "Source": "table_prefire_ndmi_et.csv"},
        {"Metric": "AWC(0-100cm)-NDMI correlation", "Value": "0.028", "Unit": "Pearson r", "Uncertainty / test": "p=0.060 (n.s.)", "Source": "table_prefire_ndmi_et.csv"},
        {"Metric": "Within-vineyard ET_z coefficient on dNBR", "Value": "+0.0384", "Unit": "dNBR / SD", "Uncertainty / test": "SE 0.0031; p<1e-3; n=1,206", "Source": "table_mechanism_et.csv"},
        {"Metric": "Spatial GAM vineyard_frac coefficient", "Value": "+0.138", "Unit": "dNBR / unit", "Uncertainty / test": "95% CI [0.128, 0.149]", "Source": "table_spatial_gam.csv"},
        {"Metric": "Spatial GAM ET_mean coefficient", "Value": "+0.0076", "Unit": "dNBR / unit", "Uncertainty / test": "95% CI [0.0075, 0.0077]", "Source": "table_spatial_gam.csv"},
        {"Metric": "Spatial GAM pseudo-R2 (explained deviance)", "Value": "0.898", "Unit": "proportion", "Uncertainty / test": "RMSE 0.055; n=5,097", "Source": "spatial_model_summary.json"},
        {"Metric": "GAM residual Moran's I", "Value": "0.519", "Unit": "Moran I", "Uncertainty / test": "p_sim=0.001", "Source": "spatial_model_summary.json"},
        {"Metric": "Days with overhead smoke over AOI", "Value": "9", "Unit": "of 19 days", "Uncertainty / test": "-", "Source": "smoke_vineyard_summary.json"},
        {"Metric": "Mean potential smoke-days per field", "Value": "7.78", "Unit": "days", "Uncertainty / test": "max 9; all fields >=1", "Source": "smoke_vineyard_summary.json"},
        {"Metric": "Total vineyard hectare-smoke-days", "Value": "69,101.6", "Unit": "ha-days", "Uncertainty / test": "-", "Source": "smoke_vineyard_summary.json"},
        {"Metric": "NDVI 2019->2021 ratio, inside perimeter", "Value": "0.815", "Unit": "ratio", "Uncertainty / test": "n=1,327", "Source": "table_recovery_tests.csv"},
        {"Metric": "NDVI 2019->2021 ratio, outside perimeter", "Value": "0.854", "Unit": "ratio", "Uncertainty / test": "n=3,254; diff p=2.3e-10", "Source": "table_recovery_tests.csv"},
        {"Metric": "Total road length (2019 OSM drive network)", "Value": "1,581.9", "Unit": "km", "Uncertainty / test": "major 321.6 km", "Source": "table_network_metrics.json"},
        {"Metric": "Dead-end node fraction", "Value": "34.2", "Unit": "%", "Uncertainty / test": "-", "Source": "table_network_metrics.json"},
        {"Metric": "Median vineyard distance to major road", "Value": "719.5", "Unit": "m", "Uncertainty / test": "mean 1,204 m", "Source": "table_network_metrics.json"},
        {"Metric": "GEDI valid RH98 pixels in perimeter", "Value": "87,601", "Unit": "25 m pixels", "Uncertainty / test": "45 monthly scenes", "Source": "lidar_inventory_summary.json"},
    ]
)


# ---------------------------------------------------------------------------
# Table 4 — Robustness diagnostics and planning implications
# ---------------------------------------------------------------------------
table4 = pd.DataFrame(
    [
        {
            "Diagnostic / test": "Bandwidth sensitivity (tau)",
            "Result": "h30 +0.045; h60 -0.018; h100 -0.017; h150 -0.011; h300 -0.004 (p=0.20)",
            "Interpretation": "Sign flips at very small h; stable negative 60-150 m; attenuates by 300 m",
            "Planning implication": "Boundary severity contrast is scale-dependent; report multiple bandwidths",
        },
        {
            "Diagnostic / test": "Covariate continuity at boundary",
            "Result": "Slope differs strongly (p~1e-36); elevation balanced (p=0.83)",
            "Interpretation": "Boundary is not continuous in terrain -> RDD identification fails",
            "Planning implication": "Interpret as boundary-discontinuity association, not causal effect",
        },
        {
            "Diagnostic / test": "Donut hole (exclude +/-h)",
            "Result": "tau = +0.0068, p=0.10 at h=100 m",
            "Interpretation": "Contrast is driven by the immediate edge; null away from it",
            "Planning implication": "Effect is an edge phenomenon; avoid over-generalizing",
        },
        {
            "Diagnostic / test": "Placebo boundary",
            "Result": "tau = +0.062, p<1e-300 (large, wrong-signed)",
            "Interpretation": "Placebo is non-null -> background spatial trend present",
            "Planning implication": "Strengthens caution; supports association-only language",
        },
        {
            "Diagnostic / test": "Spatial GAM residual autocorrelation",
            "Result": "Moran's I = 0.519 (p_sim=0.001)",
            "Interpretation": "Unmodeled spatial structure remains; SEs optimistic",
            "Planning implication": "Coefficients are conditional associations, not effects",
        },
        {
            "Diagnostic / test": "Simpson / confounding contrast",
            "Result": "Unconditional vine<<wild (0.130 vs 0.337); conditional vineyard_frac +0.138",
            "Interpretation": "Sign reversal after conditioning on terrain/position/ET",
            "Planning implication": "Vineyards are not universal firebreaks; context matters",
        },
        {
            "Diagnostic / test": "Cross-sensor severity check",
            "Result": "Landsat-8 dNBR mean 0.086 vs Sentinel-2 0.082 (AOI)",
            "Interpretation": "Independent sensors agree on landscape mean",
            "Planning implication": "Severity signal is robust to sensor choice",
        },
        {
            "Diagnostic / test": "Recovery persistence",
            "Result": "Inside deficit grows 2020 (p=4.4e-5) -> 2021 (p=2.3e-10)",
            "Interpretation": "Recovery gap widens, not closes, by year 2",
            "Planning implication": "Post-fire vineyard monitoring should extend >=2 seasons",
        },
        {
            "Diagnostic / test": "Event-day 3-D fuels",
            "Result": "No 2019 Sonoma airborne collect; GEDI is 2019-2023 baseline",
            "Interpretation": "Vertical fuels are structural baseline, not event-day",
            "Planning implication": "Motivates routine pre-fire lidar over working landscapes",
        },
    ]
)


tables = {
    "Table1_datasets": table1,
    "Table2_questions": table2,
    "Table3_results": table3,
    "Table4_robustness": table4,
}

for name, df in tables.items():
    csv_path = TABLES / f"{name}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"wrote {csv_path}  ({df.shape[0]} rows x {df.shape[1]} cols)")

xlsx_path = TABLES / "manuscript_tables.xlsx"
with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
    for name, df in tables.items():
        df.to_excel(xw, sheet_name=name[:31], index=False)
print(f"wrote {xlsx_path}")
