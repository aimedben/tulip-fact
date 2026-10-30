from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

MONEY = Decimal("0.01")
PERCENT = Decimal("0.0001")


def dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def compute_line(line: Any) -> dict[str, Decimal | None]:
    quantity = dec(getattr(line, "quantity", None))
    unit_price = dec(getattr(line, "unit_price_ht", None))
    discount_value = dec(getattr(line, "discount_value", None))
    discount_type = getattr(line, "discount_type", None)
    extracted_total = dec(getattr(line, "line_total_ht_extracted", None))

    gross = None
    discount_amount = None
    net = None
    if quantity is not None and unit_price is not None:
        gross = money(quantity * unit_price)
        if discount_value is not None and discount_value > 0:
            if discount_type == "percent":
                discount_amount = money(gross * discount_value / Decimal("100"))
            else:
                discount_amount = money(discount_value)
            net = money(gross - (discount_amount or Decimal("0")))
        else:
            net = gross
    elif extracted_total is not None:
        net = money(extracted_total)

    return {
        "gross": gross,
        "discount": discount_amount,
        "net": net,
        "extracted": money(extracted_total),
    }


def _check(
    code: str,
    severity: str,
    message: str,
    *,
    field: str | None = None,
    line_position: int | None = None,
    expected: Any = None,
    actual: Any = None,
    difference: Any = None,
    source: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if field:
        payload["field"] = field
    if line_position is not None:
        payload["line_position"] = line_position
    if expected is not None:
        payload["expected"] = str(expected)
    if actual is not None:
        payload["actual"] = str(actual)
    if difference is not None:
        payload["difference"] = str(difference)
    if source:
        payload["source"] = source
    return payload


def verify_invoice(invoice: Any, tolerance: Decimal | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tolerance = tolerance if tolerance is not None else Decimal("0.05")
    checks: list[dict[str, Any]] = []
    totals_extracted: dict[str, Any] = getattr(invoice, "totals_extracted", None) or {}
    lines: Iterable[Any] = getattr(invoice, "lines", []) or []

    line_results: list[dict[str, Any]] = []
    computed_ht = Decimal("0")
    line_discount_total = Decimal("0")
    vat_bases: dict[Decimal, Decimal] = {}
    missing_vat: list[int] = []
    missing_amounts: list[int] = []
    computed_line_count = 0
    vat_consistency: list[str] = []

    for index, line in enumerate(lines, start=1):
        result = compute_line(line)
        position = getattr(line, "position", index) or index
        net = result["net"]
        extracted = result["extracted"]
        if net is not None:
            computed_ht += net
            computed_line_count += 1
        if result["discount"]:
            line_discount_total += result["discount"]

        if extracted is not None and net is not None:
            difference = abs(extracted - net)
            if difference > tolerance:
                checks.append(
                    _check(
                        "LIGNE_MONTANT_ECART",
                        "error",
                        "Écart entre le montant HT imprimé et le calcul quantité × prix unitaire.",
                        field="line_total_ht",
                        line_position=position,
                        expected=net,
                        actual=extracted,
                        difference=difference,
                        source="ligne",
                    )
                )
        elif extracted is None or net is None:
            missing_amounts.append(position)
            checks.append(
                _check(
                    "LIGNE_MONTANT_NON_VERIFIABLE",
                    "warning",
                    "Montant de ligne incomplet : le contrôle quantité × prix est impossible.",
                    field="line_total_ht",
                    line_position=position,
                )
            )

        rate = dec(getattr(line, "vat_rate", None))
        if rate is None:
            missing_vat.append(position)
        elif net is not None:
            vat_bases[rate] = vat_bases.get(rate, Decimal("0")) + net
            vat_consistency.append(str(position))

        quantity = dec(getattr(line, "quantity", None))
        if quantity is not None and quantity <= 0:
            checks.append(
                _check(
                    "LIGNE_QUANTITE_INVALIDE",
                    "error",
                    "La quantité doit être strictement positive.",
                    field="quantity",
                    line_position=position,
                )
            )

    computed_vat_lines: dict[str, Decimal] = {}
    computed_vat_total = Decimal("0")
    for rate, base in sorted(vat_bases.items()):
        vat_amount = money(base * rate / Decimal("100"))
        computed_vat_lines[str(rate.normalize())] = vat_amount
        computed_vat_total += vat_amount

    extracted_vat_total = dec(totals_extracted.get("vat_total"))
    extracted_breakdown = totals_extracted.get("vat_breakdown") or {}
    extracted_breakdown_dec: dict[str, Decimal] = {}
    for key, value in extracted_breakdown.items():
        parsed = dec(value)
        if parsed is not None:
            extracted_breakdown_dec[str(key)] = parsed

    vat_total_used = computed_vat_total if computed_vat_lines else (extracted_vat_total or Decimal("0"))
    if extracted_vat_total is not None and computed_vat_lines:
        vat_difference = abs(extracted_vat_total - computed_vat_total)
        if vat_difference > tolerance:
            checks.append(
                _check(
                    "TVA_TOTALE_ECART",
                    "error",
                    "La TVA extraite ne correspond pas à la ventilation calculée par taux.",
                    field="vat_total",
                    expected=computed_vat_total,
                    actual=extracted_vat_total,
                    difference=vat_difference,
                    source="tva",
                )
            )
    elif extracted_vat_total is None:
        checks.append(
            _check(
                "TVA_NON_EXTRAITE",
                "warning",
                "La TVA n'a pas été extraite ; elle est calculée à partir des taux de ligne.",
                field="vat_total",
                expected=computed_vat_total,
            )
        )

    for rate_key, extracted_amount in extracted_breakdown_dec.items():
        computed_amount = computed_vat_lines.get(rate_key)
        if computed_amount is None:
            checks.append(
                _check(
                    "TVA_TAUX_SANS_BASE",
                    "warning",
                    f"Un taux de TVA de {rate_key} % figure sur la facture sans base calculable dans les lignes.",
                    field="vat_breakdown",
                )
            )
            continue
        difference = abs(extracted_amount - computed_amount)
        if difference > tolerance:
            checks.append(
                _check(
                    "TVA_TAUX_ECART",
                    "warning",
                    f"Écart de TVA pour le taux {rate_key} %.",
                    field="vat_breakdown",
                    expected=computed_amount,
                    actual=extracted_amount,
                    difference=difference,
                    source="tva",
                )
            )

    if missing_vat:
        checks.append(
            _check(
                "TVA_LIGNE_MANQUANTE",
                "warning",
                "Certaines lignes n'ont pas de taux de TVA identifié : "
                + ", ".join(str(value) for value in missing_vat),
                field="vat_rate",
            )
        )
    if missing_amounts:
        checks.append(
            _check(
                "LIGNES_INCOMPLETES",
                "warning",
                "Des lignes sont incomplètes et n'ont pas pu être contrôlées intégralement.",
                field="line_total_ht",
            )
        )

    other_taxes = dec(totals_extracted.get("other_taxes")) or Decimal("0")
    timbre = dec(totals_extracted.get("timbre")) or Decimal("0")
    discount_total = dec(totals_extracted.get("discount_total"))
    extracted_ht = dec(totals_extracted.get("total_ht"))
    extracted_ttc = dec(totals_extracted.get("total_ttc"))

    computed_ht = money(computed_ht)
    computed_ttc = money(computed_ht + vat_total_used + other_taxes + timbre)

    if computed_line_count == 0:
        checks.append(
            _check(
                "AUCUNE_LIGNE_CALCULABLE",
                "error",
                "Aucune ligne complète ne permet de recalculer les totaux.",
                field="lines",
            )
        )

    if extracted_ht is not None:
        difference = abs(extracted_ht - computed_ht)
        if difference > tolerance:
            source = "total HT"
            message = "Le total HT extrait ne correspond pas à la somme des lignes."
            if discount_total and abs(extracted_ht - (computed_ht - discount_total)) <= tolerance:
                source = "remise globale"
                message = (
                    "Le total HT extrait correspond à la somme des lignes diminuée de la remise globale. "
                    "Vérifiez l'ordre d'application de la remise."
                )
            checks.append(
                _check(
                    "TOTAL_HT_ECART",
                    "error",
                    message,
                    field="total_ht",
                    expected=computed_ht,
                    actual=extracted_ht,
                    difference=difference,
                    source=source,
                )
            )
    else:
        checks.append(
            _check(
                "TOTAL_HT_NON_EXTRAIT",
                "warning",
                "Le total HT n'a pas été extrait ; la valeur calculée est proposée.",
                field="total_ht",
                expected=computed_ht,
            )
        )

    if extracted_ttc is not None:
        difference = abs(extracted_ttc - computed_ttc)
        if difference > tolerance:
            source = "total TTC"
            if extracted_ht is not None and abs(extracted_ht - computed_ht) > tolerance:
                source = "total HT"
            elif extracted_vat_total is not None and abs(extracted_vat_total - computed_vat_total) > tolerance:
                source = "TVA"
            checks.append(
                _check(
                    "TOTAL_TTC_ECART",
                    "error",
                    "Le total TTC extrait ne correspond pas au recalcul (HT + TVA + autres taxes + timbre).",
                    field="total_ttc",
                    expected=computed_ttc,
                    actual=extracted_ttc,
                    difference=difference,
                    source=source,
                )
            )
    else:
        checks.append(
            _check(
                "TOTAL_TTC_NON_EXTRAIT",
                "warning",
                "Le total TTC n'a pas été extrait ; la valeur calculée est proposée.",
                field="total_ttc",
                expected=computed_ttc,
            )
        )

    if extracted_ht is not None and extracted_ttc is not None:
        extracted_implied_vat = extracted_ttc - extracted_ht - other_taxes - timbre
        if extracted_implied_vat < 0:
            checks.append(
                _check(
                    "TOTAL_TTC_INFERIEUR_HT",
                    "error",
                    "Le total TTC extrait est inférieur au total HT : les totaux sont incohérents.",
                    field="total_ttc",
                    expected=extracted_ht,
                    actual=extracted_ttc,
                )
            )

    totals_calculated = {
        "total_ht": computed_ht,
        "line_discounts": money(line_discount_total),
        "discount_total_extracted": discount_total,
        "vat_breakdown": computed_vat_lines,
        "vat_total": money(computed_vat_total),
        "vat_total_used": money(vat_total_used),
        "other_taxes": money(other_taxes),
        "timbre": money(timbre),
        "total_ttc": computed_ttc,
        "line_count": computed_line_count,
    }

    return totals_calculated, checks


def check_summary(checks: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"error": 0, "warning": 0, "info": 0}
    for check in checks:
        severity = check.get("severity", "info")
        summary[severity] = summary.get(severity, 0) + 1
    return summary
