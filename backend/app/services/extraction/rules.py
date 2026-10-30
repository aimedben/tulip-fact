from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import mean
from typing import Any

from ...normalization import (
    clean_text,
    normalize_key,
    normalize_reference,
    parse_date,
    parse_decimal,
    to_jsonable,
)
from ..ocr.base import OcrLine

MONEY_TOKEN = re.compile(
    r"(?<![\w])([+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?|[+-]?\d+(?:[.,]\d{1,4})?)(?![\w%])"
)
TOKEN_RE = re.compile(
    r"[+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?%?"
    r"|[+-]?\d+(?:[.,]\d{1,4})?%?(?=$|[^\w])"
    r"|\S+"
)
RATE_TOKEN = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%")
COLISAGE_PATTERN = re.compile(r"(?<![\d.,])(\d{1,6}(?:\s*[.,]\s*\d{1,3})?)\s*[xX]\s*(\d{1,4})(?![\d])")
TOTAL_KEYWORDS = (
    "total",
    "montant",
    "net a payer",
    "net à payer",
    "tva",
    "timbre",
    "remise",
    "ristourne",
    "rabais",
    "sous total",
    "arrêtée",
    "arretee",
)
LINE_HEADER_KEYWORDS = (
    "designation",
    "désignation",
    "quantite",
    "quantité",
    "pu ht",
    "p.u",
    "montant ht",
    "reference",
    "référence",
)
STOP_LINE_KEYWORDS = (
    "total",
    "montant ttc",
    "net a payer",
    "net à payer",
    "tva",
    "timbre",
    "remise",
    "arrêtée",
    "arretee",
    "page ",
    "conditions",
    "mode de paiement",
    "telephone",
    "fax",
    "email",
    "nif",
    " rc ",
    "adresse",
    "devise",
    "echeance",
)
CONTACT_PREFIXES = ("tel", "tél", "fax", "nif", "rc", "email", "mail", "adresse", "devise", "client")

INVOICE_NUMBER_PATTERNS = (
    re.compile(
        r"(?:n[°o]\s*(?:de\s*)?facture|facture\s*n[°o]|num[eé]ro\s*(?:de\s*)?facture|facture\s*n)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{1,40})",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*n[°o]\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{2,40})\s*$", re.IGNORECASE),
)
BC_PATTERN = re.compile(
    r"(?:n[°o]\s*b\.?\s*c\.?|b\.?\s*c\.?\s*n[°o]?|bon\s+de\s+commande\s*n[°o]?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{1,40})",
    re.IGNORECASE,
)
BL_PATTERN = re.compile(
    r"(?:n[°o]\s*b\.?\s*l\.?|b\.?\s*l\.?\s*n[°o]?|bon\s+de\s+livraison\s*n[°o]?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{1,40})",
    re.IGNORECASE,
)
DATE_INVOICE_PATTERNS = (
    re.compile(r"date\s*(?:de\s*la\s*)?facture\s*[:#\-]?\s*(.{4,20})", re.IGNORECASE),
    re.compile(r"date\s*[:#\-]?\s*(.{4,20})", re.IGNORECASE),
)
DATE_BC_PATTERN = re.compile(r"date\s*(?:du\s*)?b\.?\s*c\.?\s*[:#\-]?\s*(.{4,20})", re.IGNORECASE)
DATE_BL_PATTERN = re.compile(r"date\s*(?:du\s*)?b\.?\s*l\.?\s*[:#\-]?\s*(.{4,20})", re.IGNORECASE)
BL_FACTURE_PATTERN = re.compile(
    r"(?:\[x\]|☒|coch[ée]e?)\s*bl\s*[-/]\s*facture|bl\s*[-/]\s*facture\s*[:=]\s*(?:oui|x|coch[ée]e?)",
    re.IGNORECASE,
)
LOT_PATTERN = re.compile(r"\b(?:lot|n[°o]\s*lot)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{0,30})", re.IGNORECASE)
DISCOUNT_PATTERN = re.compile(r"(?:remise|ristourne|rabais)\s*[:#\-]?\s*([\d]+(?:[.,]\d{1,2})?)\s*(%)?", re.IGNORECASE)


