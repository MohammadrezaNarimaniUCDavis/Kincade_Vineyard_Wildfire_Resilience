# Kincade Vineyard Wildfire Resilience

Public replication package for an **open geospatial assessment** of vineyard
wildfire impacts and resilience during the **2019 Kincade Fire** (Sonoma County,
California).

> Farajpoor, P., Khoshnevis Ansari, H., Ardebili Pour, M., Ghiasi, M. B., &
> Narimani, M. (2026). *Multisource Remote Sensing and Geospatial Analysis of
> Vineyard Wildfire Impacts and Resilience: The 2019 Kincade Fire.*
> Preprint submitted to *Frontiers in Sustainability*.

**Authors and affiliations**

| Author | Affiliation |
|---|---|
| Parastoo Farajpoor | Department of Biological and Agricultural Engineering, University of California, Davis |
| Hanieh Khoshnevis Ansari | Department of Civil and Environmental Engineering, University of California, Davis |
| Mahla Ardebili Pour | Department of Civil and Environmental Engineering, University of California, Davis |
| Mohammad Bagher Ghiasi | Department of Electrical and Computer Engineering, University of California, Davis |
| Mohammadreza Narimani (corresponding) | Department of Biological and Agricultural Engineering, University of California, Davis |

**Contact:** mnarimani@ucdavis.edu

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22713181-blue.svg)](https://doi.org/10.5281/zenodo.22713181)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

| Resource | Link |
|---|---|
| **Dataset (Zenodo)** | https://doi.org/10.5281/zenodo.22713181 |
| **This code** | https://github.com/MohammadrezaNarimaniUCDavis/Kincade_Vineyard_Wildfire_Resilience |

This repository is the **public replication package**. It contains only the
audited `.py` scripts and analysis-ready products needed to reproduce the
paper’s principal tables, diagnostics, and figures. The authors’ full working
archive remains private.

---

## What this study does

1. Map **4,581** vineyard fields (8,813.2 ha) against the 2019 Kincade Fire perimeter.
2. Quantify pre-fire canopy–water status (NDMI/NDVI–OpenET), vineyard–wildland
   dNBR contrast, and spatial-boundary / GAM diagnostics.
3. Add cascading exposure layers: overhead HMS smoke, OSM road topology, and
   post-fire greenness recovery through 2021.
4. Keep claims at their native analytical units — **no composite resilience score**.

### Locked headline numbers

| Metric | Value |
|---|---|
| Vineyard / wildland mean dNBR | 0.130 / 0.337 |
| Boundary contrast at 100 m ($\tau$) | −0.0166 |
| Spatial GAM residual Moran’s $I$ | 0.519 |
| Mean potential smoke-days / field | 7.78 |
| Dead-end road nodes | 34.2% |
| 2021 recovery ratio (inside / outside) | 0.8145 / 0.8543 |

---

## Repository layout

```
Kincade_Vineyard_Wildfire_Resilience/
├── config/                 # project + figure style
├── data/
│   ├── processed/          # analysis-ready tables (shipped)
│   └── raw/                # small clipped vectors + weather/smoke
├── docs/                   # DATA, REPRODUCIBILITY, NOTICE
├── outputs/
│   ├── tables/             # manuscript tables + diagnostics
│   ├── figures/data/       # figure-source CSVs
│   └── figures/final/      # final PNGs
├── src/
│   ├── download/           # 01–09, 99
│   ├── analysis/           # 25–45
│   ├── visualization/      # 42_make_main_figures.py
│   └── pipeline/
├── scripts/                # table builders
├── run_pipeline.py
├── environment.yml
├── requirements.txt
├── CITATION.cff
└── LICENSE
```

---

## Quick start

```bash
conda env create -f environment.yml
conda activate gee
# Optional: earthengine authenticate   # only if re-downloading GEE layers
python run_pipeline.py --from 25       # analysis + figures using shipped data
```

To rebuild only figures from shipped figure-source tables:

```bash
python src/visualization/42_make_main_figures.py
```

Large analysis rasters (burn severity, DEM, OpenET) are on **Zenodo**
(https://doi.org/10.5281/zenodo.22713181). Place them under `data/raw/gee/` if you
need offline map regeneration.

---

## Data availability

| Content | Location |
|---|---|
| Code + processed tables + manuscript diagnostics | **This GitHub repo** |
| Clipped analysis rasters (S2 dNBR, DEM, OpenET, Landsat check) | **Zenodo** |
| Statewide vineyard source / full lidar point clouds | **Not redistributed** (public providers) |

See [`docs/DATA.md`](docs/DATA.md).

---

## Citation

**Paper (preferred):**

```bibtex
@article{kincade2026vineyard,
  author  = {Farajpoor, Parastoo and Khoshnevis Ansari, Hanieh and
              Ardebili Pour, Mahla and Ghiasi, Mohammad Bagher and
              Narimani, Mohammadreza},
  title   = {Multisource Remote Sensing and Geospatial Analysis of Vineyard
              Wildfire Impacts and Resilience: The 2019 Kincade Fire},
  year    = {2026},
  note    = {Preprint submitted to Frontiers in Sustainability}
}
```

**Dataset:**

```bibtex
@misc{kincade2026data,
  author    = {Farajpoor, Parastoo and Khoshnevis Ansari, Hanieh and
                Ardebili Pour, Mahla and Ghiasi, Mohammad Bagher and
                Narimani, Mohammadreza},
  title     = {Kincade Vineyard Wildfire Resilience: Analysis-Ready Geospatial
                Products for the 2019 Kincade Fire},
  year      = {2026},
  publisher = {Zenodo},
  version   = {1.0.0},
  doi       = {10.5281/zenodo.22713181}
}
```

---

## License

Code is released under the [MIT License](LICENSE). Source geospatial products
retain their original provider licenses (see `docs/DATA_SOURCES.md`).
The Zenodo dataset is distributed under **CC-BY-4.0**.

## Contact

Mohammadreza Narimani — mnarimani@ucdavis.edu
