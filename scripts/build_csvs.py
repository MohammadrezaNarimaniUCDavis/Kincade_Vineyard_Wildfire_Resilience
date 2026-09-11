"""Build literature_review.csv and reference_verification.csv from verified
Crossref metadata (bib_metadata.json) plus hand-curated thematic annotations
and grey-literature rows. Uses csv module for correct quoting."""
import csv
import json

with open("bib_metadata.json", "r", encoding="utf-8") as fh:
    META = {r["citekey"]: r for r in json.load(fh)}

# Grey-literature / data metadata (verified via WebSearch / DataCite / Crossref search).
GREY_META = {
    "calfire2020kincade": {
        "authors": "California Department of Forestry and Fire Protection (CAL FIRE)",
        "year": "2020", "title": "CAL FIRE Investigators Determine Cause of the Kincade Fire",
        "venue": "CAL FIRE news release", "type": "report", "doi": "", "source": "grey"},
    "cpuc2021kincadeinvestigation": {
        "authors": "California Public Utilities Commission, Safety and Enforcement Division",
        "year": "2021", "title": "Investigation Report on the Utility Company Involvement with the Kincade Fire that Started on October 23, 2019",
        "venue": "California Public Utilities Commission", "type": "report", "doi": "", "source": "grey"},
    "cpuc2021consentorder": {
        "authors": "California Public Utilities Commission",
        "year": "2021", "title": "Resolution SED-6: Administrative Consent Order and Agreement regarding the 2019 Kincade Fire",
        "venue": "California Public Utilities Commission", "type": "report", "doi": "", "source": "grey"},
    "sonoma2020kincadeaar": {
        "authors": "County of Sonoma",
        "year": "2020", "title": "2019 Kincade Fire After Action Report / Improvement Plan",
        "venue": "County of Sonoma, Department of Emergency Management", "type": "report", "doi": "", "source": "grey"},
    "nass2020grapecrush": {
        "authors": "USDA National Agricultural Statistics Service and California Department of Food and Agriculture",
        "year": "2020", "title": "California Grape Crush Report, Final 2019",
        "venue": "USDA NASS Pacific Regional Office", "type": "report", "doi": "", "source": "grey"},
    "perkins2025postfiresoils": {
        "authors": "Perkins, Kimberlie and Cerovski-Darriau, Corina R. and Baird, Allegra F. and Prancevic, Jeffrey P.",
        "year": "2025", "title": "Soil texture for infiltration parameters: postfire soil hydrologic and biogeochemical response and recovery in northern California, USA",
        "venue": "U.S. Geological Survey data release", "type": "dataset", "doi": "10.5066/P13WGEQS", "source": "datacite"},
    "purdy2021psps": {
        "authors": "Purdy, Scott",
        "year": "2021", "title": "Fire Weather Associated with the 2019 Northern California Public Safety Power Shutoff Events",
        "venue": "San Jose State University (M.S. thesis)", "type": "dissertation", "doi": "10.31979/etd.w9ez-52xy", "source": "crossref"},
}
for _k, _v in GREY_META.items():
    META.setdefault(_k, _v)

