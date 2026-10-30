"""Relecture ciblée d'une zone de la page quand le libellé d'une ligne est illisible.

Tesseract en mode page entière rate parfois un mot isolé (souvent le début du libellé).
On recadre la zone du libellé et on relit uniquement cette bande, ce qui suffit
généralement à récupérer le nom du produit — toujours en local, sans appel réseau.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytesseract
from PIL import Image

from ...config import settings
from ..ocr.preprocessing import configure_tesseract

PLACEHOLDERS = {"", "article à compléter", "article a completer"}


def recover_designation(image_path: Path, bbox: dict[str, float] | None) -> str | None:
    if not bbox:
        return None
    try:
        configure_tesseract()
        image = Image.open(image_path)
        width, height = image.size
        left = max(0, int(float(bbox.get("x0", 0.0)) * width) - 6)
        top = max(0, int(float(bbox.get("y0", 0.0)) * height) - 6)
        right = min(width, int(float(bbox.get("x1", 1.0)) * width) + 6)
        bottom = min(height, int(float(bbox.get("y1", 1.0)) * height) + 6)
        if right - left < 20 or bottom - top < 8:
            return None
        crop = image.crop((left, top, right, bottom))
        scale = max(1, int(1200 / max(1, crop.width)))
        if scale > 1:
            crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(
            crop,
            lang=settings.tesseract_langs,
            config="--oem 1 --psm 6",
        )
    except Exception:
        return None
    cleaned = re.sub(r"\s+", " ", text or "").strip(" -:;|.")
    cleaned = _designation_only(cleaned)
    if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", cleaned)) < 2:
        return None
    return cleaned[:255]


def _designation_only(text: str) -> str:
    """Coupe le libellé dès que commencent le colisage et les montants."""
    tokens = text.split()
    for index, token in enumerate(tokens):
        if re.search(r"[xX]", token) and re.search(r"\d", token):
            tokens = tokens[:index]
            break
        if re.fullmatch(r"[+\-]?\d+[.,]\d{2,3}", token):
            tokens = tokens[:index]
            break
        if re.fullmatch(r"[+\-]?\d+", token):
            following = tokens[index + 1 : index + 3]
            if following and all(re.fullmatch(r"[+\-]?\d+[.,]?\d*", item) for item in following):
                tokens = tokens[:index]
                break
    return " ".join(tokens).strip(" -:;|.")