@dataclass
class ExtractedLine:
    raw_reference: str | None
    designation: str
    lot_number: str | None = None
    packages: Decimal | None = None
    quantity: Decimal | None = None
    unit_price_ht: Decimal | None = None
    vat_rate: Decimal | None = None
    line_total_ht: Decimal | None = None
    discount_value: Decimal | None = None
    discount_type: str | None = None
    confidence: dict[str, Any] = field(default_factory=dict)
    source_page: int | None = None
    source_bbox: dict[str, float] | None = None
    original_text: str = ""
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExtractedInvoice:
    text: str
    supplier_name_raw: str | None
    supplier_candidates: list[str]
    invoice_number: str | None
    invoice_date: date | None
    bc_number: str | None
    bc_date: date | None
    bl_number: str | None
    bl_date: date | None
    document_type: str | None
    bl_facture: bool | None
    currency: str
    totals: dict[str, Any]
    lines: list[ExtractedLine]
    header_raw: dict[str, Any]
    warnings: list[dict[str, Any]]
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return to_jsonable(
            {
                "text": self.text,
                "supplier_name_raw": self.supplier_name_raw,
                "supplier_candidates": self.supplier_candidates,
                "invoice_number": self.invoice_number,
                "invoice_date": self.invoice_date,
                "bc_number": self.bc_number,
                "bc_date": self.bc_date,
                "bl_number": self.bl_number,
                "bl_date": self.bl_date,
                "document_type": self.document_type,
                "bl_facture": self.bl_facture,
                "currency": self.currency,
                "totals": self.totals,
                "lines": [line.__dict__ for line in self.lines],
                "header_raw": self.header_raw,
                "warnings": self.warnings,
                "meta": self.meta,
            }
        )


def _confidence(value: float, source: str) -> dict[str, Any]:
    return {"value": round(value, 2), "source": source}


def _is_probable_supplier_line(text: str) -> bool:
    key = normalize_key(text)
    if len(key) < 3 or len(text) > 90:
        return False
    if any(keyword in key for keyword in ("facture", "bon de livraison", "bon de commande", "client", "page")):
        return False
    if re.fullmatch(r"[\d\s.,/:-]+", text):
        return False
    return len(re.findall(r"[A-Za-zÀ-ÿ]", text)) >= 3


def _first_amount(text: str) -> tuple[Decimal | None, str | None]:
    match = MONEY_TOKEN.search(text)
    while match:
        value = parse_decimal(match.group(1))
        if value is not None:
            return value, match.group(1)
        match = MONEY_TOKEN.search(text, match.end())
    return None, None


def _last_amount(text: str) -> tuple[Decimal | None, str | None]:
    candidates: list[tuple[Decimal, str]] = []
    for match in MONEY_TOKEN.finditer(text):
        value = parse_decimal(match.group(1))
        if value is not None:
            candidates.append((value, match.group(1)))
    if not candidates:
        return None, None
    return candidates[-1]


def _amount_after_label(line: str, label_pattern: str) -> tuple[Decimal | None, str | None, float]:
    match = re.search(label_pattern, line, re.IGNORECASE)
    if not match:
        return None, None, 0.0
    tail = line[match.end():]
    value, raw = _last_amount(tail)
    if value is None:
        value, raw = _last_amount(line)
        if value is not None:
            return value, raw, 0.55
        return None, None, 0.0
    return value, raw, 0.85


