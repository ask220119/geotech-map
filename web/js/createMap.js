// The map itself. Same layer stack as map-of-github's createMap.js:
// background -> country polygons -> borders -> connection lines -> papers -> labels -> country names.
import config from './config.js';
import { getLang } from './i18n.js';
import getColorTheme from './getColorTheme.js';

const theme = getColorTheme();
const fillStyle = ['match', ['get', 'fill'], ...theme.color.flatMap(c => [c.input, c.output]), '#0a2a5a'];

export default function createMap({ onPaperClick, onCountryClick, onHover }) {
  const map = new maplibregl.Map({
    container: 'map',
    hash: true,
    center: [0, 0],
    zoom: 2,
    minZoom: 1,
    maxZoom: 14,
    renderWorldCopies: false,
    attributionControl: false,
    style: buildStyle(),
  });
  map.dragRotate.disable();
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

  let places = [];
  fetch(config.placesSource).then(r => r.json()).then(fc => {
    places = fc.features;
    const apply = () => map.getSource('place').setData(fc);
    map.isStyleLoaded() ? apply() : map.once('load', apply);
  });

  map.on('load', () => {
    if (!location.hash) fitToData();
  });

  map.on('mousemove', e => {
    const f = nearestPaper(e.point);
    map.getCanvas().style.cursor = f ? 'pointer' : '';
    onHover?.(f ? { text: f.properties.label, x: e.point.x, y: e.point.y } : null);
  });
  map.on('mouseout', () => onHover?.(null));
  map.on('movestart', () => onHover?.(null));

  map.on('click', e => {
    const paper = nearestPaper(e.point);
    if (paper) {
      onPaperClick(paper.properties.id, paper.properties.parent, paper.geometry.coordinates);
      return;
    }
    if (!map.getLayer('polygon-layer')) return;
    const bg = map.queryRenderedFeatures(e.point, { layers: ['polygon-layer'] })[0];
    if (bg) onCountryClick(bg.id);
  });

  function fitToData() {
    fetch(config.bordersSource).then(r => r.json()).then(fc => {
      let minX = 180, minY = 85, maxX = -180, maxY = -85;
      const walk = c => (typeof c[0] === 'number'
        ? (minX = Math.min(minX, c[0]), maxX = Math.max(maxX, c[0]), minY = Math.min(minY, c[1]), maxY = Math.max(maxY, c[1]))
        : c.forEach(walk));
      fc.features.forEach(f => walk(f.geometry.coordinates));
      map.fitBounds([[minX, minY], [maxX, maxY]], { padding: 40, animate: false });
    });
  }

  function nearestPaper(point) {
    const layers = ['circle-layer', 'issmge-layer'].filter(l => map.getLayer(l) &&
      map.getLayoutProperty(l, 'visibility') !== 'none');
    if (!layers.length) return null;
    const r = 8;
    const feats = map.queryRenderedFeatures([[point.x - r, point.y - r], [point.x + r, point.y + r]],
      { layers });
    let best = null, bestD = Infinity;
    for (const f of feats) {
      const p = map.project(f.geometry.coordinates);
      const d = (p.x - point.x) ** 2 + (p.y - point.y) ** 2;
      if (d < bestD) { bestD = d; best = f; }
    }
    return best;
  }

  function setConferencesVisible(on) {
    const apply = () => map.setLayoutProperty('issmge-layer', 'visibility', on ? 'visible' : 'none');
    map.isStyleLoaded() ? apply() : map.once('load', apply);
  }

  function setLanguage(lang) {
    map.setLayoutProperty('place-country', 'text-field', ['coalesce', ['get', `name_${lang}`], ['get', 'name_en']]);
  }

  function papersInCountry(countryId, limit = 40) {
    const feats = map.querySourceFeatures('points-source', {
      sourceLayer: config.usePointTiles ? 'points' : undefined,
      filter: ['==', ['get', 'parent'], countryId],
    });
    const seen = new Map();
    feats.sort((a, b) => b.properties.cites - a.properties.cites);
    for (const f of feats) {
      if (!seen.has(f.properties.id)) seen.set(f.properties.id, f);
      if (seen.size >= limit) break;
    }
    return [...seen.values()];
  }

  function highlightCountry(countryId) {
    map.setFilter('border-highlight', ['==', ['id'], countryId ?? -1]);
  }

  function showConnections(centerId, graph, positions) {
    // graph: {links: [[a, b, w, ext]]}; positions: Map(id -> [lon, lat])
    const lines = [], nodes = [];
    for (const [a, b, w, ext] of graph.links) {
      const pa = positions.get(a), pb = positions.get(b);
      if (!pa || !pb) continue;
      const first = a === centerId || b === centerId;
      if (!first && ext) continue;
      lines.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [pa, pb] },
                   properties: { first: first ? 1 : 0, w } });
      if (first) {
        const other = a === centerId ? b : a;
        nodes.push({ type: 'Feature', geometry: { type: 'Point', coordinates: positions.get(other) },
                     properties: { color: theme.secondaryHighlight, size: 5 } });
      }
    }
    if (positions.get(centerId)) {
      nodes.push({ type: 'Feature', geometry: { type: 'Point', coordinates: positions.get(centerId) },
                   properties: { color: theme.primaryHighlight, size: 8 } });
    }
    map.getSource('links').setData({ type: 'FeatureCollection', features: lines });
    map.getSource('selected-nodes').setData({ type: 'FeatureCollection', features: nodes });
  }

  function clearHighlights() {
    const empty = { type: 'FeatureCollection', features: [] };
    map.getSource('links')?.setData(empty);
    map.getSource('selected-nodes')?.setData(empty);
    highlightCountry(null);
  }

  function flyTo(lon, lat, zoom) {
    // keep the target visible beside (desktop) or above (phone) the side panel
    // (an `offset`, not `padding`: padding persists and makes MapLibre skip tiles at the top)
    const small = window.innerWidth <= 600;
    const offset = small
      ? [0, -Math.round((window.innerHeight * 0.45 - 48) / 2)]
      : [Math.round(Math.min(416, window.innerWidth * 0.45) / 2), 0];
    map.flyTo({ center: [lon, lat], zoom: zoom ?? Math.max(map.getZoom(), 8), offset });
  }

  return { map, setLanguage, setConferencesVisible, papersInCountry, highlightCountry, showConnections, clearHighlights,
           flyTo, getPlaces: () => places };
}

