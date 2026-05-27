// Mapa MapLibre para o usuário ajustar o ponto e desenhar trecho opcional.
import { OSM_STYLE } from './map-style.js';

export function createPickMap(elId, center, onMove) {
  const map = new maplibregl.Map({
    container: elId,
    style: OSM_STYLE,
    center: [center.lon, center.lat],
    zoom: 15,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

  const marker = new maplibregl.Marker({ draggable: true, color: '#0b3d2e' })
    .setLngLat([center.lon, center.lat])
    .addTo(map);

  marker.on('dragend', () => {
    const ll = marker.getLngLat();
    onMove({ lat: ll.lat, lon: ll.lng });
  });
  map.on('click', (e) => {
    marker.setLngLat(e.lngLat);
    onMove({ lat: e.lngLat.lat, lon: e.lngLat.lng });
  });

  return { map, marker };
}
