// Mapa público — camadas publicadas e resolvidas, dos dois grupos.
import { OSM_STYLE } from "./map-style.js";
import {
  downloadExportBatch,
  fetchCatalog,
  fetchIncidents,
  fetchManifestations,
} from "./api.js";
import {
  createMarkerElement,
  legendStatusSwatch,
  preloadEventIcons,
  resolveStatusColor,
  buildLegendSymbolsBlock,
} from "./gestao-markers.js";
import {
  bindPopupCloseControl,
  buildPublicMapPopupHtml,
} from "./gestao-map-popup.js";
import {
  bindRelatoriosCollapse,
  bindSidebarCollapse,
} from "./public-sidebar.js";
import { mountSidebarBrands } from "./sidebar-brand.js";

const map = new maplibregl.Map({
  container: "viewer-map",
  style: OSM_STYLE,
  center: [-46.63, -23.55],
  zoom: 6,
});
map.addControl(new maplibregl.NavigationControl(), "top-right");
map.addControl(
  new maplibregl.GeolocateControl({
    positionOptions: { enableHighAccuracy: true },
  }),
  "top-right",
);

/** @type {Record<string, maplibregl.Marker[]>} */
const categoryMarkers = {};
/** @type {Record<string, boolean>} */
const layerVisibility = {};
/** @type {string[]} */
let allLayerKeys = [];
let catalog = null;
let layerControlsBound = false;
let exportFormBound = false;
let sidebarToggleBound = false;

const PUBLIC_MAP_STATUSES = ["publicado", "resolvido"];

const EXPORT_GROUPS = [
  {
    id: "evento_trafego",
    title: "Eventos de tráfego",
    categoriesKey: "event_categories",
  },
  {
    id: "manifestacao",
    title: "Manifestação cidadã",
    categoriesKey: "manifestation_categories",
  },
];

function layerKey(typeId, catId) {
  const prefix = typeId === "evento_trafego" ? "evento" : "manifestacao";
  return `${prefix}:${catId}`;
}

function mapPublicFeatures(fc) {
  return fc.features || [];
}

/** @returns {Record<string, number>} */
function countsByCategory(fc) {
  const counts = {};
  for (const f of mapPublicFeatures(fc)) {
    const cat = f.properties?.category || "outro";
    counts[cat] = (counts[cat] || 0) + 1;
  }
  return counts;
}

function ensureLayerKeys() {
  if (!catalog) return;
  allLayerKeys = [];
  for (const c of catalog.event_categories || []) {
    allLayerKeys.push(layerKey("evento_trafego", c.id));
  }
  for (const c of catalog.manifestation_categories || []) {
    allLayerKeys.push(layerKey("manifestacao", c.id));
  }
  for (const k of allLayerKeys) {
    if (layerVisibility[k] === undefined) layerVisibility[k] = true;
  }
  if (layerVisibility.evento_trafego === undefined)
    layerVisibility.evento_trafego = true;
  if (layerVisibility.manifestacao === undefined)
    layerVisibility.manifestacao = true;
}

function totalCount(counts) {
  return Object.values(counts).reduce((sum, n) => sum + (n || 0), 0);
}