# citekey -> (theme, relevance_to_kincade, key_contribution, novelty_gap_addressed)
ANNOT = {
    "brown2022sonoma": ("Kincade event / community", "Directly documents Sonoma County residents' lived experience of the 2019 PSPS outages and Kincade Fire.", "Qualitative case study linking power shutoffs, communication, and community disruption.", "Grounds the human/community system in the study's multisystem frame."),
    "xu2023kincade": ("Kincade event / evacuation", "Machine-learning analysis of evacuation decisions in the 2019 Kincade Fire itself.", "Predicts evacuation decision-making from survey + contextual data.", "Establishes transportation/evacuation as a coupled subsystem for the same event."),
    "sayarshad2025sonoma": ("Kincade event / fire spread", "Wildfire growth modelling using Sonoma County (Kincade context) as case study.", "Optimization/prevention modelling on heterogeneous landscapes.", "Contrasts single-system fire-spread modelling with the multisystem approach."),
    "lumpkin2026birds": ("Kincade event / ecology", "Post-Kincade ecological response (breeding birds) in Sonoma County.", "Field evidence of biodiversity change after the fire.", "Shows ecosystem-response literature is single-taxon, not cross-system."),
    "abatzoglou2016climate": ("Fire regime / climate", "Explains the climate drivers intensifying California fire seasons like 2019.", "Attributes increased western US forest fire to anthropogenic climate change.", "Frames the climate backdrop; not event- or agriculture-specific."),
    "balch2017human": ("Fire regime / ignition", "Human/electrical ignition context relevant to PG&E-caused Kincade.", "Quantifies human expansion of the fire niche across the US.", "Motivates infrastructure-ignition framing absent in RS-only studies."),
    "radeloff2018wui": ("WUI / exposure", "WUI growth context; contrast case for building-centric framing.", "Maps rapid US WUI growth and associated wildfire risk.", "Represents the building/WUI-centric paradigm this study extends beyond."),
    "cattau2022pyromes": ("Fire regime / typology", "Situates California fire characteristics within US 'pyromes'.", "Biogeographical classification of fire regimes.", "Provides regime context; not multisystem resilience."),
    "eidenshink2007mtbs": ("Burn severity / methods", "MTBS is a standard burn-severity mapping framework used for perimeters/severity.", "Establishes national burn-severity monitoring program.", "Baseline severity method the study builds on for boundary analysis."),
    "miller2007rdnbr": ("Burn severity / methods", "RdNBR/dNBR severity method applicable over mixed vineyard-wildland cover.", "Relative dNBR improves severity mapping in heterogeneous landscapes.", "Method the study adapts and interprets cautiously over vineyards."),
    "key2006severity": ("Burn severity / methods", "Sampling/definition constraints for landscape fire severity.", "Clarifies ecological limits of severity indices.", "Supports careful severity interpretation at land-cover boundaries."),
    "gorelick2017gee": ("Platform / reproducibility", "Google Earth Engine underpins the reproducible multi-sensor workflow.", "Planetary-scale cloud geospatial analysis platform.", "Enables the open, transferable pipeline emphasized for the RT."),
    "drusch2012sentinel2": ("Sensors / optical", "Sentinel-2 is a core optical sensor for vineyard/vegetation status.", "Describes the Sentinel-2 mission and capabilities.", "Sensor foundation for the water-status subsystem."),
    "melton2022openet": ("Water status / ET", "OpenET provides operational ET central to vineyard water-status analysis.", "Ensemble satellite ET data product for the western US.", "Core data source distinguishing the water/agriculture subsystem."),
    "abatzoglou2013gridmet": ("Climate / meteorology", "GRIDMET supplies meteorological forcing for ET and fire-weather context.", "Gridded surface meteorological dataset.", "Meteorological backbone for cross-system covariates."),
    "bellvert2015cwsi": ("Water status / vineyard", "Grapevine crop water stress index from thermal remote sensing.", "Links canopy temperature to vine water status by variety.", "Agronomic water-status method integrated into the fire context."),
    "kalua2020vineyardet": ("Water status / vineyard", "Quantifies uncertainty of satellite ET over vineyards using sUAS.", "Cross-scale ET validation in California vineyards.", "Supports rigorous ET use in the boundary/causal design."),
    "dubayah2020gedi": ("3-D fuels / lidar", "GEDI spaceborne lidar characterizes 3-D canopy/fuel structure.", "Describes the GEDI mission and canopy structure retrievals.", "Enables 3-D fuels subsystem beyond 2-D severity mapping."),
    "neumann2019icesat2": ("3-D fuels / lidar", "ICESat-2 ATLAS photon data supports structure/terrain retrieval.", "Global geolocated photon product from ATLAS.", "Second spaceborne lidar source for 3-D structure."),
    "neuenschwander2019atl08": ("3-D fuels / lidar", "ATL08 land/vegetation product gives canopy height along-track.", "Defines the ICESat-2 canopy/terrain product.", "Operational canopy-height input for fuels characterization."),
    "malambo2024canopy": ("3-D fuels / lidar", "CONUS canopy-height mapping from ICESat-2 relevant to the study area.", "Wall-to-wall canopy height from lidar + ancillary data.", "Bridges sparse lidar to continuous 3-D fuels fields."),
    "pascual2026firebehavior": ("3-D fuels / fire behavior", "Derives canopy base height/bulk density for fire behavior from lidar.", "Airborne+spaceborne lidar estimates of CBH/CBD.", "Connects 3-D fuels to fire-behavior parameters explicitly."),
    "engelstad2019canopyfuel": ("3-D fuels / fuels", "Canopy fuel attributes from low-density lidar.", "Estimates canopy fuel load metrics from lidar.", "Establishes fuel-metric retrieval feeding the fuels subsystem."),
    "keele2015geographic": ("Causal inference / spatial RDD", "Foundational method for treating land-cover boundaries as discontinuities.", "Formalizes geographic boundaries as regression discontinuities.", "Core causal-identification method at vineyard-wildland edges."),
    "calonico2014robust": ("Causal inference / RDD", "Robust bias-corrected RDD inference used for boundary estimates.", "Robust nonparametric CIs and bandwidth selection for RDD.", "Provides defensible estimation for the spatial RDD."),
    "lee2010rdd": ("Causal inference / RDD", "Canonical RDD reference framing identification assumptions.", "Comprehensive review of RDD in economics.", "Theoretical grounding for the causal design."),
    "wuepper2020spatialrdd": ("Causal inference / spatial RDD", "Applied spatial RDD at agricultural/administrative boundaries.", "Uses spatial RDD to estimate farming/environmental outcomes.", "Precedent for spatial RDD in an agricultural land-use context."),
    "reid2016smokehealth": ("Smoke / health", "Wildfire smoke health impacts frame the smoke exposure subsystem.", "Critical review of PM/smoke health effects.", "Anchors smoke-exposure (not smoke-taint) framing."),
    "krstic2015smoketaint": ("Smoke / grapes (chemistry caveat)", "Defines smoke-taint biomarkers; flags need for chemistry to claim taint.", "Reviews volatile phenols/glycosides as smoke-exposure biomarkers.", "Justifies avoiding smoke-taint claims without chemical assays."),
    "summerson2021smokereview": ("Smoke / grapes (chemistry caveat)", "Reviews technologies to assess grapevine smoke contamination.", "Synthesizes smoke-exposure assessment methods for grapes/wine.", "Delimits what remote sensing can vs cannot claim about taint."),
    "zakowski2023winegrape": ("Agriculture / wildfire risk", "California-specific wine-grape grower needs for wildfire/smoke risk mgmt.", "Survey of grower risk-management gaps in California.", "Ties the agricultural resilience subsystem to practice/policy."),
    "wong2023evacuee": ("Transportation / evacuation", "California wildfire evacuee behavior and joint choices.", "Behavioral models of evacuation and departure choices.", "Transportation subsystem behavior across California fires."),
    "borody2025evacuation": ("Transportation / evacuation", "Network-mobility-derived evacuation and reentry dynamics.", "Empirical evacuation/reentry curves from mobility data.", "Quantitative transportation-resilience metric for cross-system analysis."),
    "steel2025cwpp": ("Community / rural resilience", "Rural community wildfire protection planning resilience.", "Assesses CWPPs for climate/wildfire resilience.", "Community-planning subsystem and decision-support angle."),
    "moftakhari2019compound": ("Cascading / infrastructure", "Compound wildfire + rainfall hazards to energy infrastructure.", "Quantifies compounding exposure of energy infrastructure.", "Direct precedent for cascading/compound multisystem framing."),
    "alcantara2025cascading": ("Cascading / theory", "Conceptual grounding for cascading hazards and compound disasters.", "Synthesizes cascading-hazard and compound-disaster concepts.", "Provides the theoretical scaffold for 'multisystem' resilience."),
    "li2025coupled": ("Multisystem / methods", "ML for resilience in coupled human-infrastructure systems.", "Data-driven coupled-systems resilience assessment.", "Methodological precedent for coupled-systems resilience metrics."),
    "chen2014cnh": ("Coupled human-natural systems", "Landscape-ecology view of coupled natural and human systems.", "Frames CNH interactions at landscape scale.", "Foundational CNH framing for the vineyard-wildland mosaic."),
    "neris2023soilerosion": ("Post-fire soils / hydrology", "Post-fire soil erosion processes relevant to recovery subsystem.", "Assesses post-fire soil losses and controls.", "Links burn severity to soil/hydrologic recovery outcomes."),
    "biswas2025geoai": ("GeoAI / contrast", "Represents generic GeoAI wildfire-susceptibility remote sensing.", "Compares ML/DL ensembles for California susceptibility.", "Explicit contrast: single-outcome GeoAI vs multisystem resilience."),
    # ---- grey literature / data ----
    "calfire2020kincade": ("Kincade event / ignition (grey)", "CAL FIRE cause determination: PG&E transmission lines.", "Official cause attribution to electrical infrastructure.", "Primary electrical-ignition provenance for the event."),
    "cpuc2021kincadeinvestigation": ("Kincade event / ignition (grey)", "CPUC SED investigation detailing GO 95 / PU Code 451 violations.", "Regulatory investigation of PG&E infrastructure failure.", "Authoritative infrastructure-failure documentation."),
    "cpuc2021consentorder": ("Kincade event / policy (grey)", "CPUC Resolution SED-6 $125M administrative consent order.", "Regulatory penalty/settlement record.", "Policy/decision context for the electrical subsystem."),
    "sonoma2020kincadeaar": ("Kincade event / emergency mgmt (grey)", "Official acreage, structures, and 186,000+ evacuations.", "After-action facts and improvement plan.", "Authoritative event statistics for multiple subsystems."),
    "nass2020grapecrush": ("Agriculture / statistics (grey)", "2019 California grape crush tonnage/prices by district.", "Official agricultural production/value statistics.", "Baseline agricultural-value data for the vineyard subsystem."),
    "perkins2025postfiresoils": ("Post-fire soils / data (grey)", "USGS post-fire soil hydrologic/biogeochemical data, northern California.", "Field/lab soil texture + infiltration parameters data release.", "Primary post-fire soils dataset for the recovery subsystem."),
    "purdy2021psps": ("Fire weather / PSPS (grey)", "Fire weather during the 2019 Northern California PSPS events.", "Synoptic/fire-weather analysis of the 2019 PSPS period.", "Meteorological/PSPS context for the ignition-avoidance subsystem."),
}

