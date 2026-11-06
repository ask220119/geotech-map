"""Step 1b — SPECTER2 embeddings from Semantic Scholar.

A SPECTER2 vector is a 768-number "meaning fingerprint" of a paper (title + abstract,
trained on citations). Papers with similar vectors are about the same thing, even when
OpenAlex has no reference list for them. The graph step uses these as extra links.

Optional: if this step is skipped or Semantic Scholar is unreachable, the map is built
from citations alone. Set S2_API_KEY (free, semanticscholar.org/product/api) for a
dedicated rate limit; without it requests share a public pool and may be slowed down.
Output: data/embeddings.npy (float16, one row per embedded paper) + data/embedding_ids.json
"""
from __future__ import annotations

import os
import time

import numpy as np
import requests

from .common import DATA, load_config, log, read_jsonl, write_json

API = "https://api.semanticscholar.org/graph/v1/paper/batch"
BATCH = 500


def doi_of(w):
    d = (w.get("doi") or "").lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d or None


def post_batch(session, ids, headers):
    for attempt in range(8):
        try:
            r = session.post(API, params={"fields": "embedding.specter_v2"},
                             json={"ids": ids}, headers=headers, timeout=120)
        except requests.RequestException as e:
            if attempt >= 3:
                raise RuntimeError(f"cannot reach Semantic Scholar ({e.__class__.__name__})")
            log("embed", f"network error {e.__class__.__name__}, retrying")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(60, 2 ** attempt)
            log("embed", f"HTTP {r.status_code}, retry in {wait}s")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Semantic Scholar rejected the request (HTTP {r.status_code}): {r.text[:300]}")
    raise RuntimeError("Semantic Scholar kept failing")


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    works = list(read_jsonl(DATA / "works.jsonl"))
    todo = [(w["id"], doi_of(w)) for w in works if doi_of(w)]
    log("embed", f"{len(todo):,}/{len(works):,} papers have a DOI")
    if not todo:
        log("embed", "nothing to embed; the map will use citations only")
        return

    headers = {}
    if os.environ.get("S2_API_KEY"):
        headers["x-api-key"] = os.environ["S2_API_KEY"]
    pause = 1.1 if headers else 3.0          # stay under the rate limit

    session = requests.Session()
    ids, vecs = [], []
    try:
        for start in range(0, len(todo), BATCH):
            chunk = todo[start:start + BATCH]
            res = post_batch(session, [f"DOI:{d}" for _, d in chunk], headers)
            for (pid, _), p in zip(chunk, res):
                v = ((p or {}).get("embedding") or {}).get("vector")
                if v and len(v) == 768:
                    ids.append(pid)
                    vecs.append(np.asarray(v, np.float32))
            log("embed", f"{min(start + BATCH, len(todo)):,}/{len(todo):,} asked, {len(ids):,} embedded")
            time.sleep(pause)
    except (RuntimeError, requests.RequestException) as e:
        if not ids:
            for f in (DATA / "embeddings.npy", DATA / "embedding_ids.json"):
                f.unlink(missing_ok=True)   # never mix in vectors from an older corpus
            log("embed", f"skipped ({e}); the map will use citations only")
            return
        log("embed", f"stopped early ({e}); keeping {len(ids):,} embeddings")

    X = np.vstack(vecs)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    np.save(DATA / "embeddings.npy", X.astype(np.float16))
    write_json(DATA / "embedding_ids.json", ids)
    log("embed", f"saved {len(ids):,} SPECTER2 vectors ({len(ids) / max(1, len(works)):.0%} of papers)")
