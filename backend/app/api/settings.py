from __future__ import annotations

import base64
import json
import os
import socket
import sqlite3
import tempfile
import zipfile
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__
from ..config import settings
from ..database import get_db
from ..models import Invoice
from ..services.ocr.preprocessing import available_languages
from ..services.storage import resolve_relative
from ..services.tulip import integration_status, probe_ui
from ..services.tulip.service import MISSING_INFORMATION

router = APIRouter(tags=["configuration et intégration"])


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    languages = available_languages()
    invoice_count = db.query(Invoice).count()
    return {
        "app": {
            "name": "Factures fournisseurs — Tulip",
            "version": __version__,
            "mode": settings.app_mode,
            "data_dir": str(settings.data_dir),
            "database": "SQLite locale" if settings.database_url.startswith("sqlite") else "base externe",
            "invoice_count": invoice_count,
        },
        "ocr": {
            "engine": settings.ocr_engine,
            "tesseract_available": "fra" in languages or "eng" in languages,
            "languages": languages,
            "configured_languages": settings.tesseract_langs,
            "psm": settings.ocr_psm,
            "render_dpi": settings.ocr_render_dpi,
            "note": (
                "L'OCR local Tesseract ne garantit pas une lecture parfaite. "
                "Toute donnée extraite doit être vérifiée par un utilisateur."
            ),
        },
        "llm": {
            "enabled": settings.llm_enabled and bool(settings.llm_api_key),
            "configured": bool(settings.llm_api_key),
            "model": settings.llm_model if settings.llm_api_key else None,
            "base_url": settings.llm_base_url if settings.llm_api_key else None,
            "data_transmitted": (
                "Texte OCR de la facture (sans image) vers le service configuré, "
                "uniquement si TULIP_LLM_ENABLED=true et qu'une clé est présente."
            ),
            "note": "Désactivé par défaut. Aucun document n'est transmis sans configuration explicite.",
        },
        "vision": {
            "enabled": settings.vision_enabled and bool(settings.vision_api_key),
            "provider": settings.vision_active_provider,
            "providers": {
                name: {
                    "configured": bool(os.getenv(f"TULIP_VISION_{name.upper()}_API_KEY")),
                    "model": os.getenv(f"TULIP_VISION_{name.upper()}_MODEL")
                    or {"gemini": "gemini-3.8-flash", "openai": "gpt-4o-mini", "groq": "openai/gpt-oss-120b"}.get(name),
                    "available": name in ("gemini", "openai", "groq"),
                }
                for name in VISION_PROVIDERS
            },
            "active_model": settings.vision_model if settings.vision_api_key else None,
            "active_base_url": settings.vision_base_url if settings.vision_api_key else None,
            "note": (
                "L'IA vision lit directement les images des pages (factures imprimées, photographiées"
                " ou manuscrites) : le moyen le plus fiable. Sans vision, l'app retombe sur OCR + IA texte."
            ),
        },
        "accounting": {
            "amount_tolerance": float(settings.amount_tolerance),
            "currency_default": "DZD",
        },
        "tulip": {**integration_status(), "missing_information": MISSING_INFORMATION},
    }


def _lan_addresses() -> list[str]:
    found: list[str] = []

    def _add(ip: str) -> None:
        if ip and ip not in found and not ip.startswith("127.") and not ip.startswith("169.254"):
            found.append(ip)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            _add(info[4][0])
    except OSError:
        pass
    for probe_host in ("8.8.8.8", "1.1.1.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe_host, 80))
            _add(sock.getsockname()[0])
        except OSError:
            pass
        finally:
            sock.close()

    def _rank(ip: str) -> int:
        if ip.startswith(("192.168.", "10.")):
            return 0
        octets = ip.split(".")
        if octets[0] == "172" and len(octets) > 1 and octets[1].isdigit() and 16 <= int(octets[1]) <= 31:
            return 0
        if ip.startswith("100."):
            return 2
        return 1

    return sorted(found, key=_rank)


def _tcp_reachable(ip: str, port: int) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=0.6):
            return True
    except OSError:
        return False


