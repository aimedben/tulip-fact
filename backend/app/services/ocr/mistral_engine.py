from __future__ import annotations

import base64
import logging
import os
import re
import time
from typing import Any

import httpx

from .base import OcrLine

logger = logging.getLogger(__name__)


class MistralOcrEngine:
    """Moteur OCR via l'API officielle Mistral « /v1/ocr » (modèle mistral-ocr-latest).

    L'API renvoie un markdown par page ; on le transforme en lignes OCR brutes
    (sans mots positionnés) : le parseur de règles utilise ensuite les sauts de
    ligne. Après une erreur 429 (quota) ou un modèle invalide, le moteur se met
    en cooldown : les appels suivants échouent immédiatement et le repli local
    (rapidocr/tesseract) prend le relais sans latency.
    """

    name = "mistral-ocr"

    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY", "").strip()
        self.api_base = os.getenv("MISTRAL_API_BASE", "https://api.mistral.ai/v1").rstrip("/")
        self.model = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest").strip()
        try:
            self.timeout = float(os.getenv("MISTRAL_OCR_TIMEOUT", "120").strip())
        except ValueError:
            self.timeout = 120.0
        self._cooldown_seconds = 600.0
        self._blocked_until = 0.0

    def available(self) -> bool:
        """Disponible si une clé est configurée et hors cooldown."""
        return bool(self.api_key) and time.time() >= self._blocked_until

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    @staticmethod
    def _data_uri(image_path: str) -> str:
        suffix = (image_path.rsplit(".", 1)[-1] or "jpeg").lower()
        mime = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "bmp": "image/bmp",
        }.get(suffix, "image/jpeg")
        return f"data:{mime};base64,{MistralOcrEngine._encode_image(image_path)}"

    def _call_ocr(self, data_uri: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "document": {"type": "image_url", "image_url": data_uri},
            "include_image_base64": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(
                f"{self.api_base}/ocr", headers=headers, json=payload, timeout=self.timeout
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Erreur API Mistral: {exc}") from exc
        if response.status_code == 400 and self.model != "mistral-ocr-latest":
            # Modèle configuré invalide : une seule relance avec le modèle canonique.
            logger.warning("Mistral : modèle « %s » refusé, nouvel essai avec mistral-ocr-latest", self.model)
            payload["model"] = "mistral-ocr-latest"
            response = httpx.post(
                f"{self.api_base}/ocr", headers=headers, json=payload, timeout=self.timeout
            )
        if response.status_code == 429:
            self._blocked_until = time.time() + self._cooldown_seconds
            raise RuntimeError(
                "Mistral OCR : quota dépassé (429), moteur local activé "
                f"(cooldown {int(self._cooldown_seconds / 60)} min)."
            )
        if response.status_code != 200:
            detail = response.text[:300]
            raise RuntimeError(f"Mistral OCR HTTP {response.status_code} : {detail}")
        return response.json()

    def recognize(
        self, image_path: str, page_number: int = 1
    ) -> tuple[str, list[OcrLine], float | None]:
        """Reconnaissance OCR via l'API Mistral.

        Returns:
            Tuple (markdown concaténé, lignes, confiance moyenne)
        """
        if not self.available():
            remaining = max(0, int(self._blocked_until - time.time()))
            raise RuntimeError(f"Mistral OCR indisponible (cooldown, {remaining}s restantes).")

        logger.info("Appel Mistral /v1/ocr pour %s (page %s)", image_path, page_number)
        data = self._call_ocr(self._data_uri(image_path))

        logger.info("Mistral OCR : %s page(s) lue(s)", len(data.get("pages", [])))

        lines: list[OcrLine] = []

        for index, page in enumerate(data.get("pages", []), start=1):
            markdown = str(page.get("markdown") or "").strip()
            if not markdown:
                continue
            for raw in markdown.splitlines():
                text = raw.strip()
                # Pieds de page source : images/pdf intégrés
                if not text or text.startswith("!") or text.startswith("<"):
                    continue
                text = re.sub(r"[*_`#>]+", " ", text).strip()
                if not text:
                    continue
                lines.append(
                    OcrLine(
                        text=text,
                        page_number=page_number,
                        confidence=0.92,
                        source="mistral-ocr",
                    )
                )

        text = "\n".join(line.text for line in lines)
        confidence = 0.92 if lines else None
        return text, lines, confidence


# Instance singleton
engine = MistralOcrEngine()
