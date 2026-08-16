"""Aplicação FastAPI raiz: serve API, mídia e a PWA estática."""
from __future__ import annotations

import asyncio
import logging
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.responses import Response

from .config import settings
from .database import init_db
from .routes.auth import router as auth_router
from .routes.export import router as export_router
from .routes.health import router as health_router
from .routes.moderation import router as moderation_router
from .routes.public_api import router as public_api_router
from .routes.reports import router as reports_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
GESTAO_DIR = FRONTEND_DIR / "gestao"
_HTML_NO_CACHE = {"Cache-Control": "no-cache"}

logger = logging.getLogger("pli_reporta.maintenance")


async def _maintenance_loop() -> None:
    """Roda o ciclo de vida automático dos eventos em segundo plano."""
    from .services.maintenance import run_maintenance

    interval = max(60, settings.maintenance_interval_seconds)
    while True:
        try:
            result = await asyncio.to_thread(run_maintenance)
            if result.get("expired") or result.get("closed_clusters"):
                logger.info("manutenção: %s", result)
        except Exception:  # noqa: BLE001 - loop não pode morrer
            logger.exception("falha no ciclo de manutenção")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from .database import engine

    init_db()
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(_maintenance_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Reportes viários colaborativos georreferenciados, com pipeline de veracidade e relevância.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") and (
        path.endswith(".js") or path.endswith(".css")
    ):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif path.startswith("/gestao"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# ---------------------------------------------------------------------------
# Suporte a sub-rota (subpath) atras do Nginx do SIGMA:
#   http://<IP>/pli-reporta/...  -> Nginx faz strip do prefixo e envia
#   X-Forwarded-Prefix: /pli-reporta. Este middleware reescreve as URLs
#   absolutas ("/static", "/api", "/media", ...) no HTML e no JSON e injeta
#   um shim que prefixa fetch()/serviceWorker.register no cliente.
#
#   Tambem reconhece /pli-reporta diretamente para manter a mesma URL
#   quando a aplicacao roda localmente sem Nginx.
# ---------------------------------------------------------------------------
_ABS_ATTR_RE = re.compile(r'((?:src|href|action)=")/(?!/)')


def _subpath_client_shim(prefix: str) -> str:
    p = json.dumps(prefix)
    return (
        "<script>(function(){var P=" + p + ";if(!P)return;"
        "window.__BASE_PATH__=P;"
        "function n(x){return x.charAt(0)===\"/\"&&x.indexOf(P+\"/\")!==0&&"
        "(x.indexOf(\"/api\")===0||x.indexOf(\"/media/\")===0||x.indexOf(\"/static/\")===0);}"
        "function r(u){try{if(typeof u===\"string\"){return n(u)?P+u:u;}"
        "if(u instanceof URL){return (u.origin===location.origin&&n(u.pathname))?"
        "new URL(P+u.pathname+u.search+u.hash,location.origin):u;}"
        "if(typeof Request!==\"undefined\"&&u instanceof Request){var q=new URL(u.url);"
        "return (q.origin===location.origin&&n(q.pathname))?"
        "new Request(P+q.pathname+q.search+q.hash,u):u;}}catch(e){}return u;}"
        "var f=window.fetch;window.fetch=function(i,o){return f.call(this,r(i),o);};"
        "if(navigator.serviceWorker&&navigator.serviceWorker.register){"
        "var g=navigator.serviceWorker.register.bind(navigator.serviceWorker);"
        "navigator.serviceWorker.register=function(u,o){o=o||{};"
        "if(o.scope==null)o.scope=P+\"/\";return g(r(u),o);};}"
        "})();</script>"
    )


@app.middleware("http")
async def subpath_rewrite(request, call_next):
    prefix = (request.headers.get("x-forwarded-prefix") or "").rstrip("/")
    direct_prefix = "/pli-reporta"
    path = request.scope.get("path", "")
    if not prefix and (path == direct_prefix or path.startswith(direct_prefix + "/")):
        prefix = direct_prefix
        stripped_path = path[len(direct_prefix) :] or "/"
        request.scope["path"] = stripped_path
        request.scope["raw_path"] = stripped_path.encode("utf-8")
    response = await call_next(request)
    if not prefix:
        return response
    ctype = response.headers.get("content-type", "")
    is_html = ctype.startswith("text/html")
    is_jsonish = ctype.startswith("application/json") or ctype.startswith("application/manifest")
    if not (is_html or is_jsonish):
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
    text = body.decode("utf-8", "replace")

    if is_html:
        text = _ABS_ATTR_RE.sub(lambda m: m.group(1) + prefix + "/", text)
        shim = _subpath_client_shim(prefix)
        lower = text.lower()
        idx = lower.find("<head")
        if idx != -1:
            gt = text.find(">", idx)
            if gt != -1:
                text = text[: gt + 1] + shim + text[gt + 1:]
            else:
                text = shim + text
        else:
            text = shim + text
    else:
        for needle in ('"/static/', '"/media/', '"/api/'):
            text = text.replace(needle, '"' + prefix + needle[1:])
        for key in ("start_url", "scope"):
            text = text.replace(
                '"' + key + '": "/"', '"' + key + '": "' + prefix + '/"'
            ).replace(
                '"' + key + '":"/"', '"' + key + '":"' + prefix + '/"'
            )

    new_body = text.encode("utf-8")
    headers = MutableHeaders(raw=list(response.raw_headers))
    headers["content-length"] = str(len(new_body))
    return Response(
        content=new_body,
        status_code=response.status_code,
        headers=dict(headers),
        media_type=ctype.split(";")[0] or None,
    )


# API (mapa público: catalog + export)
app.include_router(reports_router, prefix="/api", tags=["reports"])
app.include_router(public_api_router, prefix="/api/public", tags=["public-api"])
app.include_router(export_router, prefix="/api", tags=["export"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(moderation_router, prefix="/api", tags=["moderation"])
app.include_router(health_router, tags=["health"])

# Mídia (fotos publicadas)
app.mount("/media", StaticFiles(directory=str(settings.photo_dir)), name="media")

# Frontend estático (PWA)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend-static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html", headers=_HTML_NO_CACHE)


@app.get("/mapa", include_in_schema=False)
def mapa():
    return FileResponse(FRONTEND_DIR / "viewer.html", headers=_HTML_NO_CACHE)


@app.get("/api-publica", include_in_schema=False)
def api_publica_page():
    return FileResponse(FRONTEND_DIR / "api-publica.html", headers=_HTML_NO_CACHE)


@app.get("/acesso", include_in_schema=False)
def acesso():
    return FileResponse(FRONTEND_DIR / "acesso.html", headers=_HTML_NO_CACHE)


@app.get("/gestao", include_in_schema=False)
def gestao_dashboard():
    return FileResponse(GESTAO_DIR / "index.html", headers=_HTML_NO_CACHE)


@app.get("/gestao/eventos", include_in_schema=False)
def gestao_eventos():
    return FileResponse(GESTAO_DIR / "eventos.html", headers=_HTML_NO_CACHE)


@app.get("/gestao/manifestacoes", include_in_schema=False)
def gestao_manifestacoes():
    return FileResponse(GESTAO_DIR / "manifestacoes.html", headers=_HTML_NO_CACHE)


@app.get("/gestao/aprovador", include_in_schema=False)
def gestao_aprovador():
    return FileResponse(GESTAO_DIR / "aprovador.html", headers=_HTML_NO_CACHE)


@app.get("/gestao/funcionalidades", include_in_schema=False)
def gestao_funcionalidades():
    return FileResponse(GESTAO_DIR / "funcionalidades.html", headers=_HTML_NO_CACHE)


@app.get("/moderar", include_in_schema=False)
def moderar_redirect():
    return RedirectResponse(url="/acesso", status_code=301)


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def sw():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    p = FRONTEND_DIR / "favicon.ico"
    if p.exists():
        return FileResponse(p)
    return RedirectResponse(url="/static/icons/icon-192.png", status_code=302)
