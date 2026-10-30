from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from ...config import settings
from .llm import LlmInvoice

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 600
_cooldown_until = 0.0
_cooldown_reason = ""


def _start_cooldown(status_code: int) -> None:
    global _cooldown_until, _cooldown_reason
    _cooldown_until = time.time() + _COOLDOWN_SECONDS
    _cooldown_reason = (
        f"Quota/clé vision indisponible (HTTP {status_code}) : "
        "IA vision ignorée pendant 10 minutes, OCR seul utilisé."
    )
    logger.warning(_cooldown_reason)


def cooldown_status() -> tuple[bool, str]:
    remaining = int(max(0, _cooldown_until - time.time()))
    return remaining > 0, _cooldown_reason if remaining > 0 else ""

SYSTEM_PROMPT = (
    "Tu es un lecteur de factures fournisseurs algériennes. Tu lis les images des pages"
    " (imprimées, photographiées, parfois manuscrites) et tu extrais les données factuelles."
    " Tu ne dois jamais inventer une valeur absente : utilise null pour tout champ inconnu."
    " Ne confonds jamais 1/l/I, 0/O, 5/S, 8/B, 6/G. Relis chaque total deux fois."
    " Réponds uniquement avec un objet JSON valide respectant le schéma demandé."
)

SCHEMA_PROMPT = """Lis la/les image(s) de cette facture et extrais TOUS les champs.
RÈGLES DE LECTURE DES COLONNES (tableaux à la Tulip' style supermarché) :
- « Produit » : designation + éventuellement contenance (ex. « Delicia 480 gr ») et le format de vente à la fin (ex. « 4X1 », « 6X1 ») = colisage, PAS une quantité.
- « Qnt » : la quantité facturée, écrite « A XY » (ex. « 4X1 », « 2,996X1 », « 4.043X1 »). La quantité = le PREMIER nombre, lu avec le point ou la virgule comme SÉPARATEUR DÉCIMAL (jamais séparateur de milliers) : « 4X1 » → quantity "4" ; « 2.996X1 » → quantity "2.996" ; « 4.043X1 » → quantity "4.043". NE JAMAIS coller les chiffres ensemble ni les passer en milliers.
- « Prix » : le prix unitaire HT (ex. 265,00). « Total » : montant de la ligne (ex. 1060,00).
- Une ligne peut être répartie sur 2 lignes de texte (contenu puis « — 4.043X1 340,00 1 374,62 ») : regroupe le tout en UNE ligne de facture avec la bonne quantité.
- Liste CHAQUE produit du tableau, sans en oublier aucun. Compte-les avant de répondre ; n'invente rien en plus.
- Le nom du fournisseur est l'en-tête du document (ex. grand titre en haut), pas le client ou l'établissement récepteur.
Si une valeur est ambiguë ou illisible, mets null.
Vérification finale obligatoire : pour chaque ligne, quantity × unit_price_ht doit ≈ line_total_ht (sinon relis la ligne et corrige).
Schéma JSON attendu :
{"supplier_name": string|null, "invoice_number": string|null, "invoice_date": "JJ/MM/AAAA"|null,
"bc_number": string|null, "bc_date": string|null, "bl_number": string|null, "bl_date": string|null,
"document_type": "FACTURE"|"BL"|"AVOIR"|null, "currency": string|null,
"total_ht": string|null, "discount_total": string|null, "vat_total": string|null,
"timbre": string|null, "other_taxes": string|null, "total_ttc": string|null,
"lines": [{"raw_reference": string|null, "designation": string, "lot_number": string|null,
"packages": string|null, "quantity": string|null, "unit_price_ht": string|null,
"vat_rate": string|null, "line_total_ht": string|null, "discount_value": string|null,
"discount_type": "percent"|"value"|null}]}
"""

MAX_IMAGE_PAGES = 8


