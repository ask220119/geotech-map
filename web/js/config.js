// Where the map reads its data. Mirrors src/lib/config.js in map-of-github.
const params = new URLSearchParams(window.location.search);
const dataRoot = params.get('data') || 'data';
// absolute base URL; built by hand because new URL() would percent-encode the {z}/{fontstack} tokens
const base = new URL('.', window.location.href).href;

export default {
  pointsSource: `${dataRoot}/points.geojson`,
  // Set to true after `tippecanoe` produced data/points/{z}/{x}/{y}.pbf (for 100k+ papers).
  usePointTiles: false,
  pointTiles: `${base}${dataRoot}/points/{z}/{x}/{y}.pbf`,
  bordersSource: `${dataRoot}/borders.geojson`,
  placesSource: `${dataRoot}/places.geojson`,
  searchIndex: `${dataRoot}/search.json`,
  papersEndpoint: `${dataRoot}/papers`,
  graphsEndpoint: `${dataRoot}/graphs`,
  meta: `${dataRoot}/meta.json`,
  glyphs: `${base}fonts/{fontstack}/{range}.pbf`,
  fontRegular: ['DejaVu Sans Condensed'],
  fontBold: ['DejaVu Sans Condensed Bold'],
  paperLabelsMinZoom: 6.5,
};
