"""Lecture de tableaux de factures à partir des coordonnées OCR.

Problème historique : une ligne OCR comme
    « Delicia 480 gr 4X1 265,00 1 060,00 »
est ambiguë quand on ne connaît pas la position horizontale des mots : impossible de
savoir si « 4 » est la quantité et « 265,00 » le prix, ou l'inverse.

Ici on reconstruit les colonnes avec les boîtes de chaque mot, exactement comme un
humain lit le papier : chaque montant est rattaché à la colonne sous laquelle il est
imprimé. Déterministe, local, sans quota ni coût.
"""

from __future__ import annotations

import re
from statistics import mean
from decimal import Decimal
from typing import Any

from ...normalization import parse_decimal
from ..ocr.base import OcrLine
from .rules import (
    DISCOUNT_PATTERN,
    LOT_PATTERN,
    ExtractedLine,
    clean_text,
)

TOLERANCE = Decimal("0.05")

TOTAL_LINE_RE = re.compile(
    r"^(total|tot\b|montant|net\b|reste|sous[-\s]?total|arr[êe]t|timbre|tva|pay[ée]|remise|ristourne|rabais)",
    re.IGNORECASE,
)

HEADER_KEYS = {
    "packages": {"colis", "colisage", "pack", "pkgs", "nbc", "nbrcolis"},
    "quantity": {"qnt", "qte", "qté", "qte.", "quantite", "quantité", "qty", "nbr", "nb"},
    "unit_price": {"pu", "p.u", "p.u.", "puht", "prix", "prixu", "p.unit", "punitaire"},
    "vat": {"tva", "vat", "taux"},
    "total": {"total", "montant", "totalht", "tot.", "tot", "montantht"},
    "discount": {"remise", "rem", "ristourne", "rabais"},
}

def _words(line: OcrLine) -> list[dict[str, Any]]:
    words = list(getattr(line, "words", None) or [])
    if words:
        return sorted(words, key=lambda item: item["x0"])
    bbox = line.bbox or {}
    tokens = [token for token in line.text.split() if token]
    if not tokens or not bbox:
        return []
    x0, x1 = float(bbox.get("x0", 0.0)), float(bbox.get("x1", 1.0))
    y0, y1 = float(bbox.get("y0", 0.0)), float(bbox.get("y1", 0.0))
    step = (x1 - x0) / max(1, len(tokens))
    return [
        {"text": token, "x0": x0 + i * step, "x1": x0 + (i + 1) * step, "y0": y0, "y1": y1}
        for i, token in enumerate(tokens)
    ]


def _anchors(line: OcrLine) -> dict[str, tuple[float, float]] | None:
    found: dict[str, tuple[float, float]] = {}
    for word in _words(line):
        key = word["text"].lower().strip(".:*()")
        for column, keys in HEADER_KEYS.items():
            if key in keys and column not in found:
                found[column] = (float(word["x0"]), float(word["x1"]))
    if "unit_price" not in found or "total" not in found:
        return None
    return found


def _is_header(line: OcrLine) -> bool:
    lowered = line.text.lower()
    if "total" not in lowered and "prix" not in lowered and "pu" not in lowered:
        return False
    hits = sum(1 for keys in HEADER_KEYS.values() for key in keys if key in lowered.split())
    return hits >= 2 or ("prix" in lowered and "total" in lowered)


def _amount(cell: str) -> Decimal | None:
    token = re.sub(r"[\s\u00a0\u202f]", "", cell.strip())
    token = token.strip("|:;")
    if not re.fullmatch(r"[+-]?\d[\d.,]*", token):
        return None
    return parse_decimal(token)


STRICT_COLISAGE = re.compile(r"(?<![\d.,])(\d{1,6}(?:[.,]\d{1,3})?)\s*[xX]\s*\d{1,4}(?![\d])")


def _decimal_from_printed(raw: str) -> Decimal | None:
    """« 6.091 » / « 6,091 » = six unités et 91 millièmes (jamais six mille)."""
    cleaned = raw.strip().replace(" ", "")
    if not cleaned:
        return None
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _token_quantity(token: str) -> Decimal | None:
    match = re.fullmatch(r"(\d{1,6}(?:[.,]\d{1,3})?)[xX]\d{1,4}", token.strip())
    if not match:
        return None
    value = _decimal_from_printed(match.group(1))
    if value is None or value <= 0 or value > Decimal("100000"):
        return None
    return value


def _plausible_price(value: Decimal) -> bool:
    return Decimal("0.01") <= value <= Decimal("1000000")


