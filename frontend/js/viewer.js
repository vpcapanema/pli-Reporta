// Mapa público de incidentes.
import { OSM_STYLE } from './map-style.js';
import { fetchIncidents } from './api.js';

const COLORS = {
  bloqueio_total: '#b3261e',
  acidente: '#d77a1f',
  alagamento: '#1565c0',
  obra_grande: '#7b3ea8',
  lentidao_corredor: '#b88500',
  sinalizacao_quebrada: '#5c6bc0',
  buraco: '#3e2723',
  outro: '#555',
};

const map = new maplibregl.Map({
  container: 'viewer-map',
  style: OSM_STYLE,
  center: [-46.63, -23.55],
  zoom: 6,
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } }), 'top-right');

map.on('load', async () => {
  map.addSource('incidents', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

  map.addLayer({
    id: 'inc-circles',
    type: 'circle',
    source: 'incidents',
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['get', 'priority'],
        0, 4, 0.5, 8, 1, 14,
      ],
      'circle-color': [
        'match', ['get', 'category'],
        'bloqueio_total', COLORS.bloqueio_total,
        'acidente', COLORS.acidente,
        'alagamento', COLORS.alagamento,
        'obra_grande', COLORS.obra_grande,
        'lentidao_corredor', COLORS.lentidao_corredor,
        'sinalizacao_quebrada', COLORS.sinalizacao_quebrada,
        'buraco', COLORS.buraco,
        COLORS.outro,
      ],
      'circle-opacity': 0.85,
      'circle-stroke-color': '#fff',
      'circle-stroke-width': 1.5,
    },
  });

  map.on('click', 'inc-circles', (e) => {
    const f = e.features[0];
    const p = f.properties;
    const html = `
      <strong>${p.category}</strong> · ${p.magnitude}<br/>
      V=${p.veracity} · R=${p.relevance} · P=${p.priority}<br/>
      <small>id ${p.id}</small><br/>
      ${p.photo_url ? `<img src="${p.photo_url}" style="max-width:200px;border-radius:6px;margin-top:6px"/>` : ''}
    `;
    new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
  });
  map.on('mouseenter', 'inc-circles', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'inc-circles', () => map.getCanvas().style.cursor = '');

  await refresh();
  setInterval(refresh, 60_000);
});

async function refresh() {
  try {
    const data = await fetchIncidents();
    map.getSource('incidents').setData(data);
    document.getElementById('count').textContent = data.features.length;
  } catch (e) {
    console.error(e);
  }
}
