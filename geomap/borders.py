"""Step 5 — country borders: Voronoi cell around every paper, clipped to a "coastline"
(the union of buffered papers), then dissolved per country. Output: data/borders.json
({cluster_id: GeoJSON geometry}).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import MultiPoint, Point, mapping
from shapely.ops import unary_union

from .common import DATA, load_config, log, read_json, write_json


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    layout = read_json(DATA / "layout.json")
    clusters = read_json(DATA / "clusters.json")
    pids = list(layout)
    pts = np.array([layout[p] for p in pids])

    # typical spacing between neighbouring papers -> coastline buffer
    from scipy.spatial import cKDTree
    d, _ = cKDTree(pts).query(pts, k=2)
    spacing = float(np.median(d[:, 1])) or 0.1
    buf = spacing * 3.0

    # Coastline per country (buffer its own points), smoothed with a close operation
    by_c = defaultdict(list)
    for k, p in enumerate(pids):
        by_c[clusters[p]].append(k)

    mp = MultiPoint([Point(x, y) for x, y in pts])
    cells = shapely.voronoi_polygons(mp, extend_to=mp.envelope.buffer(buf * 4), ordered=True)
    cells = list(cells.geoms)

    out = {}
    for c, idx in by_c.items():
        cp = pts[idx]
        # coastline buffer from this country's own point spacing (sparse countries need more)
        if len(cp) > 2:
            dc, _ = cKDTree(cp).query(cp, k=2)
            local = float(np.median(dc[:, 1]))
        else:
            local = spacing
        b = max(buf, local * 3.0)
        land = unary_union([Point(*p).buffer(b, quad_segs=6) for p in cp])
        land = land.buffer(b * 1.2).buffer(-b * 1.2)            # close gaps: one solid island
        region = unary_union([cells[k] for k in idx]).intersection(land)
        region = region.buffer(-spacing * 0.08).simplify(spacing * 0.15)   # thin gap = border line
        if region.is_empty:
            continue
        # drop crumbs: keep pieces holding at least 2% of the country's area
        if region.geom_type == "MultiPolygon":
            parts = [g for g in region.geoms if g.area >= 0.02 * region.area]
            region = unary_union(parts)
        out[str(c)] = mapping(region)
    write_json(DATA / "borders.json", out)
    log("borders", f"{len(out)} country polygons (spacing {spacing:.4f}°)")