function renderLayerControls(eventCounts, manifCounts) {
  const layersEl = document.getElementById("viewer-layers");
  if (!layersEl || !catalog) return;

  ensureLayerKeys();

  const catLabel = (c, counts) => {
    const n = counts[c.id] || 0;
    return `
      <span class="public-layer-cat-name">${c.label}</span>
      <span class="public-layer-cat-count muted">${n}</span>`;
  };

  const groupLayers = (typeId, categories, counts, title) => {
    const total = totalCount(counts);
    const childrenId = `public-layer-children-${typeId}`;
    const cats = categories
      .map((c) => {
        const key = layerKey(typeId, c.id);
        const checked = layerVisibility[key] !== false ? "checked" : "";
        return `
        <label class="public-layer-cat">
          <input type="checkbox" data-layer="${key}" ${checked}/>
          ${catLabel(c, counts)}
        </label>`;
      })
      .join("");
    const groupChecked = layerVisibility[typeId] !== false ? "checked" : "";
    return `
      <div class="public-layer-group" data-group="${typeId}">
        <div class="public-layer-group-head">
          <label class="public-layer-group-check" title="${title}">
            <input type="checkbox" data-layer="${typeId}" ${groupChecked}/>
          </label>
          <button type="button" class="public-layer-group-toggle" aria-expanded="true" aria-controls="${childrenId}" aria-label="Recolher ${title}">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <span class="public-layer-group-title">${title}</span>
          <span class="public-layer-group-count muted">${total}</span>
        </div>
        <div class="public-layer-children" id="${childrenId}">${cats}</div>
      </div>`;
  };

  const eventCategories = catalog.event_categories || [];
  const manifCategories = catalog.manifestation_categories || [];
  layersEl.innerHTML =
    groupLayers(
      "evento_trafego",
      eventCategories,
      eventCounts,
      "Eventos de tráfego",
    ) +
    groupLayers(
      "manifestacao",
      manifCategories,
      manifCounts,
      "Manifestação cidadã",
    );

  if (!layerControlsBound) {
    layerControlsBound = true;
    layersEl.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".public-layer-group-toggle");
      if (!btn) return;
      const group = btn.closest(".public-layer-group");
      const body = group?.querySelector(".public-layer-children");
      if (!body) return;
      const collapsed = group.classList.toggle("collapsed");
      body.hidden = collapsed;
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      btn.setAttribute(
        "aria-label",
        collapsed ? `Expandir ${group.querySelector(".public-layer-group-title")?.textContent || "grupo"}` : `Recolher ${group.querySelector(".public-layer-group-title")?.textContent || "grupo"}`,
      );
    });
    layersEl.addEventListener("change", (ev) => {
      const input = ev.target;
      if (!(input instanceof HTMLInputElement) || !input.dataset.layer) return;
      const key = input.dataset.layer;
      layerVisibility[key] = input.checked;
      if (key === "evento_trafego" || key === "manifestacao") {
        const prefix = key === "evento_trafego" ? "evento" : "manifestacao";
        layersEl
          .querySelectorAll(`input[data-layer^="${prefix}:"]`)
          .forEach((child) => {
            if (!(child instanceof HTMLInputElement)) return;
            child.checked = input.checked;
            layerVisibility[child.dataset.layer] = input.checked;
            applyLayerVisibility(child.dataset.layer);
          });
      }
      applyLayerVisibility(key);
    });
  }
}

function exportLayerRef(typeId, catId) {
  return { interaction_type: typeId, category_id: catId };
}

function syncExportGroupState(exportsEl, groupId) {
  const boxes = exportsEl.querySelectorAll(
    `input[data-export-layer^="${groupId}:"]`,
  );
  const groupBox = exportsEl.querySelector(
    `input[data-export-all="${groupId}"]`,
  );
  if (!(groupBox instanceof HTMLInputElement) || !boxes.length) return;
  const checked = [...boxes].filter((b) => b.checked).length;
  groupBox.checked = checked === boxes.length;
  groupBox.indeterminate = checked > 0 && checked < boxes.length;
}

function syncExportGlobalState(exportsEl) {
  const globalBox = exportsEl.querySelector('input[data-export-all="global"]');
  if (!(globalBox instanceof HTMLInputElement)) return;
  const all = exportsEl.querySelectorAll("input[data-export-layer]");
  const checked = [...all].filter((b) => b.checked).length;
  globalBox.checked = checked === all.length && all.length > 0;
  globalBox.indeterminate = checked > 0 && checked < all.length;
}

