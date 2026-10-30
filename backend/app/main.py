from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import api_router
from .config import settings
from .database import init_db
from .services.worker import requeue_unfinished, start_worker


def configure_logging() -> None:
    log_file = settings.logs_dir / "application.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    if not any(isinstance(existing, logging.FileHandler) for existing in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    init_db()
    start_worker()
    requeue_unfinished()
    yield


app = FastAPI(
    title="Factures fournisseurs — Tulip Gestion commerciale",
    version=__version__,
    description=(
        "Application locale de scan, OCR, extraction, contrôle et préparation des factures fournisseurs. "
        "L'intégration Tulip n'est pas confirmée et aucune écriture n'est effectuée dans Tulip."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

static_dir = Path(settings.static_dir)
if (static_dir / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def root():
    index = static_dir / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "message": "API démarrée. Le frontend n'est pas compilé.",
        "frontend_dev": "npm run dev dans le dossier frontend",
        "frontend_build": "npm run build dans le dossier frontend",
        "docs": "/docs",
    }


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Ressource API introuvable.")
    candidate = (static_dir / full_path).resolve()
    if static_dir.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    index = static_dir / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend non compilé.")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
