"""Parser spécifique pour les tickets de caisse avec format multi-lignes.

Ce module gère les tickets où les produits et leurs montants sont sur des lignes séparées,
contrairement aux factures classiques où tout est sur une seule ligne.

Format typique:
    PRODUIT QTE U.G P.U
    PRODUIT A
    CONTINUATION A
    CONTINUATION A
    1X8 105,00          <- montants pour TOUS les produits ci-dessus
    PRODUIT B
    40 80 46,00         <- montants pour ce produit
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from ...normalization import parse_decimal, clean_text
from ..ocr.base import OcrLine
from .rules import ExtractedLine


def _is_header_line(text: str) -> bool:
    """Détecte l'en-tête du tableau de produits."""
    normalized = text.lower().strip()
    keywords = {'produit', 'qte', 'p.u', 'prix', 'designation'}
    return sum(1 for kw in keywords if kw in normalized) >= 2


def _is_totals_line(text: str) -> bool:
    """Détecte les lignes de totaux/pied de ticket."""
    normalized = text.lower().strip()
    keywords = ['total', 'solde', 'versement', 'payer', 'nbr produit']
    return any(kw in normalized for kw in keywords)


def _is_product_line(text: str) -> bool:
    """Détecte si une ligne est une désignation de produit (pas de montants)."""
    has_text = bool(re.search(r'[a-zA-ZÀ-ÿ]{2,}', text))
    if not has_text:
        return False
    # Si c'est une ligne de montants pure
    parsed = _parse_amount_line(text)
    if parsed:
        return False
    has_decimal_amount = bool(re.search(r'\d+[.,]\d{2}', text))
    if has_decimal_amount:
        letter_count = len(re.findall(r'[a-zA-ZÀ-ÿ]', text))
        digit_count = len(re.findall(r'\d', text))
        return letter_count > digit_count
    return True


def _inline_row_pattern() -> re.Pattern[str]:
    """Ligne de tableau avec montants sur la même ligne que la désignation.

    « BLITERE 8 ORANGE 1 LT       10    0.00 65,00 » : les trois derniers
    nombres sont quantité / PU / total. Exige au moins deux décimales marquées
    (PU ou total) pour ne pas avaler un nom de produit chiffré.
    """
    return re.compile(
        r"^(?P<desig>.*[A-Za-zÀ-ÿ].*?)\s+"
        r"(?P<qty>\d{1,6}(?:[.,]\d{1,3})?)\s+"
        r"(?P<pu>\d{1,10}(?:[.,]\d{1,2})?)\s+"
        r"(?P<res>\d{1,3}(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,3})?)\s*[|]?\s*$"
    )


def _parse_inline_row(text: str) -> dict[str, Any] | None:
    """Extrait {designation, quantity, unit_price_ht, line_total_ht, coherent}."""
    text = clean_text(text).strip()
    match = _inline_row_pattern().match(text)
    if not match:
        return None
    designation = match.group("desig").strip(" -:;|.")
    if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", designation)) < 2:
        return None
    quantity = parse_decimal(match.group("qty"))
    unit_price = parse_decimal(match.group("pu"))
    line_total = parse_decimal(match.group("res"))
    if quantity is None or line_total is None:
        return None
    coherent = (
        abs(quantity * unit_price - line_total) <= Decimal("0.05")
        if unit_price is not None and quantity > 0
        else False
    )
    return {
        "designation": designation,
        "quantity": quantity,
        "unit_price_ht": unit_price,
        "line_total_ht": line_total,
        "coherent": coherent,
    }


