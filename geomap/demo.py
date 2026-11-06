"""Synthetic corpus for testing the pipeline offline (`python run.py demo`).
Papers are fake ("[DEMO]" in every title); themes share reference pools so clusters emerge.
"""
from __future__ import annotations

import numpy as np

from .common import DATA, log, write_json, write_jsonl

THEMES = [
    ("liquefaction", ["soil liquefaction", "cyclic loading", "site response", "shear wave velocity"]),
    ("pile foundations", ["pile groups", "laterally loaded piles", "bearing capacity", "piled raft"]),
    ("slope stability", ["limit equilibrium", "reliability analysis", "spatial variability", "random field"]),
    ("landslides", ["landslide susceptibility", "rainfall", "debris flow", "insar"]),
    ("unsaturated soils", ["matric suction", "soil water retention curve", "hydraulic conductivity", "swelling"]),
    ("tunnelling", ["shield tunnelling", "settlement", "tbm", "face stability"]),
    ("rock mechanics", ["rock mass classification", "fractures", "acoustic emission", "rockburst"]),
    ("ground improvement", ["prefabricated vertical drains", "vacuum preloading", "stone columns", "jet grouting"]),
    ("biocementation", ["micp", "lime", "cement", "soil stabilization"]),
    ("geosynthetics", ["geogrid", "reinforced soil", "embankments", "pavement"]),
    ("constitutive modelling", ["critical state", "hypoplasticity", "anisotropy", "small strain"]),
    ("discrete element method", ["granular materials", "particle breakage", "triaxial test", "dem"]),
    ("deep excavations", ["diaphragm wall", "retaining walls", "earth pressure", "monitoring"]),
    ("offshore", ["monopile", "suction caisson", "scour", "marine clay"]),
    ("frozen soil", ["permafrost", "freeze-thaw", "thermal", "energy piles"]),
    ("consolidation", ["soft clay", "creep", "secondary compression", "settlement"]),
]
NEIGHBOURS = {0: [10, 11], 1: [12, 13], 2: [3, 4], 3: [2], 4: [8, 14], 5: [12, 6], 6: [5, 11],
              7: [15, 8], 8: [7, 4], 9: [7, 1], 10: [11, 0, 15], 11: [10, 6], 12: [5, 1],
              13: [1, 0], 14: [4], 15: [7, 10]}


def run(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    pools = [[f"R{t}_{k}" for k in range(250)] for t in range(len(THEMES))]
    common = [f"RC_{k}" for k in range(150)]
    rows = []
    for i in range(n):
        t = int(rng.integers(len(THEMES)))
        theme, kws = THEMES[t]
        nref = int(rng.integers(12, 45))
        refs = set(rng.choice(pools[t], size=int(nref * 0.7), replace=False))
        nb = NEIGHBOURS[t][int(rng.integers(len(NEIGHBOURS[t])))]
        refs |= set(rng.choice(pools[nb], size=int(nref * 0.2), replace=False))
        refs |= set(rng.choice(common, size=max(1, int(nref * 0.1)), replace=False))
        if rng.random() < 0.08:  # old paper without reference list in OpenAlex
            refs = set()
        k = list(rng.choice(kws, size=2, replace=False))
        if rng.random() < 0.3:
            k.append(THEMES[nb][1][0])
        rows.append({
            "id": f"W{900000 + i}", "title": f"[DEMO] {theme.capitalize()}: study of {k[0]} #{i}",
            "year": int(rng.integers(1975, 2026)), "cites": int(rng.lognormal(4.3, 0.9)) + 50,
            "doi": None, "venue": "Demo Journal of Geotechnics", "authors": [f"Author {i % 97}"],
            "topic": "Geotechnical Engineering and Soil Mechanics", "topic_id": "T10233",
            "keywords": [theme] + k, "refs": sorted(refs), "related": [], "lang": "en", "_theme": t,
        })
    # in-corpus citations: newer papers cite older ones of the same theme
    by_t = {}
    for r in rows:
        by_t.setdefault(r["_theme"], []).append(r)
    for r in rows:
        older = [o for o in by_t[r["_theme"]] if o["year"] < r["year"]]
        if older:
            for o in rng.choice(len(older), size=min(3, len(older)), replace=False):
                r["refs"].append(older[int(o)]["id"])
    # fake SPECTER2-like vectors: theme direction + noise, for 90% of papers
    centres = rng.normal(size=(len(THEMES), 768))
    emb_ids, emb = [], []
    for r in rows:
        if rng.random() < 0.9:
            emb_ids.append(r["id"])
            emb.append(centres[r["_theme"]] + rng.normal(scale=1.2, size=768))
    X = np.array(emb, np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    np.save(DATA / "embeddings.npy", X.astype(np.float16))
    write_json(DATA / "embedding_ids.json", emb_ids)
    for r in rows:
        r.pop("_theme")
    write_jsonl(DATA / "works.jsonl", rows)
    log("demo", f"wrote {n:,} synthetic papers -> {DATA / 'works.jsonl'}")
