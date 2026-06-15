/**
 * Rótulos e valores amigáveis do road_context_json (malha DER).
 * Espelha backend/services/road_context.py.
 */

export const ROAD_CONTEXT_EXCLUDED = new Set(['jurisdicao', 'perimetro_urbano', 'scope']);

const TIPO_PISTA_LABELS = {
  DUP: 'Duplicada',
  PAV: 'Pavimentada',
  CIM: 'Cimento',
  ASF: 'Asfaltada',
  BLO: 'Bloqueada / bloquete',
  CCPB: 'CBUQ / concreto betuminoso',
  TSD: 'Tratamento superficial duplo',
  TER: 'Terra',
  TERRA: 'Terra',
  PED: 'Pedra',
  PEDREIRA: 'Pedreira',
  REC: 'Revestimento primário',
};

const ADMINISTRA_LABELS = {
  DER: 'DER-SP',
  DNIT: 'DNIT',
  CONCESSIONARIA: 'Concessionária',
  CONCESSIONÁRIA: 'Concessionária',
};

/** Ordem e rótulos das linhas no popup (eventos de tráfego). */
export const ROAD_CONTEXT_POPUP_FIELDS = [
  { key: 'scope_label', label: 'Classificação viária' },
  { key: '_rodovia_line', label: 'Rodovia' },
  { key: 'tipo_rodoviario', label: 'Tipo rodoviário', titleCase: true },
  { key: 'municipio', label: 'Município', titleCase: true },
  { key: 'tipo_pista', label: 'Tipo de pista', valueKey: 'tipo_pista' },
  { key: 'administra', label: 'Administrador da via', valueKey: 'administra' },
  { key: 'cod_regional', label: 'Coordenadoria Regional Geral DER' },
  { key: 'sede_regional', label: 'Sede da coordenadoria', titleCase: true },
  { key: 'residencia', label: 'Residência de conserva DER' },
  { key: 'sede_residencia', label: 'Sede da residência de conserva', titleCase: true },
  { key: 'snap_dist_m', label: 'Distância snap utilizada' },
];

function titleCase(value) {
  if (!value) return value;
  return String(value)
    .toLowerCase()
    .replace(/(^|\s|[-/])(\S)/g, (_, sep, ch) => sep + ch.toUpperCase());
}

export function normalizeRoadContext(raw) {
  if (!raw) return null;
  let ctx = typeof raw === 'object' ? { ...raw } : null;
  if (!ctx) {
    try {
      ctx = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!ctx.scope_label && ctx.scope) {
    const scopeLabels = {
      federal: 'Rodovia federal',
      estadual: 'Rodovia estadual',
      municipal: "Provavelmente municipal",
    };
    ctx.scope_label = scopeLabels[ctx.scope] || ctx.scope;
  }
  return ctx;
}

export function formatTipoPista(value) {
  if (value == null || value === '') return null;
  const code = String(value).trim().toUpperCase();
  return TIPO_PISTA_LABELS[code] || titleCase(code);
}

export function formatAdministra(value) {
  if (value == null || value === '') return null;
  const code = String(value).trim().toUpperCase();
  return ADMINISTRA_LABELS[code] || titleCase(String(value).trim());
}

export function formatSnapDistM(value) {
  if (value == null || value === '') return null;
  const n = Number(value);
  if (Number.isNaN(n)) return null;
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} m`;
}

export function formatRoadContextValue(key, value) {
  if (value == null || value === '') return null;
  if (key === 'tipo_pista') return formatTipoPista(value);
  if (key === 'administra') return formatAdministra(value);
  if (key === 'snap_dist_m') return formatSnapDistM(value);
  if (key === 'scope_label') {
    const v = String(value).trim();
    if (v === 'Via municipal' || v === 'Rodovia municipal') return 'Provavelmente municipal';
    return v;
  }
  return String(value).trim();
}

export function rodoviaLine(ctx) {
  if (!ctx) return null;
  const rod = ctx.rodovia;
  const denom = ctx.denominacao;
  if (rod && denom) return `${rod} — ${denom}`;
  if (rod) return String(rod);
  if (denom) return String(denom);
  return null;
}

/** Linhas { label, value } para popup — omite vazios. */
export function buildRoadContextRows(ctx) {
  const c = normalizeRoadContext(ctx);
  if (!c) return [];

  const rows = [];
  for (const field of ROAD_CONTEXT_POPUP_FIELDS) {
    if (field.key === '_rodovia_line') {
      const value = rodoviaLine(c);
      if (value) rows.push({ label: field.label, value });
      continue;
    }
    let raw = c[field.key];
    if (raw == null || raw === '') continue;

    let value = formatRoadContextValue(field.key, raw);
    if (field.titleCase && value) value = titleCase(value);
    if (value) rows.push({ label: field.label, value });
  }
  return rows;
}

/** Fallback municipal quando road_context existe mas sem snap DER. */
export function buildMunicipalFallbackRows(p) {
  const ctx = normalizeRoadContext(p?.road_context);
  const rows = [];
  if (ctx?.scope_label) {
    rows.push({ label: 'Classificação viária', value: ctx.scope_label });
  }
  if (ctx?.municipio) {
    rows.push({ label: 'Município', value: titleCase(ctx.municipio) });
  }
  if (p?.road_label && !rodoviaLine(ctx)) {
    rows.push({ label: 'Referência local', value: String(p.road_label) });
  }
  return rows;
}