@router.get("/access")
def access_info(request: Request) -> dict[str, Any]:
    port = request.url.port or 8000
    candidates = []
    for ip in _lan_addresses():
        candidates.append(
            {
                "ip": ip,
                "url": f"http://{ip}:{port}",
                "reachable": _tcp_reachable(ip, port),
            }
        )
    primary = next((item for item in candidates if item["reachable"]), candidates[0] if candidates else None)
    return {
        "port": port,
        "primary_url": primary["url"] if primary else None,
        "primary_ip": primary["ip"] if primary else None,
        "candidates": candidates,
        "local_url": f"http://127.0.0.1:{port}",
        "hint": (
            "Le téléphone doit être connecté au même Wi-Fi que ce PC."
            if primary and primary["reachable"]
            else "Le serveur n'écoute pas sur le réseau : relancez-le avec --host 0.0.0.0."
        ),
    }


@router.get("/access/qr.svg")
def access_qr(url: str, scale: int = 6) -> Response:
    import io

    import segno

    target = (url or "").strip()
    if not target.startswith(("http://", "https://")) or len(target) > 300:
        raise HTTPException(status_code=400, detail="URL invalide pour le QR code.")
    qr = segno.make(target, error="m")
    buffer = io.BytesIO()
    qr.save(
        buffer,
        kind="svg",
        scale=max(2, min(scale, 16)),
        border=2,
        dark="#111827",
        light="#ffffff",
    )
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/tulip/status")
def tulip_status() -> dict[str, Any]:
    return integration_status()


