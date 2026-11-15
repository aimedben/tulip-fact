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

def _split_text(text: str, x0: float, x1: float, y0: float, y1: float) -> list[dict[str, Any]]:
    tokens = [token for token in text.split() if token]
    if len(tokens) <= 1:
        return [{"text": text.strip(), "x0": x0, "x1": x1, "y0": y0, "y1": y1}] if text.strip() else []
    widths = [max(1, len(token)) for token in tokens]
    total = float(sum(widths)) + max(0, len(tokens) - 1)
    span = x1 - x0
    result: list[dict[str, Any]] = []
    cursor = x0
    for token, width in zip(tokens, widths):
        token_span = span * (width + 1) / total
        result.append(
            {"text": token, "x0": cursor, "x1": min(x1, cursor + token_span), "y0": y0, "y1": y1}
        )
        cursor += token_span
    return result


def _words(line: OcrLine) -> list[dict[str, Any]]:
    words = list(getattr(line, "words", None) or [])
    result: list[dict[str, Any]] = []
    for word in words:
        text = str(word.get("text", ""))
        x0, x1 = float(word.get("x0", 0.0)), float(word.get("x1", 1.0))
        y0, y1 = float(word.get("y0", 0.0)), float(word.get("y1", 0.0))
        if len(text.split()) > 1:
            result.extend(_split_text(text, x0, x1, y0, y1))
        else:
            result.append({"text": text, "x0": x0, "x1": x1, "y0": y0, "y1": y1})
    if result:
        return sorted(result, key=lambda item: item["x0"])
    bbox = line.bbox or {}
    tokens = [token for token in line.text.split() if token]
    if not tokens or not bbox:
        return []
    return _split_text(
        line.text,
        float(bbox.get("x0", 0.0)),
        float(bbox.get("x1", 1.0)),
        float(bbox.get("y0", 0.0)),
        float(bbox.get("y1", 0.0)),
    )


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


STRICT_COLISAGE = re.compile(r"(?<![\d.,])(\d{1,6}(?:[.,]\d{1,3})?)\s*[xX]\s*(\d{1,4})(?![\d])")


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


COLISAGE_FIX = re.compile(r"(?<![\d.,])(\d{1,2}[.,]\d{1,3})\s*[?×\ufffd]\s*(\d{1,4})(?!\d)")


def _fix_colisage_glyphs(text: str) -> str:
    """« 6.091?1 » → « 6.091x1 » : l'OCR dégrade parfois le « X » de colisage."""
    return COLISAGE_FIX.sub(r"\1x\2", text)


