# Data guide

## What is in this repository (GitHub)

| Path | Contents |
|---|---|
| `data/processed/` | Analysis-ready vineyard-field and transect tables used by the manuscript |
| `data/raw/fire|vineyards|dins|soils/` | Small clipped GeoPackages for the Kincade AOI |
| `data/raw/smoke/` | NOAA/NESDIS HMS daily smoke polygon zips |
| `data/raw/weather/` | gridMET daily RH/VPD/wind summaries |
| `outputs/tables/` | Manuscript Tables 1–4 and diagnostic CSV/JSON |
| `outputs/figures/data/` | Figure-source CSVs |
| `outputs/figures/final/` | Final figure PNGs |
| `outputs/result_registry.csv` | Locked manuscript numbers |

## What is on Zenodo (not GitHub)

Large clipped analysis rasters needed for offline re-runs of burn severity,
terrain, and OpenET maps:

- `s2_burn_severity.tif`
- `dem_3dep_10m.tif`
- `openet_monthly_2019.tif`
- `landsat8_burn_severity.tif` (cross-check)

Sentinel-2 true-color / SWIR composites for Figure 3 are **not** archived here
by default (large and regenerable). Rebuild with:

```bash
python src/download/09_s2_rgb_composites_gee.py
```

after authenticating Google Earth Engine.

Dataset DOI: https://doi.org/10.5281/zenodo.22713181

## Licenses of source products

Source layers retain original provider licenses (CAL FIRE, WFIGS/NIFC, DWR,
USGS, USDA, Copernicus/Sentinel, OpenET, NOAA, OpenStreetMap ODbL, etc.).
See `docs/DATA_SOURCES.md`.
