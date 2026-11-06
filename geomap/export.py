"""Step 7 — write the files the web map reads (same contract as map-of-github-data):

web/data/
  points.geojson        every paper (id, short label, year, cites, size, parent country)
  borders.geojson       country polygons with a fill colour
  places.geojson        country labels (name_en, name_fr, symbolzoom), editable by hand
  search.json           [id, title, first author, year, lon, lat, country], most cited first
  papers/<country>.json full details for the side panel (loaded on click)
  graphs/<country>.json links inside the country + links leaving it ("connections" view)
  meta.json             counts, build date
  points/{z}/{x}/{y}.pbf  vector tiles, only if tippecanoe is installed (for very large maps)
"""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from collections import defaultdict

import numpy as np
from shapely.geometry import shape

from .common import DATA, OUT, load_config, log, read_json, read_jsonl, write_json

# fill colours (input keys like anvaka's theme; the front-end maps them to the active theme)
PALETTE = ["#516ebc", "#00529c", "#153477", "#37009c", "#00789c", "#37549c", "#2f6f73"]


def short(title: str, n=60):
    return title if len(title) <= n else title[: n - 1].rsplit(" ", 1)[0] + "…"


def color_countries(geoms: dict):
    """Neighbouring countries (touching or close across the sea) get different fills,
    and colours are spread evenly so the map never comes out in one colour."""
    ids = sorted(geoms, key=lambda c: -geoms[c].area)
    span = max(max(g.bounds[2] for g in geoms.values()) - min(g.bounds[0] for g in geoms.values()), 1e-9)
    near = span * 0.08
    colors, used = {}, {p: 0 for p in PALETTE}
    for c in ids:
        taken = {colors[o] for o in colors if geoms[c].distance(geoms[o]) < near}
        free = [p for p in PALETTE if p not in taken] or PALETTE
        pick = min(free, key=lambda p: used[p])
        colors[c] = pick
        used[pick] += 1
    return colors


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    works = {w["id"]: w for w in read_jsonl(DATA / "works.jsonl")}
    clusters = read_json(DATA / "clusters.json")
    layout = read_json(DATA / "layout.json")
    borders = read_json(DATA / "borders.json")
    names = read_json(DATA / "names.json")
    e = np.load(DATA / "edges.npz")
    ids = read_json(DATA / "nodes.json")

    if OUT.exists():
        for sub in ("papers", "graphs", "points"):
            shutil.rmtree(OUT / sub, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)

    # ISSMGE conference papers (overlay step): metadata + link only, never the abstract
    conf = {}
    if (DATA / "issmge.jsonl").exists():
        conf = {p["id"]: p for p in read_jsonl(DATA / "issmge.jsonl")}
    overlay = read_json(DATA / "overlay.json") if (DATA / "overlay.json").exists() else {}

    placed = [pid for pid in layout if pid in works or pid in conf]
    jlc = np.log1p([works[p]["cites"] for p in placed if p in works])
    lo, hi = (float(jlc.min()), float(jlc.max())) if len(jlc) else (0.0, 1.0)

    # --- points ---
    feats, search, details = [], [], defaultdict(dict)
    n_conf = 0
    for pid in placed:
        (lon, lat), c = layout[pid], clusters[pid]
        if pid in works:
            w = works[pid]
            size = round(2 + 8 * (np.log1p(w["cites"]) - lo) / ((hi - lo) or 1), 2)
            props = {"id": pid, "label": short(w["title"]), "year": w["year"], "cites": w["cites"],
                     "size": size, "parent": c, "kind": "journal"}
            details[c][pid] = {k: w[k] for k in ("title", "year", "cites", "doi", "venue", "authors",
                                                 "keywords", "topic")}
            rank = w["cites"]
        else:
            w = conf[pid]
            n_conf += 1
            props = {"id": pid, "label": short(w["title"]), "year": w.get("year"), "cites": 0,
                     "size": 3, "parent": c, "kind": "issmge"}
            details[c][pid] = {"title": w["title"], "year": w.get("year"), "cites": None,
                               "doi": ("https://doi.org/" + w["doi"]) if w.get("doi") else None,
                               "venue": w.get("venue"), "authors": w.get("authors", []),
                               "keywords": [], "kind": "issmge", "url": w["url"], "pdf": w.get("pdf")}
            rank = -1
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": props})
        first = w["authors"][0] if w.get("authors") else ""
        search.append([pid, w["title"], first, w.get("year"), lon, lat, c, rank])
    write_json(OUT / "points.geojson", {"type": "FeatureCollection", "features": feats})
    search.sort(key=lambda r: -r[7])
    write_json(OUT / "search.json", [r[:7] for r in search])
    for c, d in details.items():
        write_json(OUT / "papers" / f"{c}.json", d)

    # --- borders + places ---
    geoms = {c: shape(g) for c, g in borders.items()}
    colors = color_countries(geoms)
    sizes = sorted(((n.get("size", 0), c) for c, n in names.items()), reverse=True)
    rank = {c: r for r, (_, c) in enumerate(sizes)}
    bfeats, pfeats = [], []
    for c, g in geoms.items():
        n = names.get(c, {"en": f"Country {c}", "fr": f"Pays {c}"})
        bfeats.append({"type": "Feature", "id": int(c), "geometry": borders[c],
                       "properties": {"fill": colors[c], "name_en": n["en"], "name_fr": n["fr"]}})
        main = max(g.geoms, key=lambda p: p.area) if g.geom_type == "MultiPolygon" else g
        p = main.representative_point()
        r = rank.get(c, len(rank))
        symbolzoom = 2 if r < 8 else 3 if r < 25 else 4 if r < 60 else 5 if r < 150 else 6
        pfeats.append({"type": "Feature", "geometry": {"type": "Point",
                                                       "coordinates": [round(p.x, 4), round(p.y, 4)]},
                       "properties": {"labelId": f"c{c}", "ownerId": int(c), "name_en": n["en"],
                                      "name_fr": n["fr"], "symbolzoom": symbolzoom,
                                      "keywords": n.get("keywords", [])[:5], "size": n.get("size", 0)}})
    write_json(OUT / "borders.geojson", {"type": "FeatureCollection", "features": bfeats})
    write_json(OUT / "places.geojson", {"type": "FeatureCollection", "features": pfeats}, indent=1)

    # --- per-country link graphs (for "show connections") ---
    graphs = defaultdict(lambda: {"links": [], "external": {}})
    for a, b, w in zip(e["i"].tolist(), e["j"].tolist(), e["w"].tolist()):
        pa, pb = ids[a], ids[b]
        ca, cb = clusters.get(pa), clusters.get(pb)
        if ca is None or cb is None:
            continue
        ext = int(ca != cb)
        graphs[ca]["links"].append([pa, pb, round(w, 3), ext])
        if ext:
            graphs[cb]["links"].append([pa, pb, round(w, 3), ext])
            graphs[ca]["external"][pb] = layout[pb] + [works[pb]["title"][:80], cb]
            graphs[cb]["external"][pa] = layout[pa] + [works[pa]["title"][:80], ca]
    # conference papers: links to their nearest journal papers
    for pid, o in overlay.items():
        if pid not in conf or pid not in clusters:
            continue
        ca = clusters[pid]
        for other, sim in o["nn"]:
            cb = clusters.get(other)
            if cb is None:
                continue
            ext = int(ca != cb)
            graphs[ca]["links"].append([pid, other, sim, ext])
            if ext:
                graphs[ca]["external"][other] = layout[other] + [works[other]["title"][:80], cb]
    for c, gdata in graphs.items():
        write_json(OUT / "graphs" / f"{c}.json", gdata)

    write_json(OUT / "meta.json", {
        "papers": len(placed), "journal_papers": len(placed) - n_conf, "issmge_papers": n_conf,
        "countries": len(geoms), "links": int(len(e["i"])),
        "built": dt.date.today().isoformat(), "source": "OpenAlex, Semantic Scholar, ISSMGE Online Library",
        "topics": list(cfg["openalex"]["topics"].values()),
        "min_citations": cfg["openalex"]["min_citations"]}, indent=1)

    if shutil.which("tippecanoe"):
        subprocess.run(["tippecanoe", "-e", str(OUT / "points"), "-l", "points", "-z", "11", "-Z", "4",
                        "--no-tile-compression", "--drop-densest-as-needed", "--force",
                        str(OUT / "points.geojson")], check=True)
        log("export", "vector tiles written (set usePointTiles: true in web/js/config.js)")
    log("export", f"{len(placed):,} papers ({n_conf:,} ISSMGE), {len(geoms)} countries -> {OUT}")
