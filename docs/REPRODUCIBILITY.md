# Reproducibility

This project is config-driven and reproducible end to end. Analysis CRS is
NAD83 / UTM zone 10N (EPSG:26910). All parameters live in `config/project.yaml`;
every reported number is appended to `outputs/result_registry.csv` keyed by a
stable result ID.

## 1. Environment

```powershell
conda env create -f environment.yml      # creates env "gee"
# (a full exact solve is archived at environment/gee_env_snapshot.yml)
conda run -n gee python -c "import ee, geopandas, rasterio, pygam, osmnx; print('ok')"
```

External tools for manuscript conversion:
- pandoc >= 3.x (tested with 3.8) — `C:\Program Files\Pandoc\pandoc.exe`
- A LaTeX engine for PDF: xelatex or pdflatex (TeX Live 2024 tested).

Google Earth Engine must be authenticated once: `conda run -n gee earthengine authenticate`.

## 2. Run the full pipeline

```powershell
conda run -n gee python src/pipeline/run_all.py --list      # inspect stages
conda run -n gee python src/pipeline/run_all.py --dry-run   # print commands
conda run -n gee python src/pipeline/run_all.py             # execute all
conda run -n gee python src/pipeline/run_all.py --only analysis   # one group
```

Stage order: acquisition (`src/download/01..08,99`) → analysis
(`src/analysis/25,30,34,36,38,40,45`) → figures (`src/visualization/42`) → tables
(`scripts/build_csvs.py`, `scripts/build_manuscript_tables.py`) → references
(`scripts/build_bib.py`) → manuscript build (below).

## 3. Build the manuscript, supplementary, and tables

```powershell
# Tables 1-4 (CSV + XLSX)
conda run -n gee python scripts/build_manuscript_tables.py

# From manuscript/ (relative bibliography resolves there):
cd manuscript

# DOCX (with citeproc)
& "C:\Program Files\Pandoc\pandoc.exe" Frontiers_Kincade_Manuscript.md `
    --citeproc --bibliography=references.bib -o Frontiers_Kincade_Manuscript.docx

# LaTeX
& "C:\Program Files\Pandoc\pandoc.exe" Frontiers_Kincade_Manuscript.md `
    --citeproc --bibliography=references.bib -s -o Frontiers_Kincade_Manuscript.tex

# PDF (xelatex, with line + page numbers via _header.tex; broad-coverage font)
& "C:\Program Files\Pandoc\pandoc.exe" Frontiers_Kincade_Manuscript.md `
    --citeproc --bibliography=references.bib --pdf-engine=xelatex `
    -H _header.tex -V mainfont="DejaVu Serif" -V monofont="DejaVu Sans Mono" `
    -V geometry:margin=1in -o Frontiers_Kincade_Manuscript.pdf

# Inline figures (embedded in text — for review / sharing; not Frontiers upload format)
cd ..
conda run -n gee python scripts/build_inline_figures_manuscript.py

# Supplementary (docx + pdf) — same flags, Supplementary_Material.md
```

## 4. Verify

```powershell
conda run -n gee python scripts/wordcount.py manuscript/Frontiers_Kincade_Manuscript.md
conda run -n gee python scripts/check_figures.py         # dpi/mode/size
```

- Unresolved citations should be **0** (search the `.tex` for `[@`).
- All output files should be **> 0 bytes** (verified: docx/pdf/tex all non-empty).

## 5. Provenance guarantees

- No number in the manuscript is hand-typed from memory; each traces to
  `outputs/result_registry.csv` (R001–R068) or a per-module summary JSON/CSV.
- References are verified in `references/reference_verification.csv`.
- Generative-AI assistance is disclosed; human verification is required pre-submission.

## 6. Known nondeterminism / caveats

- Live web services (DWR, some agency endpoints) may be intermittently offline;
  the acquisition scripts include documented fallbacks (see `DATA_SOURCES.md`).
- GEE composites depend on the archive state; scene counts may shift slightly over time.
- `USGS/3DEP/10m` is flagged deprecated by GEE but still served.
