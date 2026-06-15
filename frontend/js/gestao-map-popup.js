/** HTML dos popups do mapa (gestão e público). */
import { categoryLabel, escHtml, formatDate, statusLabel } from "./gestao-common.js";
import { resolveStatusColor } from "./gestao-markers.js";
import {
  splitGestaoLayerRowsForPopup,
  splitPublicLayerRowsForPopup,
} from "./layer-popup-fields.js";

function kvRowsHtml(rows, prefix = "gestao-map-popup") {
  const items = rows
    .map(
      ({ label, value }) => `
    <div class="${prefix}-kv-row">
      <dt>${escHtml(label)}</dt>
      <dd>${escHtml(value)}</dd>
    </div>`,
    )
    .join("");
  return `<dl class="${prefix}-kv">${items}</dl>`;
}

function layerFieldsSection(title, rows, prefix) {
  if (!rows.length) return "";
  return `
    <section class="gestao-map-popup-section map-popup-fields-section">
      <h4>${escHtml(title)}</h4>
      ${kvRowsHtml(rows, prefix)}
    </section>`;
}

const PUBLIC_STATUS_INFO = {
  publicado: {
    headline: "Situação ativa",
    detail:
      "Evento confirmado e exibido neste mapa. A autoridade responsável foi informada.",
  },
  resolvido: {
    headline: "Situação encerrada",
    detail:
      "Este registro foi encerrado pela autoridade competente e permanece aqui como histórico.",
  },
};

function publicStatusBlock(p, catalog) {
  const statusId = p.status || "publicado";
  const meta = catalog?.statuses?.[statusId] || {};
  const copy = PUBLIC_STATUS_INFO[statusId] || {
    headline: statusLabel(statusId, catalog),
    detail: meta.descricao || "Informação publicada pelo PLI Reporta.",
  };
  const color = resolveStatusColor(p, catalog);
  const bg = statusId === "resolvido" ? "#faf5ff" : "#f0fdf4";
  return `
    <section class="public-map-popup-status" style="--status-color:${escHtml(color)};background:${bg}">
      <strong>${escHtml(copy.headline)}</strong>
      <p>${escHtml(copy.detail)}</p>
    </section>`;
}

function photoBlock(p) {
  if (!p.photo_url) return "";
  return `<img src="${escHtml(p.photo_url)}" alt="Foto do registro" class="gestao-map-popup-photo" loading="lazy"/>`;
}

function layerTypeLabel(p) {
  return p.interaction_type === "manifestacao"
    ? "Manifestação cidadã"
    : "Evento de tráfego";
}

/** Cabeçalho superior: [camada] do tipo [categoria], cor do ícone por status. */
function popupLocationHeader(p, catalog) {
  const catLabel = categoryLabel(p.category, catalog);
  const typeLabel = layerTypeLabel(p);
  const title = `${typeLabel} do tipo ${catLabel}`;
  const statusColor = resolveStatusColor(p, catalog);
  return `
    <div class="map-popup-location" style="background-color:${escHtml(statusColor)}">
      <p class="map-popup-location-title">${escHtml(title)}</p>
      <button type="button" class="map-popup-close" aria-label="Fechar">×</button>
    </div>`;
}

const SECTION_CADASTRO = "Informações de Cadastro";
const SECTION_RODOVIARIO = "Informações Rodoviários";

/** Liga o botão fechar embutido no cabeçalho (MapLibre ou Leaflet). */
export function bindPopupCloseControl(root, closeFn) {
  if (!root || typeof closeFn !== "function") return;
  root.querySelector(".map-popup-close")?.addEventListener(
    "click",
    (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      closeFn();
    },
    { once: true },
  );
}

/** Popup do mapa público — informativo para o cidadão (sem ações de moderação). */
export function buildPublicMapPopupHtml(p, catalog) {
  const isManif = p.interaction_type === "manifestacao";
  const { system, der } = splitPublicLayerRowsForPopup(p, catalog);
  const roadTitle = isManif ? "Contexto local" : SECTION_RODOVIARIO;

  return `
    <div class="gestao-map-popup-inner public-map-popup-inner">
      ${popupLocationHeader(p, catalog)}
      <div class="map-popup-body">
        ${publicStatusBlock(p, catalog)}
        ${layerFieldsSection(SECTION_CADASTRO, system, "public-map-popup")}
        ${isManif ? "" : layerFieldsSection(roadTitle, der, "public-map-popup")}
        ${photoBlock(p)}
        <footer class="gestao-map-popup-foot muted">
          <span>Consultado em ${escHtml(formatDate(new Date().toISOString()))}</span>
        </footer>
      </div>
    </div>`;
}

/** Popup do mapa de gestão — pacote completo (36 campos). */
export function buildGestaoPopupHtml(p, catalog) {
  const isManif = p.interaction_type === "manifestacao";
  const { system, der } = splitGestaoLayerRowsForPopup(p, catalog);
  const roadTitle = isManif ? "Contexto local" : SECTION_RODOVIARIO;

  return `
    <div class="gestao-map-popup-inner">
      ${popupLocationHeader(p, catalog)}
      <div class="map-popup-body">
        ${layerFieldsSection(SECTION_CADASTRO, system, "gestao-map-popup")}
        ${layerFieldsSection(roadTitle, der, "gestao-map-popup")}
        ${photoBlock(p)}
        <footer class="gestao-map-popup-foot muted">
          <span>${formatDate(p.received_at || p.captured_at)}</span>
          <code title="${escHtml(p.id)}">${escHtml(p.id)}</code>
        </footer>
      </div>
    </div>`;
}
