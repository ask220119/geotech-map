# Map of Geotechnics / Carte de la géotechnique

A zoomable map of geotechnical research, built the same way as
[anvaka/map-of-github](https://github.com/anvaka/map-of-github):

| map-of-github                          | Map of Geotechnics                                                      |
|----------------------------------------|-------------------------------------------------------------------------|
| a city = a GitHub repo                 | a city = a paper (OpenAlex, ≥ 50 citations, 14 geotechnics topics)      |
| similarity = Jaccard of stargazers     | similarity = Jaccard of reference lists (bibliographic coupling) + direct citations + OpenAlex related works |
| Leiden clustering → countries          | same (`leidenalg`)                                                      |
| ngraph.forcelayout, two levels         | igraph Fruchterman-Reingold, two levels (countries, then papers inside) |
| borders.geojson / places.geojson       | same files, same `symbolzoom` convention                                |
| ChatGPT names countries                | keyword TF-IDF names offline, or Claude (`naming.method: llm`)          |
| English                                | **English + French** (country names, interface, glossary)               |
| Vue + Vite                             | plain ES modules, no build step; MapLibre and fonts vendored            |

## Quick start

```bash
pip install -r requirements.txt

python run.py demo        # 4,000 fake papers, offline: checks the whole pipeline in ~3 s
python -m http.server -d web 8000   # open http://localhost:8000

python run.py all         # the real map: download from OpenAlex (~38k papers, ~15 min), then build
```

Set your email in `config.yaml` (`openalex.mailto`) or `OPENALEX_MAILTO` to use OpenAlex's faster "polite pool".
`web/data/` ships with the demo build (every title starts with `[DEMO]`) so the site opens immediately.

## Pipeline (`python run.py <step>`)

| step      | file                 | output (in `data/`)                  |
|-----------|----------------------|--------------------------------------|
| `fetch`   | `geomap/fetch.py`    | `works.jsonl` — one paper per line   |
| `graph`   | `geomap/graph.py`    | `nodes.json`, `edges.npz` (sparse top-k graph) |
| `cluster` | `geomap/cluster.py`  | `clusters.json` — paper → country    |
| `layout`  | `geomap/layout.py`   | `layout.json` — paper → [lon, lat]   |
| `borders` | `geomap/borders.py`  | `borders.json` — Voronoi cells dissolved per country |
| `names`   | `geomap/naming.py`   | `names.json` — `en`, `fr`, keywords  |
| `export`  | `geomap/export.py`   | `web/data/*` — what the site reads   |

`python run.py build` re-runs everything after `fetch`. Each step reads the previous step's files,
so you can tune one stage (e.g. `cluster.resolution`) and re-run from there.

### Tuning (`config.yaml`)

- **Scope** — `openalex.topics` (add offshore, earthquake, landfill topics…), `min_citations`, `from_year`.
- **Country size** — `cluster.resolution` (higher → more, smaller countries) and `cluster.min_size`.
- **Graph density** — `graph.k_neighbors`, `min_jaccard`, `citation_weight`.

### Names (EN/FR)

- `keywords` (default): the most distinctive OpenAlex keywords of each country, translated with
  `glossary.yaml` (≈ 250 geotechnical terms, e.g. *stone columns → colonnes ballastées*). Names the
  glossary could not fully translate are flagged `"fr_checked": false` in `data/names.json`.
- `llm`: set `naming.method: llm` and `ANTHROPIC_API_KEY`. Uses anvaka's naming prompt adapted to
  geotechnics, asks for both languages, and retries hotter when a name clashes.
- Manual fixes: create `names.overrides.json` at the repo root, e.g.
  `{"12": {"en": "Pressuremeter Plains", "fr": "Plaines du pressiomètre"}}` — it always wins.

## Web map (`web/`)

- Click a paper: authors, venue, citations, DOI/OpenAlex links, its 20 closest papers, and connection lines.
- Click a country: its name in both languages, keywords, most cited papers.
- Search: titles, first authors and country names (accent-insensitive).
- EN/FR switch (remembered per browser; `?lang=fr` in the URL also works).
- `js/getColorTheme.js` restyles the map without rebuilding data.
- File names follow map-of-github (`createMap.js`, `createFuzzySearcher.js`, `config.js`, `getColorTheme.js`).

For 100k+ papers install [tippecanoe](https://github.com/felt/tippecanoe); `export` will then write vector
tiles and you set `usePointTiles: true` in `web/js/config.js`.

Deploy: `web/` is a static site; push it to GitHub Pages, Netlify, or any web server.

### Fonts

MapLibre needs SDF glyphs for labels. They are generated locally from DejaVu Sans Condensed (accents, œ, …) by
`tools/make_glyphs.py`, so the map needs no external font server.

## Credits & licences

- Idea, method and UX: Andrei Kashcha, [map-of-github](https://github.com/anvaka/map-of-github) (MIT). No code copied; the naming prompt is adapted from its README.
- Data: [OpenAlex](https://openalex.org) (CC0).
- Rendering: [MapLibre GL JS](https://maplibre.org) 4.7.1 (BSD-3, `web/vendor/`).
- Fonts: DejaVu (free licence, `web/fonts/DejaVu-LICENSE.txt`).
- This project: MIT (see `LICENSE`).
