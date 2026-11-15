from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...config import settings
from ...normalization import parse_date, parse_decimal
from .rules import ExtractedInvoice, ExtractedLine

logger = logging.getLogger(__name__)


class LlmLine(BaseModel):
    model_config = ConfigDict(extra="ignore")
    raw_reference: str | None = None
    designation: str = ""
    lot_number: str | None = None
    packages: str | None = None
    quantity: str | None = None
    unit_price_ht: str | None = None
    vat_rate: str | None = None
    line_total_ht: str | None = None
    discount_value: str | None = None
    discount_type: str | None = None


class LlmInvoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supplier_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    bc_number: str | None = None
    bc_date: str | None = None
    bl_number: str | None = None
    bl_date: str | None = None
    document_type: str | None = None
    currency: str | None = None
    total_ht: str | None = None
    discount_total: str | None = None
    vat_total: str | None = None
    timbre: str | None = None
    other_taxes: str | None = None
    total_ttc: str | None = None
    lines: list[LlmLine] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "Tu es un assistant d'extraction de factures fournisseurs algériennes. "
    "Tu ne dois jamais inventer une valeur absente. Utilise null pour tout champ inconnu. "
    "Réponds uniquement avec un objet JSON valide respectant le schéma demandé."
)

USER_TEMPLATE = """Extrait les données de cette facture. Le texte provient d'un OCR et peut contenir des erreurs.
Ne devine aucun numéro de lot, prix, taux de TVA, référence ou date. N'invente pas de lignes.
Schéma JSON attendu :
{{"supplier_name": string|null, "invoice_number": string|null, "invoice_date": "JJ/MM/AAAA"|null,
"bc_number": string|null, "bc_date": string|null, "bl_number": string|null, "bl_date": string|null,
"document_type": "FACTURE"|"BL"|"AVOIR"|null, "currency": string|null,
"total_ht": string|null, "discount_total": string|null, "vat_total": string|null,
"timbre": string|null, "other_taxes": string|null, "total_ttc": string|null,
"lines": [{{"raw_reference": string|null, "designation": string, "lot_number": string|null,
"packages": string|null, "quantity": string|null, "unit_price_ht": string|null,
"vat_rate": string|null, "line_total_ht": string|null, "discount_value": string|null,
"discount_type": "percent"|"value"|null}}]}}

Texte OCR :
---
{text}
---
"""


class LlmExtractor:
    @property
    def available(self) -> bool:
        return bool(settings.llm_enabled and settings.llm_api_key and settings.llm_model)

    def extract(self, text: str) -> LlmInvoice | None:
        if not self.available:
            return None
        if len(text.strip()) < 20:
            return None
        payload: dict = {
            "model": settings.llm_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(text=text[:12000])},
            ],
        }
        # json_object mode n'est pas supporté par tous les providers (ex: opencode)
        base_url = settings.llm_base_url.rstrip("/")
        if "openai.com" in base_url or "azure" in base_url:
            payload["response_format"] = {"type": "json_object"}
        url = base_url + "/chat/completions"
        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            content = body["choices"][0]["message"]["content"]
            data = json.loads(content)
            return LlmInvoice.model_validate(data)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Extraction LLM ignorée : HTTP %s — %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return None
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Extraction LLM ignorée après erreur : %s — %s", type(exc).__name__, exc)
            return None


def merge_llm_result(extracted: ExtractedInvoice, llm: LlmInvoice, replace_lines: bool = False) -> ExtractedInvoice:
    if not extracted.supplier_name_raw and llm.supplier_name:
        extracted.supplier_name_raw = llm.supplier_name
        if llm.supplier_name not in extracted.supplier_candidates:
            extracted.supplier_candidates.insert(0, llm.supplier_name)
    if not extracted.invoice_number and llm.invoice_number:
        extracted.invoice_number = llm.invoice_number
        extracted.header_raw["invoice_number"] = {"value": 0.6, "source": "extraction IA optionnelle"}
    if extracted.invoice_date is None and llm.invoice_date:
        parsed = parse_date(llm.invoice_date)
        if parsed:
            extracted.invoice_date = parsed
            extracted.header_raw["invoice_date"] = {"value": 0.6, "source": "extraction IA optionnelle"}
    if not extracted.bc_number and llm.bc_number:
        extracted.bc_number = llm.bc_number
    if extracted.bc_date is None and llm.bc_date:
        extracted.bc_date = parse_date(llm.bc_date)
    if not extracted.bl_number and llm.bl_number:
        extracted.bl_number = llm.bl_number
    if extracted.bl_date is None and llm.bl_date:
        extracted.bl_date = parse_date(llm.bl_date)
    if extracted.document_type is None and llm.document_type:
        extracted.document_type = llm.document_type
    if llm.currency:
        extracted.currency = llm.currency.upper()[:8]

    total_fields = ("total_ht", "discount_total", "vat_total", "timbre", "other_taxes", "total_ttc")
    for field_name in total_fields:
        if field_name not in extracted.totals:
            value = parse_decimal(getattr(llm, field_name))
            if value is not None:
                extracted.totals[field_name] = value
                extracted.totals.setdefault("confidence", {})[field_name] = 0.55
                extracted.totals.setdefault("raw", {})[field_name] = str(getattr(llm, field_name))

    if not extracted.lines or (replace_lines and llm.lines):
        if replace_lines:
            extracted.lines = []
        for item in llm.lines:
            if not item.designation:
                continue
            extracted.lines.append(
                ExtractedLine(
                    raw_reference=item.raw_reference,
                    designation=item.designation[:255],
                    lot_number=item.lot_number,
                    packages=parse_decimal(item.packages),
                    quantity=parse_decimal(item.quantity),
                    unit_price_ht=parse_decimal(item.unit_price_ht),
                    vat_rate=parse_decimal(item.vat_rate),
                    line_total_ht=parse_decimal(item.line_total_ht),
                    discount_value=parse_decimal(item.discount_value),
                    discount_type=item.discount_type if item.discount_type in {"percent", "value"} else None,
                    confidence={"global": 0.6, "source": "ia_optionnelle"},
                    original_text="extraction IA optionnelle",
                )
            )
    if llm.lines:
        extracted.meta["llm_lines_used"] = True
        if not replace_lines:
            _fill_missing_designations(extracted, llm)

    extracted.meta["llm_used"] = True
    return extracted


def _fill_missing_designations(extracted: ExtractedInvoice, llm: LlmInvoice) -> None:
    """Complète les libellés manquants sans toucher aux quantités/montants lus localement."""
    for line in extracted.lines:
        weak = not line.designation or line.designation.strip().lower() in {
            "",
            "article à compléter",
            "article a completer",
        }
        if not weak:
            continue
        for item in llm.lines:
            if not item.designation:
                continue
            item_total = parse_decimal(item.line_total_ht)
            item_quantity = parse_decimal(item.quantity)
            same_total = item_total is not None and line.line_total_ht == item_total
            same_quantity = item_quantity is not None and line.quantity == item_quantity
            if same_total or (same_quantity and line.unit_price_ht == parse_decimal(item.unit_price_ht)):
                clean = item.designation.strip()[:255]
                if clean:
                    line.designation = clean
                    line.confidence["designation"] = 0.6
                    line.confidence["global"] = max(float(line.confidence.get("global") or 0), 0.6)
                break


extractor = LlmExtractor()
