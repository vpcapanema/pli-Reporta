#!/usr/bin/env node
/** Audita páginas públicas: scripts, botões e handlers esperados. */
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = path.resolve(import.meta.dirname, "..");
const frontend = path.join(root, "frontend");

const PAGES = [
  {
    route: "/",
    file: "index.html",
    script: "js/app.js",
    buttons: [
      "branch-evento",
      "branch-manifestacao",
      "btn-back-0",
      "btn-step1-evento",
      "btn-back-0b",
      "btn-toggle-photo",
      "btn-step1-manifestacao",
      "btn-back",
      "btn-shoot",
      "btn-submit",
      "btn-new",
    ],
    handlers: [
      ["js/app.js", "branch-evento"],
      ["js/app.js", "branch-manifestacao"],
      ["js/app.js", "btn-back-0"],
      ["js/app.js", "btn-step1-evento"],
      ["js/app.js", "btn-back-0b"],
      ["js/app.js", "btn-toggle-photo"],
      ["js/app.js", "btn-step1-manifestacao"],
      ["js/app.js", "btn-back"],
      ["js/app.js", "btn-shoot"],
      ["js/app.js", "btn-submit"],
      ["js/app.js", "btn-new"],
      ["js/app.js", "fallback-input"],
      ["js/app.js", "function openCameraStep"],
      ["js/app.js", "function bindUI"],
    ],
    deps: [
      "js/db.js",
      "js/api.js",
      "js/camera.js",
      "js/map-pick.js",
      "js/map-style.js",
    ],
  },
  {
    route: "/mapa",
    file: "viewer.html",
    script: "js/viewer.js",
    buttons: ["layer-events", "layer-manif"],
    handlers: [
      ["js/viewer.js", "layer-events"],
      ["js/viewer.js", "layer-manif"],
      ["js/viewer.js", "buildPublicMapPopupHtml"],
    ],
    deps: ["js/map-style.js", "js/api.js"],
  },
  {
    route: "/acesso",
    file: "acesso.html",
    script: "js/access-login.js",
    buttons: ["login-toggle-pw"],
    handlers: [
      ["js/access-login.js", "login-toggle-pw"],
      ["js/access-login.js", "login-form"],
      ["js/access-login.js", "bindPasswordToggle"],
    ],
    deps: ["js/api.js"],
  },
];

function read(rel) {
  return fs.readFileSync(path.join(frontend, rel), "utf8");
}

function syntaxOk(rel) {
  const abs = path.join(frontend, rel);
  const r = spawnSync("node", ["--check", abs], { encoding: "utf8" });
  return r.status === 0
    ? null
    : (r.stderr || r.stdout || "syntax error").trim();
}

const issues = [];

for (const page of PAGES) {
  const html = read(page.file);
  const title = `${page.route} (${page.file})`;

  if (!html.includes(page.script)) {
    issues.push(`${title}: script ${page.script} não referenciado no HTML`);
  }

  for (const id of page.buttons) {
    if (!html.includes(`id="${id}"`)) {
      issues.push(`${title}: botão #${id} ausente no HTML`);
    }
  }

  for (const [jsRel, needle] of page.handlers) {
    const js = read(jsRel);
    if (!js.includes(needle)) {
      issues.push(`${title}: handler "${needle}" não encontrado em ${jsRel}`);
    }
  }

  for (const dep of [page.script, ...page.deps]) {
    const err = syntaxOk(dep);
    if (err)
      issues.push(`${title}: erro de sintaxe em ${dep}: ${err.split("\n")[0]}`);
  }
}

// Páginas estáticas extras em /static/
for (const extra of [
  "traffic-icons-preview.html",
  "traffic-icons-guide.html",
]) {
  const abs = path.join(frontend, extra);
  if (!fs.existsSync(abs)) continue;
  const html = fs.readFileSync(abs, "utf8");
  const buttons = [...html.matchAll(/<button[^>]*id="([^"]+)"/g)].map(
    (m) => m[1],
  );
  if (buttons.length) {
    issues.push(
      `/static/${extra}: botões com id (${buttons.join(", ")}) sem script associado — revisar manualmente`,
    );
  }
}

if (issues.length) {
  console.error("FALHAS:");
  for (const i of issues) console.error(" -", i);
  process.exit(1);
}

console.log("OK: todas as páginas públicas auditadas");
for (const page of PAGES) {
  console.log(
    `  ${page.route}: ${page.buttons.length} botões, script ${page.script}`,
  );
}