function renderExportForm(eventCounts, manifCounts) {
  const exportsEl = document.getElementById("viewer-exports");
  if (!exportsEl || !catalog) return;

  const countsFor = (groupId) =>
    groupId === "evento_trafego" ? eventCounts : manifCounts;

  if (exportFormBound) {
    EXPORT_GROUPS.forEach((g) => {
      const counts = countsFor(g.id);
      for (const c of catalog[g.categoriesKey] || []) {
        const box = exportsEl.querySelector(
          `input[data-export-layer="${g.id}:${c.id}"]`,
        );
        const label = box?.closest("label")?.querySelector("span");
        if (label) {
          const n = counts[c.id] || 0;
          label.innerHTML = `${c.label} <span class="muted">(${n})</span>`;
        }
      }
    });
    return;
  }

  const groupBlocks = EXPORT_GROUPS.map((g) => {
    const categories = catalog[g.categoriesKey] || [];
    const counts = countsFor(g.id);
    const catRows = categories
      .map((c) => {
        const n = counts[c.id] || 0;
        return `
        <label class="public-export-cat">
          <input type="checkbox" data-export-layer="${g.id}:${c.id}"/>
          <span>${c.label} <span class="muted">(${n})</span></span>
        </label>`;
      })
      .join("");
    return `
      <div class="public-export-group-block" data-export-group="${g.id}">
        <label class="public-export-group-all">
          <input type="checkbox" data-export-all="${g.id}"/>
          <span>Todas — ${g.title}</span>
        </label>
        <div class="public-export-cats">${catRows}</div>
      </div>`;
  }).join("");

  exportsEl.innerHTML = `
    <form class="public-export-form" id="viewer-export-form">
      <fieldset class="public-export-format">
        <legend>Formato de saída</legend>
        <div class="public-export-format-options">
          <label><input type="radio" name="export-format" value="pdf" checked/> PDF</label>
          <label><input type="radio" name="export-format" value="csv"/> CSV</label>
          <label><input type="radio" name="export-format" value="zip"/> Shape (ZIP)</label>
        </div>
      </fieldset>
      <label class="public-export-global">
        <input type="checkbox" data-export-all="global"/>
        <span>Todas as camadas (todos os grupos)</span>
      </label>
      ${groupBlocks}
      <button type="submit" class="public-export-btn" id="export-download-btn">Baixar relatório</button>
      <p class="public-export-status muted" id="export-status" aria-live="polite"></p>
    </form>`;

  if (!exportFormBound) {
    exportFormBound = true;
    exportsEl.addEventListener("change", (ev) => {
      const input = ev.target;
      if (!(input instanceof HTMLInputElement)) return;

      if (input.dataset.exportAll === "global") {
        const on = input.checked;
        exportsEl
          .querySelectorAll("input[data-export-layer]")
          .forEach((box) => {
            if (box instanceof HTMLInputElement) box.checked = on;
          });
        EXPORT_GROUPS.forEach((g) => syncExportGroupState(exportsEl, g.id));
        return;
      }

      if (input.dataset.exportAll) {
        const groupId = input.dataset.exportAll;
        const on = input.checked;
        exportsEl
          .querySelectorAll(`input[data-export-layer^="${groupId}:"]`)
          .forEach((box) => {
            if (box instanceof HTMLInputElement) box.checked = on;
          });
        syncExportGlobalState(exportsEl);
        return;
      }

      if (input.dataset.exportLayer) {
        const [groupId] = input.dataset.exportLayer.split(":");
        syncExportGroupState(exportsEl, groupId);
        syncExportGlobalState(exportsEl);
      }
    });

    exportsEl.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      if (!(form instanceof HTMLFormElement)) return;
      const statusEl = document.getElementById("export-status");
      const btn = document.getElementById("export-download-btn");
      const formatInput = form.querySelector(
        'input[name="export-format"]:checked',
      );
      const format =
        formatInput instanceof HTMLInputElement ? formatInput.value : "pdf";
      const selected = [
        ...form.querySelectorAll("input[data-export-layer]:checked"),
      ]
        .map((el) => {
          const key =
            el instanceof HTMLInputElement ? el.dataset.exportLayer : "";
          const [typeId, catId] = (key || "").split(":");
          return typeId && catId ? exportLayerRef(typeId, catId) : null;
        })
        .filter(Boolean);

      if (!selected.length) {
        if (statusEl) statusEl.textContent = "Selecione ao menos uma camada.";
        return;
      }

      if (btn instanceof HTMLButtonElement) btn.disabled = true;
      if (statusEl) statusEl.textContent = "Gerando arquivo…";
      try {
        await downloadExportBatch({ format, layers: selected });
        if (statusEl) statusEl.textContent = "Download iniciado.";
      } catch (err) {
        if (statusEl)
          statusEl.textContent = err.message || "Falha na exportação.";
      } finally {
        if (btn instanceof HTMLButtonElement) btn.disabled = false;
      }
    });
  }
}

