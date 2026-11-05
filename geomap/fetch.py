"""Step 1 — download geotechnics papers from OpenAlex.

Equivalent of anvaka's BigQuery "who starred what" step: for every paper we keep its
reference list (what it "stars"), its related works and a little metadata for the UI.
Output: data/works.jsonl (one compact record per paper).
"""
from __future__ import annotations

import os
import time

import requests

from .common import DATA, load_config, log, short_id, write_jsonl

API = "https://api.openalex.org/works"
FIELDS = ",".join([
    "id", "doi", "display_name", "publication_year", "cited_by_count",
    "referenced_works", "related_works", "primary_topic", "keywords",
    "authorships", "primary_location", "language",
])


def compact(w: dict) -> dict:
    loc = (w.get("primary_location") or {}).get("source") or {}
    topic = w.get("primary_topic") or {}
    return {
        "id": short_id(w["id"]),
        "title": (w.get("display_name") or "").strip(),
        "year": w.get("publication_year"),
        "cites": w.get("cited_by_count") or 0,
        "doi": w.get("doi"),
        "venue": loc.get("display_name"),
        "authors": [a["author"]["display_name"] for a in (w.get("authorships") or [])[:6]
                    if a.get("author")],
        "topic": topic.get("display_name"),
        "topic_id": short_id(topic.get("id", "")),
        "keywords": [k["display_name"] for k in (w.get("keywords") or [])[:6]],
        "refs": [short_id(r) for r in (w.get("referenced_works") or [])],
        "related": [short_id(r) for r in (w.get("related_works") or [])],
        "lang": w.get("language"),
    }


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    oa = cfg["openalex"]
    mailto = os.environ.get("OPENALEX_MAILTO") or oa.get("mailto") or None
    filt = ",".join([
        "primary_topic.id:" + "|".join(oa["topics"].keys()),
        f"cited_by_count:>{int(oa['min_citations']) - 1}",
        f"publication_year:>{int(oa['from_year']) - 1}",
        "type:article|review|book-chapter|conference-paper",
    ])
    params = {"filter": filt, "select": FIELDS, "per-page": 200, "cursor": "*",
              "sort": "cited_by_count:desc"}
    if mailto:
        params["mailto"] = mailto

    session = requests.Session()
    rows, total = [], None
    while params["cursor"] and len(rows) < oa["max_works"]:
        for attempt in range(6):
            r = session.get(API, params=params, timeout=60)
            if r.status_code == 200:
                break
            wait = 2 ** attempt
            log("fetch", f"HTTP {r.status_code}, retry in {wait}s")
            time.sleep(wait)
        else:
            r.raise_for_status()
        page = r.json()
        total = total or page["meta"]["count"]
        rows.extend(compact(w) for w in page["results"])
        params["cursor"] = page["meta"].get("next_cursor")
        log("fetch", f"{len(rows):,} / {min(total, oa['max_works']):,}")
        if not mailto:
            time.sleep(0.12)  # stay well under the anonymous rate limit

    rows = rows[: oa["max_works"]]
    write_jsonl(DATA / "works.jsonl", rows)
    log("fetch", f"saved {len(rows):,} papers -> {DATA / 'works.jsonl'}")
    return rows
