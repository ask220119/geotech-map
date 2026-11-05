"""Step 4 — two-level layout, like anvaka's: a global layout of countries, then a
force layout of papers inside each country. Output: data/layout.json {paper_id: [lon, lat]}.
"""
from __future__ import annotations

from collections import defaultdict

import igraph as ig
import numpy as np

from .cluster import load_graph
from .common import DATA, load_config, log, read_json, write_json


def separate_circles(pos, radii, iters=400, pad=1.08):
    """Push overlapping country discs apart while keeping the global arrangement."""
    pos = pos.copy()
    for _ in range(iters):
        moved = False
        for a in range(len(pos)):
            d = pos - pos[a]
            dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
            need = (radii + radii[a]) * pad
            ov = (dist < need)
            ov[a] = False
            if ov.any():
                push = ((need[ov] - dist[ov]) / 2)[:, None] * (d[ov] / dist[ov][:, None])
                pos[ov] += push
                pos[a] -= push.sum(0) * 0.5
                moved = True
        if not moved:
            break
    return pos


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    rng = np.random.default_rng(cfg["layout"]["seed"])
    clusters = read_json(DATA / "clusters.json")
    g = load_graph()
    pid_to_v = {pid: v for v, pid in enumerate(g.vs["pid"])}
    members = defaultdict(list)
    for pid, c in clusters.items():
        members[c].append(pid_to_v[pid])
    K = len(members)

    # --- level 1: countries -------------------------------------------------
    inter = defaultdict(float)
    for e in g.es:
        ca, cb = clusters.get(g.vs[e.source]["pid"]), clusters.get(g.vs[e.target]["pid"])
        if ca is not None and cb is not None and ca != cb:
            inter[(min(ca, cb), max(ca, cb))] += e["weight"]
    cg = ig.Graph(n=K, edges=list(inter.keys()))
    cg.es["weight"] = list(inter.values()) or []
    sizes = np.array([len(members[c]) for c in range(K)], float)
    radii = np.sqrt(sizes)
    if K > 1 and cg.ecount():
        w = np.log1p(np.array(cg.es["weight"]))
        cpos = np.array(cg.layout_fruchterman_reingold(weights=list(w), niter=2000, seed=None).coords)
    else:
        cpos = rng.normal(size=(K, 2))
    # scale so that discs are roughly touching, then remove overlaps
    span = np.ptp(cpos, axis=0).max() or 1
    cpos = cpos / span * radii.sum() * 0.6
    cpos = separate_circles(cpos, radii)

    # --- level 2: papers inside each country --------------------------------
    xy = {}
    for c in range(K):
        vs = members[c]
        sub = g.induced_subgraph(vs)
        if len(vs) > 2 and sub.ecount():
            p = np.array(sub.layout_fruchterman_reingold(weights=sub.es["weight"], niter=500).coords)
        else:
            p = rng.normal(size=(len(vs), 2))
        p -= np.median(p, axis=0)
        r95 = np.percentile(np.hypot(p[:, 0], p[:, 1]), 95) or 1
        p = p / r95 * radii[c] * 0.9
        # tame far outliers (papers weakly attached to their country)
        d = np.hypot(p[:, 0], p[:, 1])
        far = d > radii[c]
        p[far] *= (radii[c] / d[far])[:, None]
        for k, v in enumerate(vs):
            xy[g.vs[v]["pid"]] = p[k] + cpos[c]

    # --- to lon/lat ---------------------------------------------------------
    allp = np.array(list(xy.values()))
    center = (allp.max(0) + allp.min(0)) / 2
    half = (allp.max(0) - allp.min(0)) / 2
    lon_max, lat_max = cfg["layout"]["world_lon"], cfg["layout"]["world_lat"]
    s = min(lon_max / (half[0] or 1), lat_max / (half[1] or 1))
    out = {pid: [round(float((p[0] - center[0]) * s), 5), round(float((p[1] - center[1]) * s), 5)]
           for pid, p in xy.items()}
    write_json(DATA / "layout.json", out)
    log("layout", f"placed {len(out):,} papers in {K} countries")
