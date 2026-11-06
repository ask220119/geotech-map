"""Step 1d — SPECTER2 embeddings computed locally, for papers Semantic Scholar did not cover
(ISSMGE proceedings, journal papers without a DOI or unknown to S2).

Uses the same model Semantic Scholar serves (allenai/specter2_base + the "specter2"
proximity adapter, input = title [SEP] abstract), so local and downloaded vectors share
one space. A calibration check embeds up to 200 papers that already have an S2 vector and
logs the mean cosine between the two; data/embedding_check.json records it, and the overlay
step falls back to word similarity (TF-IDF) if the spaces disagree.

Optional heavy dependencies (CPU is fine, ~20-40 papers/s on a GitHub runner):
    pip install -r requirements-embed.txt
If they are missing or the model cannot be downloaded, the step is skipped and the overlay
step places papers by word similarity instead.
Output: rows appended to data/embeddings.npy / data/embedding_ids.json, data/embedding_check.json
"""
from __future__ import annotations

import json
import time

import numpy as np

from .common import DATA, load_config, log, read_json, read_jsonl, write_json

MODEL, ADAPTER = "allenai/specter2_base", "allenai/specter2"


def load_model():
    from adapters import AutoAdapterModel
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoAdapterModel.from_pretrained(MODEL)
    model.load_adapter(ADAPTER, source="hf", load_as="specter2", set_active=True)
    model.eval()
    return tok, model


def encode(tok, model, papers, batch=32):
    import torch
    out = []
    for start in range(0, len(papers), batch):
        chunk = papers[start:start + batch]
        texts = [(p.get("title") or "") + tok.sep_token + (p.get("abstract") or "") for p in chunk]
        enc = tok(texts, padding=True, truncation=True, return_tensors="pt",
                  return_token_type_ids=False, max_length=512)
        with torch.no_grad():
            v = model(**enc).last_hidden_state[:, 0, :].numpy()
        out.append(v)
    X = np.vstack(out).astype(np.float32)
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    works = list(read_jsonl(DATA / "works.jsonl"))
    conf = list(read_jsonl(DATA / "issmge.jsonl")) if (DATA / "issmge.jsonl").exists() else []

    emb_path, ids_path = DATA / "embeddings.npy", DATA / "embedding_ids.json"
    have_ids = read_json(ids_path) if ids_path.exists() else []
    X_have = np.load(emb_path).astype(np.float32) if emb_path.exists() else np.zeros((0, 768), np.float32)
    have = set(have_ids)
    todo = [p for p in conf + works if p["id"] not in have and p.get("title")]
    if not todo:
        log("embed_local", "every paper already has a vector")
        return
    log("embed_local", f"{len(todo):,} papers need a local vector "
                       f"({sum(p['id'].startswith('I') for p in todo):,} ISSMGE)")
    try:
        t0 = time.time()
        tok, model = load_model()
        log("embed_local", f"model loaded in {time.time() - t0:.0f}s")
    except Exception as e:  # missing packages, no network, ...
        log("embed_local", f"skipped ({e.__class__.__name__}: {str(e)[:200]}); "
                           "the overlay will use word similarity")
        return

    # calibration: local vs Semantic Scholar on papers that have both
    by_id = {w["id"]: w for w in works}
    sample = [(k, pid) for k, pid in enumerate(have_ids) if pid in by_id and by_id[pid].get("abstract")][:200]
    check = {"n": len(sample)}
    if sample:
        L = encode(tok, model, [by_id[pid] for _, pid in sample])
        S = X_have[[k for k, _ in sample]]
        S = S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-9)
        cos = (L * S).sum(1)
        check.update(mean_cos=float(cos.mean()), p10_cos=float(np.percentile(cos, 10)))
        log("embed_local", f"calibration on {len(sample)} papers: mean cosine local vs S2 = "
                           f"{cos.mean():.3f} (10th pct {np.percentile(cos, 10):.3f})")
    write_json(DATA / "embedding_check.json", check, indent=1)

    t0, vecs = time.time(), []
    step = 2000
    for start in range(0, len(todo), step):
        vecs.append(encode(tok, model, todo[start:start + step]))
        done = min(start + step, len(todo))
        log("embed_local", f"{done:,}/{len(todo):,} ({done / (time.time() - t0):.0f} papers/s)")
    X_new = np.vstack(vecs)
    X = np.vstack([X_have, X_new]).astype(np.float16)
    np.save(emb_path, X)
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(have_ids + [p["id"] for p in todo], f)
    log("embed_local", f"saved {len(todo):,} local vectors ({len(have_ids) + len(todo):,} in total)")
