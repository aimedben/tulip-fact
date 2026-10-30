from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from pathlib import Path

from ..config import settings

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._()\- ]+")
_MAGIC = {
    b"%PDF": ".pdf",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
}


class StorageError(ValueError):
    pass


def sanitize_filename(name: str | None, fallback: str = "facture") -> str:
    if not name:
        return fallback
    name = unicodedata.normalize("NFKC", name)
    name = name.replace("\\", "/").split("/")[-1]
    name = _SAFE_CHARS.sub("_", name).strip(" ._-")
    if not name:
        return fallback
    if len(name) > 180:
        stem = Path(name).stem[:120]
        suffix = Path(name).suffix[:10]
        name = f"{stem}{suffix}"
    return name


def sniff_extension(path: Path) -> str | None:
    with path.open("rb") as handle:
        head = handle.read(16)
    for magic, extension in _MAGIC.items():
        if head.startswith(magic):
            return extension
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def store_document(temp_path: Path, invoice_uuid: str, extension: str) -> str:
    destination_dir = settings.documents_dir / invoice_uuid[:2]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{invoice_uuid}{extension}"
    shutil.copy2(temp_path, destination)
    return destination.relative_to(settings.data_dir).as_posix()


def pages_dir_for(invoice_uuid: str) -> Path:
    directory = settings.pages_dir / invoice_uuid
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def pages_prefix_for(invoice_uuid: str) -> str:
    return f"pages/{invoice_uuid}"


def resolve_relative(relative_path: str) -> Path:
    base = settings.data_dir.resolve()
    candidate = (base / relative_path).resolve()
    if base != candidate and base not in candidate.parents:
        raise StorageError("Chemin de fichier non autorisé.")
    return candidate


def delete_invoice_files(invoice_uuid: str) -> None:
    for relative in (f"pages/{invoice_uuid}",):
        try:
            path = resolve_relative(relative)
        except StorageError:
            continue
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