def _parse_amount_line(text: str) -> dict[str, Any] | None:
    """Parse une ligne de montants au format ticket.

    Formats supportés (le dernier nombre DOIT porter les décimales du prix) :
    - "105,00"                  -> 2 nombres : quantité, prix
    - "1X8 105,00"              -> 3 nombres : colisage, quantité, prix
    - "40 80 46,00"             -> 3 nombres : colisage, quantité, prix
    - "1 X 10 10 150,00"        -> 4 nombres : colisage, contenu, quantité, prix
    - "1 × 10 = 10 150,00"      -> 4 nombres (le multiplicateur × et le = sont
      ignorés) : colisage, contenu, quantité, prix

    Une décimale manquante sur le dernier nombre disqualifie la ligne : ce
    n'est pas un prix (évite d'avaler « 01/11/2026 11:02:17 » ou un N° BL).
    """
    text = clean_text(text).strip()
    if _is_totals_line(text):
        return None
    tokens = re.findall(r"\d+(?:[.,]\d+)?", text)
    if not tokens:
        return None
    # Le prix final porte forcément une décimale (les DZD s'écrivent 150,00).
    if not re.search(r"[.,]\d{1,3}$", tokens[-1]):
        return None

    count = len(tokens)
    values: list[Decimal] = []
    for token in tokens:
        value = parse_decimal(token)
        if value is None:
            return None
        values.append(value)

    if count >= 5:
        return None  # Trop de nombres : pas un format de ticket connu

    if len(values) == 2:
        quantity, unit_price = values
        if quantity > 0 and unit_price > 0 and quantity < 1000:
            return {
                "packages": None,
                "quantity": quantity,
                "unit_price_ht": unit_price,
                "line_total_ht": (quantity * unit_price).quantize(Decimal("0.01")),
                "coherent": True,
            }
        return None

    if len(values) == 3:
        packages, quantity, unit_price = values
        if packages >= 1000 or quantity <= 0 or quantity >= 1000 or unit_price <= 0:
            return None
        if not re.search(r"\d+\s*[xX×]\s*\d", text) and packages * quantity > quantity * 2:
            # Sans ×, un seul nombre guide la quantité (colisage facultatif).
            packages = None
        return {
            "packages": int(packages) if packages is not None else None,
            "quantity": quantity,
            "unit_price_ht": unit_price,
            "line_total_ht": (quantity * unit_price).quantize(Decimal("0.01")),
            "coherent": True,
        }

    # 4 nombres : colisage × contenu = quantité totale, prix
    packages, package_content, quantity, unit_price = values
    if quantity <= 0 or quantity >= 1000 or unit_price <= 0:
        return None
    coherent = abs(packages * package_content - quantity) <= Decimal("0.05")
    return {
        "packages": int(packages) if packages is not None and packages < 1000 else None,
        "quantity": quantity,
        "unit_price_ht": unit_price,
        "line_total_ht": (quantity * unit_price).quantize(Decimal("0.01")),
        "coherent": coherent,
    }


def _money_amounts(text: str) -> list[str]:
    """Montants type DA (« 1 060,00 », « 720,00 ») pas les heures ni les N°."""
    return re.findall(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})*[.,]\d{2}\b", text)


def _is_tabular_invoice(ordered_lines: list[OcrLine]) -> bool:
    """Facture A4 tabulaire plutôt que ticket thermaliculture.

    Sur une facture à colonnes, quantité, PU et total sont en double montant
    sur la MÊME ligne que la désignation ; sur un ticket multi-lignes, chaque
    ligne de montants ne porte qu'un seul prix. Dès que deux lignes portent
    deux montants, c'est un tableau : le parseur géométrique est mieux armé.
    """
    hits = sum(1 for line in ordered_lines if len(_money_amounts(line.text)) >= 2)
    return hits >= 2


