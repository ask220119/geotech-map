"""Harvest state kept between workflow runs (``python run.py save_state`` / ``restore_state``).

The ISSMGE harvest takes several 4-hour runs and the local SPECTER2 vectors take ~40 min
to compute, so both are saved as one archive that the workflow uploads to a GitHub release
(tag ``harvest-state``). Unlike the Actions cache, a release asset does not expire.

The repository is public, so the archive holds no abstracts: ISSMGE records are saved
without their ``abstract`` field. The abstract is only needed once, to compute the paper's
SPECTER2 vector, and that vector is saved instead (``local_vectors.npy``).

Archive content (``data/harvest-state.tar.gz``):
    issmge_urls.json        every paper link found on issmge.org
    issmge.jsonl            harvested records, abstracts removed
    local_vectors.npy       SPECTER2 vectors computed locally (float16, L2-normalised)
    local_vector_ids.json   paper id of each row above
    embedding_check.json    calibration of local vs Semantic Scholar vectors
"""
from __future__ import annotations

import io
import json
import sys
import tarfile

from .common import DATA, load_config, log, read_json, write_json

ARCHIVE = "harvest-state.tar.gz"
RESTORED = "state_restored.json"   # counts at restore time, so save() never shrinks the harvest
PLAIN = ["issmge_urls.json", "local_vectors.npy", "local_vector_ids.json", "embedding_check.json"]


def _issmge_without_abstracts() -> bytes:
    out = io.StringIO()
    with open(DATA / "issmge.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                rec.pop("abstract", None)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out.getvalue().encode("utf-8")


def _counts() -> dict:
    out = {"issmge": 0, "vectors": 0}
    if (DATA / "issmge.jsonl").exists():
        with open(DATA / "issmge.jsonl", encoding="utf-8") as f:
            out["issmge"] = sum(1 for line in f if line.strip())
    if (DATA / "local_vector_ids.json").exists():
        out["vectors"] = len(read_json(DATA / "local_vector_ids.json"))
    return out


def save(cfg: dict | None = None):
    path = DATA / ARCHIVE
    now = _counts()
    before = read_json(DATA / RESTORED) if (DATA / RESTORED).exists() else {}
    if now["issmge"] < before.get("issmge", 0):
        # never replace a saved harvest with a smaller one (e.g. a run that broke early)
        sys.exit(f"[state] refusing to save: {now['issmge']:,} ISSMGE records now, "
                 f"{before['issmge']:,} when the run started")
    n = 0
    with tarfile.open(path, "w:gz") as tar:
        if (DATA / "issmge.jsonl").exists():
            data = _issmge_without_abstracts()
            info = tarfile.TarInfo("issmge.jsonl")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            n += 1
        for name in PLAIN:
            if (DATA / name).exists():
                tar.add(DATA / name, arcname=name)
                n += 1
    log("state", f"saved {n} files -> {path} ({path.stat().st_size / 1e6:.1f} MB): "
                 f"{now['issmge']:,} ISSMGE records, {now['vectors']:,} local vectors")


def restore(cfg: dict | None = None):
    path = DATA / ARCHIVE
    if not path.exists():
        log("state", f"no {ARCHIVE} in {DATA}; starting from what is already there")
        return
    allowed = set(PLAIN) | {"issmge.jsonl"}
    with tarfile.open(path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name in allowed]
        for m in members:
            with tar.extractfile(m) as src, open(DATA / m.name, "wb") as dst:
                dst.write(src.read())
    counts = _counts()
    write_json(DATA / RESTORED, counts)
    log("state", f"restored {len(members)} files from {path}: {counts['issmge']:,} ISSMGE records, "
                 f"{counts['vectors']:,} local vectors")


if __name__ == "__main__":
    save(load_config())