class LlmSettingsUpdate(BaseModel):
    enabled: bool = True
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def _persist_env(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.is_file() else []
    remaining: list[str] = []
    seen: set[str] = set()
    for line in lines:
        name = line.split("=", 1)[0].strip()
        if name in values:
            if name in seen:
                continue
            remaining.append(f"{name}={values[name]}")
            seen.add(name)
        else:
            remaining.append(line)
    for name, value in values.items():
        if name not in seen:
            remaining.append(f"{name}={value}")
            seen.add(name)
    ENV_PATH.write_text("\n".join(remaining) + "\n", encoding="utf-8")


def _apply_llm_settings(payload: LlmSettingsUpdate) -> list[str]:
    import os

    values: dict[str, str] = {}
    if payload.api_key:
        settings.llm_api_key = payload.api_key
        os.environ["TULIP_LLM_API_KEY"] = payload.api_key
        values["TULIP_LLM_API_KEY"] = payload.api_key
    if payload.base_url and payload.base_url.strip():
        settings.llm_base_url = payload.base_url.strip()
        os.environ["TULIP_LLM_BASE_URL"] = payload.base_url.strip()
        values["TULIP_LLM_BASE_URL"] = payload.base_url.strip()
    if payload.model and payload.model.strip():
        settings.llm_model = payload.model.strip()
        os.environ["TULIP_LLM_MODEL"] = payload.model.strip()
        values["TULIP_LLM_MODEL"] = payload.model.strip()
    settings.llm_enabled = payload.enabled
    os.environ["TULIP_LLM_ENABLED"] = "true" if payload.enabled else "false"
    values["TULIP_LLM_ENABLED"] = "true" if payload.enabled else "false"
    if values:
        _persist_env(values)
    return sorted(values)


@router.put("/settings/llm")
def update_llm_settings(payload: LlmSettingsUpdate) -> dict[str, Any]:
    changed = _apply_llm_settings(payload)
    return {
        "message": "Configuration IA enregistrée (appliquée immédiatement).",
        "enabled": settings.llm_enabled and bool(settings.llm_api_key),
        "model": settings.llm_model if settings.llm_api_key else None,
        "base_url": settings.llm_base_url if settings.llm_api_key else None,
        "changed": changed,
    }


class VisionSettingsUpdate(BaseModel):
    enabled: bool = True
    provider: str | None = Field(description=None, default=None)
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


VISION_PROVIDERS = ("gemini", "openai", "groq")


def _apply_vision_settings(payload) -> list[str]:
    import os

    values: dict[str, str] = {}
    if payload.provider and payload.provider.strip().lower() in VISION_PROVIDERS:
        provider = payload.provider.strip().lower()
        settings.vision_active_provider = provider
        os.environ["TULIP_VISION_PROVIDER"] = provider
        values["TULIP_VISION_PROVIDER"] = provider
    if payload.api_key:
        import os

        provider = settings.vision_active_provider.upper()
        env_name = f"TULIP_VISION_{provider}_API_KEY"
        os.environ[env_name] = payload.api_key
        values[env_name] = payload.api_key
    if payload.base_url and payload.base_url.strip():
        import os

        env_name = f"TULIP_VISION_{settings.vision_active_provider.upper()}_BASE_URL"
        os.environ[env_name] = payload.base_url.strip()
        values[env_name] = payload.base_url.strip()
    if payload.model and payload.model.strip():
        import os

        env_name = f"TULIP_VISION_{settings.vision_active_provider.upper()}_MODEL"
        os.environ[env_name] = payload.model.strip()
        values[env_name] = payload.model.strip()
    settings.vision_enabled = payload.enabled
    os.environ["TULIP_VISION_ENABLED"] = "true" if payload.enabled else "false"
    values["TULIP_VISION_ENABLED"] = "true" if payload.enabled else "false"
    if values:
        _persist_env(values)
    return sorted(values)


@router.put("/settings/vision")
def update_vision_settings(payload: VisionSettingsUpdate) -> dict[str, Any]:
    changed = _apply_vision_settings(payload)
    return {
        "message": "Configuration IA vision enregistrée (appliquée immédiatement).",
        "enabled": settings.vision_enabled and bool(settings.vision_api_key),
        "model": settings.vision_model if settings.vision_api_key else None,
        "base_url": settings.vision_base_url if settings.vision_api_key else None,
        "changed": changed,
    }


class FirebirdSettingsUpdate(BaseModel):
    enabled: bool = False
    database: str | None = None
    host: str = "localhost"
    port: int = 3050
    user: str = "SYSDBA"
    password: str | None = None
    isql_path: str | None = None
    fb_home: str | None = None
    charset: str = "WIN1252"
    write_enabled: bool = False


def _apply_firebird_settings(payload: FirebirdSettingsUpdate) -> list[str]:
    import os

    values: dict[str, str] = {}

    settings.tulip_fb_enabled = payload.enabled
    os.environ["TULIP_FB_ENABLED"] = "true" if payload.enabled else "false"
    values["TULIP_FB_ENABLED"] = "true" if payload.enabled else "false"

    if payload.database and payload.database.strip():
        settings.tulip_fb_database = payload.database.strip()
        os.environ["TULIP_FB_DATABASE"] = payload.database.strip()
        values["TULIP_FB_DATABASE"] = payload.database.strip()

    settings.tulip_fb_host = payload.host
    os.environ["TULIP_FB_HOST"] = payload.host
    values["TULIP_FB_HOST"] = payload.host

    settings.tulip_fb_port = payload.port
    os.environ["TULIP_FB_PORT"] = str(payload.port)
    values["TULIP_FB_PORT"] = str(payload.port)

    settings.tulip_fb_user = payload.user
    os.environ["TULIP_FB_USER"] = payload.user
    values["TULIP_FB_USER"] = payload.user

    if payload.password is not None:
        settings.tulip_fb_password = payload.password
        os.environ["TULIP_FB_PASSWORD"] = payload.password
        values["TULIP_FB_PASSWORD"] = payload.password

    if payload.isql_path and payload.isql_path.strip():
        settings.tulip_fb_isql_path = payload.isql_path.strip()
        os.environ["TULIP_FB_ISQL_PATH"] = payload.isql_path.strip()
        values["TULIP_FB_ISQL_PATH"] = payload.isql_path.strip()

    if payload.fb_home and payload.fb_home.strip():
        settings.tulip_fb_home = payload.fb_home.strip()
        os.environ["TULIP_FB_HOME"] = payload.fb_home.strip()
        values["TULIP_FB_HOME"] = payload.fb_home.strip()

    settings.tulip_fb_charset = payload.charset
    os.environ["TULIP_FB_CHARSET"] = payload.charset
    values["TULIP_FB_CHARSET"] = payload.charset

    settings.tulip_fb_write_enabled = payload.write_enabled
    os.environ["TULIP_FB_WRITE_ENABLED"] = "true" if payload.write_enabled else "false"
    values["TULIP_FB_WRITE_ENABLED"] = "true" if payload.write_enabled else "false"

    if values:
        _persist_env(values)
    return sorted(values)


@router.put("/settings/firebird")
def update_firebird_settings(payload: FirebirdSettingsUpdate) -> dict[str, Any]:
    changed = _apply_firebird_settings(payload)
    return {
        "message": "Configuration Firebird enregistrée (appliquée immédiatement).",
        "enabled": settings.tulip_fb_enabled,
        "database": settings.tulip_fb_database,
        "changed": changed,
    }


@router.get("/settings/firebird")
def get_firebird_settings() -> dict[str, Any]:
    return {
        "enabled": settings.tulip_fb_enabled,
        "database": settings.tulip_fb_database,
        "host": settings.tulip_fb_host,
        "port": settings.tulip_fb_port,
        "user": settings.tulip_fb_user,
        "isql_path": settings.tulip_fb_isql_path,
        "fb_home": settings.tulip_fb_home,
        "charset": settings.tulip_fb_charset,
        "write_enabled": settings.tulip_fb_write_enabled,
    }


@router.post("/settings/vision/test")
def test_vision_settings() -> dict[str, Any]:
    if not (settings.vision_enabled and settings.vision_api_key and settings.vision_model):
        raise HTTPException(status_code=400, detail="L'IA vision n'est pas configurée (clé ou modèle manquant).")
    url = settings.vision_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.vision_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": 'Réponds uniquement par un objet JSON {"status":"ok"}.'},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Test de connexion vision."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + base64.b64encode(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000"
                                                            "001f15c4890000000d49444154789c6300010000050001"
                                                            "0d0a2db40000000049454e44ae426082")).decode("ascii")
                        },
                    },
                ],
            },
        ],
    }
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(url, headers={"Authorization": f"Bearer {settings.vision_api_key}"}, json=payload)
        response.raise_for_status()
        body = response.json()
        answer = str(body["choices"][0]["message"]["content"])[:120]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Test vision échoué : {type(exc).__name__} — {exc}") from exc
    return {"ok": True, "model": settings.vision_model, "base_url": settings.vision_base_url, "answer": answer}