def parse_ticket_multiline(ordered_lines: list[OcrLine]) -> list[ExtractedLine] | None:
    """Parse un ticket où produits et montants sont sur des lignes séparées.

    Format: PLUSIEURS lignes de produit → UNE ligne de montants → PLUSIEURS lignes de produit → etc.
    Exemple:
        TLI TLI 500GRS EXTRA
        COUDE3EXTRA500GRS
        PLUME 500 GRS EXTRA X10
        1X8 105,00           <- montants pour les 3 produits ci-dessus
        PAIN BURGER SENIOR 4PX12
        40 80 46,00          <- montants pour ce produit

    Retourne None si le format ne correspond pas à un ticket multi-lignes.
    Retourne une liste (possiblement vide) si c'est bien un ticket de ce type.
    """
    if not ordered_lines:
        return None

    # Vérifier si c'est bien un ticket avec en-tête "PRODUIT QTE P.U"
    full_text = '\n'.join(line.text for line in ordered_lines[:20])
    if not _is_header_line(full_text):
        return None

    # Facture tabulaire A4 : désignation + PU + total sur une même ligne.
    if _is_tabular_invoice(ordered_lines):
        return None

    extracted: list[ExtractedLine] = []
    i = 0
    product_group: list[tuple[OcrLine, str]] = []
    in_table = False
    last_amounts = None

    while i < len(ordered_lines):
        line = ordered_lines[i]
        text = line.text.strip()

        if not text:
            i += 1
            continue

        if _is_header_line(text):
            in_table = True
            i += 1
            continue

        if _is_totals_line(text):
            # Si on a des produits en attente et des montants récents, les attacher
            if product_group and last_amounts:
                if len(product_group) == 1:
                    prod_line, prod_text = product_group[0]
                    extracted.append(ExtractedLine(
                        raw_reference=None,
                        designation=prod_text[:255],
                        quantity=last_amounts['quantity'],
                        unit_price_ht=last_amounts['unit_price_ht'],
                        line_total_ht=last_amounts['line_total_ht'],
                        packages=last_amounts.get('packages'),
                        confidence={
                            'global': 0.75,
                            'designation': 0.75,
                            'quantity': 0.75,
                            'unit_price': 0.75,
                            'total': 0.75,
                            'coherent': last_amounts['coherent'],
                        },
                        source_page=prod_line.page_number,
                        source_bbox=prod_line.bbox,
                        original_text=f"{prod_text} | (from previous line)",
                        warnings=[],
                    ))
                else:
                    for prod_line, prod_text in product_group:
                        extracted.append(ExtractedLine(
                            raw_reference=None,
                            designation=prod_text[:255],
                            quantity=last_amounts['quantity'],
                            unit_price_ht=last_amounts['unit_price_ht'],
                            line_total_ht=last_amounts['line_total_ht'],
                            packages=last_amounts.get('packages'),
                            confidence={
                                'global': 0.75,
                                'designation': 0.75,
                                'quantity': 0.75,
                                'unit_price': 0.75,
                                'total': 0.75,
                                'coherent': last_amounts['coherent'],
                            },
                            source_page=prod_line.page_number,
                            source_bbox=prod_line.bbox,
                            original_text=f"{prod_text} | (from previous line)",
                            warnings=[],
                        ))
                product_group = []
                break
            for prod_line, prod_text in product_group:
                extracted.append(ExtractedLine(
                    raw_reference=None,
                    designation=prod_text[:255],
                    quantity=None,
                    unit_price_ht=None,
                    line_total_ht=None,
                    confidence={'global': 0.3, 'designation': 0.6},
                    source_page=prod_line.page_number,
                    source_bbox=prod_line.bbox,
                    original_text=prod_text,
                    warnings=[{
                        'code': 'MONTANTS_MANQUANTS',
                        'severity': 'warning',
                        'message': 'Quantité et prix non détectés pour ce produit.',
                    }],
                ))
            break

        if not in_table:
            i += 1
            continue

        # Vérifier si c'est une ligne de montants
        parsed_amounts = _parse_amount_line(text)
        if parsed_amounts and not _is_totals_line(text):
            last_amounts = parsed_amounts
            if product_group:
                if len(product_group) == 1:
                    prod_line, prod_text = product_group[0]
                    extracted.append(ExtractedLine(
                        raw_reference=None,
                        designation=prod_text[:255],
                        quantity=parsed_amounts['quantity'],
                        unit_price_ht=parsed_amounts['unit_price_ht'],
                        line_total_ht=parsed_amounts['line_total_ht'],
                        packages=parsed_amounts.get('packages'),
                        confidence={
                            'global': 0.85 if parsed_amounts['coherent'] else 0.60,
                            'designation': 0.75,
                            'quantity': 0.80,
                            'unit_price': 0.80,
                            'total': 0.80,
                            'coherent': parsed_amounts['coherent'],
                        },
                        source_page=line.page_number,
                        source_bbox=line.bbox,
                        original_text=f"{prod_text} | {text}",
                        warnings=[],
                    ))
                else:
                    for prod_line, prod_text in product_group:
                        extracted.append(ExtractedLine(
                            raw_reference=None,
                            designation=prod_text[:255],
                            quantity=parsed_amounts['quantity'],
                            unit_price_ht=parsed_amounts['unit_price_ht'],
                            line_total_ht=parsed_amounts['line_total_ht'],
                            packages=parsed_amounts.get('packages'),
                            confidence={
                                'global': 0.85 if parsed_amounts['coherent'] else 0.60,
                                'designation': 0.75,
                                'quantity': 0.80,
                                'unit_price': 0.80,
                                'total': 0.80,
                                'coherent': parsed_amounts['coherent'],
                            },
                            source_page=line.page_number,
                            source_bbox=line.bbox,
                            original_text=f"{prod_text} | {text}",
                            warnings=[],
                        ))
                product_group = []
            i += 1
            continue

        # Sinon c'est une ligne de produit - l'accumuler
        inline = _parse_inline_row(text) if in_table else None
        if inline:
            extracted.append(ExtractedLine(
                raw_reference=None,
                designation=inline['designation'][:255],
                quantity=inline['quantity'],
                unit_price_ht=inline['unit_price_ht'],
                line_total_ht=inline['line_total_ht'],
                confidence={
                    'global': 0.85 if inline['coherent'] else 0.60,
                    'designation': 0.75,
                    'quantity': 0.80,
                    'unit_price': 0.75,
                    'total': 0.85,
                    'coherent': inline['coherent'],
                },
                source_page=line.page_number,
                source_bbox=line.bbox,
                original_text=text,
                warnings=[],
            ))
            i += 1
            continue

        if _is_product_line(text):
            product_group.append((line, text))
            i += 1
            continue

        # Ligne non reconnue - passer
        i += 1

    # Sauvegarder les produits en attente s'il y en a
    for prod_line, prod_text in product_group:
        extracted.append(ExtractedLine(
            raw_reference=None,
            designation=prod_text[:255],
            quantity=None,
            unit_price_ht=None,
            line_total_ht=None,
            confidence={'global': 0.3, 'designation': 0.6},
            source_page=prod_line.page_number,
            source_bbox=prod_line.bbox,
            original_text=prod_text,
            warnings=[{
                'code': 'MONTANTS_MANQUANTS',
                'severity': 'warning',
                'message': 'Quantité et prix non détectés pour ce produit.',
            }],
        ))

    # Retourner les lignes extraites si on en a trouvé, sinon None
    return extracted if extracted else None
