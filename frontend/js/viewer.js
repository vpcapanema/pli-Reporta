// Mapa público — eventos de tráfego e manifestações cidadãs.
import { OSM_STYLE } from './map-style.js';
import { fetchIncidents, fetchManifestations, resolveIncident } from './api.js';

const EVENT_COLORS = {
  bloqueio_total: '#b3261e',
  acidente: '#d77a1f',
  incendio: '#e8590c',
  animal_na_pista: '#a1887f',
  objeto_na_pista: '#8d6e63',
  queda_arvore: '#2e7d32',
  veiculo_quebrado: '#607d8b',
  alagamento: '#1565c0',
  obra_grande: '#7b3ea8',
  lentidao_corredor: '#b88500',
  sinalizacao_quebrada: '#5c6bc0',
  buraco: '#3e2723',
  outro: '#555',
};

const MANIF_COLORS = {
  elogio: '#2fa854',
  sugestao: '#116593',
  reclamacao: '#c45a11',
};

const map = new maplibregl.Map({
  container: 'viewer-map',
  style: OSM_STYLE,
  center: [-46.63, -23.55],
  zoom: 6,
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } }), 'top-right');

function layerVisibility(id, visible) {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
}

function popupHtml(p) {
  const label = p.interaction_type === 'manifestacao'
    ? `Manifestação · ${p.category}`
    : p.category;
  let roadBlock = '';
  if (p.road_context) {
    try {
      const ctx = typeof p.road_context === 'string' ? JSON.parse(p.road_context) : p.road_context;
      const lines = [];
      if (ctx.scope_label) lines.push(`<strong>${ctx.scope_label}</strong>`);
      if (ctx.rodovia && ctx.denominacao) {
        lines.push(`${ctx.rodovia} — ${ctx.denominacao}`);
      } else if (ctx.rodovia) {
        lines.push(String(ctx.rodovia));
      }
      if (ctx.tipo_rodoviario) lines.push(`Tipo: ${ctx.tipo_rodoviario}`);
      if (ctx.municipio) lines.push(`Município: ${ctx.municipio}`);
      if (ctx.cod_regional || ctx.sede_regional) {
        const reg = [ctx.cod_regional, ctx.sede_regional && `sede ${ctx.sede_regional}`].filter(Boolean).join(' · ');
        lines.push(`Regional DER: ${reg}`);
      }
      if (ctx.residencia || ctx.sede_residencia) {
        const res = [ctx.residencia && `residência ${ctx.residencia}`, ctx.sede_residencia].filter(Boolean).join(' · ');
        lines.push(`Residência: ${res}`);
      }
      if (lines.length) {
        roadBlock = `<div class="popup-road" style="margin:6px 0;padding:6px 8px;background:#eef3f7;border-radius:6px;font-size:12px;line-height:1.45">${lines.join('<br/>')}</div>`;
      }
    } catch (_) { /* ignora JSON inválido */ }
  }
  const canResolve = p.interaction_type !== 'manifestacao' && p.cluster_id;
  const resolveBtn = canResolve
    ? `<button type="button" class="popup-resolver" data-cluster="${p.cluster_id}"
         style="margin-top:8px;width:100%;padding:8px;border:0;border-radius:6px;
         background:#2fa854;color:#fff;font-weight:600;cursor:pointer">
         Já foi resolvido?
       </button>`
    : '';
  return `
    <strong>${label}</strong>${p.magnitude ? ` · ${p.magnitude}` : ''}<br/>
    ${roadBlock}
    ${p.description ? `<em>${p.description.slice(0, 120)}</em><br/>` : ''}
    <small>id ${p.id}</small><br/>
    ${p.photo_url ? `<img src="${p.photo_url}" style="max-width:200px;border-radius:6px;margin-top:6px"/>` : ''}
    ${resolveBtn}
  `;
}

document.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('.popup-resolver');
  if (!btn) return;
  btn.disabled = true;
  try {
    const r = await resolveIncident(btn.dataset.cluster);
    btn.textContent = r.message || 'Obrigado pelo aviso!';
    btn.style.background = '#116593';
  } catch (_) {
    btn.disabled = false;
    btn.textContent = 'Não foi possível enviar. Tente de novo.';
  }
});

function bindPopup(layerId) {
  map.on('click', layerId, (e) => {
    const p = e.features[0].properties;
    new maplibregl.Popup().setLngLat(e.lngLat).setHTML(popupHtml(p)).addTo(map);
  });
  map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = ''; });
}

map.on('load', async () => {
  map.addSource('events', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addSource('manifestations', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

  map.addLayer({
    id: 'events-circles',
    type: 'circle',
    source: 'events',
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['get', 'priority'], 0, 4, 0.5, 8, 1, 14],
      'circle-color': [
        'match', ['get', 'category'],
        'bloqueio_total', EVENT_COLORS.bloqueio_total,
        'acidente', EVENT_COLORS.acidente,
        'incendio', EVENT_COLORS.incendio,
        'animal_na_pista', EVENT_COLORS.animal_na_pista,
        'objeto_na_pista', EVENT_COLORS.objeto_na_pista,
        'queda_arvore', EVENT_COLORS.queda_arvore,
        'veiculo_quebrado', EVENT_COLORS.veiculo_quebrado,
        'alagamento', EVENT_COLORS.alagamento,
        'obra_grande', EVENT_COLORS.obra_grande,
        'lentidao_corredor', EVENT_COLORS.lentidao_corredor,
        'sinalizacao_quebrada', EVENT_COLORS.sinalizacao_quebrada,
        'buraco', EVENT_COLORS.buraco,
        EVENT_COLORS.outro,
      ],
      'circle-opacity': 0.85,
      'circle-stroke-color': '#fff',
      'circle-stroke-width': 1.5,
    },
  });

  map.addLayer({
    id: 'manif-circles',
    type: 'circle',
    source: 'manifestations',
    paint: {
      'circle-radius': 8,
      'circle-color': [
        'match', ['get', 'category'],
        'elogio', MANIF_COLORS.elogio,
        'sugestao', MANIF_COLORS.sugestao,
        'reclamacao', MANIF_COLORS.reclamacao,
        '#888',
      ],
      'circle-opacity': 0.8,
      'circle-stroke-color': '#fff',
      'circle-stroke-width': 1.5,
    },
  });

  bindPopup('events-circles');
  bindPopup('manif-circles');

  document.getElementById('layer-events').addEventListener('change', (e) => {
    layerVisibility('events-circles', e.target.checked);
  });
  document.getElementById('layer-manif').addEventListener('change', (e) => {
    layerVisibility('manif-circles', e.target.checked);
  });

  await refresh();
  setInterval(refresh, 60_000);
});

async function refresh() {
  try {
    const [events, manif] = await Promise.all([
      fetchIncidents(),
      fetchManifestations(),
    ]);
    map.getSource('events').setData(events);
    map.getSource('manifestations').setData(manif);
    document.getElementById('count-events').textContent = events.features.length;
    document.getElementById('count-manif').textContent = manif.features.length;
  } catch (e) {
    console.error(e);
  }
}
