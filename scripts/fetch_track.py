"""One-off: build data/snapshots/ets_track_osm.geojson from OpenStreetMap railway lines.

Not part of the app or the tests. Run it again only if the station list changes:

    python scripts/fetch_track.py            # fetch from Overpass, then build
    python scripts/fetch_track.py --cached   # rebuild from data/raw/osm_rail.json

Method. Download every railway=rail way in the stations' bounding box, build a graph of
OSM nodes, snap each station to its nearest node, and take the shortest path between consecutive
stations. Sidings and yards cost more per metre, so the path keeps to the running lines. On
double track the path follows whichever track is shorter; at the scale of the 3D view that is
fine. The result is two lines (main line, Butterworth branch), simplified to about 5 m.

Map data (c) OpenStreetMap contributors, ODbL 1.0. https://www.openstreetmap.org/copyright
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
STATIONS = ROOT / "data" / "processed" / "stations.csv"
RAW = ROOT / "data" / "raw" / "osm_rail.json"
# Committed with the pinned GTFS snapshot (data/processed/ is generated and ignored).
OUT = ROOT / "data" / "snapshots" / "ets_track_osm.geojson"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
BUFFER_M = 6000          # margin around the stations' bounding box
SERVICE_COST = 4.0       # cost multiplier for sidings, yards, spurs
SIMPLIFY_M = 5.0
MAX_SNAP_M = 400.0
SNAP_BAND_M = 60.0       # station candidates: rail nodes within nearest + this (both tracks)
GAP_M = 1500.0           # join a dead-end way to rail this close (OSM gaps at bridges, works)
GAP_COST = 2.0           # per metre, for a gap under 80 m
LONG_GAP_COST = 10.0     # per metre above that: used only when it saves a long detour


def dist_m(a, b) -> float:
    """Equirectangular distance in metres between (lat, lon) points. Good to 0.1% at this scale."""
    lat = math.radians((a[0] + b[0]) / 2)
    dx = math.radians(b[1] - a[1]) * math.cos(lat) * 6371008.8
    dy = math.radians(b[0] - a[0]) * 6371008.8
    return math.hypot(dx, dy)


def fetch(stations: pd.DataFrame) -> dict:
    """All railway=rail ways in the bounding box of the stations, plus a margin."""
    m = BUFFER_M / 111_000
    s_, w, n, e = (stations["lat"].min() - m, stations["lon"].min() - m,
                   stations["lat"].max() + m, stations["lon"].max() + m)
    query = (f'[out:json][timeout:300];way["railway"="rail"]({s_:.4f},{w:.4f},{n:.4f},{e:.4f});'
             "out body;>;out skel qt;")
    print("Querying Overpass (this can take a minute)...", file=sys.stderr)
    errors = []
    for url in OVERPASS:
        try:
            resp = requests.post(url, data={"data": query}, timeout=360,
                                 headers={"User-Agent": "ets-sim-track-fetch/1.0"})
            resp.raise_for_status()
            out = resp.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{url}: {exc}")
            continue
        if out.get("elements"):
            return out
        errors.append(f"{url}: no data ({out.get('remark', 'no remark')})")
    raise RuntimeError("Every Overpass server failed: " + "; ".join(errors))


def build_graph(osm: dict):
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in osm["elements"] if e["type"] == "node"}
    adj: dict[int, list[tuple[int, float, float]]] = {}
    for e in osm["elements"]:
        if e["type"] != "way":
            continue
        tags = e.get("tags", {})
        mult = SERVICE_COST if tags.get("service") in {"yard", "siding", "spur"} else 1.0
        refs = [n for n in e["nodes"] if n in nodes]
        for a, b in zip(refs, refs[1:]):
            d = dist_m(nodes[a], nodes[b])
            adj.setdefault(a, []).append((b, d * mult, d))
            adj.setdefault(b, []).append((a, d * mult, d))
    _bridge_gaps(nodes, adj)
    return nodes, adj


def _bridge_gaps(nodes, adj) -> None:
    """Connect each dead end (degree 1) to the nearest other rail node within GAP_M.
    OSM often leaves a few metres between ways at bridges or where double-tracking works split
    a line; without this the shortest path takes a long detour."""
    cell = GAP_M / 111_000
    grid: dict[tuple[int, int], list[int]] = {}
    for n in adj:
        lat, lon = nodes[n]
        grid.setdefault((int(lat / cell), int(lon / cell)), []).append(n)
    added = 0
    for n in [n for n, e in adj.items() if len(e) == 1]:
        lat, lon = nodes[n]
        ci, cj = int(lat / cell), int(lon / cell)
        near = {v for v, _, _ in adj[n]} | {n}
        best, bd = None, GAP_M
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):  # cell == GAP_M, so 3x3 cells cover the radius
                for m in grid.get((ci + di, cj + dj), ()):
                    if m in near:
                        continue
                    d = dist_m(nodes[n], nodes[m])
                    if d < bd:
                        best, bd = m, d
        if best is not None:
            cost = bd * (GAP_COST if bd <= 80 else LONG_GAP_COST)
            adj[n].append((best, cost, bd))
            adj[best].append((n, cost, bd))
            added += 1
    print(f"Bridged {added} gaps of up to {GAP_M:.0f} m", file=sys.stderr)


def largest_component(adj) -> list[int]:
    seen: set[int] = set()
    best: list[int] = []
    for start in adj:
        if start in seen:
            continue
        comp, stack = [start], [start]
        seen.add(start)
        while stack:
            for v, _, _ in adj[stack.pop()]:
                if v not in seen:
                    seen.add(v)
                    comp.append(v)
                    stack.append(v)
        if len(comp) > len(best):
            best = comp
    return best


def shortest_path(adj, srcs: set[int], dsts: set[int]) -> list[int]:
    """Cheapest path from any node in srcs to any node in dsts."""
    best = {n: 0.0 for n in srcs}
    prev: dict[int, int] = {}
    heap = [(0.0, n) for n in srcs]
    heapq.heapify(heap)
    end = None
    while heap:
        c, u = heapq.heappop(heap)
        if c > best[u]:
            continue
        if u in dsts:
            end = u
            break
        for v, w, _ in adj.get(u, ()):
            nc = c + w
            if nc < best.get(v, math.inf):
                best[v], prev[v] = nc, u
                heapq.heappush(heap, (nc, v))
    if end is None:
        raise RuntimeError(f"No rail path from {sorted(srcs)[:3]}... to {sorted(dsts)[:3]}...")
    out = [end]
    while out[-1] not in srcs:
        out.append(prev[out[-1]])
    return out[::-1]


def simplify(points: list[tuple[float, float]], keep: set[int], tol_m: float) -> list[int]:
    """Douglas-Peucker on (lat, lon), returning kept indices. Indices in `keep` always stay."""
    def perp(p, a, b):
        ab, ap = dist_m(a, b), dist_m(a, p)
        if ab < 1e-6:
            return ap
        # project in a local flat frame
        lat = math.radians(a[0])
        ax, ay = 0.0, 0.0
        bx, by = math.radians(b[1] - a[1]) * math.cos(lat), math.radians(b[0] - a[0])
        px, py = math.radians(p[1] - a[1]) * math.cos(lat), math.radians(p[0] - a[0])
        t = max(0.0, min(1.0, (px * bx + py * by) / (bx * bx + by * by)))
        return math.hypot(px - t * bx, py - t * by) * 6371008.8

    kept = set(keep) | {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        inner = [k for k in kept if i < k < j]
        if inner:  # split on forced points first
            k = inner[0]
            stack += [(i, k), (k, j)]
            continue
        far, fd = -1, tol_m
        for k in range(i + 1, j):
            d = perp(points[k], points[i], points[j])
            if d > fd:
                far, fd = k, d
        if far >= 0:
            kept.add(far)
            stack += [(i, far), (far, j)]
    return sorted(kept)


def line_feature(name: str, chain: list[str], snap: dict[str, set[int]], nodes, adj) -> tuple[dict, list[dict]]:
    """Path through the chain. Each station may use any of its candidate nodes, because on double
    track the two tracks are often joined only at crossovers far away. Where one section ends on
    one track and the next starts on the other, the line steps sideways a few metres."""
    path: list[int] = []
    st_idx: dict[str, int] = {}
    start = snap[chain[0]]
    for a, b in zip(chain, chain[1:]):
        seg = shortest_path(adj, start, snap[b])
        st_idx.setdefault(a, len(path))
        path += seg
        start = snap[b]
    st_idx[chain[-1]] = len(path) - 1
    pts = [nodes[n] for n in path]
    kept = simplify(pts, set(st_idx.values()), SIMPLIFY_M)
    remap = {old: new for new, old in enumerate(kept)}
    coords = [[round(pts[i][1], 6), round(pts[i][0], 6)] for i in kept]
    cum = [0.0]
    for a, b in zip(kept, kept[1:]):
        cum.append(cum[-1] + dist_m(pts[a], pts[b]))
    feat = {"type": "Feature", "properties": {"kind": "line", "line": name, "length_m": round(cum[-1], 1)},
            "geometry": {"type": "LineString", "coordinates": coords}}
    stations = []
    for s in chain:
        i = remap[st_idx[s]]
        stations.append({"station": s, "line": name, "vertex": i, "chainage_m": round(cum[i], 1)})
    return feat, stations


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cached", action="store_true", help="reuse data/raw/osm_rail.json")
    args = ap.parse_args(argv)
    stations = pd.read_csv(STATIONS)
    if args.cached and RAW.exists():
        osm = json.loads(RAW.read_text(encoding="utf-8"))
    else:
        osm = fetch(stations)
        RAW.parent.mkdir(parents=True, exist_ok=True)
        RAW.write_text(json.dumps(osm), encoding="utf-8")
    nodes, adj = build_graph(osm)
    print(f"{len(nodes)} nodes, {sum(len(v) for v in adj.values()) // 2} edges", file=sys.stderr)

    graph_nodes = largest_component(adj)  # a station must not snap onto an isolated siding
    snap, snap_m = {}, {}
    for r in stations.itertuples():
        p = (r.lat, r.lon)
        d = {n: dist_m(p, nodes[n]) for n in graph_nodes}
        near = min(d.values())
        snap[r.station] = {n for n, v in d.items() if v <= near + SNAP_BAND_M}
        snap_m[r.station] = near
        if snap_m[r.station] > MAX_SNAP_M:
            print(f"WARNING {r.station}: nearest rail node {snap_m[r.station]:.0f} m away", file=sys.stderr)

    main_chain = stations[stations["branch_junction"].isna()].sort_values("line_km")["station"].tolist()
    feats, st_rows = [], []
    f, rows = line_feature("main", main_chain, snap, nodes, adj)
    feats.append(f)
    st_rows += rows
    for r in stations[stations["branch_junction"].notna()].itertuples():
        f, rows = line_feature(f"branch:{r.station}", [r.branch_junction, r.station], snap, nodes, adj)
        feats.append(f)
        st_rows += rows  # the junction appears on both lines, at chainage 0 here
    for row in st_rows:
        s = stations.set_index("station").loc[row["station"]]
        feats.append({"type": "Feature",
                      "properties": {"kind": "station", **row, "snap_m": round(snap_m[row["station"]], 1)},
                      "geometry": {"type": "Point", "coordinates": [float(s.lon), float(s.lat)]}})
    out = {"type": "FeatureCollection",
           "attribution": "Track geometry (c) OpenStreetMap contributors, ODbL 1.0",
           "features": feats}
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    n_pts = sum(len(f["geometry"]["coordinates"]) for f in feats if f["properties"]["kind"] == "line")
    print(f"Wrote {OUT.relative_to(ROOT)}: {n_pts} points, {OUT.stat().st_size / 1024:.0f} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
