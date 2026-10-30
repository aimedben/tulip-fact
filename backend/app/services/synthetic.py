"""Documents et référentiels clairement fictifs, réservés aux tests et au mode DEMO."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, Supplier
from ..normalization import name_key

DEMO_SUPPLIER_CODE = "DEMO-F001"
DEMO_SUPPLIER_NAME = "DEMO FOURNITURES SARL"
DEMO_PRODUCTS = [
    {
        "tulip_code": "DEMO-ART-001",
        "supplier_ref": "ART-001",
        "designation": "CAFE MOULU 500G",
        "packaging": "1 carton = 12 unités",
        "stock_unit": "UNITE",
        "default_vat_rate": "19",
        "barcode": "6130000000011",
    },
    {
        "tulip_code": "DEMO-ART-002",
        "supplier_ref": "ART-002",
        "designation": "THE VERT 200G",
        "packaging": "1 carton = 12 unités",
        "stock_unit": "UNITE",
        "default_vat_rate": "19",
        "barcode": "6130000000028",
    },
    {
        "tulip_code": "DEMO-ART-003",
        "supplier_ref": "ART-003",
        "designation": "SUCRE BLANC 1KG",
        "packaging": "1 carton = 10 unités",
        "stock_unit": "UNITE",
        "default_vat_rate": "19",
        "barcode": "6130000000035",
    },
]

INVOICE_LINES = [
    ("ART-001", "CAFE MOULU 500G", "LOT-A17", 2, 24, "450,00", "19", "10 800,00"),
    ("ART-002", "THE VERT 200G", "LOT-B04", 1, 12, "320,50", "19", "3 846,00"),
    ("ART-003", "SUCRE BLANC 1KG", "LOT-C09", 3, 36, "120,00", "19", "4 320,00"),
]
EXPECTED_TOTALS = {
    "total_ht": "18966.00",
    "vat_total": "3603.54",
    "timbre": "0.00",
    "total_ttc": "22569.54",
}


@dataclass
class SyntheticInvoice:
    path: Path
    supplier_name: str
    invoice_number: str
    invoice_date: str
    totals: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "supplier_name": self.supplier_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "totals": self.totals,
        }


def _header_text(number: str, date_fr: str) -> list[str]:
    return [
        DEMO_SUPPLIER_NAME,
        "Zone Industrielle, Lot 12, Alger - DOCUMENT FICTIF DE TEST",
        "NIF: 000216001234567   RC: 16/00-DEMO   Tel: 021 00 00 00",
        "",
        "FACTURE",
        f"N° Facture: {number}",
        f"Date facture: {date_fr}",
        "N° BC: BC-2026-118",
        "Date BC: 02/03/2026",
        "N° BL: BL-2026-090",
        "Date BL: 10/03/2026",
        "Devise: DZD",
        "",
    ]


def _line_text(item: tuple) -> str:
    reference, designation, lot, packages, qty, price, vat, total = item
    return (
        f"{reference:<9} {designation:<28} {lot:<11} {packages:>5} {qty:>5} "
        f"{price:>10} {vat:>5} {total:>12}"
    )


def _all_lines(number: str, date_fr: str) -> list[str]:
    return [
        *_header_text(number, date_fr),
        f"{'Réf.':<9} {'Désignation':<28} {'Lot':<11} {'Colis':>5} {'Qté':>5} {'PU HT':>10} {'TVA':>5} {'Montant HT':>12}",
        *[_line_text(item) for item in INVOICE_LINES],
        "",
        "Total HT: 18 966,00",
        "Remise: 0,00",
        "TVA 19%: 3 603,54",
        "Timbre: 0,00",
        "Total TTC: 22 569,54",
        "Document synthétique fictif - aucune valeur commerciale.",
    ]


def create_invoice_pdf(
    path: Path,
    number: str = "DEMO-FA-2026-001",
    date_fr: str = "12/03/2026",
    split_pages: bool = False,
) -> SyntheticInvoice:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    lines = _all_lines(number, date_fr)
    if split_pages:
        first = lines[:20]
        second = lines[20:]
        for chunk in (first, second):
            page = document.new_page()
            y = 55
            for text in chunk:
                page.insert_text((45, y), text, fontname="cour", fontsize=9)
                y += 16
    else:
        page = document.new_page()
        y = 55
        for text in lines:
            page.insert_text((45, y), text, fontname="cour", fontsize=9)
            y += 16
    document.save(path)
    document.close()
    return SyntheticInvoice(path=path, supplier_name=DEMO_SUPPLIER_NAME, invoice_number=number, invoice_date=date_fr, totals=dict(EXPECTED_TOTALS))


def create_invoice_png(
    path: Path,
    number: str = "DEMO-FA-2026-002",
    date_fr: str = "13/03/2026",
) -> SyntheticInvoice:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 2100, 2400
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path(r"C:\Windows\Fonts\cour.ttf")
    title_font_path = Path(r"C:\Windows\Fonts\courbd.ttf")
    try:
        font = ImageFont.truetype(str(font_path), 30)
        title_font = ImageFont.truetype(str(title_font_path), 34)
    except Exception:
        font = ImageFont.load_default()
        title_font = font

    y = 80
    for index, text in enumerate(_all_lines(number, date_fr)):
        active_font = title_font if index == 0 else font
        draw.text((80, y), text, fill="black", font=active_font)
        y += 45
    image.save(path, format="PNG")
    return SyntheticInvoice(path=path, supplier_name=DEMO_SUPPLIER_NAME, invoice_number=number, invoice_date=date_fr, totals=dict(EXPECTED_TOTALS))


def seed_demo_referential(db: Session) -> None:
    supplier = db.scalar(select(Supplier).where(Supplier.code == DEMO_SUPPLIER_CODE))
    if supplier is None:
        supplier = Supplier(
            code=DEMO_SUPPLIER_CODE,
            name=DEMO_SUPPLIER_NAME,
            normalized_name=name_key(DEMO_SUPPLIER_NAME),
            name_variants=["DEMO FOURNITURES", "FOURNITURES DEMO SARL"],
            tax_id="000216001234567",
            notes="Fournisseur fictif du mode DEMO.",
        )
        db.add(supplier)
    for data in DEMO_PRODUCTS:
        product = db.scalar(select(Product).where(Product.tulip_code == data["tulip_code"]))
        if product is None:
            product = Product(
                tulip_code=data["tulip_code"],
                supplier_ref=data["supplier_ref"],
                barcode=data["barcode"],
                designation=data["designation"],
                normalized_designation=name_key(data["designation"]),
                packaging=data["packaging"],
                stock_unit=data["stock_unit"],
                default_vat_rate=data["default_vat_rate"],
            )
            db.add(product)
    db.commit()