# verification metadata: citekey -> (registration_agency, http_status, title_match, status, method, notes)
VERIF = {
    # crossref scholarly -> all HTTP 200, verified
}
CROSSREF_KEYS = [k for k, v in ANNOT.items() if META.get(k, {}).get("source") == "crossref"]
for k in CROSSREF_KEYS:
    VERIF[k] = ("Crossref", "200", "yes", "verified", "Crossref /works/{doi} metadata match", "Title/authors/year/venue returned by Crossref.")

VERIF["calfire2020kincade"] = ("none (agency URL)", "n/a", "n/a", "pending_manual",
    "WebSearch corroboration (CPUC ACO + Sonoma DA)",
    "CAL FIRE cause statement corroborated by CPUC ACO and Sonoma DA; incident URL constructed, not directly fetched. Confirm exact CAL FIRE release URL.")
VERIF["cpuc2021kincadeinvestigation"] = ("none (agency URL)", "200", "yes", "verified",
    "WebFetch of CPUC SED report PDF", "PDF content confirms GO 95 / PU Code 451 violations.")
VERIF["cpuc2021consentorder"] = ("none (agency URL)", "200", "yes", "verified",
    "WebFetch of CPUC Resolution SED-6 PDF", "PDF confirms $125M ACO, 2 Dec 2021, 77,758 acres / 374 structures.")
