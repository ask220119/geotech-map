"""Step 6 — bilingual country names.

method "keywords": distinctive OpenAlex keywords per country (TF-IDF across countries,
                   weighted by citations), translated with glossary.yaml. Offline, deterministic.
method "llm":      anvaka's ChatGPT approach, adapted: Claude names each country from its most
                   cited papers and returns English + French. Needs ANTHROPIC_API_KEY.
Output: data/names.json {cluster_id: {"en", "fr", "keywords", "topic", "size"}}.
Hand-edit that file (or web/data/places.geojson) to fix names, as anvaka invites PRs for labels.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict

import requests
import yaml

from .common import DATA, ROOT, load_config, log, read_json, read_jsonl, write_json

GENERIC = {"geotechnical engineering", "geology", "engineering", "geotechnics", "materials science",
           "civil engineering", "computer science", "physics", "mechanics", "soil mechanics",
           "geotechnical", "soil", "rock", "analysis", "mathematics"}


def load_glossary():
    with open(ROOT / "glossary.yaml", encoding="utf-8") as f:
        g = yaml.safe_load(f)
    return {k.lower(): v for k, v in g["terms"].items()}, {k.lower(): v for k, v in g["words"].items()}


def to_french(term: str, terms: dict, words: dict) -> tuple[str, bool]:
    t = term.lower().strip()
    if t in terms:
        return terms[t], True
    # longest glossary term contained in the phrase
    for key in sorted(terms, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", t):
            rest = re.sub(rf"\b{re.escape(key)}\b", "", t).strip()
            if not rest:
                return terms[key], True
            rest_fr, ok = to_french(rest, terms, words)
            return f"{terms[key]} ({rest_fr})", ok
    return term, False   # keep the English term; flagged for a human check


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def keyword_names(works, clusters, cfg):
    terms, words_fr = load_glossary()
    per_c = defaultdict(Counter)
    topics = defaultdict(Counter)
    df = Counter()
    for w in works:
        c = clusters.get(w["id"])
        if c is None:
            continue
        weight = 1 + math.log1p(w["cites"])
        kws = {k.lower() for k in w["keywords"]} - GENERIC
        for k in kws:
            per_c[c][k] += weight
        topics[c][w["topic"]] += 1
    for c, cnt in per_c.items():
        for k in cnt:
            df[k] += 1
    K = max(1, len(per_c))
    names, used = {}, set()
    stop = {"and", "of", "the", "in", "for", "soil", "soils", "rock", "analysis", "&"}

    def words(k):
        # crude stems: "tunnel"/"tunneling", "dam"/"dams" count as the same word
        return {w[:5] for w in re.findall(r"[a-z]+", k.lower()) if w not in stop}

    for c in sorted(per_c):
        scored = sorted(((v * math.log(1 + K / df[k]), k) for k, v in per_c[c].items()), reverse=True)
        picks = [k for _, k in scored[:8]]
        if not picks:
            continue
        # second term must add something: no shared content word with the first
        first = picks[0]
        second = next((k for k in picks[1:] if not (words(k) & words(first))), None)
        parts = [first] + ([second] if second else [])
        en = " & ".join(cap(p) for p in parts)
        if en.lower() in used and len(picks) > 2:              # keep names distinct, like anvaka
            alt = next((k for k in picks[1:] if k != second and not (words(k) & words(first))), None)
            if alt:
                parts = [first, alt]
                en = " & ".join(cap(p) for p in parts)
        used.add(en.lower())
        fr_parts = [to_french(p, terms, words_fr) for p in parts]
        # a half-translated second term reads worse than none: drop it
        if len(fr_parts) == 2 and not fr_parts[1][1]:
            fr_parts = fr_parts[:1]
        fr = " et ".join(cap(p) for p, _ in fr_parts)
        names[str(c)] = {"en": en, "fr": fr, "fr_checked": all(ok for _, ok in fr_parts),
                         "keywords": picks[:6], "topic": topics[c].most_common(1)[0][0],
                         "size": sum(topics[c].values())}
    return names


SYSTEM = """You are a master namer of geotechnical research communities. Your task is to create a unique, \
specific and memorable name for a "country" on a map of geotechnics research, based on the papers it contains.
The name should be:
1. Concise (1-4 words)
2. Specific to these papers (a soil type, a structure, a test, a method, a hazard...)
3. Understandable by a practising geotechnical engineer
4. Avoid generic words like "Geotechnics", "Engineering", "Research", "Hub", "Land", "Republic"
5. Distinct from the names already used, which are listed by the user
Return ONLY a JSON object: {"en": "<English name>", "fr": "<French name, natural technical French as used in France and Morocco>"}"""


def llm_names(works, clusters, cfg, base):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("naming.method=llm needs ANTHROPIC_API_KEY")
    by_c = defaultdict(list)
    for w in works:
        if w["id"] in clusters:
            by_c[clusters[w["id"]]].append(w)
    used = []
    for c in sorted(by_c, key=int):
        papers = sorted(by_c[c], key=lambda w: -w["cites"])[: cfg["naming"]["papers_in_prompt"]]
        listing = "\n".join(f"- {w['title']} ({w['year']}; keywords: {', '.join(w['keywords'][:4])})"
                            for w in papers)
        prompt = (f"Name a country containing these geotechnics papers:\n{listing}\n\n"
                  f"Names already used: {', '.join(used[-150:]) or 'none'}")
        for temp in (0.4, 0.8, 1.0):                    # retry hotter on a clash, as anvaka did
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
                "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": cfg["naming"]["llm_model"], "max_tokens": 120, "temperature": temp,
                      "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            text = r.json()["content"][0]["text"]
            try:
                got = json.loads(text[text.index("{"): text.rindex("}") + 1])
            except ValueError:
                continue
            if got.get("en", "").lower() not in {u.lower() for u in used}:
                break
        base[str(c)].update(en=got["en"], fr=got["fr"], fr_checked=True)
        used.append(got["en"])
        log("naming", f"{c}: {got['en']} / {got['fr']}")
    return base


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    works = list(read_jsonl(DATA / "works.jsonl"))
    clusters = read_json(DATA / "clusters.json")
    names = keyword_names(works, clusters, cfg)
    if cfg["naming"]["method"] == "llm":
        names = llm_names(works, clusters, cfg, names)
    # keep manual edits: anything in names.overrides.json wins
    ov = DATA.parent / "names.overrides.json"
    if ov.exists():
        for c, v in read_json(ov).items():
            names.setdefault(c, {}).update(v)
    write_json(DATA / "names.json", names, indent=1)
    unchecked = sum(not v.get("fr_checked") for v in names.values())
    log("naming", f"{len(names)} names; {unchecked} French names need a human check "
                  f"(see fr_checked=false in data/names.json)")