@router.post("/settings/llm/test")
def test_llm_settings() -> dict[str, Any]:
    if not (settings.llm_enabled and settings.llm_api_key and settings.llm_model):
        raise HTTPException(status_code=400, detail="L'IA n'est pas configurée (clé ou modèle manquant).")
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "Réponds uniquement par un objet JSON {\"status\": \"ok\"}."},
                        {"role": "user", "content": "Test de connexion."},
                    ],
                },
            )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Test IA échoué : {type(exc).__name__} — {exc}") from exc
    return {"ok": True, "model": settings.llm_model, "base_url": settings.llm_base_url, "answer": str(content)[:120]}


@router.post("/tulip/probe")
def tulip_probe() -> dict[str, Any]:
    return probe_ui()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
    ocr_languages = available_languages()
    storage_ok = True
    try:
        probe = settings.data_dir / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception:
        storage_ok = False
    return {
        "status": "ok" if database_ok and storage_ok else "degraded",
        "version": __version__,
        "database": database_ok,
        "storage": storage_ok,
        "ocr": {"available": bool(ocr_languages), "languages": ocr_languages},
    }


@router.post("/maintenance/backup")
def create_backup(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not settings.database_url.startswith("sqlite"):
        raise HTTPException(
            status_code=400,
            detail="La sauvegarde intégrée ne prend en charge que la base SQLite locale. Sauvegardez votre base externe séparément.",
        )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_path = settings.backups_dir / f"sauvegarde-{settings.app_mode}-{timestamp}.zip"
    database_path = Path(settings.database_url.split("sqlite:///", 1)[1])

    with tempfile.TemporaryDirectory() as temp_dir:
        db_copy = Path(temp_dir) / "tulip_factures.db"
        source = sqlite3.connect(str(database_path))
        destination = sqlite3.connect(str(db_copy))
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        invoice_count = db.query(Invoice).count()
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": settings.app_mode,
            "version": __version__,
            "invoice_count": invoice_count,
            "contents": ["tulip_factures.db", "documents/", "pages/", "exports/"],
            "restore_note": (
                "Restauration manuelle : arrêtez l'application, sauvegardez les données actuelles, "
                "puis remplacez la base et les dossiers par le contenu de cette archive."
            ),
        }
        (Path(temp_dir) / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_copy, "tulip_factures.db")
            archive.write(Path(temp_dir) / "manifest.json", "manifest.json")
            for folder, name in (
                (settings.documents_dir, "documents"),
                (settings.pages_dir, "pages"),
                (settings.exports_dir, "exports"),
            ):
                for path in folder.rglob("*"):
                    if path.is_file():
                        archive.write(path, f"{name}/{path.relative_to(folder).as_posix()}")

    size = archive_path.stat().st_size
    return {
        "message": "Sauvegarde créée.",
        "filename": archive_path.name,
        "size": size,
        "created_at": timestamp,
        "download_url": f"/api/maintenance/backups/{archive_path.name}/download",
    }


@router.get("/maintenance/backups/{filename}/download")
def download_backup(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nom de sauvegarde invalide.")
    try:
        path = resolve_relative(f"backups/{filename}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Nom de sauvegarde invalide.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable.")
    return FileResponse(path, media_type="application/zip", filename=filename)
