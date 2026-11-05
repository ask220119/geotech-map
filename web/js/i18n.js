// Bilingual interface (EN/FR). Country names come from places.geojson (name_en / name_fr).
const STRINGS = {
  en: {
    search_placeholder: 'Find a paper, author or country',
    country: 'Country', paper: 'Paper',
    cited: n => `cited ${n} times`,
    show_connections: 'Show connections', hide_connections: 'Hide connections',
    open_doi: 'Open DOI', open_openalex: 'OpenAlex',
    in_country: 'Most cited papers in this country', keywords: 'Keywords',
    connections: 'Closest papers', external: 'other country',
    papers_count: n => `${n.toLocaleString('en')} papers`,
    about_title: 'Map of Geotechnics',
    made_by: 'Inspired by <a href="https://github.com/anvaka/map-of-github" target="_blank" rel="noopener">map-of-github</a> · data <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a>',
    about_html: meta => `
      <p>Each dot is a geotechnics paper. Two papers sit close to each other when they cite the same literature
      (bibliographic coupling, measured with the Jaccard index) or cite each other. The size of a dot reflects its citations.</p>
      <p>Papers are grouped into <b>${meta.countries}</b> countries with Leiden clustering; borders are Voronoi cells around the papers.
      The map holds <b>${meta.papers.toLocaleString('en')}</b> papers with at least ${meta.min_citations} citations, built on ${meta.built}.</p>
      <h3>How to use it</h3>
      <p>Click a dot to read about the paper and see its closest neighbours. Click a country to list its most cited papers.
      Search by title, author or country name.</p>
      <h3>Credits</h3>
      <p>Method and design inspired by Andrei Kashcha's <a href="https://github.com/anvaka/map-of-github" target="_blank" rel="noopener">Map of GitHub</a> (MIT).
      Paper metadata from <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a> (CC0). Rendering by MapLibre GL JS.</p>`,
  },
  fr: {
    search_placeholder: 'Chercher un article, un auteur ou un pays',
    country: 'Pays', paper: 'Article',
    cited: n => `cité ${n} fois`,
    show_connections: 'Voir les liens', hide_connections: 'Masquer les liens',
    open_doi: 'Ouvrir le DOI', open_openalex: 'OpenAlex',
    in_country: 'Articles les plus cités de ce pays', keywords: 'Mots-clés',
    connections: 'Articles les plus proches', external: 'autre pays',
    papers_count: n => `${n.toLocaleString('fr')} articles`,
    about_title: 'Carte de la géotechnique',
    made_by: 'Inspiré de <a href="https://github.com/anvaka/map-of-github" target="_blank" rel="noopener">map-of-github</a> · données <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a>',
    about_html: meta => `
      <p>Chaque point est un article de géotechnique. Deux articles sont proches lorsqu'ils citent la même littérature
      (couplage bibliographique, mesuré par l'indice de Jaccard) ou se citent l'un l'autre. La taille d'un point reflète ses citations.</p>
      <p>Les articles sont regroupés en <b>${meta.countries}</b> pays par l'algorithme de Leiden ; les frontières sont des cellules de Voronoï autour des articles.
      La carte compte <b>${meta.papers.toLocaleString('fr')}</b> articles cités au moins ${meta.min_citations} fois, construite le ${meta.built}.</p>
      <h3>Mode d'emploi</h3>
      <p>Cliquez sur un point pour voir l'article et ses plus proches voisins. Cliquez sur un pays pour lister ses articles les plus cités.
      Recherchez par titre, auteur ou nom de pays.</p>
      <h3>Crédits</h3>
      <p>Méthode et design inspirés de la <a href="https://github.com/anvaka/map-of-github" target="_blank" rel="noopener">Map of GitHub</a> d'Andrei Kashcha (MIT).
      Métadonnées d'OpenAlex (CC0). Rendu MapLibre GL JS.</p>`,
  },
};

const listeners = new Set();
let lang = (navigator.language || '').toLowerCase().startsWith('fr') ? 'fr' : 'en';
try {
  const saved = localStorage.getItem('geomap-lang');
  if (saved === 'fr' || saved === 'en') lang = saved;
} catch (e) { /* storage blocked */ }
const fromUrl = new URLSearchParams(location.search).get('lang');
if (fromUrl === 'fr' || fromUrl === 'en') lang = fromUrl;

export function t(key, ...args) {
  const v = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
  return typeof v === 'function' ? v(...args) : v;
}
export function getLang() { return lang; }
export function setLang(next) {
  if (next === lang) return;
  lang = next;
  try { localStorage.setItem('geomap-lang', lang); } catch (e) { /* ignore */ }
  document.documentElement.lang = lang;
  listeners.forEach(fn => fn(lang));
}
export function onLangChange(fn) { listeners.add(fn); }
export function countryName(props) {
  return props?.[`name_${lang}`] || props?.name_en || '';
}
