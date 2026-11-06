"""Step 1c — harvest ISSMGE Online Library metadata (conference proceedings).

~17,000 open-access papers from ~72 proceedings (ICSMGE since 1936, regional conferences,
TC symposia). Only titles, authors, conference, year, DOI, page/PDF links and the abstract
are collected. The abstract is used ONLY to place the paper on the map (it is never
exported to the website): no licence is stated on issmge.org, so we publish metadata + link.

Polite and resumable:
  * one request per `issmge.delay_s` seconds, identifying User-Agent, robots.txt respected
    (it only disallows /seoul-council-meeting-papers);
  * results are appended to data/issmge.jsonl as they arrive; a later run skips papers it
    already has and stops when `issmge.max_minutes` is used up, so a full harvest can span
    several workflow runs (the workflow caches data/issmge*.json*).
Output: data/issmge.jsonl, data/issmge_urls.json
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .common import DATA, load_config, log, read_json, write_json

BASE = "https://www.issmge.org"
LIBRARY = f"{BASE}/publications/online-library"
PUB_RE = re.compile(r"^/publications/publication/[^/?#]+/?$")
AUTHOR_RE = re.compile(r"^/publications/author/")


class Client:
    def __init__(self, cfg):
        c = cfg.get("issmge", {})
        self.delay = float(c.get("delay_s", 1.0))
        contact = os.environ.get("OPENALEX_MAILTO") or cfg.get("openalex", {}).get("mailto") or ""
        self.s = requests.Session()
        self.s.headers["User-Agent"] = (
            "geotech-map/1.0 (+https://github.com/ask220119/geotech-map"
            + (f"; {contact}" if contact else "") + ")")
        self.last = 0.0
        self.deadline = time.time() + 60 * float(c.get("max_minutes", 300))

    def out_of_time(self):
        return time.time() > self.deadline

    def get(self, url, params=None):
        for attempt in range(5):
            wait = self.delay - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = self.s.get(url, params=params, timeout=60)
            except requests.RequestException as e:
                log("issmge", f"network error {e.__class__.__name__} on {url}, retrying")
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(120, 10 * 2 ** attempt))   # back off generously
                continue
            log("issmge", f"HTTP {r.status_code} on {url}")
            return None
        return None


# ---------------------------------------------------------------- listing pages
def publication_links(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        path = urlparse(urljoin(BASE, a["href"])).path
        if PUB_RE.match(path):
            url = BASE + path.rstrip("/")
            if url not in out:
                out.append(url)
    return out, soup


def total_entries(soup):
    m = re.search(r"of\s+([\d,]+)\s+entries", soup.get_text(" "))
    return int(m.group(1).replace(",", "")) if m else None


def database_filter(soup):
    """Find the 'Database' <select> of the library form: (form action, param name, [values])."""
    for sel in soup.find_all("select"):
        opts = sel.find_all("option")
        if any("all databases" in o.get_text(" ", strip=True).lower() for o in opts) and sel.get("name"):
            form = sel.find_parent("form")
            action = urljoin(LIBRARY, form.get("action")) if form and form.get("action") else LIBRARY
            values = [o.get("value") for o in opts if o.get("value")]
            return action, sel["name"], values
    return None


def scan_listing(client, url, params, known, stop_when_known):
    """Page through one listing; stop at the end, or (incremental mode) when 2 pages bring nothing new."""
    found, stale, page, prev = [], 0, 1, None
    while not client.out_of_time():
        p = dict(params or {}, page=page)
        html = client.get(url, p)
        if not html:
            break
        links, soup = publication_links(html)
        if page == 1:
            log("issmge", f"listing {params or ''}: {total_entries(soup) or '?'} entries announced")
        if not links or links == prev:          # past the last page (some sites repeat it)
            break
        prev = links
        new = [u for u in links if u not in known and u not in found]
        found += new
        stale = 0 if new else stale + 1
        if stale >= 2 and (stop_when_known or not links):
            break
        if page > 3000:
            break
        page += 1
        if page % 50 == 0:
            log("issmge", f"  page {page}, {len(found):,} new links so far")
    return found


def discover(client, known):
    incremental = len(known) > 0
    urls = scan_listing(client, LIBRARY, None, known, stop_when_known=incremental)
    seen = set(known) | set(urls)
    # The unfiltered list may only show recent additions: also walk every 'Database'.
    if not incremental or len(seen) < 2000:
        html = client.get(LIBRARY)
        filt = database_filter(BeautifulSoup(html or "", "html.parser"))
        if filt:
            action, name, values = filt
            log("issmge", f"walking {len(values)} databases via '{name}'")
            for v in values:
                if client.out_of_time():
                    break
                more = scan_listing(client, action, {name: v}, seen, stop_when_known=incremental)
                seen |= set(more)
                urls += more
        else:
            log("issmge", "no 'Database' filter found on the library page; using the plain listing only")
    return urls


# ---------------------------------------------------------------- paper pages
def meta_all(soup, name):
    return [m.get("content", "").strip() for m in soup.find_all("meta", attrs={"name": name}) if m.get("content")]


def find_abstract(soup):
    for name in ("citation_abstract", "dc.description", "DC.description"):
        v = meta_all(soup, name)
        if v and len(v[0]) > 80:
            return v[0]
    for tag in soup.find_all(re.compile("^h[1-6]$|^strong$|^dt$|^b$")):
        if tag.get_text(strip=True).lower().rstrip(":") == "abstract":
            texts = []
            for sib in tag.find_all_next(string=True, limit=40):
                t = sib.strip()
                if t and t.lower().rstrip(":") != "abstract":
                    texts.append(t)
                if sum(len(x) for x in texts) > 300 and t.endswith("."):
                    break
            text = " ".join(texts)
            if len(text) > 80:
                return text[:3000]
    for name in ("description", "og:description"):
        v = meta_all(soup, name) or [m.get("content", "") for m in soup.find_all("meta", attrs={"property": name})]
        if v and len(v[0]) > 150:
            return v[0]
    paras = sorted((p.get_text(" ", strip=True) for p in soup.find_all("p")), key=len, reverse=True)
    return paras[0][:3000] if paras and len(paras[0]) > 200 else ""


def parse_paper(url, html):
    soup = BeautifulSoup(html, "html.parser")
    title = (meta_all(soup, "citation_title") or [soup.title.get_text(strip=True) if soup.title else ""])[0]
    authors = meta_all(soup, "citation_author")
    if not authors:
        authors = [a.get_text(" ", strip=True) for a in soup.find_all("a", href=True)
                   if AUTHOR_RE.match(urlparse(urljoin(BASE, a["href"])).path)]
    conf = (meta_all(soup, "citation_conference_title") or meta_all(soup, "citation_journal_title") or [""])[0]
    date = (meta_all(soup, "citation_publication_date") or meta_all(soup, "citation_date") or [""])[0]
    year = int(date[:4]) if date[:4].isdigit() else None
    if year is None:
        m = re.search(r"\b(19[3-9]\d|20[0-4]\d)\b", conf + " " + title)
        year = int(m.group(1)) if m else None
    doi = (meta_all(soup, "citation_doi") or [""])[0]
    if not doi:
        a = soup.find("a", href=re.compile(r"doi\.org/10\."))
        doi = a["href"] if a else ""
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip()) or None
    pdf = (meta_all(soup, "citation_pdf_url") or [""])[0] or None
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return {
        "id": "I" + hashlib.sha1(slug.encode()).hexdigest()[:11],
        "kind": "issmge", "url": url, "pdf": pdf, "doi": doi,
        "title": re.sub(r"\s+", " ", title).strip(), "authors": authors[:12],
        "venue": conf, "year": year, "abstract": find_abstract(soup),
    }


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    if not cfg.get("issmge", {}).get("enabled", True):
        log("issmge", "disabled in config.yaml")
        return
    client = Client(cfg)
    urls_path, out_path = DATA / "issmge_urls.json", DATA / "issmge.jsonl"
    DATA.mkdir(parents=True, exist_ok=True)

    known_urls = read_json(urls_path) if urls_path.exists() else []
    new_urls = discover(client, set(known_urls))
    all_urls = known_urls + [u for u in new_urls if u not in set(known_urls)]
    write_json(urls_path, all_urls)
    log("issmge", f"{len(all_urls):,} paper links known ({len(new_urls):,} new)")

    done = set()
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            done = {json.loads(line)["url"] for line in f if line.strip()}
    todo = [u for u in all_urls if u not in done]
    log("issmge", f"{len(done):,} papers already harvested, {len(todo):,} to go")

    n = 0
    with open(out_path, "a", encoding="utf-8") as f:
        for url in todo:
            if client.out_of_time():
                log("issmge", "time budget used up; the next run continues from here")
                break
            html = client.get(url)
            if not html:
                continue
            rec = parse_paper(url, html)
            if rec["title"]:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
            if n % 250 == 0 and n:
                f.flush()
                log("issmge", f"  {n:,} harvested this run")
    total = len(done) + n
    log("issmge", f"harvested {n:,} this run; {total:,}/{len(all_urls):,} in total")
