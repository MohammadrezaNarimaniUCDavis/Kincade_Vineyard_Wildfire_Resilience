# Kincade Multisystem Resilience — Final Main Figures

Publication-quality main figures for the manuscript *Kincade Multisystem
Resilience* (target: **Frontiers in Sustainability**, section Resilience).

All figures are generated **from real project outputs only** by a single
reproducible entry point:

```
conda run -n gee python src/visualization/42_make_main_figures.py
```

## Visual grammar
- Shared style loaded from `config/figure_style.yaml` via
  `src/visualization/style.py`, wrapped by `src/visualization/style_kincade.py`
  (adds the robust final-deliverable saver).
- Fonts resolved at runtime: **Helvetica → Arial → FreeSans → DejaVu Sans**
  (Arial used on this machine). No font binaries are copied.
- Frontiers dimensions: single-column 85 mm, double-column 180 mm, **300 dpi, RGB**.
- Full four-sided frames, inward ticks, panel labels formatted `(a) Title`.
- Kincade semantic palette (NOT the Palisades blue–red survival palette):
  purple = vineyards, teal = moisture/water, ochre/orange = thermal & severity,
  green = wildland/recovery, purple = smoke.
- Maps: **EPSG:26910 (NAD83 / UTM 10N)**, DEM hillshade background,
  scale bars in **km**, north arrows.

## Deliverables per figure
Each figure is written in three formats to this directory:
`Figure_XX_slug.pdf`, `Figure_XX_slug.png`, `Figure_XX_slug.tif` (RGB, 300 dpi,
LZW). The PNG is mirrored to `manuscript/figures/final/`.

## Figure list
| # | File slug | Content | Primary data sources |
|---|-----------|---------|----------------------|
| 01 | `Figure_1` | Multidisciplinary analytical workflow infographic (external PNG) | user-provided `Figure_1.png` |
| 02 | `Figure_02_study_area` | Study area: fire perimeter, vineyards, DINS structures on DEM hillshade | `data/raw/fire`, `data/raw/vineyards`, `data/raw/dins`, `data/raw/gee/dem_3dep_10m.tif` |
| 03 | `Figure_03_TRUE_B4B3B2_FalseB12B11B4` | Sentinel-2 true color (B4/B3/B2) + SWIR false color (B12/B11/B4): pre / active / post | `data/raw/gee/s2_*_{rgb,swir}.tif`, `s2_activefire_scene.json` |
| 04 | `Figure_04_vineyard_water` | Pre-fire vineyard water status (NDMI/NDVI vs. ET, ET distribution) | `outputs/figures/data/fig_prefire_ndmi_et.csv`, `outputs/tables/table_prefire_ndmi_et.csv` |
| 05 | `Figure_05_structure_context` | 3D structure data availability (lidar campaigns, 3DEP, GEDI) | `outputs/tables/lidar_inventory_summary.json` |
| 06 | `Figure_06_weather_electrical` | Fire-weather time series (RH, VPD, wind) + documented PG&E ignition context | `data/raw/weather/gridmet_aoi_mean_daily.csv` |
| 07 | `Figure_07_boundary_rdd` | **Headline**: burn-severity boundary discontinuity (binned dNBR, τ vs. bandwidth, map inset) | `outputs/figures/data/fig06_*.csv`, `outputs/tables/table_rdd_bandwidth.csv`, `outputs/tables/rdd_claim_language.json` |
| 08 | `Figure_08_mechanisms` | Mechanisms: ET vs. dNBR, vine vs. wild severity, boundary covariate balance | `data/processed/vineyard_fields_fire_sample.csv`, `outputs/tables/table_mechanism_et.csv`, `table_rdd_continuity.csv`, `landscape_severity_summary.json` |
| 09 | `Figure_09_transport` | Transport access: road-distance ECDF, access by fire exposure, network topology | `outputs/figures/data/fig_vineyard_access.csv`, `outputs/tables/table_network_metrics.json` |
| 10 | `Figure_10_smoke_recovery` | Potential smoke exposure (HMS) + NDVI recovery inside vs. outside perimeter | `outputs/tables/table_smoke_daily.csv`, `outputs/figures/data/fig_recovery_trajectory.csv`, `table_recovery_tests.csv` |
| 11 | `Figure_11_synthesis` | Evidence synthesis (8 domains; no composite 0–1 score) | synthesis of all tables above |

## Notes and honest scope
- **Figure 05** is a *coverage/context* panel: the project holds a lidar/GEDI
  data **inventory** (14 OpenTopography datasets, USGS 3DEP tile counts, and
  87,601 valid GEDI RH98 pixels over the perimeter), not a processed
  wall-to-wall canopy-height product. It is presented as context and may be
  moved to the supplement.
- **Figure 06** annotates the *documented* PG&E transmission ignition
  (CAL FIRE / CPUC investigation) as literature context; it is not an
  independent re-derivation of the ignition.
- **Smoke** (Figure 10a) is **potential atmospheric exposure** from NOAA/NESDIS
  HMS plume polygons — overhead smoke detected in satellite imagery — **not**
  ground-level PM2.5 or grape smoke taint.
- **Boundary RDD** (Figure 07) is reported as a *spatial boundary-discontinuity
  association* per `rdd_claim_language.json`; slope differs across the boundary
  (continuity diagnostics in Figure 08c), so it is not interpreted as a clean
  causal design.
- No panel invents data: where a data stream was unavailable, the panel was
  omitted rather than fabricated.

## Reproducibility
- Entry point: `src/visualization/42_make_main_figures.py`
- Style helpers: `src/visualization/style_kincade.py`, `src/visualization/style.py`
- CRS for maps: `EPSG:26910`; scale bars in km.
- Environment: conda env `gee` (geopandas, rasterio, matplotlib, pandas, numpy, Pillow).