VERIF["sonoma2020kincadeaar"] = ("none (agency URL)", "200", "partial", "verified",
    "WebFetch of AAR PDF (city mirror)", "Content confirmed; hosted on City of Sebastopol mirror. Confirm canonical County of Sonoma URL.")
VERIF["nass2020grapecrush"] = ("none (agency URL)", "200", "yes", "verified",
    "WebFetch of USDA NASS PDF", "PDF confirms Final 2019 crush = 4,114,672 tons; NASS/CDFA.")
VERIF["perkins2025postfiresoils"] = ("DataCite", "200", "yes", "verified",
    "DataCite REST API", "USGS data release; title/creators/year/publisher confirmed.")
VERIF["purdy2021psps"] = ("Crossref", "200", "yes", "verified",
    "Crossref /works/{doi}", "SJSU ETD; metadata confirmed via Crossref search.")


def main():
    # literature_review.csv
    lit_fields = ["citekey", "theme", "authors", "year", "title", "venue", "type",
                  "doi", "relevance_to_kincade", "key_contribution",
                  "novelty_gap_addressed", "verification_status"]
    with open("../references/literature_review.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=lit_fields)
        w.writeheader()
        for k, (theme, rel, key, gap) in ANNOT.items():
            m = META.get(k, {})
            w.writerow({
                "citekey": k,
                "theme": theme,
                "authors": m.get("authors", ""),
                "year": m.get("year", ""),
                "title": m.get("title", ""),
                "venue": m.get("venue", ""),
                "type": m.get("type", ""),
                "doi": m.get("doi", ""),
                "relevance_to_kincade": rel,
                "key_contribution": key,
                "novelty_gap_addressed": gap,
                "verification_status": VERIF.get(k, ("", "", "", "pending_manual"))[3],
            })

    # reference_verification.csv
    ver_fields = ["citekey", "doi", "registration_agency", "http_status",
                  "title_match", "verification_status", "verification_method",
                  "checked_date", "notes"]
    with open("../references/reference_verification.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ver_fields)
        w.writeheader()
        for k in ANNOT:
            m = META.get(k, {})
            agency, http, tmatch, status, method, notes = VERIF.get(
                k, ("", "", "", "pending_manual", "", ""))
            w.writerow({
                "citekey": k,
                "doi": m.get("doi", GREY_DOI.get(k, "")),
                "registration_agency": agency,
                "http_status": http,
                "title_match": tmatch,
                "verification_status": status,
                "verification_method": method,
                "checked_date": "2026-08-27",
                "notes": notes,
            })
    print("wrote literature_review.csv and reference_verification.csv with", len(ANNOT), "rows")


GREY_DOI = {
    "perkins2025postfiresoils": "10.5066/P13WGEQS",
    "purdy2021psps": "10.31979/etd.w9ez-52xy",
    "calfire2020kincade": "",
    "cpuc2021kincadeinvestigation": "",
    "cpuc2021consentorder": "",
    "sonoma2020kincadeaar": "",
    "nass2020grapecrush": "",
}

if __name__ == "__main__":
    main()
