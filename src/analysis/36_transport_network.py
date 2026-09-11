"""Transportation network structure around Kincade-area vineyards (OpenStreetMap).

Downloads the drivable OSM road network for the study AOI with osmnx, computes
basic graph metrics, and derives vineyard-centroid accessibility measures:
  - edge betweenness centrality on a sampled set of node pairs,
  - dead-end (cul-de-sac) exposure: distance from each vineyard centroid to the
    nearest degree-1 (dead-end) node,
  - distance from each vineyard centroid to the nearest major road
    (motorway/trunk/primary/secondary).

No traffic volumes are invented; only network geometry/topology is used.

A historical Overpass snapshot near the 2019 fire date is requested first
([date:2019-10-23]); if unavailable the current network is used and flagged as
a caveat. The env ships osmnx built against geopandas >=1.0 while geopandas is
0.14.x, so we use osmnx only to fetch the (lat/lon) graph and then build/project
GeoDataFrames with geopandas directly, avoiding osmnx's incompatible converters.

Outputs
-------
- data/processed/osm_edges_aoi.gpkg / osm_nodes_aoi.gpkg
- data/processed/vineyard_network_access.csv
- outputs/tables/table_network_metrics.json
- outputs/tables/table_network_edge_betweenness.csv (top edges)
- outputs/figures/data/fig_vineyard_access.csv
- appends rows to outputs/result_registry.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import LineString, box

# osmnx (installed) expects geopandas >=1.0 APIs; the env ships geopandas 0.14.x.
# Shim the few attributes osmnx touches during download so graph_from_polygon works.
if not hasattr(gpd.GeoDataFrame, "union_all"):
    gpd.GeoDataFrame.union_all = lambda self, *a, **k: self.geometry.unary_union
if not hasattr(gpd.GeoSeries, "union_all"):
    gpd.GeoSeries.union_all = lambda self, *a, **k: self.unary_union
if not hasattr(gpd.GeoDataFrame, "active_geometry_name"):
    gpd.GeoDataFrame.active_geometry_name = property(
        lambda self: getattr(self, "_geometry_column_name", None))

import osmnx as ox  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_common import (  # noqa: E402
    CRS,
    FIGDATA,
    PROC,
    RAW,
    TABLES,
    WGS84,
    append_registry,
    get_logger,
)

log = get_logger("36_transport_network")
SCRIPT = "src/analysis/36_transport_network.py"
MAJOR = {"motorway", "trunk", "primary", "secondary",
         "motorway_link", "trunk_link", "primary_link", "secondary_link"}
BETWEENNESS_SAMPLE = 400
SEED = 42


def _hwy_set(val) -> set:
    if isinstance(val, list):
        return set(val)
    return {val}


def _first(val):
    return val[0] if isinstance(val, list) else val


def download_graph(poly_wgs):
    """Return (graph, provenance). Try 2019 historical snapshot, else current."""
    ox.settings.log_console = False
    ox.settings.use_cache = True
    try:
        ox.settings.overpass_settings = '[out:json][timeout:180][date:"2019-10-23T00:00:00Z"]'
        G = ox.graph_from_polygon(poly_wgs, network_type="drive", simplify=True, retain_all=True)
        log.info("Downloaded historical (2019-10-23) OSM network")
        return G, ('OSM historical snapshot via Overpass [date:2019-10-23]; '
                   'osmnx graph_from_polygon network_type=drive')
    except Exception as e:  # noqa: BLE001
        log.warning("Historical Overpass snapshot unavailable (%s); using current OSM", e)
        ox.settings.overpass_settings = "[out:json][timeout:180]"
        G = ox.graph_from_polygon(poly_wgs, network_type="drive", simplify=True, retain_all=True)
        return G, ('OSM CURRENT network (historical snapshot unavailable); osmnx '
                   'graph_from_polygon network_type=drive. CAVEAT: present-day topology, '
                   'not necessarily Oct 2019.')


def graph_to_gdfs_manual(G):
    """Build node/edge GeoDataFrames (EPSG:4326) directly from the osmnx graph."""
    node_ids, node_geoms = [], []
    for nid, data in G.nodes(data=True):
        node_ids.append(nid)
        node_geoms.append(gpd.points_from_xy([data["x"]], [data["y"]])[0])
    nodes = gpd.GeoDataFrame({"osmid": node_ids}, geometry=node_geoms, crs=WGS84)

    coord = {nid: (data["x"], data["y"]) for nid, data in G.nodes(data=True)}
    rows, geoms = [], []
    for u, v, k, data in G.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is None:
            geom = LineString([coord[u], coord[v]])
        rows.append({
            "u": u, "v": v, "key": k,
            "osmid": str(_first(data.get("osmid", ""))),
            "name": str(_first(data.get("name", ""))),
            "highway": _first(data.get("highway", "")),
            "length": float(data.get("length", np.nan)),
        })
        geoms.append(geom)
    edges = gpd.GeoDataFrame(rows, geometry=geoms, crs=WGS84)
    return nodes, edges


def main() -> int:
    fire = gpd.read_file(RAW / "fire" / "kincade_perimeter.gpkg").to_crs(CRS)
    vy = gpd.read_file(RAW / "vineyards" / "kincade_vineyards.gpkg").to_crs(CRS)
    vy = vy[vy.geometry.is_valid & ~vy.geometry.is_empty].copy()
    if "area_ha" not in vy.columns:
        vy["area_ha"] = vy.geometry.area / 10000.0
    fire_u = fire.geometry.unary_union

    minx, miny, maxx, maxy = fire.total_bounds
    buf = 5000.0
    aoi_utm = box(minx - buf, miny - buf, maxx + buf, maxy + buf)
    poly_wgs = gpd.GeoDataFrame(geometry=[aoi_utm], crs=CRS).to_crs(WGS84).iloc[0].geometry

    G, provenance = download_graph(poly_wgs)
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    log.info("Network: %d nodes, %d edges (%s)", n_nodes, n_edges, provenance)

    nodes_wgs, edges_wgs = graph_to_gdfs_manual(G)
    nodes = nodes_wgs.to_crs(CRS)
    edges = edges_wgs.to_crs(CRS)

    # osmnx 'length' is geodesic metres; fall back to projected length if missing
    if edges["length"].isna().any():
        edges.loc[edges["length"].isna(), "length"] = edges.loc[edges["length"].isna()].geometry.length

    edges["is_major"] = edges["highway"].apply(lambda h: bool(_hwy_set(h) & MAJOR))
    major_edges = edges[edges["is_major"]].copy()

    # undirected topology (dedupe two-way directed pairs -> single edge)
    Gu = nx.Graph()
    Gu.add_nodes_from(G.nodes())
    for u, v, data in G.edges(data=True):
        w = float(data.get("length", 1.0))
        if Gu.has_edge(u, v):
            if w < Gu[u][v]["length"]:
                Gu[u][v]["length"] = w
        else:
            Gu.add_edge(u, v, length=w)

    # road lengths from the undirected graph (avoids double-counting two-way roads)
    total_len_km = float(sum(d["length"] for _, _, d in Gu.edges(data=True)) / 1000.0)
    major_len_km = float(
        major_edges.assign(uv_key=lambda d: d.apply(lambda r: frozenset((r["u"], r["v"])), axis=1))
        .drop_duplicates("uv_key")["length"].sum() / 1000.0)
    deg = dict(Gu.degree())
    deadend_nodes = [nid for nid, d in deg.items() if d == 1]
    intersection_nodes = [nid for nid, d in deg.items() if d >= 3]
    node_pt = {nid: geom for nid, geom in zip(nodes["osmid"], nodes.geometry)}

    # approximate edge betweenness (sampled node pairs, length-weighted)
    edge_bc = nx.edge_betweenness_centrality(
        Gu, k=min(BETWEENNESS_SAMPLE, n_nodes), weight="length", seed=SEED)

    def _bc(row):
        return edge_bc.get((row["u"], row["v"]), edge_bc.get((row["v"], row["u"]), 0.0))
    edges["edge_betweenness"] = edges.apply(_bc, axis=1)
    top_edges = edges.sort_values("edge_betweenness", ascending=False).head(50)
    top_edges[["u", "v", "osmid", "name", "highway", "length", "edge_betweenness", "is_major"]].to_csv(
        TABLES / "table_network_edge_betweenness.csv", index=False)

    # vineyard centroids
    cents = gpd.GeoDataFrame(
        {"vineyard_field_id": vy["vineyard_field_id"].values, "area_ha": vy["area_ha"].values},
        geometry=list(vy.geometry.centroid), crs=CRS)
    cents["in_perimeter"] = cents.geometry.intersects(fire_u).astype(int)

    nn = gpd.sjoin_nearest(cents[["vineyard_field_id", "geometry"]], nodes[["osmid", "geometry"]],
                           how="left", distance_col="dist_nearest_node_m").drop_duplicates(
        "vineyard_field_id")

    if deadend_nodes:
        de_gdf = gpd.GeoDataFrame({"node": deadend_nodes},
                                  geometry=[node_pt[n] for n in deadend_nodes], crs=CRS)
        de = gpd.sjoin_nearest(cents[["vineyard_field_id", "geometry"]], de_gdf,
                               how="left", distance_col="dist_nearest_deadend_m").drop_duplicates(
            "vineyard_field_id")
    else:
        de = cents[["vineyard_field_id"]].copy()
        de["dist_nearest_deadend_m"] = np.nan

    if not major_edges.empty:
        md = gpd.sjoin_nearest(cents[["vineyard_field_id", "geometry"]], major_edges[["geometry"]],
                               how="left", distance_col="dist_major_road_m").drop_duplicates(
            "vineyard_field_id")
    else:
        md = cents[["vineyard_field_id"]].copy()
        md["dist_major_road_m"] = np.nan

    access = (cents[["vineyard_field_id", "area_ha", "in_perimeter"]]
              .merge(nn[["vineyard_field_id", "dist_nearest_node_m"]], on="vineyard_field_id", how="left")
              .merge(de[["vineyard_field_id", "dist_nearest_deadend_m"]], on="vineyard_field_id", how="left")
              .merge(md[["vineyard_field_id", "dist_major_road_m"]], on="vineyard_field_id", how="left"))
    access.to_csv(PROC / "vineyard_network_access.csv", index=False)
    access.to_csv(FIGDATA / "fig_vineyard_access.csv", index=False)

    try:
        edges_out = edges.copy()
        edges_out["highway"] = edges_out["highway"].apply(
            lambda x: ";".join(map(str, x)) if isinstance(x, list) else x)
        edges_out.to_file(PROC / "osm_edges_aoi.gpkg", driver="GPKG")
        nodes.assign(degree=[deg.get(n, 0) for n in nodes["osmid"]]).to_file(
            PROC / "osm_nodes_aoi.gpkg", driver="GPKG")
    except Exception as e:  # noqa: BLE001
        log.warning("Could not write network gpkg layers: %s", e)

    metrics = {
        "network_provenance": provenance,
        "aoi_buffer_m": buf,
        "n_nodes": int(n_nodes),
        "n_edges": int(n_edges),
        "total_road_length_km": round(total_len_km, 1),
        "major_road_length_km": round(major_len_km, 1),
        "n_deadend_nodes": int(len(deadend_nodes)),
        "n_intersection_nodes_deg3plus": int(len(intersection_nodes)),
        "frac_deadend_nodes": round(len(deadend_nodes) / n_nodes, 4) if n_nodes else None,
        "betweenness_sample_pairs": int(min(BETWEENNESS_SAMPLE, n_nodes)),
        "max_edge_betweenness": float(edges["edge_betweenness"].max()),
        "vineyard_access": {
            "n_fields": int(len(access)),
            "median_dist_nearest_node_m": round(float(access["dist_nearest_node_m"].median()), 1),
            "median_dist_nearest_deadend_m": round(float(access["dist_nearest_deadend_m"].median()), 1),
            "median_dist_major_road_m": round(float(access["dist_major_road_m"].median()), 1),
            "mean_dist_major_road_m": round(float(access["dist_major_road_m"].mean()), 1),
        },
        "caveats": [
            "Metrics describe road-network geometry/topology only; no traffic volumes are used.",
            "Edge betweenness is approximate (sampled node pairs, length-weighted).",
        ],
    }
    with open(TABLES / "table_network_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    log.info("Network metrics: %s", json.dumps(metrics["vineyard_access"]))

    reg = [
        {"result_id": "R040", "manuscript_section": "Results 3.6",
         "metric": "aoi_total_road_length_km", "value": round(total_len_km, 1),
         "unit": "km", "uncertainty": "", "dataset": "OSM_drive_network",
         "analysis_script": SCRIPT, "model": "osmnx_graph",
         "source_output": "outputs/tables/table_network_metrics.json"},
        {"result_id": "R041", "manuscript_section": "Results 3.6",
         "metric": "median_vineyard_dist_to_major_road_m",
         "value": round(float(access["dist_major_road_m"].median()), 1),
         "unit": "m", "uncertainty": "", "dataset": "OSM_drive_network",
         "analysis_script": SCRIPT, "model": "sjoin_nearest",
         "source_output": "outputs/tables/table_network_metrics.json"},
        {"result_id": "R042", "manuscript_section": "Results 3.6",
         "metric": "frac_deadend_nodes_aoi", "value": metrics["frac_deadend_nodes"],
         "unit": "fraction", "uncertainty": "", "dataset": "OSM_drive_network",
         "analysis_script": SCRIPT, "model": "degree_distribution",
         "source_output": "outputs/tables/table_network_metrics.json"},
        {"result_id": "R043", "manuscript_section": "Results 3.6",
         "metric": "median_vineyard_dist_to_nearest_deadend_m",
         "value": round(float(access["dist_nearest_deadend_m"].median()), 1),
         "unit": "m", "uncertainty": "", "dataset": "OSM_drive_network",
         "analysis_script": SCRIPT, "model": "sjoin_nearest",
         "source_output": "outputs/tables/table_network_metrics.json"},
    ]
    append_registry(reg)

    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
