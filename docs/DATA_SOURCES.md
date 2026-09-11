# Data Sources — Phase 8 Data Acquisition

**Project:** Kincade Multisystem Resilience
**Event:** Kincade Fire (Sonoma County, CA), ignited 2019-10-23
**Analysis CRS:** EPSG:26910 (UTM Zone 10N, NAD83)
**Study point:** −122.78, 38.79 (near Geyserville)
**AOI for gridded products:** Kincade perimeter bounding box + 5 km buffer
**Acquired:** 2026-08-27 · conda env `gee` · GEE authenticated

All files are catalogued in [`data/data_manifest.csv`](../data/data_manifest.csv)
(dataset_id, path, source, date, size_bytes, checksum_md5, notes). Download
scripts live in `src/download/` and can be re-run end to end. Logs are written
to `outputs/logs/`.

---

## 1. Fire perimeter — Kincade 2019
- **Script:** `src/download/01_fire_perimeter.py`
- **Source:** WFIGS/NIFC **InterAgency Fire Perimeter History – All Years View**
  (ArcGIS FeatureServer, `services3.arcgis.com/T4QMspbfLg3qTGWY`).
  - The specified `WFIGS_Interagency_Perimeters` current/year-to-date layers
    contain only recent incidents (no 2019 records), so the historical view was
    used. Matched on `INCIDENT LIKE '%KINCADE%'`.
- **Outputs:** `data/raw/fire/kincade_perimeter.gpkg`, `.geojson`, `_summary.json`
- **Key facts:** single incident polygon; **GIS_ACRES = 77,762** (computed
  ≈ 78,705 ac in UTM10); `DATE_CUR = 2019-11-10`; bounds (WGS84)
  −122.897, 38.528 → −122.656, 38.816. Matches the published Kincade footprint
  (~77,758 ac).

> **Item 2 (CAL FIRE fallback):** not required — the interagency source
> succeeded. CAL FIRE FRAP endpoints are coded as a fallback in the same script.

## 2. DINS structure damage points
- **Script:** `src/download/02_dins.py`
- **Source:** CAL FIRE **POSTFIRE_MASTER_DATA_SHARE** FeatureServer
  (`services1.arcgis.com/jUJYIo9tSA7EHvfZ`), `INCIDENTNAME LIKE '%KINCADE%'`.
- **Outputs:** `data/raw/dins/kincade_dins.gpkg`, `.geojson`, `_summary.json`
- **Key facts:** **1,568 inspected structures.** Damage breakdown:
  Destroyed (>50%) = 374, Major (25–50%) = 6, Minor (10–25%) = 14,
  Affected (0–10%) = 40, No Damage = 1,134. Rich attributes (construction,
  APN, assessed value, defensive actions, lat/long).

## 3. Vineyards — DWR 2019 Statewide Crop Mapping
- **Script:** `src/download/03_vineyards.py`
- **Source:** DWR **i15 Statewide Crop Mapping 2019** Geodatabase from CNRA Open
  Data (`data.cnra.ca.gov/.../i15_crop_mapping_2019_gdb.zip`, ~86 MB).
  - The live `gis.water.ca.gov` MapServer **and** FeatureServer were **offline**
    ("Service … not started" / HTTP 500) during acquisition, so the official
    statewide GDB was downloaded and processed locally. Both live endpoints are
    still coded as the preferred path and will be used automatically when back
    online.
- **Method:** vineyard class filtered with `SYMB_CLASS = 'V'` (the `CLASS2`
  code column is space-padded, e.g. `" V"`, hence `SYMB_CLASS` is used), read
  with a bbox filter, reprojected to EPSG:26910, and **clipped to the Kincade
  perimeter + 5 km buffer**. A stable `vineyard_field_id` (`VYD_#####`) and
  `area_ha` were added.
- **Outputs:** `data/raw/vineyards/kincade_vineyards.gpkg`, `.geojson`, `_summary.json`
  (source zip cached under `data/raw/vineyards/_source/`).
- **Key facts:** **4,581 vineyard fields, 8,813 ha** within the AOI. Full DWR
  attribute schema retained (CLASS/CROPTYP/IRR_TYP/ACRES/COUNTY/MAIN_CROP…).

## 4. DEM — USGS 3DEP 10 m (GEE)
- **Script:** `src/download/04_dem_gee.py`
- **Source:** GEE `USGS/3DEP/10m` (elevation), clipped to AOI, exported at 10 m.
- **Output:** `data/raw/gee/dem_3dep_10m.tif` (EPSG:26910, 3102 × 4197 px, ~46 MB)
- **Key facts:** elevation 5.7–1,442.9 m (mean ≈ 360 m).

