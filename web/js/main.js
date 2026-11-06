// UI wiring: search box, side panels, language switch. (map-of-github does this with Vue;
// here it is plain modules so the site needs no build step.)
import config from './config.js';
import createMap from './createMap.js';
import createFuzzySearcher from './createFuzzySearcher.js';
import { t, getLang, setLang, onLangChange, countryName } from './i18n.js';

const $ = sel => document.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cache = new Map();
const getJSON = url => {
  if (!cache.has(url)) cache.set(url, fetch(url).then(r => { if (!r.ok) throw new Error(url); return r.json(); }));
  return cache.get(url);
};

let meta = { papers: 0, countries: 0, min_citations: 0, built: '' };
getJSON(config.meta).then(m => { meta = m; if (!$('#about-panel').hidden) renderAbout(); }).catch(() => {});

const tooltip = $('#tooltip');
const owner = createMap({
  onPaperClick: (id, country) => showPaper(id, country),
  onCountryClick: id => showCountry(id),
  onHover: h => {
    if (!h) { tooltip.hidden = true; return; }
    tooltip.textContent = h.text;
    tooltip.style.left = `${h.x}px`;
    tooltip.style.top = `${h.y}px`;
    tooltip.hidden = false;
  },
});
window.mapOwner = owner;
const searcher = createFuzzySearcher(owner.getPlaces);

// positions of every paper (from the search index) for drawing connections anywhere on the map
let positions = null;
async function getPositions() {
  if (positions) return positions;
  const rows = await getJSON(config.searchIndex);
  positions = new Map(rows.map(r => [r[0], [r[4], r[5]]]));
  return positions;
}

