"""Step 3 — Leiden clustering into "countries" (same algorithm anvaka settled on)."""
from __future__ import annotations

from collections import Counter, defaultdict

import igraph as ig
import leidenalg
import numpy as np

from .common import DATA, load_config, log, read_json, write_json


def load_graph():
    ids = read_json(DATA / "nodes.json")
    e = np.load(DATA / "edges.npz")
    g = ig.Graph(n=len(ids), edges=list(zip(e["i"].tolist(), e["j"].tolist())), directed=False)
    g.es["weight"] = e["w"].tolist()
    g.vs["pid"] = ids
    return g


def merge_small(g, membership, min_size):
    """Fold clusters smaller than min_size into the neighbour cluster they are most tied to."""
    membership = list(membership)
    for _ in range(10):
        sizes = Counter(membership)
        small = {c for c, s in sizes.items() if s < min_size}
        if not small:
            break
        changed = False
        for c in small:
            members = [v for v, m in enumerate(membership) if m == c]
            ties = defaultdict(float)
            for v in members:
                for eid in g.incident(v):
                    u = g.es[eid].target if g.es[eid].source == v else g.es[eid].source
                    if membership[u] != c:
                        ties[membership[u]] += g.es[eid]["weight"]
            if ties:
                target = max(ties, key=ties.get)
                for v in members:
                    membership[v] = target
                changed = True
        if not changed:
            break
    return membership


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    c = cfg["cluster"]
    g = load_graph()
    # Keep only papers with at least one link (isolated papers have no "neighbourhood").
    g = g.induced_subgraph([v.index for v in g.vs if g.degree(v) > 0])
    part = leidenalg.find_partition(
        g, leidenalg.RBConfigurationVertexPartition, weights="weight",
        resolution_parameter=c["resolution"], seed=c["seed"], n_iterations=-1)
    membership = merge_small(g, part.membership, c["min_size"])

    # Drop leftover tiny islands (small disconnected components), then renumber by size.
    sizes = Counter(membership)
    order = [cid for cid, s in sizes.most_common() if s >= c["min_size"]]
    remap = {cid: k for k, cid in enumerate(order)}
    result = {g.vs[v]["pid"]: remap[m] for v, m in enumerate(membership) if m in remap}
    write_json(DATA / "clusters.json", result)
    log("cluster", f"{len(order)} countries, {len(result):,} papers placed "
                   f"(largest {sizes.most_common(1)[0][1]}, modularity {part.modularity:.3f})")
