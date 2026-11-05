// Search over paper titles, first authors and country names.
// anvaka shards his index by first letter; ours is one file loaded on the first keystroke
// (a 40k-paper index is ~1 MB gzipped). Matching is accent-insensitive and token-based.
import config from './config.js';
import { countryName } from './i18n.js';

const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const escapeHtml = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export default function createFuzzySearcher(getPlaces) {
  let index = null;
  let loading = null;

  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = fetch(config.searchIndex).then(r => r.json()).then(rows => {
        index = rows.map(([id, title, author, year, lon, lat, country]) => ({
          id, title, author, year, lon, lat, country, key: norm(`${title} ${author}`),
        }));
        return index;
      });
    }
    return loading;
  }

  function highlight(text, tokens) {
    let html = escapeHtml(text);
    tokens.forEach(tok => {
      if (tok.length < 2) return;
      const re = new RegExp(`(${tok.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig');
      html = html.replace(re, '<b>$1</b>');
    });
    return html;
  }

  async function find(query, limit = 12) {
    const tokens = norm(query).split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    const results = [];

    // countries first
    for (const f of getPlaces()) {
      const nameKey = norm(`${f.properties.name_en} ${f.properties.name_fr}`);
      if (tokens.every(t => nameKey.includes(t))) {
        results.push({
          kind: 'country', id: f.properties.ownerId, text: countryName(f.properties),
          html: highlight(countryName(f.properties), tokens),
          lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], score: 1e9,
        });
      }
    }

    const rows = await load();
    const scored = [];
    for (const r of rows) {
      let ok = true, score = 0;
      for (const t of tokens) {
        const at = r.key.indexOf(t);
        if (at < 0) { ok = false; break; }
        score += (at === 0 || r.key[at - 1] === ' ') ? 2 : 1;   // word starts rank higher
      }
      if (ok) scored.push([score, r]);
    }
    scored.sort((a, b) => b[0] - a[0]); // stable: ties stay in citation order
    for (const [, r] of scored.slice(0, limit)) {
      results.push({
        kind: 'paper', id: r.id, country: r.country, text: r.title, lon: r.lon, lat: r.lat,
        html: highlight(r.title, tokens), meta: `${r.author}${r.author ? ', ' : ''}${r.year ?? ''}`,
      });
    }
    return results.slice(0, limit);
  }

  return { find, load };
}