// ---------------- paper panel ----------------
let current = null; // {id, country}
async function showPaper(id, country, { fly = false } = {}) {
  current = { id, country };
  $('#country-panel').hidden = true;
  const panel = $('#paper-panel');
  panel.hidden = false;
  panel.innerHTML = `<p class="byline">…</p>`;
  const [papers, graph, pos] = await Promise.all([
    getJSON(`${config.papersEndpoint}/${country}.json`),
    getJSON(`${config.graphsEndpoint}/${country}.json`).catch(() => ({ links: [], external: {} })),
    getPositions(),
  ]);
  if (current?.id !== id) return;
  const p = papers[id];
  if (!p) { panel.innerHTML = `<p>Not found: ${esc(id)}</p>`; return; }
  if (fly && pos.get(id)) owner.flyTo(...pos.get(id));
  owner.highlightCountry(country);
  owner.showConnections(id, graph, pos);

  const neigh = graph.links.filter(l => l[0] === id || l[1] === id)
    .map(l => ({ other: l[0] === id ? l[1] : l[0], w: l[2], ext: l[3] }))
    .sort((a, b) => b.w - a.w).slice(0, 20);
  const place = owner.getPlaces().find(f => f.properties.ownerId === country);
  const isConf = p.kind === 'issmge';
  const doi = p.doi ? `<a href="${esc(p.doi)}" target="_blank" rel="noopener">${t('open_doi')}</a>` : '';
  const links = isConf
    ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${t('open_issmge')}</a>${p.pdf ? `<a href="${esc(p.pdf)}" target="_blank" rel="noopener">${t('open_pdf')}</a>` : ''}${doi}`
    : `${doi}<a href="https://openalex.org/${esc(id)}" target="_blank" rel="noopener">${t('open_openalex')}</a>`;
  const citeLine = isConf ? `<span class="badge">${t('issmge_badge')}</span>` : t('cited', p.cites.toLocaleString(getLang()));

  panel.innerHTML = `
    <button class="icon-btn close" data-close aria-label="Close">✕</button>
    <div class="subtitle">${t('country')} · <a href="#" data-country="${country}">${esc(countryName(place?.properties))}</a></div>
    <h2>${esc(p.title)}</h2>
    <div class="byline">${esc(p.authors.join(', '))}${p.authors.length >= 6 ? ' et al.' : ''}<br>
      ${esc(p.venue || '')}${p.venue ? ' · ' : ''}${p.year ?? ''} · ${citeLine}</div>
    <div class="tags">${(p.keywords || []).map(k => `<span>${esc(k)}</span>`).join('')}</div>
    <div class="actions">${links}</div>
    <h3>${t('connections')}</h3>
    <ol class="papers">${neigh.map(n => {
      const title = n.ext ? graph.external[n.other]?.[2] : papers[n.other]?.title;
      const c = n.ext ? graph.external[n.other]?.[3] : country;
      const ring = papers[n.other]?.kind === 'issmge' ? '<span class="ring" title="ISSMGE"></span>' : '';
      return `<li>${ring}<a href="#" data-paper="${esc(n.other)}" data-c="${c}">${esc(title || n.other)}</a>${n.ext ? `<span class="ext">${t('external')}</span>` : ''}</li>`;
    }).join('')}</ol>`;
}

// ---------------- country panel ----------------
async function showCountry(countryId) {
  current = null;
  $('#paper-panel').hidden = true;
  owner.clearHighlights();
  owner.highlightCountry(countryId);
  const panel = $('#country-panel');
  panel.hidden = false;
  panel.dataset.country = countryId;
  const place = owner.getPlaces().find(f => f.properties.ownerId === countryId);
  const papers = await getJSON(`${config.papersEndpoint}/${countryId}.json`);
  if (panel.dataset.country !== String(countryId)) return;
  const all = Object.entries(papers);
  const top = all.filter(([, p]) => p.kind !== 'issmge').sort((a, b) => b[1].cites - a[1].cites).slice(0, 40);
  const confs = all.filter(([, p]) => p.kind === 'issmge').sort((a, b) => (b[1].year || 0) - (a[1].year || 0));
  const other = getLang() === 'fr' ? place?.properties.name_en : place?.properties.name_fr;
  panel.innerHTML = `
    <button class="icon-btn close" data-close aria-label="Close">✕</button>
    <h2>${esc(countryName(place?.properties))}</h2>
    <div class="subtitle">${esc(other || '')} · ${t('papers_count', Object.keys(papers).length)}</div>
    <div class="tags">${(place?.properties.keywords || []).map(k => `<span>${esc(k)}</span>`).join('')}</div>
    <h3>${t('in_country')}</h3>
    <ol class="papers">${top.map(([id, p]) => `
      <li><a href="#" data-paper="${esc(id)}" data-c="${countryId}" data-fly="1">${esc(p.title)}</a>
      <div class="meta">${esc(p.authors[0] || '')} · ${p.year ?? ''} · ${p.cites.toLocaleString(getLang())}</div></li>`).join('')}</ol>
    ${confs.length ? `<h3>${t('conf_in_country', confs.length)}</h3>
    <ol class="papers conf">${confs.slice(0, 30).map(([id, p]) => `
      <li><a href="#" data-paper="${esc(id)}" data-c="${countryId}" data-fly="1">${esc(p.title)}</a>
      <div class="meta">${esc(p.authors[0] || '')} · ${esc(p.venue || '')} · ${p.year ?? ''}</div></li>`).join('')}</ol>` : ''}`;
}

function renderAbout() {
  $('#about-panel').innerHTML = `<button class="icon-btn close" data-close aria-label="Close">✕</button>
    <h2>${t('about_title')}</h2>${t('about_html', meta)}`;
}

// ---------------- events ----------------
document.addEventListener('click', e => {
  const close = e.target.closest('[data-close]');
  if (close) {
    close.closest('.panel').hidden = true;
    if (close.closest('#paper-panel') || close.closest('#country-panel')) owner.clearHighlights();
    return;
  }
  const link = e.target.closest('[data-paper]');
  if (link) { e.preventDefault(); showPaper(link.dataset.paper, +link.dataset.c, { fly: true }); return; }
  const c = e.target.closest('[data-country]');
  if (c) { e.preventDefault(); showCountry(+c.dataset.country); }
});

$('#about-btn').addEventListener('click', () => {
  const p = $('#about-panel');
  p.hidden = !p.hidden;
  if (!p.hidden) renderAbout();
});

// search
const input = $('#search'), list = $('#suggestions'), clearBtn = $('#clear-btn');
let results = [], selected = 0, timer;
input.addEventListener('focus', () => searcher.load());
input.addEventListener('input', () => {
  clearBtn.hidden = !input.value;
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const q = input.value;
    results = q.trim().length >= 2 ? await searcher.find(q) : [];
    if (q !== input.value) return;
    selected = 0;
    renderSuggestions();
  }, 120);
});
input.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    if (!results.length) return;
    selected = (selected + (e.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
    renderSuggestions();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (results[selected]) pick(results[selected]);
  } else if (e.key === 'Escape') {
    list.hidden = true;
  }
});
list.addEventListener('mousedown', e => {
  const li = e.target.closest('li');
  if (li) { e.preventDefault(); pick(results[+li.dataset.i]); }
});
clearBtn.addEventListener('click', () => {
  input.value = ''; clearBtn.hidden = true; list.hidden = true; results = [];
  $('#paper-panel').hidden = true; owner.clearHighlights();
});
document.addEventListener('click', e => { if (!e.target.closest('.search-box')) list.hidden = true; });

function renderSuggestions() {
  list.hidden = !results.length;
  list.innerHTML = results.map((r, i) => `
    <li data-i="${i}" class="${i === selected ? 'selected' : ''}">
      ${r.kind === 'country' ? `<div class="kind">${t('country')}</div>` : ''}
      <div>${r.html}</div>${r.meta ? `<div class="meta">${esc(r.meta)}</div>` : ''}</li>`).join('');
}

async function pick(r) {
  list.hidden = true;
  input.value = r.text;
  if (r.kind === 'country') {
    owner.flyTo(r.lon, r.lat, 5);
    showCountry(r.id);
    return;
  }
  owner.flyTo(r.lon, r.lat, 9);
  showPaper(r.id, r.country);
}

// ISSMGE toggle + legend
let confOn = true;
try { confOn = localStorage.getItem('geomap-conf') !== 'off'; } catch (e) { /* ignore */ }
const confBox = $('#conf-toggle');
confBox.checked = confOn;
owner.setConferencesVisible(confOn);
confBox.addEventListener('change', () => {
  owner.setConferencesVisible(confBox.checked);
  try { localStorage.setItem('geomap-conf', confBox.checked ? 'on' : 'off'); } catch (e) { /* ignore */ }
});
getJSON(config.meta).then(m => { if (!m.issmge_papers) $('#legend').hidden = true; }).catch(() => {});

// language
function applyLanguage(lang) {
  document.querySelectorAll('.lang-switch button').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $('#made-by').innerHTML = t('made_by');
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  if (owner.map.isStyleLoaded()) owner.setLanguage(lang); else owner.map.once('load', () => owner.setLanguage(lang));
  if (!$('#about-panel').hidden) renderAbout();
  if (current && !$('#paper-panel').hidden) showPaper(current.id, current.country);
  const cp = $('#country-panel');
  if (!cp.hidden && cp.dataset.country) showCountry(+cp.dataset.country);
}
document.querySelectorAll('.lang-switch button').forEach(b => b.addEventListener('click', () => setLang(b.dataset.lang)));
onLangChange(applyLanguage);
document.documentElement.lang = getLang();
applyLanguage(getLang());