def _repair(
    qty_from_colisage: bool,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    total: Decimal | None,
) -> tuple[Decimal | None, Decimal | None, bool]:
    """Remet d'aplomb prix et total quand l'OCR a mangé la virgule.

    Tesseract lit régulièrement « 265,00 » comme « 26500 » et « 2 070,94 » comme
    « 207094 ». On teste les décalages décimaux (÷10, ÷100, ÷1000) et on retient la
    combinaison qui vérifie quantité × prix = total.
    """
    if quantity is None or total is None or unit_price is None:
        if quantity is not None and unit_price is not None and total is None:
            return unit_price, (quantity * unit_price).quantize(Decimal("0.01")), True
        if quantity is None and unit_price and total is not None:
            ratio = (total / unit_price).quantize(Decimal("0.001"))
            if Decimal("0") < ratio <= Decimal("100000"):
                return unit_price, total, abs(ratio * unit_price - total) <= TOLERANCE
        return unit_price, total, False

    def tolerance(value: Decimal) -> Decimal:
        return max(TOLERANCE, abs(value) * Decimal("0.002"))

    if abs(quantity * unit_price - total) <= tolerance(total):
        return unit_price, total, True

    candidates_price = [unit_price]
    candidates_total = [total]
    for factor in (Decimal(10), Decimal(100), Decimal(1000)):
        shifted_price = (unit_price / factor).quantize(Decimal("0.01")) if unit_price else None
        shifted_total = (total / factor).quantize(Decimal("0.01")) if total else None
        if shifted_price is not None and _plausible_price(shifted_price):
            candidates_price.append(shifted_price)
        if shifted_total is not None and shifted_total > 0:
            candidates_total.append(shifted_total)

    best: tuple[Decimal, Decimal, Decimal] | None = None
    for price in candidates_price:
        for amount in candidates_total:
            gap = abs(quantity * price - amount)
            if gap <= tolerance(amount) and (best is None or gap < best[0]):
                best = (gap, price, amount)
    if best is not None:
        return best[1], best[2], True

    # Dernier recours : la quantité imprimée est fiable → on recale le prix sur le total.
    if qty_from_colisage and quantity:
        repaired = (total / quantity).quantize(Decimal("0.01"))
        if _plausible_price(repaired):
            return repaired, total, abs(quantity * repaired - total) <= tolerance(total)

    return unit_price, total, False


def _data_anchors(
    lines: list[OcrLine], header: OcrLine, header_anchors: dict[str, tuple[float, float]]
) -> dict[str, tuple[float, float]]:
    """Recale les colonnes sur les montants réellement imprimés.

    Les en-têtes sont souvent décalés de quelques millimètres par rapport aux chiffres ;
    en regroupant les centres horizontaux des nombres (1-D k-means), on retrouve les
    vraies colonnes, ce qui évite de coller « 24 » (quantité) à « 450,00 » (prix).
    """
    header_y = (header.bbox or {}).get("y0", 0.0)
    points: list[float] = []
    for line in lines:
        if (line.bbox or {}).get("y0", 0.0) <= header_y:
            continue
        if TOTAL_LINE_RE.match(line.text.lower()):
            continue
        for word in _words(line):
            if re.search(r"\d", word["text"]):
                points.append((float(word["x0"]) + float(word["x1"])) / 2)
    if len(points) < 8:
        return header_anchors

    ordered_header = sorted(header_anchors.items(), key=lambda item: (item[1][0] + item[1][1]) / 2)
    k = len(ordered_header)
    centers = [((x0 + x1) / 2) for _, (x0, x1) in ordered_header]
    for _ in range(15):
        clusters: list[list[float]] = [[] for _ in centers]
        for point in points:
            index = min(range(len(centers)), key=lambda i: abs(point - centers[i]))
            clusters[index].append(point)
        updated = [mean(cluster) if cluster else centers[i] for i, cluster in enumerate(clusters)]
        if all(abs(updated[i] - centers[i]) < 0.001 for i in range(k)):
            centers = updated
            break
        centers = updated

    anchors: dict[str, tuple[float, float]] = {}
    for (column, _), center in zip(ordered_header, centers):
        anchors[column] = (center - 0.01, center + 0.01)
    return anchors


def _split_columns(anchors: dict[str, tuple[float, float]]) -> list[tuple[float, float, str]]:
    """Renvoie [(début, fin, colonne)] en se basant sur les boîtes d'en-tête.

    Les frontières se placent au milieu de l'espace vide entre deux colonnes, ce qui
    laisse la désignation à gauche de la première colonne chiffrée.
    """
    ordered = sorted(anchors.items(), key=lambda item: (item[1][0] + item[1][1]) / 2)
    regions: list[tuple[float, float, str]] = []
    for index, (column, (x0, x1)) in enumerate(ordered):
        if index == 0:
            start = max(-0.5, x0 - 0.02)
        else:
            start = (ordered[index - 1][1][1] + x0) / 2
        if index == len(ordered) - 1:
            end = 1.5
        else:
            end = (x1 + ordered[index + 1][1][0]) / 2
        regions.append((start, end, column))
    return regions


def _column_of(center: float, regions: list[tuple[float, float, str]]) -> str:
    for start, end, column in regions:
        if center < end:
            return column if center >= start else "designation"
    return "total"


