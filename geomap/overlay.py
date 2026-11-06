"""Step 4b — place ISSMGE conference papers on the journal map (an overlay).

The countries and their layout are built from journal papers only, so adding proceedings
never reshuffles the map. Each conference paper then joins the country of the journal
papers it most resembles and is set down among them:

  1. similarity = SPECTER2 cosine (if local vectors exist and agree with Semantic Scholar's),
     otherwise TF-IDF word similarity of title + abstract (always available, no model);
  2. country = weighted vote of its 10 nearest journal papers;
  3. position = weighted mean of its nearest neighbours in that country, plus a little jitter.

Re-runnable: it first removes earlier overlay entries ("I..." ids) from layout/clusters.
Output: updates data/layout.json and data/clusters.json; writes data/overlay.json
(nearest journal papers per conference paper, used for the "closest papers" panel).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np
import scipy.sparse as sp

from .common import DATA, load_config, log, read_json, read_jsonl, write_json

TOKEN = re.compile(r"[a-zà-ÿ][a-zà-ÿ\-]{2,}")
STOP = set("""the and for with from this that are was were been have has its into their which
using based study analysis paper results also between under over than these those such can
two three new may more most other within effect effects case cases method methods approach
during after before about through les des une dans pour par sur avec est sont aux""".split())


def tokens(text):
    return [t for t in TOKEN.findall((text or "").lower()) if t not in STOP]


def tfidf_matrix(docs, vocab=None, idf=None):
    """Sublinear TF-IDF with unigrams + bigrams, rows L2-normalised."""
    rows, cols, vals = [], [], []
    toks = []
    for d in docs:
        t = tokens(d)
        toks.append(Counter(t + [a + "_" + b for a, b in zip(t, t[1:])]))
    if vocab is None:
        df = Counter(term for c in toks for term in c)
        n = len(docs)
        vocab = {term: k for k, term in enumerate(t for t, f in df.items() if 2 <= f <= 0.3 * n)}
        idf = np.zeros(len(vocab), np.float32)
        for term, k in vocab.items():
            idf[k] = math.log((1 + n) / (1 + df[term])) + 1
    for i, c in enumerate(toks):
        for term, f in c.items():
            k = vocab.get(term)
            if k is not None:
                rows.append(i); cols.append(k); vals.append((1 + math.log(f)) * idf[k])
    M = sp.csr_matrix((vals, (rows, cols)), shape=(len(docs), len(vocab)), dtype=np.float32)
    norms = np.sqrt(M.multiply(M).sum(1)).A.ravel() + 1e-9
    return sp.diags(1 / norms) @ M, vocab, idf


def topk_rows(S, k):
    if sp.issparse(S):
        S = S.toarray()
    k = min(k, S.shape[1])
    idx = np.argpartition(-S, k - 1, axis=1)[:, :k]
    val = np.take_along_axis(S, idx, axis=1)
    order = np.argsort(-val, axis=1)
    return np.take_along_axis(idx, order, 1), np.take_along_axis(val, order, 1)


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    path = DATA / "issmge.jsonl"
    layout = {k: v for k, v in read_json(DATA / "layout.json").items() if not k.startswith("I")}
    clusters = {k: v for k, v in read_json(DATA / "clusters.json").items() if not k.startswith("I")}
    if not path.exists():
        write_json(DATA / "layout.json", layout); write_json(DATA / "clusters.json", clusters)
        write_json(DATA / "overlay.json", {})
        log("overlay", "no ISSMGE papers harvested yet; nothing to place")
        return
    conf = [p for p in read_jsonl(path) if p.get("title")]
    seen, uniq = set(), []
    for p in conf:                               # a paper can be listed under several databases
        if p["id"] not in seen:
            seen.add(p["id"]); uniq.append(p)
    conf = uniq
    works = {w["id"]: w for w in read_jsonl(DATA / "works.jsonl")}
    jids = [pid for pid in layout if pid in works]
    jpos = np.array([layout[p] for p in jids])
    jcl = np.array([clusters[p] for p in jids])
    k = int(cfg.get("issmge", {}).get("neighbours", 10))

    # ---- choose the similarity: SPECTER2 if trustworthy, else TF-IDF
    method = "tfidf"
    emb_ids_path = DATA / "embedding_ids.json"
    check = read_json(DATA / "embedding_check.json") if (DATA / "embedding_check.json").exists() else {}
    if emb_ids_path.exists() and (not check.get("n") or check.get("mean_cos", 0) >= 0.9):
        ids = read_json(emb_ids_path)
        X = np.load(DATA / "embeddings.npy").astype(np.float32)
        row = {pid: r for r, pid in enumerate(ids)}
        jr = [row.get(p) for p in jids]
        cr = [row.get(p["id"]) for p in conf]
        if sum(r is not None for r in cr) >= 0.8 * len(conf) and sum(r is not None for r in jr) >= 0.5 * len(jids):
            method = "specter2"
    log("overlay", f"placing {len(conf):,} ISSMGE papers among {len(jids):,} journal papers by {method}")

    nn_idx = np.zeros((len(conf), k), int)
    nn_sim = np.zeros((len(conf), k), np.float32)
    if method == "specter2":
        J_ok = np.array([r is not None for r in jr])
        J = np.zeros((len(jids), X.shape[1]), np.float32)
        J[J_ok] = X[[r for r in jr if r is not None]]
        J /= np.linalg.norm(J, axis=1, keepdims=True) + 1e-9
        missing = [i for i, r in enumerate(cr) if r is None]
        C = np.zeros((len(conf), X.shape[1]), np.float32)
        have = [i for i, r in enumerate(cr) if r is not None]
        C[have] = X[[cr[i] for i in have]]
        C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
        for s in range(0, len(conf), 2000):
            S = C[s:s + 2000] @ J.T
            S[:, ~J_ok] = -1
            nn_idx[s:s + 2000], nn_sim[s:s + 2000] = topk_rows(S, k)
        if missing:   # the few without a vector: words
            tf_idx, tf_sim = place_tfidf([conf[i] for i in missing], jids, works, k)
            nn_idx[missing], nn_sim[missing] = tf_idx, tf_sim
    else:
        nn_idx, nn_sim = place_tfidf(conf, jids, works, k)

    # ---- country by weighted vote, position among the winning neighbours
    from scipy.spatial import cKDTree
    d, _ = cKDTree(jpos).query(jpos, k=2)
    spacing = float(np.median(d[:, 1])) or 0.1
    rng = np.random.default_rng(int(cfg.get("layout", {}).get("seed", 42)))
    min_sim = 0.05 if method == "tfidf" else 0.5
    overlay, placed, votes_ok = {}, 0, 0
    for i, p in enumerate(conf):
        sims = np.clip(nn_sim[i], 0, None)
        if sims.max() < min_sim:
            continue
        vote = defaultdict(float)
        for j, s in zip(nn_idx[i], sims):
            vote[int(jcl[j])] += float(s)
        c = max(vote, key=vote.get)
        votes_ok += vote[c] >= 0.5 * sum(vote.values())
        mine = [(j, s) for j, s in zip(nn_idx[i], sims) if jcl[j] == c][:5]
        w = np.array([s for _, s in mine]) + 1e-6
        xy = (jpos[[j for j, _ in mine]] * w[:, None]).sum(0) / w.sum()
        xy = xy + rng.normal(scale=spacing * 0.7, size=2)
        layout[p["id"]] = [round(float(xy[0]), 5), round(float(xy[1]), 5)]
        clusters[p["id"]] = c
        overlay[p["id"]] = {"c": c, "nn": [[jids[j], round(float(s), 3)] for j, s in zip(nn_idx[i][:8], sims[:8])]}
        placed += 1
    write_json(DATA / "layout.json", layout)
    write_json(DATA / "clusters.json", clusters)
    write_json(DATA / "overlay.json", overlay)
    log("overlay", f"placed {placed:,}/{len(conf):,} ISSMGE papers "
                   f"({votes_ok / max(1, placed):.0%} with a clear majority country)")


def place_tfidf(conf, jids, works, k):
    jdocs = [" ".join([works[p]["title"], " ".join(works[p].get("keywords", [])),
                       works[p].get("abstract", "")]) for p in jids]
    cdocs = [(p.get("title", "") + " ") * 2 + p.get("abstract", "") for p in conf]  # title counts double
    J, vocab, idf = tfidf_matrix(jdocs + cdocs)
    C = J[len(jdocs):]
    J = J[:len(jdocs)]
    idx = np.zeros((len(conf), k), int)
    sim = np.zeros((len(conf), k), np.float32)
    JT = J.T.tocsc()
    for s in range(0, len(conf), 1000):
        idx[s:s + 1000], sim[s:s + 1000] = topk_rows(C[s:s + 1000] @ JT, k)
    return idx, sim
