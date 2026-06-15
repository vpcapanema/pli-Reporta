/**
 * Pacote completo de atributos por feature (36 campos).
 * Espelha docs/CAMPOS_CAMADAS.md e backend/services/layer_schema.py.
 */
import { categoryLabel, formatDate, statusLabel } from "./gestao-common.js";
import {
  buildMunicipalFallbackRows,
  buildRoadContextRows,
  normalizeRoadContext,
  ROAD_CONTEXT_POPUP_FIELDS,
} from "./road-context-labels.js";

export const SYSTEM_LAYER_FIELD_LABELS = [
  "ID",
  "Tipo de interação",
  "Categoria (código)",
  "Categoria",
  "Sigla da categoria",
  "Magnitude",
  "Descrição",
  "Status",
  "Visível no mapa público",
  "Visível no mapa gestão",
  "Exportação pública",
  "Exportação gestão",
  "Bloqueante",
  "Cluster",
  "Veracidade (V)",
  "Relevância (R)",
  "Prioridade (P)",
  "Válido desde",
  "Válido até",
  "Capturado em",
  "Recebido em",
  "URL da foto",
  "Acurácia GPS (m)",
  "Nonce de captura válido",
  "Trechos afetados",
];

export const DER_LAYER_FIELD_LABELS = ROAD_CONTEXT_POPUP_FIELDS.map(
  (f) => f.label,
);

export const FULL_LAYER_FIELD_LABELS = [
  ...SYSTEM_LAYER_FIELD_LABELS,
  ...DER_LAYER_FIELD_LABELS,
];

/** Campos de sistema visíveis no popup do mapa público (sem metadados internos). */
export const PUBLIC_SYSTEM_POPUP_FIELD_LABELS = [
  "Tipo de interação",
  "Categoria",
  "Magnitude",
  "Descrição",
  "Status",
  "Bloqueante",
  "Válido desde",
  "Válido até",
  "Capturado em",
  "Recebido em",
  "Acurácia GPS (m)",
];

/** Malha DER no mapa público — todos os campos documentados, exceto distância de snap. */
export const PUBLIC_DER_POPUP_FIELD_LABELS = DER_LAYER_FIELD_LABELS.filter(
  (label) => label !== "Distância snap utilizada",
);

const INTERACTION_LABELS = {
  evento_trafego: "Evento de tráfego",
  manifestacao: "Manifestação cidadã",
};

const EMPTY = "—";

function boolPt(value) {
  if (value === true || value === 1 || value === "1") return "Sim";
  if (value === false || value === 0 || value === "0") return "Não";
  return EMPTY;
}

function formatScore(value) {
  if (value == null || value === "") return EMPTY;
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  });
}

function formatIso(value) {
  if (!value) return EMPTY;
  return formatDate(value);
}

function categorySigla(categoryId, catalog) {
  const lists = [
    ...(catalog?.event_categories || []),
    ...(catalog?.manifestation_categories || []),
  ];
  const hit = lists.find((c) => c.id === categoryId);
  return hit?.sigla || pSiglaFallback(categoryId);
}

function pSiglaFallback(categoryId) {
  return categoryId ? String(categoryId).slice(0, 2).toUpperCase() : EMPTY;
}

function magnitudeLabel(value) {
  if (!value) return EMPTY;
  const map = { leve: "Leve", normal: "Normal", grave: "Grave" };
  return map[value] || String(value);
}

function affectedEdgesText(value) {
  if (!value) return EMPTY;
  if (Array.isArray(value)) {
    const items = value.filter(Boolean);
    return items.length ? items.join(", ") : EMPTY;
  }
  return String(value);
}

function buildDerValueMap(p) {
  const ctx = normalizeRoadContext(p?.road_context);
  const rows = [...buildRoadContextRows(ctx), ...buildMunicipalFallbackRows(p)];
  const map = new Map();
  for (const row of rows) {
    if (row.label && row.value) map.set(row.label, row.value);
  }
  if (p?.road_scope === "municipal" || ctx?.scope === "municipal") {
    map.set("Classificação viária", "Provavelmente municipal");
  }
  return map;
}