def _build_line(
    row: OcrLine,
    anchors: dict[str, tuple[float, float]],
    pending: str | None,
) -> ExtractedLine | None:
    regions = _split_columns(anchors)
    cells: dict[str, list[str]] = {
        "designation": [],
        "packages": [],
        "quantity": [],
        "unit_price": [],
        "vat": [],
        "total": [],
        "discount": [],
    }
    for word in _words(row):
        center = (float(word["x0"]) + float(word["x1"])) / 2
        cells[_column_of(center, regions)].append(word["text"])

    designation = clean_text(" ".join(cells["designation"])).strip(" -:;|.")
    if pending:
        designation = f"{pending} {designation}".strip()

    unit_price = _amount(" ".join(cells["unit_price"]))
    total = _amount(" ".join(cells["total"]))
    packages = _amount(" ".join(cells["packages"])) if cells["packages"] else None
    vat_rate = _amount(" ".join(cells["vat"])) if cells["vat"] else None
    if unit_price is None and total is None:
        return None

    # La quantité entre parenthèses « 4X1 » / « 6.091X1 » est le colisage imprimé :
    # c'est la donnée la plus fiable de la ligne, on ne la déduit jamais d'autre chose.
    quantity = None
    qty_from_colisage = False
    for token in cells["quantity"]:
        token_quantity = _token_quantity(token)
        if token_quantity is not None:
            quantity = token_quantity
            qty_from_colisage = True
            break
    if not qty_from_colisage:
        strict = STRICT_COLISAGE.search(row.text)
        if strict:
            quantity = _decimal_from_printed(strict.group(1))
            qty_from_colisage = quantity is not None and Decimal("0") < quantity <= Decimal("100000")
    if not qty_from_colisage and cells["quantity"]:
        candidate = _amount(" ".join(cells["quantity"]))
        if candidate is not None and candidate > 0:
            quantity = candidate

    unit_price, total, coherent = _repair(qty_from_colisage, quantity, unit_price, total)
    if total is None and unit_price is None:
        return None

    if not re.search(r"[A-Za-zÀ-ÿ]{2,}", designation):
        # Libellé illisible mais montants et colisage présents : mieux vaut une ligne à
        # compléter qu'une ligne manquante (risque d'oubli sur la facture).
        if STRICT_COLISAGE.search(row.text) is None or total is None or quantity is None:
            return None
        designation = "Article à compléter"
        weak_designation = True
    else:
        weak_designation = len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", designation)) < 2

    lot_match = LOT_PATTERN.search(row.text)
    discount_match = DISCOUNT_PATTERN.search(row.text)
    reference_match = re.match(r"^([A-Z0-9]{2,}[-/][A-Z0-9/\-]+)\s+", row.text)
    if reference_match:
        designation = re.sub(
            r"^" + re.escape(reference_match.group(1)) + r"\s+",
            "",
            designation,
        ).strip()

    return ExtractedLine(
        raw_reference=reference_match.group(1) if reference_match else None,
        designation=designation,
        lot_number=lot_match.group(1) if lot_match else None,
        packages=packages,
        quantity=quantity,
        unit_price_ht=unit_price,
        vat_rate=vat_rate,
        line_total_ht=total,
        discount_value=parse_decimal(discount_match.group(1)) if discount_match else None,
        discount_type=("percent" if discount_match and discount_match.group(2) else "value") if discount_match else None,
        confidence={
            "global": (0.9 if coherent else 0.6) if not weak_designation else 0.45,
            "reference": 0.8 if reference_match else 0.0,
            "designation": 0.85,
            "quantity": 0.9 if quantity is not None else 0.0,
            "unit_price": 0.9 if unit_price is not None else 0.0,
            "total": 0.9 if total is not None else 0.0,
            "lot": 0.7 if lot_match else 0.0,
            "packages": 0.0,
        },
        source_page=row.page_number,
        source_bbox=row.bbox,
        original_text=row.text,
    )


def parse_table_rows(lines: list[OcrLine], min_rows: int = 2) -> list[ExtractedLine] | None:
    """Retourne les lignes reconstruites, ou None si aucun tableau crédible."""
    if not lines:
        return None
    positioned = sum(1 for line in lines if getattr(line, "words", None))
    if positioned < max(2, len(lines) // 2):
        return None

    by_page: dict[int, list[OcrLine]] = {}
    for line in lines:
        by_page.setdefault(line.page_number, []).append(line)

    results: list[ExtractedLine] = []
    for page_number in sorted(by_page):
        page_lines = sorted(by_page[page_number], key=lambda item: (item.bbox or {}).get("y0", 0))
        anchors: dict[str, float] | None = None
        header_y = -1.0
        for index, line in enumerate(page_lines):
            if _is_header(line):
                candidate = _anchors(line)
                if candidate:
                    anchors = _data_anchors(page_lines, line, candidate)
                    header_y = (line.bbox or {}).get("y0", 0.0)
                    break

        if anchors is None:
            continue

        pending: str | None = None
        for line in page_lines:
            y0 = (line.bbox or {}).get("y0", 0.0)
            if y0 <= header_y or _is_header(line):
                continue
            lowered = line.text.lower()
            if TOTAL_LINE_RE.match(lowered):
                continue
            if not re.search(r"\d", line.text):
                text = clean_text(line.text).strip(" -:;|.")
                if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", text)) >= 2:
                    pending = f"{pending} {text}".strip() if pending else text
                continue
            built = _build_line(line, anchors, pending)
            if built is None:
                continue
            pending = None
            results.append(built)

    if len(results) < min_rows:
        return None
    return results
