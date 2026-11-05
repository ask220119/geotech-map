"""Step 2 — similarity graph between papers.

anvaka: Jaccard similarity of two repos' stargazer sets.
Here:   Jaccard similarity of two papers' reference lists (bibliographic coupling),
        plus a bonus for direct citations and OpenAlex "related works" inside the corpus.
        (Old papers often have no reference list in OpenAlex; citations keep them on the map.)

Output: data/nodes.json (ordered paper ids) + data/edges.npz (i, j, w) — a sparse top-k graph.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import scipy.sparse as sp

from .common import DATA, load_config, log, read_jsonl, write_json


def build_paper_ref_matrix(works, max_df_frac=0.05):
    """Binary papers x references matrix, keeping refs shared by >=2 papers and not ubiquitous."""
    df = defaultdict(int)
    for w in works:
        for r in set(w["refs"]):
            df[r] += 1
    max_df = max(3, int(max_df_frac * len(works)))
    ref_index = {r: k for k, (r, c) in enumerate((r, c) for r, c in df.items() if 2 <= c <= max_df)}
    rows, cols = [], []
    for i, w in enumerate(works):
        for r in set(w["refs"]):
            k = ref_index.get(r)
            if k is not None:
                rows.append(i)
                cols.append(k)
    P = sp.csr_matrix((np.ones(len(rows), np.float32), (rows, cols)), shape=(len(works), len(ref_index)))
    return P


def coupling_topk(P, ref_counts, k, min_jaccard, min_shared, chunk=500):
    """Exact Jaccard on shared references, computed in row chunks, keeping top-k per paper."""
    n = P.shape[0]
    PT = P.T.tocsr()
    out_i, out_j, out_w = [], [], []
    for start in range(0, n, chunk):
        C = (P[start:start + chunk] @ PT).tocsr()  # shared-reference counts
        for local in range(C.shape[0]):
            i = start + local
            lo, hi = C.indptr[local], C.indptr[local + 1]
            js, shared = C.indices[lo:hi], C.data[lo:hi]
            mask = (js != i) & (shared >= min_shared)
            js, shared = js[mask], shared[mask]
            if not len(js):
                continue
            jac = shared / (ref_counts[i] + ref_counts[js] - shared)
            keep = jac >= min_jaccard
            js, jac = js[keep], jac[keep]
            if len(js) > k:
                top = np.argpartition(-jac, k)[:k]
                js, jac = js[top], jac[top]
            out_i.append(np.full(len(js), i)); out_j.append(js); out_w.append(jac)
        log("graph", f"coupling {min(start + chunk, n):,}/{n:,}")
    if not out_i:
        return np.array([], int), np.array([], int), np.array([], np.float32)
    return np.concatenate(out_i), np.concatenate(out_j), np.concatenate(out_w).astype(np.float32)


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    g = cfg["graph"]
    works = list(read_jsonl(DATA / "works.jsonl"))
    ids = [w["id"] for w in works]
    index = {pid: i for i, pid in enumerate(ids)}
    n = len(works)
    log("graph", f"{n:,} papers")

    P = build_paper_ref_matrix(works)
    ref_counts = np.array([max(1, len(set(w["refs"]))) for w in works], np.float32)
    ci, cj, cw = coupling_topk(P, ref_counts, g["k_neighbors"], g["min_jaccard"], g["min_shared_refs"])

    # Accumulate symmetric weights: coupling + direct citations + related works.
    W = defaultdict(float)
    for a, b, w in zip(ci.tolist(), cj.tolist(), cw.tolist()):
        key = (a, b) if a < b else (b, a)
        W[key] = max(W[key], w)
    n_cite = n_rel = 0
    for a, w in enumerate(works):
        for r in w["refs"]:
            b = index.get(r)
            if b is not None and b != a:
                key = (a, b) if a < b else (b, a)
                W[key] += g["citation_weight"]; n_cite += 1
        for r in w.get("related", []):
            b = index.get(r)
            if b is not None and b != a:
                key = (a, b) if a < b else (b, a)
                W[key] += g["related_weight"]; n_rel += 1

    # Sparsify: keep an edge if it is in the top-k of either endpoint.
    per_node = defaultdict(list)
    for (a, b), w in W.items():
        per_node[a].append((w, b)); per_node[b].append((w, a))
    keep = set()
    for a, lst in per_node.items():
        lst.sort(reverse=True)
        for w, b in lst[: g["k_neighbors"]]:
            keep.add((a, b) if a < b else (b, a))
    ei = np.array([e[0] for e in keep], np.int32)
    ej = np.array([e[1] for e in keep], np.int32)
    ew = np.array([W[e] for e in keep], np.float32)

    np.savez_compressed(DATA / "edges.npz", i=ei, j=ej, w=ew)
    write_json(DATA / "nodes.json", ids)
    connected = len(set(ei.tolist()) | set(ej.tolist()))
    log("graph", f"{len(keep):,} edges ({n_cite:,} citation links, {n_rel:,} related links); "
                 f"{connected:,}/{n:,} papers connected")