function buildStyle() {
  const pointsSource = config.usePointTiles
    ? { type: 'vector', tiles: [config.pointTiles], minzoom: 4, maxzoom: 11 }
    : { type: 'geojson', data: config.pointsSource };
  const srcLayer = config.usePointTiles ? { 'source-layer': 'points' } : {};
  const lang = getLang();
  return {
    version: 8,
    glyphs: config.glyphs,
    sources: {
      'borders-source': { type: 'geojson', data: config.bordersSource },
      'points-source': pointsSource,
      place: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
      links: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
      'selected-nodes': { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': theme.background } },
      { id: 'polygon-layer', type: 'fill', source: 'borders-source',
        paint: { 'fill-color': fillStyle, 'fill-opacity': 0.95 } },
      { id: 'border-line', type: 'line', source: 'borders-source',
        paint: { 'line-color': theme.borderColor, 'line-width': ['interpolate', ['linear'], ['zoom'], 2, 0.4, 8, 1.2] } },
      { id: 'border-highlight', type: 'line', source: 'borders-source', filter: ['==', ['id'], -1],
        paint: { 'line-color': '#ffffff', 'line-width': 3 } },
      { id: 'links-layer', type: 'line', source: 'links',
        paint: {
          'line-color': ['case', ['==', ['get', 'first'], 1], '#ffffff', theme.linkColor],
          'line-opacity': ['case', ['==', ['get', 'first'], 1], 0.9, 0.25],
          'line-width': ['case', ['==', ['get', 'first'], 1], 1.2, 0.6],
        } },
      { id: 'circle-layer', type: 'circle', source: 'points-source', ...srcLayer,
        filter: ['!=', ['get', 'kind'], 'issmge'],
        paint: {
          'circle-color': theme.circleColor,
          'circle-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0.35, 8, 0.9],
          'circle-stroke-color': theme.circleStrokeColor,
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 5, 0, 9, 1],
          'circle-radius': ['interpolate', ['linear'], ['zoom'],
            2, ['*', ['get', 'size'], 0.18], 6, ['*', ['get', 'size'], 0.6], 12, ['*', ['get', 'size'], 2.2]],
        } },
      { id: 'issmge-layer', type: 'circle', source: 'points-source', ...srcLayer,
        filter: ['==', ['get', 'kind'], 'issmge'],
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-stroke-color': theme.conferenceColor,
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 2, 0.5, 8, 1.4],
          'circle-stroke-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0.45, 8, 0.95],
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 0.6, 6, 1.8, 12, 6],
        } },
      { id: 'selected-nodes-layer', type: 'circle', source: 'selected-nodes',
        paint: { 'circle-color': ['get', 'color'], 'circle-radius': ['get', 'size'],
                 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 } },
      { id: 'label-layer', type: 'symbol', source: 'points-source', ...srcLayer,
        minzoom: config.paperLabelsMinZoom,
        filter: ['any', ['!=', ['get', 'kind'], 'issmge'], ['>=', ['zoom'], config.paperLabelsMinZoom + 2]],
        layout: {
          'text-font': config.fontRegular,
          'text-field': ['get', 'label'],
          'text-anchor': 'top', 'text-offset': [0, 0.6], 'text-max-width': 12,
          'symbol-sort-key': ['-', 0, ['get', 'cites']],
          'text-size': ['interpolate', ['linear'], ['zoom'],
            config.paperLabelsMinZoom, ['+', 8, ['/', ['get', 'size'], 2]], 12, ['+', 11, ['get', 'size']]],
        },
        paint: { 'text-color': theme.circleLabelsColor, 'text-halo-color': theme.circleLabelsHaloColor,
                 'text-halo-width': 1 } },
      { id: 'place-country', type: 'symbol', source: 'place', maxzoom: 10,
        filter: ['<=', ['get', 'symbolzoom'], ['+', ['zoom'], 3]],
        layout: {
          'text-font': config.fontBold,
          'text-field': ['coalesce', ['get', `name_${lang}`], ['get', 'name_en']],
          'text-size': ['interpolate', ['linear'], ['zoom'],
            1, ['step', ['get', 'symbolzoom'], 15, 3, 13, 4, 12, 5, 11],
            9, ['step', ['get', 'symbolzoom'], 24, 3, 20, 4, 18, 5, 16]],
          'symbol-sort-key': ['get', 'symbolzoom'],
          'text-max-width': 8, 'text-line-height': 1.1, 'text-padding': 4,
        },
        paint: { 'text-color': theme.placeLabelsColor, 'text-halo-color': theme.placeLabelsHaloColor,
                 'text-halo-width': 1.2 } },
    ],
  };
}