def _token_quantity(token: str) -> Decimal | None:
    match = re.fullmatch(
        r"(\d{1,6}(?:[.,]\d{1,3})?)[xX]\d{1,4}", _fix_colisage_glyphs(token.strip())
    )
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
        # Prix absent mais quantité et total présents et cohérents : on déduit
        # le prix par l'arithmétique (total / quantité) quand le quotient est un
        # montant monétaire propre. La valeur dérivée reste tracée (warning
        # PRIX_DEDUIT_PAR_ARITHMETIQUE posé par l'appelant).
        if quantity is not None and quantity > 0 and total is not None and total > 0 and unit_price is None:
            derived = (total / quantity).quantize(Decimal("0.001"))
            rounded = derived.quantize(Decimal("0.01"))
            if _plausible_price(rounded) and abs(derived - rounded) <= Decimal("0.005"):
                repaired = (quantity * rounded).quantize(Decimal("0.01"))
                if abs(repaired - total) <= TOLERANCE:
                    return rounded, total, True
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
    numeric_rows = sum(
        1
        for line in lines
        if (line.bbox or {}).get("y0", 0.0) > header_y and re.search(r"\d", line.text) and not TOTAL_LINE_RE.match(line.text.lower())
    )
    if len(points) < 8 or numeric_rows < 6:
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

    for (column, (x0, x1)), center in zip(ordered_header, centers):
        if abs(center - (x0 + x1) / 2) > 0.08:
            return header_anchors

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
    words: list[dict[str, Any]] | None = None,
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
    for word in (words if words is not None else _words(row)):
        center = (float(word["x0"]) + float(word["x1"])) / 2
        column = _column_of(center, regions)
        if column != "designation" and re.search(r"[A-Za-z\u00c0-\u00ff]{2,}", word["text"]):
            column = "designation"
        cells[column].append(word["text"])

    designation = clean_text(" ".join(cells["designation"])).strip(" -:;|.")
    if pending:
        designation = f"{pending} {designation}".strip()
    designation = re.sub(
        r"\b(?:lot|n[°o]\s*lot)\s*[:#-]?\s*[A-Z0-9._/-]+",
        "",
        designation,
        flags=re.IGNORECASE,
    ).strip(" -:;|.")
    designation = re.sub(r"^[^0-9A-Za-z\u00c0-\u00ff]+", "", designation).strip()

    total = _amount(" ".join(cells["total"]))
    vat_rate = _amount(" ".join(cells["vat"])) if cells["vat"] else None

    # Colisage imprimé « 2X4 » : nombre de colis et contenance séparés.
    packages = None
    pack_multiplier = None
    if cells["packages"]:
        strict = STRICT_COLISAGE.search(_fix_colisage_glyphs(" ".join(cells["packages"])))
        if strict:
            packages = _decimal_from_printed(strict.group(1))
            pack_multiplier = _decimal_from_printed(strict.group(2))
        else:
            packages = _amount(" ".join(cells["packages"]))

    raw_unit_price = _amount(" ".join(cells["unit_price"]))
    if raw_unit_price is None and total is None:
        return None

    # Le prix imprimé a toujours des décimales ; les chiffres ajoutés à la main
    # sur la facture (ex. « 530 » dans la colonne Prix du bon de caisse) n'en ont
    # pas : on les écarte en priorité.
    def _has_decimals(token: str) -> bool:
        return bool(re.search(r"\d[.,]\d{1,2}\s*$", token.strip()))

    quantity_candidates = [
        {"token": token, "value": _amount(token)}
        for token in cells["quantity"]
        if _amount(token) is not None and _amount(token) > 0
    ]
    price_candidates = [
        {"token": token, "value": _amount(token)}
        for token in cells["unit_price"]
        if _amount(token) is not None
    ]

    unit_price = None
    for entry in price_candidates:
        if _has_decimals(entry["token"]):
            unit_price = entry["value"]
            if len([e for e in price_candidates if _has_decimals(e["token"])]) <= 1:
                break
    else:
        if price_candidates:
            unit_price = price_candidates[0]["value"]

    # La quantité imprimée dans sa colonne est prioritaire ; entre deux prix
    # plausibles, celui qui vérifie quantité × prix = montant gagne.
    quantity = None
    qty_from_colisage = False
    for entry in quantity_candidates:
        token_quantity = _token_quantity(entry["token"])
        if token_quantity is not None:
            # Cas rare « 4X1 » dans la colonne Quantité : multiplier × colis.
            quantity = token_quantity
            qty_from_colisage = True
            break
    if quantity is None and quantity_candidates:
        quantity = quantity_candidates[0]["value"]
    if quantity is not None and total is not None:
        decimal_prices = [e for e in price_candidates if _has_decimals(e["token"])]
        if len(decimal_prices) > 1:
            best = min(
                decimal_prices,
                key=lambda entry: abs(quantity * entry["value"] - total),
            )
            unit_price = best["value"]

    # Colisage en repli : « 2X4 » = 2 colis × 4 unités = 8 quantité.
    if not qty_from_colisage:
        strict = STRICT_COLISAGE.search(_fix_colisage_glyphs(row.text))
        if strict:
            strict_quantity = _decimal_from_printed(strict.group(1))
            if (
                strict_quantity is not None
                and Decimal("0") < strict_quantity <= Decimal("100000")
                and quantity in (None, packages)
            ):
                quantity = strict_quantity
                qty_from_colisage = True
        if (
            quantity is None
            and packages is not None
            and pack_multiplier is not None
            and packages > 0
        ):
            quantity = (packages * pack_multiplier).quantize(Decimal("0.001"))

        # Quantité décimale collée au prix par l'OCR (« 2.996X155000 » =
        # « 2.996X1 550,00 ») : le préfixe collé au X est la quantité — on ne
        # l'accepte qu'avec 1 à 4 décimales, quantité absente par ailleurs.
        if quantity is None:
            stuck = re.search(
                r"(?<![\d.,])(\d{1,3}[.,]\d{1,4})\s*[xX×]", row.text
            )
            if stuck:
                # « 2.996 » dans « 2.996X155000 » : 1 à 4 digits après le
                # séparateur, ce n'est pas un séparateur milliers mais une
                # décimale (quantité en kg ou unités fractionnaires).
                stuck_quantity = Decimal(stuck.group(1).replace(",", "."))
                if Decimal("0") < stuck_quantity < Decimal("100"):
                    quantity = stuck_quantity

    ocr_total = total  # valeur OCR d'origine, conservée pour la traçabilité
    lot_match = LOT_PATTERN.search(row.text)
    discount_match = DISCOUNT_PATTERN.search(row.text)
    reference_match = re.match(r"^([A-Z0-9]{2,}[-/][A-Z0-9/\-]+)\s+", row.text)
    if reference_match:
        designation = re.sub(
            r"^" + re.escape(reference_match.group(1)) + r"\s+",
            "",
            designation,
        ).strip()

    unit_price, total, coherent = _repair(qty_from_colisage, quantity, unit_price, total)
    if total is None and unit_price is None:
        return None

    line_warnings: list[dict[str, Any]] = []

    # Total HT calculé automatiquement : quand la quantité et le prix unitaire
    # sont fiables mais que le total imprimé est absent ou imprécis (virgule
    # mangée par l'OCR), la valeur livrée est quantité × prix unitaire. La
    # valeur OCR d'origine reste tracée dans le warning.
    recalculated = False
    if (
        not coherent
        and quantity is not None
        and quantity > 0
        and unit_price is not None
        and discount_match is None  # remise : « qte × PU ≠ total » est légitime
    ):
        total = (quantity * unit_price).quantize(Decimal("0.01"))
        recalculated = True
        line_warnings.append(
            {
                "code": "TOTAL_RECALCULE",
                "severity": "warning",
                "message": (
                    "Total HT recalculé automatiquement (quantité × prix unitaire). "
                    f"Valeur OCR d'origine : {ocr_total if ocr_total is not None else 'absente'}."
                ),
                "original_total": str(ocr_total) if ocr_total is not None else None,
            }
        )
        coherent = True
    elif (
        coherent
        and ocr_total is None
        and total is not None
        and quantity is not None
        and unit_price is not None
    ):
        # Total absent de l'OCR : calculé, tracé à titre informatif.
        line_warnings.append(
            {
                "code": "TOTAL_CALCULE",
                "severity": "info",
                "message": "Total HT absent de l'OCR, calculé par quantité × prix unitaire.",
            }
        )

    if not re.search(r"[A-Za-zÀ-ÿ]{2,}", designation):
        # Libellé illisible mais montants et colisage présents : mieux vaut une ligne à
        # compléter qu'une ligne manquante (risque d'oubli sur la facture).
        if STRICT_COLISAGE.search(_fix_colisage_glyphs(row.text)) is None or total is None or quantity is None:
            return None
        designation = "Article à compléter"
        weak_designation = True
    else:
        weak_designation = len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", designation)) < 2

    price_derived = (
        quantity is not None
        and unit_price is not None
        and not any(_amount(token) for token in (cells["unit_price"] or []))
    )
    if price_derived:
        line_warnings.append(
            {
                "code": "PRIX_DEDUIT_PAR_ARITHMETIQUE",
                "severity": "info",
                "message": "Prix unitaire absent de l'OCR, déduit par quantité × prix = total.",
            }
        )

    confidence = {
        "global": (0.9 if coherent else 0.6) if not weak_designation else 0.45,
        "reference": 0.8 if reference_match else 0.0,
        "designation": 0.85,
        "quantity": 0.9 if quantity is not None else 0.0,
        "unit_price": 0.9 if unit_price is not None else 0.0,
        "total": 0.9 if total is not None else 0.0,
        "lot": 0.7 if lot_match else 0.0,
        "packages": 0.0,
    }
    if line_warnings:
        # Convention du pipeline : les warnings de ligne vivent dans la
        # configuration JSON de confiance (« _warnings »), comme
        # LIGNE_CALCUL_INCOHERENT côté pipeline.
        confidence["_warnings"] = line_warnings
    if recalculated:
        # Un montant issu d'un recalcul reste à vérifier par l'humain.
        confidence["global"] = min(confidence["global"], 0.7)

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
        confidence=confidence,
        source_page=row.page_number,
        source_bbox=row.bbox,
        original_text=row.text,
        warnings=line_warnings,
    )