## 5. Burn severity — Sentinel-2 & Landsat-8 (GEE)
- **Script:** `src/download/05_burn_severity_gee.py`
- **Windows:** prefire 2019-09-01 → 2019-10-22; postfire 2019-11-10 → 2019-12-15.
- **Sentinel-2** `COPERNICUS/S2_SR_HARMONIZED` (SCL cloud/shadow masked), NBR =
  (B8−B12)/(B8+B12). Median composites; **dNBR = NBR_pre − NBR_post**;
  **RdNBR = dNBR / √|NBR_pre|**. 71 prefire / 24 postfire scenes.
  - Output: `data/raw/gee/s2_burn_severity.tif` — bands
    `NBR_pre, NBR_post, dNBR, RdNBR` @ 20 m (~48 MB). dNBR range −1.23…1.46.
- **Landsat-8** `LANDSAT/LC08/C02/T1_L2` (QA_PIXEL masked, C2 SR scaling), NBR =
  (SR_B5−SR_B7)/(SR_B5+SR_B7). 9 prefire / 3 postfire scenes.
  - Output: `data/raw/gee/landsat8_burn_severity.tif` — bands
    `NBR_pre, NBR_post, dNBR` @ 30 m (~16 MB). Independent cross-sensor check
    (dNBR mean 0.086 vs S2 0.082).

## 6. OpenET monthly ensemble ET (GEE)
- **Script:** `src/download/06_openet_gee.py`
- **Source:** `projects/openet/assets/ensemble/conus/gridmet/monthly/v2_1`
  (**accessible** with current credentials; band `et_ensemble_mad`, mm/month).
- **Outputs:**
  - `data/raw/gee/openet_monthly_2019.tif` — 7 bands, growing season
    Apr–Oct 2019 (`ET_2019_04 … ET_2019_10`) @ 30 m (~13 MB).
  - `data/raw/gee/openet_vineyard_monthly.csv` — zonal-mean monthly ET for all
    **4,581 vineyard fields** (`reduceRegions`, keyed by `vineyard_field_id`).

## 7. gridMET fire-weather — event window (GEE)
- **Script:** `src/download/07_gridmet.py`
- **Source:** `IDAHO_EPSCOR/GRIDMET` (~4 km daily), 2019-10-23 → 2019-11-06 (15 days).
- **Variables:** tmmn, tmmx, rmin, rmax, vs, th, pr, sph, vpd, erc, bi, fm100,
  fm1000, etr.
- **Outputs:**
  - `data/raw/weather/gridmet_point_geyserville.csv` — daily series at the study point.
  - `data/raw/weather/gridmet_aoi_mean_daily.csv` — AOI-mean daily series.
  - `data/raw/weather/gridmet_wind_daily.tif` — daily wind speed `vs` stack (15 bands @ 4 km).
- **Notes:** captures the Diablo-wind onset — e.g. min RH ≈ 2.8 % (Oct 24) and
  elevated AOI-mean wind on Oct 27, consistent with rapid fire growth.

## 8. Soils — SSURGO (USDA NRCS Soil Data Access)
- **Script:** `src/download/08_ssurgo.py`
- **Source:** USDA NRCS **Soil Data Access** tabular/spatial REST
  (`sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest`). `mupolygon` polygons
  intersecting the AOI bbox joined to `muaggatt` + `mapunit`.
- **Output:** `data/raw/soils/kincade_ssurgo.gpkg`, `.geojson`, `_summary.json`
- **Key facts:** **2,517 map-unit polygons, 253 unique map units.** Attributes:
  `muname, drainage_class, awc_0_100cm, awc_0_150cm, slope_pct,
  hydrologic_group, flooding_freq, bedrock_depth_min`.

---

## Reproducibility
Run in order (conda env `gee`):

```powershell
conda run -n gee python src/download/01_fire_perimeter.py
conda run -n gee python src/download/02_dins.py
conda run -n gee python src/download/03_vineyards.py
conda run -n gee python src/download/04_dem_gee.py
conda run -n gee python src/download/05_burn_severity_gee.py
conda run -n gee python src/download/06_openet_gee.py
conda run -n gee python src/download/07_gridmet.py
conda run -n gee python src/download/08_ssurgo.py
conda run -n gee python src/download/99_finalize_manifest.py
```

Shared helpers: `src/download/common.py` (paths, CRS, manifest, checksums) and
`src/download/gee_utils.py` (EE init, AOI, tiled GeoTIFF downloader that fetches
`getDownloadURL` GeoTIFF tiles and assembles them locally — no Drive export).

## Blockers / caveats
- **DWR live crop-mapping services (MapServer + FeatureServer) were down** during
  acquisition; the official statewide GDB was used instead (identical data).
- All GEE products are downloaded directly to local GeoTIFF via tiled
  `getDownloadURL`; a single request must stay < 48 MB, so multi-band/large
  exports are tiled automatically.
- `USGS/3DEP/10m` is flagged deprecated by GEE but still served; swap to the
  successor asset if it is retired.
- No credentials beyond the existing GEE auth were required; OpenET v2_1 was
  reachable without additional access grants.