def _extract_totals(lines: list[OcrLine]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    totals: dict[str, Any] = {}
    raw_values: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    vat_breakdown: dict[str, str] = {}

    for line in lines:
        text = line.text.strip()
        key = normalize_key(text)
        if not key:
            continue

        if re.search(r"(?:total\s*t\.?\s*t\.?\s*c|montant\s*ttc|net\s*[àa]\s*payer|total\s*pay[ée])", text, re.IGNORECASE):
            value, raw, confidence = _amount_after_label(
                text, r"(?:total\s*t\.?\s*t\.?\s*c|montant\s*ttc|net\s*[àa]\s*payer|total\s*pay[ée])"
            )
            if value is not None and "total_ttc" not in totals:
                totals["total_ttc"] = value
                raw_values["total_ttc"] = raw or ""
                totals.setdefault("confidence", {})["total_ttc"] = confidence

        if re.search(r"(?:total|montant)\s*h\.?\s*t\.?", text, re.IGNORECASE) and "total_ht" not in totals:
            value, raw, confidence = _amount_after_label(text, r"(?:total|montant)\s*h\.?\s*t\.?")
            if value is not None:
                totals["total_ht"] = value
                raw_values["total_ht"] = raw or ""
                totals.setdefault("confidence", {})["total_ht"] = confidence

        if re.search(r"t\.?\s*v\.?\s*a\.?", text, re.IGNORECASE):
            rate_match = RATE_TOKEN.search(text)
            rate = parse_decimal(rate_match.group(1)) if rate_match else None
            if rate_match:
                value, raw = _last_amount(text[rate_match.end():])
                confidence = 0.85
            else:
                value, raw, confidence = _amount_after_label(text, r"(?:total\s*)?t\.?\s*v\.?\s*a\.?")
            if value is not None:
                if not re.search(r"tva\s*(?:19|9|0)\s*%", text, re.IGNORECASE) and "tva" in key and "total" not in key:
                    if "vat_total" not in totals:
                        totals["vat_total"] = value
                        raw_values["vat_total"] = raw or ""
                        totals.setdefault("confidence", {})["vat_total"] = confidence
                else:
                    if "vat_total" not in totals:
                        totals["vat_total"] = value
                        raw_values["vat_total"] = raw or ""
                        totals.setdefault("confidence", {})["vat_total"] = confidence
                if rate is not None:
                    vat_breakdown[str(rate.normalize())] = str(value)

        if "timbre" in key:
            value, raw, confidence = _amount_after_label(text, r"timbre")
            if value is not None:
                totals["timbre"] = value
                raw_values["timbre"] = raw or ""
                totals.setdefault("confidence", {})["timbre"] = confidence

        if re.search(r"(?:autres?\s*taxes?|taxe\s*compl[eé]mentaire)", text, re.IGNORECASE):
            value, raw, confidence = _amount_after_label(
                text, r"(?:autres?\s*taxes?|taxe\s*compl[eé]mentaire)"
            )
            if value is not None:
                totals["other_taxes"] = value
                raw_values["other_taxes"] = raw or ""
                totals.setdefault("confidence", {})["other_taxes"] = confidence

        if re.search(r"(?:remise|ristourne|rabais)", text, re.IGNORECASE) and "total" not in key:
            value, raw, confidence = _amount_after_label(text, r"(?:remise|ristourne|rabais)")
            if value is not None:
                totals["discount_total"] = value
                raw_values["discount_total"] = raw or ""
                totals.setdefault("confidence", {})["discount_total"] = confidence

    if vat_breakdown:
        totals["vat_breakdown"] = vat_breakdown
    if raw_values:
        totals["raw"] = raw_values
    for field_name, value in totals.items():
        if field_name in {"confidence", "raw", "vat_breakdown"}:
            continue
        if value is None:
            warnings.append(
                {
                    "code": "TOTAL_ABSENT",
                    "severity": "warning",
                    "field": field_name,
                    "message": f"Le total « {field_name} » est absent ou illisible sur la facture.",
                }
            )
    return totals, warnings


def _is_number_token(token: str) -> bool:
    candidate = token.strip().strip(":;")
    if not candidate or candidate in {"-", "/"}:
        return False
    if not re.fullmatch(r"[+-]?\(?\d[\d \u00a0\u202f.,]*\)?%?", candidate):
        return False
    return parse_decimal(candidate) is not None


def _is_structure_token(token: str) -> bool:
    upper = token.upper().strip(":;")
    if _is_number_token(token):
        return True
    if re.fullmatch(r"(?:LOT|N[°O]\s*LOT)[\s:._/-]*[A-Z0-9][A-Z0-9._/-]*", upper):
        return True
    if re.fullmatch(r"(?:C/|COLIS)[\s:._/-]*\d+", upper):
        return True
    return False


def _parse_reference_and_rest(line: str) -> tuple[str | None, str]:
    text = line.strip()
    match = re.match(r"^([A-Z0-9][A-Z0-9._/\-]{1,29})\s+(.+)$", text)
    if not match:
        return None, text
    token = match.group(1)
    if token.upper() in {"LOT", "TVA", "TTC", "HT", "TOTAL", "DATE", "NET", "COLIS"}:
        return None, text
    if not re.search(r"[\d\-/._]", token):
        return None, text
    return token, match.group(2)


def _colisage_quantity(text: str) -> Decimal | None:
    """Quantité portée par un colisage « 4X1 », « 6.091X1 » (le 1er nombre est la quantité)."""
    match = COLISAGE_PATTERN.search(text)
    if not match:
        return None
    raw = re.sub(r"\s+", "", match.group(1)).replace(",", ".")
    try:
        value = Decimal(raw)
    except Exception:  # noqa: BLE001
        return None
    return value if value > 0 else None


def _emphasis_money(text: str) -> list[Decimal]:
    """Montants écrits avec une partie décimale (ex. « 265,00 », « 1 060,00 »)."""
    values: list[Decimal] = []
    for match in MONEY_TOKEN.finditer(text):
        token = match.group(1)
        if not re.search(r"[.,]\d{2}(?!\d)", token):
            continue
        value = parse_decimal(token)
        if value is not None:
            values.append(value)
    return values


def _split_merged_quantity(price: Decimal, total: Decimal) -> tuple[Decimal, Decimal] | None:
    """« 24 450,00 » sans les espaces devient 24450,00 : on recolle quantité et prix.

    On essaie toutes les coupures du nombre et on garde celle qui vérifie
    quantité x prix = total imprimé.
    """
    digits = str(int(price))
    if len(digits) < 4 or price != price.to_integral_value():
        return None
    tolerance = max(Decimal("0.05"), abs(total) * Decimal("0.002"))
    for index in range(1, len(digits) - 2):
        quantity = Decimal(digits[:index])
        unit_price = Decimal(digits[index:]).quantize(Decimal("0.01"))
        if quantity > 0 and unit_price > 0 and abs(quantity * unit_price - total) <= tolerance:
            return quantity, unit_price
    return None


def _structured_amounts(
    text: str, designation: str
) -> tuple[Decimal, Decimal, Decimal, bool] | None:
    """Lit une ligne « désignation colisage PU Total » (ex. « 4X1 265,00 1 060,00 »).

    Les deux derniers montants à décimale sont le prix unitaire et le total imprimé ;
    la quantité vient du colisage (« 4X1 » → 4) ou, à défaut, du rapport total/PU.
    """
    money = _emphasis_money(text)
    if len(money) < 2:
        return None
    unit_price = money[-2]
    line_total = money[-1]
    if unit_price <= 0 or line_total <= 0:
        return None
    quantity = _colisage_quantity(designation) or _colisage_quantity(text)
    if quantity is None:
        ratio = line_total / unit_price
        rounded = ratio.quantize(Decimal("0.001"))
        if rounded <= 0 or rounded > Decimal("100000"):
            return None
        if abs(rounded - rounded.to_integral_value()) <= Decimal("0.002"):
            rounded = rounded.to_integral_value()
        quantity = rounded
    computed = (quantity * unit_price).quantize(Decimal("0.01"))
    coherent = abs(computed - line_total) <= max(Decimal("0.05"), abs(line_total) * Decimal("0.0002"))
    if not coherent:
        split = _split_merged_quantity(unit_price, line_total)
        if split is not None:
            quantity, unit_price = split
            computed = (quantity * unit_price).quantize(Decimal("0.01"))
            coherent = abs(computed - line_total) <= max(Decimal("0.05"), abs(line_total) * Decimal("0.0002"))
    return quantity, unit_price, line_total, coherent


def _split_designation_and_suffix(rest: str) -> tuple[str, list[str]]:
    tokens = [match.group(0) for match in TOKEN_RE.finditer(rest)]
    index = len(tokens)
    while index > 0:
        token = tokens[index - 1]
        if _is_structure_token(token):
            index -= 1
            continue
        if token.upper().rstrip(":") in {"REMISE", "TVA", "HT"}:
            index -= 1
            continue
        break
    return " ".join(tokens[:index]).strip(" -:;"), tokens[index:]


def _number_variants(tokens: list[str]) -> list[list[Decimal]]:
    variants: list[list[Decimal]] = [[]]
    for token in tokens:
        value = parse_decimal(token)
        if value is None:
            continue
        options: list[list[Decimal]] = [[value]]
        stripped = token.strip()
        if re.fullmatch(r"[+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?%?", stripped):
            parts = [parse_decimal(part) for part in re.split(r"[ \u00a0\u202f]+", stripped) if part]
            if len(parts) > 1 and all(part is not None for part in parts):
                options.append([part for part in parts if part is not None])
        expanded: list[list[Decimal]] = []
        for prefix in variants:
            for option in options:
                expanded.append(prefix + option)
        variants = expanded[:64]
    return variants


def _hypotheses(numbers: list[Decimal]) -> list[dict[str, Any]]:
    if len(numbers) < 2:
        return []
    total = numbers[-1]
    candidates: list[dict[str, Any]] = []
    for qty_index in range(0, len(numbers) - 2):
        for pu_index in range(qty_index + 1, len(numbers) - 1):
            qty = numbers[qty_index]
            pu = numbers[pu_index]
            if qty is None or pu is None:
                continue
            if qty <= 0 or pu < 0 or total < 0:
                continue
            vat_index = None
            vat = None
            if pu_index + 1 < len(numbers) - 1:
                possible_rate = numbers[pu_index + 1]
                if Decimal("0") <= possible_rate <= Decimal("100"):
                    vat_index = pu_index + 1
                    vat = possible_rate
            computed = (qty * pu).quantize(Decimal("0.01"))
            difference = abs(computed - total)
            tolerance = max(Decimal("0.05"), abs(total) * Decimal("0.002"))
            coherent = difference <= tolerance
            used = 4 if vat_index is not None else 3
            extras = numbers[:qty_index]
            closeness = 1.0 - min(float(difference) / max(float(abs(total)), 1.0), 1.0)
            candidates.append(
                {
                    "qty": qty,
                    "pu": pu,
                    "vat": vat,
                    "total": total,
                    "computed": computed,
                    "difference": difference,
                    "coherent": coherent,
                    "vat_index": vat_index,
                    "extras": extras,
                    "score": (10.0 if coherent else 0.0) + used * 0.1 + closeness,
                }
            )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _parse_item_line(line: OcrLine) -> ExtractedLine | None:
    text = clean_text(line.text).strip()
    if not text or len(text) < 6:
        return None
    lowered = normalize_key(text)
    if any(keyword in lowered for keyword in TOTAL_KEYWORDS):
        return None
    if any(keyword in lowered for keyword in LINE_HEADER_KEYWORDS):
        return None
    if any(lowered.startswith(prefix) for prefix in CONTACT_PREFIXES):
        return None

    raw_reference, rest = _parse_reference_and_rest(text)
    designation_part, suffix = _split_designation_and_suffix(rest)
    variants = _number_variants(suffix)
    numbers = variants[0] if variants else []
    if len(numbers) < 2:
        return None
    letter_words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", designation_part)
    if not designation_part or len(designation_part) < 6 or len(letter_words) < 2:
        return None

    candidates = [
        candidate
        for variant in variants
        for candidate in _hypotheses(variant)
    ]
    candidates.sort(key=lambda item: item["score"], reverse=True)

    structured = _structured_amounts(text, designation_part)
    warnings: list[dict[str, Any]] = []
    if structured is not None:
        quantity, unit_price, line_total, coherent = structured
        vat_rate = None
        extras = []
        try:
            price_index = numbers.index(unit_price)
        except ValueError:
            price_index = -1
        if price_index > 0:
            leading = numbers[:price_index]
            if len(leading) >= 2 and leading[-1] == quantity:
                extras = [leading[-2]]
            between = numbers[price_index + 1 : -1]
            for value in between:
                if Decimal("0") <= value < Decimal("100") and value == value.to_integral_value():
                    vat_rate = value
                    break
        if not coherent:
            warnings.append(
                {
                    "code": "LIGNE_CALCUL_INCOHERENT",
                    "severity": "warning",
                    "message": "Quantité × prix unitaire ne correspond pas au montant imprimé sur cette ligne.",
                }
            )
    elif candidates:
        best = candidates[0]
        quantity = best["qty"]
        unit_price = best["pu"]
        vat_rate = best["vat"]
        line_total = best["total"]
        extras = best["extras"]
        coherent = best["coherent"]
        if not coherent:
            warnings.append(
                {
                    "code": "LIGNE_CALCUL_INCOHERENT",
                    "severity": "warning",
                    "message": "Quantité × prix unitaire ne correspond pas au montant imprimé sur cette ligne.",
                }
            )
    else:
        quantity = numbers[0]
        unit_price = numbers[1] if len(numbers) > 2 else None
        line_total = numbers[-1]
        vat_rate = None
        extras = numbers[1:-1] if len(numbers) > 3 else []
        coherent = False
        warnings.append(
            {
                "code": "LIGNE_INCOMPLETE",
                "severity": "warning",
                "message": "La structure de la ligne est incomplète ; certains montants sont incertains.",
            }
        )

    lot_match = LOT_PATTERN.search(text)
    lot_number = lot_match.group(1) if lot_match else None
    discount_match = DISCOUNT_PATTERN.search(text)
    discount_value = None
    discount_type = None
    if discount_match:
        discount_value = parse_decimal(discount_match.group(1))
        discount_type = "percent" if discount_match.group(2) else "value"

    packages = None
    for extra in reversed(extras):
        if extra == extra.to_integral_value() and Decimal("0") < extra < Decimal("100000"):
            packages = extra
            break

    confidence_value = 0.55
    if raw_reference:
        confidence_value += 0.1
    if coherent:
        confidence_value += 0.2
    elif len(numbers) >= 3:
        confidence_value += 0.05
    if vat_rate is not None:
        confidence_value += 0.05
    if lot_number:
        confidence_value += 0.03
    confidence_value = min(0.95, confidence_value)

    reference_confidence = 0.85 if raw_reference else 0.0
    amount_confidence = 0.8 if coherent else 0.45
    return ExtractedLine(
        raw_reference=normalize_reference(raw_reference),
        designation=designation_part,
        lot_number=lot_number,
        packages=packages,
        quantity=quantity,
        unit_price_ht=unit_price,
        vat_rate=vat_rate,
        line_total_ht=line_total,
        discount_value=discount_value,
        discount_type=discount_type,
        confidence={
            "global": round(confidence_value, 2),
            "reference": reference_confidence,
            "designation": 0.75,
            "quantity": amount_confidence,
            "unit_price": amount_confidence,
            "total": amount_confidence,
            "lot": 0.7 if lot_number else 0.0,
            "packages": 0.45 if packages is not None else 0.0,
            "coherent": coherent,
        },
        source_page=line.page_number,
        source_bbox=line.bbox,
        original_text=text,
        warnings=warnings,
    )


def _merge_continuation(previous: ExtractedLine | None, line: OcrLine) -> bool:
    if previous is None:
        return False
    text = clean_text(line.text).strip()
    if not text or len(text) < 3 or len(text) > 120:
        return False
    lowered = normalize_key(text)
    if any(keyword in lowered for keyword in TOTAL_KEYWORDS):
        return False
    if re.search(r"\d[.,]\d{2}", text):
        return False
    if len(re.findall(r"[A-Za-zÀ-ÿ]", text)) < 3:
        return False
    previous.designation = f"{previous.designation} {text}".strip()[:255]
    previous.confidence["designation"] = min(float(previous.confidence.get("designation", 0.75)), 0.6)
    return True


def _rescale_impossible_lines(lines: list[ExtractedLine], totals: dict[str, Any]) -> None:
    """Une ligne ne peut pas coûter plus cher que la facture entière.

    Quand Tesseract perd la virgule à la fois sur le prix et sur le total d'une même
    ligne (« 55000 » et « 164780 »), le produit reste cohérent et passe inaperçu.
    Le total de la facture tranche : on divise par 100 ces lignes aberrantes.
    """
    total_ttc = totals.get("total_ttc")
    if not total_ttc or total_ttc <= 0:
        return
    for line in lines:
        if not line.line_total_ht or line.line_total_ht <= total_ttc:
            continue
        for factor in (Decimal("100"), Decimal("10")):
            candidate_total = (line.line_total_ht / factor).quantize(Decimal("0.01"))
            if candidate_total <= total_ttc:
                line.line_total_ht = candidate_total
                if line.unit_price_ht:
                    line.unit_price_ht = (line.unit_price_ht / factor).quantize(Decimal("0.01"))
                if line.quantity and line.unit_price_ht:
                    tolerance = max(Decimal("0.05"), abs(candidate_total) * Decimal("0.002"))
                    if abs(line.quantity * line.unit_price_ht - candidate_total) > tolerance:
                        repaired = (candidate_total / line.quantity).quantize(Decimal("0.01"))
                        if repaired > 0:
                            line.unit_price_ht = repaired
                break


def parse_invoice(lines: list[OcrLine]) -> ExtractedInvoice:
    ordered = sorted(lines, key=lambda item: (item.page_number, (item.bbox or {}).get("y0", 0)))
    full_text = "\n".join(item.text for item in ordered)
    header_lines = [item for item in ordered if item.page_number == 1][:25]
    warnings: list[dict[str, Any]] = []
    header_raw: dict[str, Any] = {}

    supplier_candidates: list[str] = []
    for item in header_lines[:12]:
        text = item.text.strip()
        if _is_probable_supplier_line(text) and text not in supplier_candidates:
            supplier_candidates.append(text)
    supplier_name_raw = supplier_candidates[0] if supplier_candidates else None
    if supplier_name_raw:
        header_raw["supplier_name_raw"] = _confidence(0.5, "heuristique en-tête")

    invoice_number = None
    for item in ordered[:30]:
        line = item.text.strip()
        if re.search(r"\bB\.?\s*[CL]\.?\b", line, re.IGNORECASE) and "facture" not in normalize_key(line):
            continue
        for pattern in INVOICE_NUMBER_PATTERNS:
            match = pattern.search(line)
            if match:
                candidate = match.group(1).strip(" .,;:-")
                if parse_date(candidate) is not None:
                    continue
                if normalize_key(candidate) in {"facture", "bl", "bc", "ttc", "ht"}:
                    continue
                invoice_number = candidate
                header_raw["invoice_number"] = _confidence(0.9, "libellé explicite")
                break
        if invoice_number:
            break

    invoice_date = None
    for item in header_lines:
        text = item.text.strip()
        for pattern in DATE_INVOICE_PATTERNS:
            match = pattern.search(text)
            if match:
                candidate = parse_date(match.group(1))
                if candidate:
                    invoice_date = candidate
                    header_raw["invoice_date"] = _confidence(
                        0.9 if "facture" in normalize_key(text) else 0.6, "libellé date"
                    )
                    break
        if invoice_date:
            break
    if invoice_date is None:
        for item in header_lines:
            if re.search(r"\bB\.?\s*[CL]\.?\b", item.text, re.IGNORECASE):
                continue
            candidate = parse_date(item.text)
            if candidate:
                invoice_date = candidate
                header_raw["invoice_date"] = _confidence(0.45, "première date de l'en-tête")
                break

    bc_number = None
    bc_date = None
    bl_number = None
    bl_date = None
    for item in ordered[:40]:
        text = item.text.strip()
        if bc_number is None:
            match = BC_PATTERN.search(text)
            if match:
                bc_number = match.group(1).strip(" .,;:-")
                header_raw["bc_number"] = _confidence(0.85, "libellé B.C.")
        if bl_number is None and not re.search(r"bl\s*[-/]\s*facture", text, re.IGNORECASE):
            match = BL_PATTERN.search(text)
            if match:
                bl_number = match.group(1).strip(" .,;:-")
                header_raw["bl_number"] = _confidence(0.85, "libellé B.L.")
        if bc_date is None:
            match = DATE_BC_PATTERN.search(text)
            if match:
                bc_date = parse_date(match.group(1))
                if bc_date:
                    header_raw["bc_date"] = _confidence(0.85, "libellé date B.C.")
        if bl_date is None:
            match = DATE_BL_PATTERN.search(text)
            if match:
                bl_date = parse_date(match.group(1))
                if bl_date:
                    header_raw["bl_date"] = _confidence(0.85, "libellé date B.L.")

    bl_facture = True if BL_FACTURE_PATTERN.search(full_text) else None
    if bl_facture:
        header_raw["bl_facture"] = _confidence(0.8, "case explicitement cochée")

    lowered = normalize_key(full_text[:4000])
    if "avoir" in lowered:
        document_type = "AVOIR"
    elif "bon de livraison" in lowered and "facture" not in lowered:
        document_type = "BL"
    elif "facture" in lowered:
        document_type = "FACTURE"
    else:
        document_type = None

    currency = "DZD"
    currency_source = "valeur par défaut"
    currency_match = re.search(r"\b(DZD|DA|DINARS?)\b", full_text, re.IGNORECASE)
    if currency_match:
        currency = "DZD"
        currency_source = "mention explicite"
    header_raw["currency"] = _confidence(0.95 if currency_match else 0.4, currency_source)

    totals, total_warnings = _extract_totals(ordered)
    warnings.extend(total_warnings)

    extracted_lines: list[ExtractedLine] = []
    from .tables import parse_table_rows  # import local : tables.py dépend de ce module

    table_lines = parse_table_rows(ordered)
    if table_lines:
        extracted_lines = table_lines
        warnings_meta: dict[str, Any] = {"table_parsing": True}
    else:
        warnings_meta = {}
    previous: ExtractedLine | None = None
    for item in ([] if table_lines else ordered):
        text = item.text.strip()
        lowered_line = normalize_key(text)
        if not text:
            continue
        if any(keyword in lowered_line for keyword in STOP_LINE_KEYWORDS):
            continue
        parsed = _parse_item_line(item)
        if parsed is not None:
            extracted_lines.append(parsed)
            previous = parsed
            continue
        if previous is not None and _merge_continuation(previous, item):
            continue

    if extracted_lines:
        _rescale_impossible_lines(extracted_lines, totals)

    if not extracted_lines:
        warnings.append(
            {
                "code": "AUCUNE_LIGNE",
                "severity": "error",
                "message": "Aucune ligne d'article n'a pu être extraite. Vérifiez la lisibilité ou saisissez les lignes manuellement.",
            }
        )
    if invoice_number is None:
        warnings.append(
            {
                "code": "NUMERO_FACTURE_ABSENT",
                "severity": "warning",
                "message": "Le numéro de facture n'a pas été détecté.",
            }
        )
    if invoice_date is None:
        warnings.append(
            {
                "code": "DATE_FACTURE_ABSENTE",
                "severity": "warning",
                "message": "La date de facture n'a pas été détectée.",
            }
        )
    if supplier_name_raw is None:
        warnings.append(
            {
                "code": "FOURNISSEUR_NON_DETECTE",
                "severity": "warning",
                "message": "Le nom du fournisseur n'a pas été détecté dans l'en-tête.",
            }
        )

    for line in extracted_lines:
        for warning in line.warnings:
            warnings.append({**warning, "line_reference": line.raw_reference or line.designation[:40]})

    confidences = [line.confidence.get("global", 0) for line in extracted_lines]
    meta = {
        "line_count": len(extracted_lines),
        "average_line_confidence": round(mean(confidences), 2) if confidences else None,
        "parser": "regles-locales-v1",
    }

    return ExtractedInvoice(
        text=full_text,
        supplier_name_raw=supplier_name_raw,
        supplier_candidates=supplier_candidates,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        bc_number=bc_number,
        bc_date=bc_date,
        bl_number=bl_number,
        bl_date=bl_date,
        document_type=document_type,
        bl_facture=bl_facture,
        currency=currency,
        totals=totals,
        lines=extracted_lines,
        header_raw=header_raw,
        warnings=warnings,
        meta={**meta, **warnings_meta},
    )