def _cluster_rows(page_lines: list[OcrLine], header_y: float) -> list[list[dict[str, Any]]]:
    words: list[dict[str, Any]] = []
    for line in page_lines:
        y0 = (line.bbox or {}).get("y0", 0.0)
        if y0 <= header_y or _is_header(line):
            continue
        for word in _words(line):
            words.append(
                {
                    "text": word["text"],
                    "x0": float(word["x0"]),
                    "x1": float(word["x1"]),
                    "y0": float(word["y0"]),
                    "y1": float(word["y1"]),
                }
            )
    if not words:
        return []
    heights = sorted(max(1e-4, word["y1"] - word["y0"]) for word in words)
    median = heights[len(heights) // 2]
    tolerance = max(0.004, 0.5 * median)
    words.sort(key=lambda word: ((word["y0"] + word["y1"]) / 2, word["x0"]))
    rows: list[dict[str, Any]] = []
    for word in words:
        center = (word["y0"] + word["y1"]) / 2
        if rows and abs(center - rows[-1]["center"]) <= tolerance:
            rows[-1]["words"].append(word)
            group = rows[-1]["words"]
            rows[-1]["center"] = sum((item["y0"] + item["y1"]) / 2 for item in group) / len(group)
        else:
            rows.append({"center": center, "words": [word]})
    for row in rows:
        row["words"].sort(key=lambda word: word["x0"])
    return [row["words"] for row in rows]


SETTLED_LINE_RE = re.compile(
    r"^(?:anc\.?\s*solde|nouv\.?\s*solde|solde|verse(?:ment)?|rendu|especes?|vers[ée])\b",
    re.IGNORECASE,
)


def _rows_to_lines(
    rows: list[list[dict[str, Any]]],
    anchors: dict[str, tuple[float, float]],
    page_number: int,
) -> list[ExtractedLine]:
    output: list[ExtractedLine] = []
    pending: str | None = None
    for words in rows:
        text = " ".join(str(word["text"]) for word in words)
        if TOTAL_LINE_RE.match(text.lower()) or SETTLED_LINE_RE.match(clean_text(text).strip(" -:;|.")):
            continue
        if not re.search(r"\d", text):
            cleaned = clean_text(text).strip(" -:;|.")
            if len(re.findall(r"[A-Za-z\u00c0-\u00ff]{2,}", cleaned)) >= 2:
                pending = f"{pending} {cleaned}".strip() if pending else cleaned
            continue
        bbox = {
            "x0": min(word["x0"] for word in words),
            "y0": min(word["y0"] for word in words),
            "x1": max(word["x1"] for word in words),
            "y1": max(word["y1"] for word in words),
        }
        stub = OcrLine(text=text, page_number=page_number, bbox=bbox)
        built = _build_line(stub, anchors, pending, words=words)
        if built is None:
            continue
        pending = None
        output.append(built)
    return output


def parse_table_rows(lines: list[OcrLine], min_rows: int = 2) -> list[ExtractedLine] | None:
    """Retourne les lignes reconstruites, ou None si aucun tableau cr閐ible."""
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
        for line in page_lines:
            if _is_header(line):
                candidate = _anchors(line)
                if candidate:
                    if line.source == "pdf-text":
                        anchors = candidate
                    else:
                        anchors = _data_anchors(page_lines, line, candidate)
                    header_y = (line.bbox or {}).get("y0", 0.0)
                    break

        if anchors is None:
            continue

        by_line: list[ExtractedLine] = []
        pending: str | None = None
        for line in page_lines:
            y0 = (line.bbox or {}).get("y0", 0.0)
            if y0 <= header_y or _is_header(line):
                continue
            if TOTAL_LINE_RE.match(line.text.lower()):
                continue
            if SETTLED_LINE_RE.match(clean_text(line.text).strip(" -:;|.")):
                continue
            if not re.search(r"\d", line.text):
                text = clean_text(line.text).strip(" -:;|.")
                if len(re.findall(r"[A-Za-z\u00c0-\u00ff]{2,}", text)) >= 2:
                    pending = f"{pending} {text}".strip() if pending else text
                continue
            built = _build_line(line, anchors, pending)
            if built is None:
                continue
            pending = None
            by_line.append(built)

        by_words = _rows_to_lines(_cluster_rows(page_lines, header_y), anchors, page_number)
        results.extend(by_words if len(by_words) > len(by_line) else by_line)

    if len(results) < min_rows:
        return None
    return results