def _encode_page(path: Path) -> str | None:
    """Redimensionne et réencode la page en JPEG compact pour l'API vision."""
    blob = path.read_bytes()
    from io import BytesIO

    from PIL import Image, ImageOps

    with Image.open(BytesIO(blob)) as image:
        image = ImageOps.exif_transpose(image)
        if image.width > 2200:
            ratio = 2200 / float(image.width)
            image = image.resize((2200, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=88)
        return base64.b64encode(buffer.getvalue()).decode("ascii")


def _num(value: str | None) -> float | None:
    if not value:
        return None
    text = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _reconcile(data: dict) -> dict:
    """Corrige les quantités mal décodées en comparant qté × PU au total de ligne.

    Cas fréquent : « 2.996X1 » relu « 2996 ». Si le total rapporté à l'unité multiplié
    par un facteur 100/1000 tombe sur la quantité lue, on répare la décimale.
    """
    for line in data.get("lines") or []:
        quantity = _num(line.get("quantity"))
        unit_price = _num(line.get("unit_price_ht"))
        line_total = _num(line.get("line_total_ht"))
        if quantity in (None, 0) or not unit_price or not line_total:
            continue
        if abs(quantity * unit_price - line_total) <= 0.06:
            continue
        candidate = line_total / unit_price
        for scale in (1000, 100):
            if abs(candidate * scale - quantity) <= max(0.05, quantity * 0.002):
                decimals = 3 if scale == 1000 else 2
                line["quantity"] = f"{candidate:.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")
                break
    return data


def _parse_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Réponse IA non-objet")
    return data


def _build_content(page_paths: list[Path], ocr_text: str | None) -> list[dict]:
    text = SCHEMA_PROMPT
    if ocr_text and ocr_text.strip():
        text += (
            "\n\nTexte OCR auxiliaire (peut contenir des erreurs de lecture, les images restent la source de vérité"
            " — sers-t'en pour vérifier noms/numéros illisibles) :\n---\n" + ocr_text[:6000] + "\n---"
        )
    content: list[dict] = [{"type": "text", "text": text}]
    for path in page_paths:
        encoded = _encode_page(path)
        if encoded is None:
            logger.warning("Page non transmissible à l'IA vision : %s", path)
            continue
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
    return content


class VisionExtractor:
    """Extraction structurée directement depuis les images de pages (multimodale)."""

    @property
    def available(self) -> bool:
        return bool(settings.vision_enabled and settings.vision_api_key and settings.vision_model)

    def extract(self, page_paths: list[Path], ocr_text: str | None = None) -> LlmInvoice | None:
        if not self.available:
            return None
        if cooldown_status()[0]:
            return None
        usable = [path for path in page_paths if path.is_file()][:MAX_IMAGE_PAGES]
        if not usable:
            return None
        url = settings.vision_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": settings.vision_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_content(usable, ocr_text)},
            ],
        }
        try:
            last_error: Exception | None = None
            body: dict | None = None
            for attempt in range(2):
                try:
                    with httpx.Client(timeout=min(90, settings.vision_timeout_seconds)) as client:
                        response = client.post(
                            url, headers={"Authorization": f"Bearer {settings.vision_api_key}"}, json=payload
                        )
                        response.raise_for_status()
                        body = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status_code = exc.response.status_code
                    if status_code in (429, 401, 403) or "insufficient_quota" in exc.response.text:
                        _start_cooldown(status_code)
                        raise
                    if status_code in (503, 500) and attempt < 1:
                        time.sleep(5)
                        continue
                    raise
                except httpx.TransportError as exc:
                    last_error = exc
                    if attempt < 1:
                        time.sleep(4)
                        continue
                    raise
            if body is None:
                if isinstance(last_error, httpx.HTTPStatusError):
                    logger.warning(
                        "Extraction vision rejetée : HTTP %s", last_error.response.status_code
                    )
                return None
            content = body["choices"][0]["message"]["content"]
            data = _reconcile(_parse_json(content))
            return LlmInvoice.model_validate(data)
        except httpx.HTTPStatusError as exc:
            body_text = ""
            try:
                body_text = exc.response.text[:300]
            except Exception:  # noqa: BLE001
                pass
            logger.warning("Extraction vision rejetée : HTTP %s — %s", exc.response.status_code, body_text)
            return None
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning("Extraction vision ignorée après erreur : %s", type(exc).__name__)
            return None


extractor = VisionExtractor()
