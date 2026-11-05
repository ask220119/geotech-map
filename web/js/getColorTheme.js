// Colour theme. `input` values are the fills written by the pipeline (export.py PALETTE);
// `output` is what is drawn, so you can restyle the whole map here without rebuilding data.
// Earthy "geology" palette; swap for anvaka's blue "explorer" theme if you prefer.
const strata = {
  background: '#0b1a2b',
  borderColor: 'rgba(10, 20, 30, 0.85)',
  circleColor: '#f4efe4',
  circleStrokeColor: '#1b1b1b',
  circleLabelsColor: '#ffffff',
  circleLabelsHaloColor: '#1b2430',
  placeLabelsColor: '#ffffff',
  placeLabelsHaloColor: 'rgba(0,0,0,0.75)',
  linkColor: '#ffd59a',
  primaryHighlight: '#bf2072',
  secondaryHighlight: '#e56aaa',
  color: [
    { input: '#516ebc', output: '#7a5c3e' }, // ochre clay
    { input: '#00529c', output: '#4f6b4a' }, // moss
    { input: '#153477', output: '#5b4a6e' }, // schist
    { input: '#37009c', output: '#8a6a2f' }, // sand
    { input: '#00789c', output: '#3f6470' }, // slate
    { input: '#37549c', output: '#6e4b3f' }, // laterite
    { input: '#2f6f73', output: '#55603a' }, // loess
  ],
};

export default function getColorTheme() {
  return strata;
}