/** Mapa rótulo amigável → valor formatado (36 campos, docs/CAMPOS_CAMADAS.md). */
export function buildFullLayerPropertyMap(p, catalog) {
  const catLabel = p.category_label || categoryLabel(p.category, catalog);
  const sigla = p.category_sigla || categorySigla(p.category, catalog);
  const derMap = buildDerValueMap(p);

  const system = {
    ID: p.id || EMPTY,
    "Tipo de interação":
      INTERACTION_LABELS[p.interaction_type] || p.interaction_type || EMPTY,
    "Categoria (código)": p.category || EMPTY,
    Categoria: catLabel || EMPTY,
    "Sigla da categoria": sigla || EMPTY,
    Magnitude: magnitudeLabel(p.magnitude),
    Descrição: p.description ? String(p.description) : EMPTY,
    Status: statusLabel(p.status, catalog) || EMPTY,
    "Visível no mapa público": boolPt(p.visivel_mapa_publico),
    "Visível no mapa gestão": boolPt(p.visivel_mapa_gestao),
    "Exportação pública": boolPt(p.export_publico),
    "Exportação gestão": boolPt(p.export_gestao),
    Bloqueante: boolPt(p.blocking),
    Cluster: p.cluster_id || EMPTY,
    "Veracidade (V)": formatScore(p.veracity),
    "Relevância (R)": formatScore(p.relevance),
    "Prioridade (P)": formatScore(p.priority),
    "Válido desde": formatIso(p.valid_from),
    "Válido até": formatIso(p.valid_to),
    "Capturado em": formatIso(p.captured_at),
    "Recebido em": formatIso(p.received_at),
    "URL da foto": p.photo_url || EMPTY,
    "Acurácia GPS (m)":
      p.accuracy_m != null && p.accuracy_m !== ""
        ? `${Number(p.accuracy_m).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} m`
        : EMPTY,
    "Nonce de captura válido": boolPt(p.capture_nonce_valid),
    "Trechos afetados": affectedEdgesText(p.affected_edges),
  };

  const full = { ...system };
  for (const label of DER_LAYER_FIELD_LABELS) {
    full[label] = derMap.get(label) || EMPTY;
  }
  return full;
}

/** Linhas ordenadas para popup/PDF ({ label, value }). */
export function buildFullLayerRows(p, catalog) {
  const map = buildFullLayerPropertyMap(p, catalog);
  return FULL_LAYER_FIELD_LABELS.map((label) => ({
    label,
    value: map[label] ?? EMPTY,
  }));
}

export function splitLayerRowsForPopup(p, catalog) {
  const all = buildFullLayerRows(p, catalog);
  const systemCount = SYSTEM_LAYER_FIELD_LABELS.length;
  return {
    system: all.slice(0, systemCount),
    der: all.slice(systemCount),
  };
}

function pickRows(map, labels, { hideEmpty = false } = {}) {
  const rows = labels.map((label) => ({
    label,
    value: map[label] ?? EMPTY,
  }));
  if (!hideEmpty) return rows;
  return rows.filter((row) => row.value !== EMPTY);
}

/** Popup mapa público — subset de sistema + DER operacional (sem snap). */
export function splitPublicLayerRowsForPopup(p, catalog) {
  const map = buildFullLayerPropertyMap(p, catalog);
  return {
    system: pickRows(map, PUBLIC_SYSTEM_POPUP_FIELD_LABELS, { hideEmpty: true }),
    der: pickRows(map, PUBLIC_DER_POPUP_FIELD_LABELS, { hideEmpty: false }),
  };
}

/** Popup mapa gestão — pacote completo (36 campos). */
export function splitGestaoLayerRowsForPopup(p, catalog) {
  return splitLayerRowsForPopup(p, catalog);
}
