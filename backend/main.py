"""Aplicação FastAPI raiz: serve API, mídia e a PWA estática."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routes import health, moderation, reports

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    yield


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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# API
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])
app.include_router(moderation.router, prefix="/api/v1", tags=["moderation"])
app.include_router(health.router, tags=["health"])

# Mídia (fotos publicadas)
app.mount("/media", StaticFiles(directory=str(settings.photo_dir)), name="media")

# Frontend estático (PWA)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend-static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/mapa", include_in_schema=False)
def mapa():
    return FileResponse(FRONTEND_DIR / "viewer.html")


@app.get("/moderar", include_in_schema=False)
def moderar():
    return FileResponse(FRONTEND_DIR / "moderation.html")


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