function applyLayerVisibility(key) {
  const visible = layerVisibility[key] !== false;
  if (key === "evento_trafego" || key === "manifestacao") {
    const prefix = key === "evento_trafego" ? "evento" : "manifestacao";
    allLayerKeys
      .filter((k) => k.startsWith(`${prefix}:`))
      .forEach((k) => {
        (categoryMarkers[k] || []).forEach((m) => {
          m.getElement().style.display =
            visible && layerVisibility[k] !== false ? "" : "none";
        });
      });
    return;
  }
  (categoryMarkers[key] || []).forEach((m) => {
    m.getElement().style.display = visible ? "" : "none";
  });
}

function clearAllMarkers() {
  for (const key of Object.keys(categoryMarkers)) {
    categoryMarkers[key].forEach((m) => m.remove());
    categoryMarkers[key] = [];
  }
}

function addMarkers(fc, interactionType) {
  for (const f of mapPublicFeatures(fc)) {
    const p = {
      ...f.properties,
      interaction_type: f.properties?.interaction_type || interactionType,
    };
    const [lon, lat] = f.geometry?.coordinates || [];
    if (lat == null || lon == null) continue;
    const prefix =
      interactionType === "manifestacao" ? "manifestacao" : "evento";
    const key = `${prefix}:${p.category || "outro"}`;
    if (!categoryMarkers[key]) categoryMarkers[key] = [];

    const el = createMarkerElement(p, catalog, { wrapForMaplibre: true });
    const popup = new maplibregl.Popup({
      offset: 20,
      closeButton: false,
      maxWidth: "none",
      className: "viewer-map-popup map-feature-popup public-map-popup",
    }).setHTML(buildPublicMapPopupHtml(p, catalog));
    popup.on("open", () => {
      bindPopupCloseControl(popup.getElement(), () => popup.remove());
    });

    const marker = new maplibregl.Marker({ element: el, anchor: "center" })
      .setLngLat([lon, lat])
      .setPopup(popup)
      .addTo(map);
    categoryMarkers[key].push(marker);
  }
}

function renderPublicLegend() {
  const el = document.getElementById("viewer-legend");
  if (!el || !catalog) return;

  const statuses = PUBLIC_MAP_STATUSES.map((id) => {
    const m = catalog.statuses?.[id];
    if (!m) return "";
    const color = resolveStatusColor({ status: id }, catalog);
    return `
      <div class="gestao-legend-row">
        ${legendStatusSwatch(color)}
        <div class="gestao-legend-copy">
          <strong>${m.label}</strong>
        </div>
      </div>`;
  }).join("");

  el.innerHTML = `
    <h3>Legenda</h3>
    ${buildLegendSymbolsBlock()}
    <div class="gestao-legend-list">${statuses}</div>
  `;
}

function bindSidebarToggle() {
  if (sidebarToggleBound) return;
  const btn = document.getElementById("toggle-sidebar");
  const sidebar = document.getElementById("public-sidebar");
  if (!btn || !sidebar) return;
  sidebarToggleBound = true;
  btn.addEventListener("click", () => {
    sidebar.classList.toggle("public-sidebar-collapsed");
    const collapsed = sidebar.classList.contains("public-sidebar-collapsed");
    document.body.classList.toggle("viewer-sidebar-collapsed", collapsed);
    btn.textContent = collapsed ? "»" : "«";
    btn.setAttribute(
      "aria-label",
      collapsed ? "Expandir menu lateral" : "Recolher menu lateral",
    );
    setTimeout(() => map.resize(), 280);
  });
}

mountSidebarBrands();

map.on("load", async () => {
  try {
    catalog = await fetchCatalog();
    await preloadEventIcons(catalog);
    bindSidebarCollapse("panel-mapa", { defaultExpanded: true });
    bindRelatoriosCollapse();
    bindSidebarToggle();
    renderLayerControls({}, {});
    renderExportForm({}, {});
    renderPublicLegend();
    await refresh();
    setInterval(refresh, 60_000);
  } catch (e) {
    console.error(e);
  }
});

async function refresh() {
  try {
    const [events, manif] = await Promise.all([
      fetchIncidents(),
      fetchManifestations(),
    ]);
    const eventCounts = countsByCategory(events);
    const manifCounts = countsByCategory(manif);
    renderLayerControls(eventCounts, manifCounts);
    renderExportForm(eventCounts, manifCounts);

    clearAllMarkers();
    addMarkers(events, "evento_trafego");
    addMarkers(manif, "manifestacao");
    allLayerKeys.forEach((k) => applyLayerVisibility(k));
  } catch (e) {
    console.error(e);
  }
}
