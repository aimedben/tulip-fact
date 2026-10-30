from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ImportBatch, Product, Supplier
from ..normalization import name_key, parse_decimal, strip_accents


class ImportFormatError(ValueError):
    def __init__(self, message: str, missing: list[str] | None = None):
        super().__init__(message)
        self.missing = missing or []


def _header_key(value: Any) -> str:
    text = strip_accents(str(value or "")).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


SUPPLIER_COLUMNS = {
    "code": ["code", "code fournisseur", "code frs", "code tiers", "code auxiliaire", "compte"],
    "name": ["nom", "nom fournisseur", "raison sociale", "intitule", "designation", "fournisseur"],
    "variants": ["variantes", "variantes connues", "alias", "autres noms", "noms alternatifs"],
    "tax_id": ["nif", "numero fiscal", "identifiant fiscal", "matricule fiscal", "mf"],
    "phone": ["telephone", "tel", "phone"],
    "email": ["email", "mail", "courriel"],
    "address": ["adresse", "address"],
    "notes": ["notes", "commentaire"],
}

PRODUCT_COLUMNS = {
    "tulip_code": ["code article", "code tulip", "code", "reference tulip", "code produit", "code article tulip"],
    "supplier_ref": ["reference fournisseur", "ref fournisseur", "ref frs", "reference frs", "code fournisseur article"],
    "barcode": ["code barre", "code barres", "code barre ean", "ean", "ean13", "gencod"],
    "designation": ["designation", "libelle", "nom article", "produit", "designation article"],
    "brand": ["marque", "brand"],
    "packaging": ["conditionnement", "colisage", "packaging"],
    "stock_unit": ["unite", "unite de stock", "unite stock", "unite de mesure", "um"],
    "default_vat_rate": ["tva", "taux tva", "tva habituelle", "taux de tva"],
}


def _map_headers(headers: list[str], mapping: dict[str, list[str]], required: list[str]) -> dict[str, int]:
    normalized = [_header_key(header) for header in headers]
    result: dict[str, int] = {}
    for field_name, synonyms in mapping.items():
        for index, header in enumerate(normalized):
            if header in synonyms:
                result[field_name] = index
                break
    missing = [field_name for field_name in required if field_name not in result]
    if missing:
        readable = {"code": "Code fournisseur", "name": "Nom fournisseur", "tulip_code": "Code article Tulip", "designation": "Désignation"}
        raise ImportFormatError(
            "Colonnes obligatoires manquantes : " + ", ".join(readable.get(item, item) for item in missing),
            missing=missing,
        )
    return result


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_csv(data: bytes) -> tuple[list[str], list[list[Any]]]:
    text = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ImportFormatError("Impossible de décoder le fichier CSV.")
    sample = text[:4096]
    delimiter = ";"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        counts = {candidate: sample.count(candidate) for candidate in (";", ",", "\t")}
        delimiter = max(counts, key=counts.get) if any(counts.values()) else ";"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [row for row in reader]
    if not rows:
        raise ImportFormatError("Le fichier CSV est vide.")
    return rows[0], rows[1:]


def read_table(path: Path) -> tuple[list[str], list[list[Any]]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path.read_bytes())
    if suffix in {".xlsx", ".xlsm"}:
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            raise ImportFormatError(f"Le fichier Excel est illisible : {exc}") from exc
        sheet = workbook.active
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        workbook.close()
        if not rows:
            raise ImportFormatError("Le fichier Excel est vide.")
        return [_cell_to_text(cell) for cell in rows[0]], rows[1:]
    raise ImportFormatError("Format de catalogue non pris en charge. Utilisez CSV ou XLSX.")


def _row_value(row: list[Any], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return _cell_to_text(row[index])


def import_suppliers(db: Session, path: Path, filename: str) -> ImportBatch:
    headers, rows = read_table(path)
    mapping = _map_headers(headers, SUPPLIER_COLUMNS, ["code", "name"])
    batch = ImportBatch(kind="suppliers", filename=filename, total_rows=len(rows), errors=[])
    seen: set[str] = set()
    imported = 0
    skipped = 0
    for row_number, row in enumerate(rows, start=2):
        code = _row_value(row, mapping.get("code"))
        name = _row_value(row, mapping.get("name"))
        if not code and not name and not any(_cell_to_text(cell) for cell in row):
            continue
        if not code or not name:
            skipped += 1
            batch.errors.append(
                {
                    "row": row_number,
                    "field": "code" if not code else "name",
                    "message": "Code fournisseur et nom sont obligatoires.",
                }
            )
            continue
        if code in seen:
            skipped += 1
            batch.errors.append({"row": row_number, "field": "code", "message": f"Code « {code} » en doublon dans le fichier."})
            continue
        seen.add(code)
        variants_raw = _row_value(row, mapping.get("variants"))
        variants = [item.strip() for item in re.split(r"[|;/]", variants_raw) if item.strip()]
        supplier = db.scalar(select(Supplier).where(Supplier.code == code))
        if supplier is None:
            supplier = Supplier(code=code, name=name, normalized_name=name_key(name))
            db.add(supplier)
        supplier.name = name
        supplier.normalized_name = name_key(name)
        merged = list(dict.fromkeys([*(supplier.name_variants or []), *variants]))
        supplier.name_variants = merged
        supplier.tax_id = _row_value(row, mapping.get("tax_id")) or supplier.tax_id
        supplier.phone = _row_value(row, mapping.get("phone")) or supplier.phone
        supplier.email = _row_value(row, mapping.get("email")) or supplier.email
        supplier.address = _row_value(row, mapping.get("address")) or supplier.address
        supplier.notes = _row_value(row, mapping.get("notes")) or supplier.notes
        imported += 1
    batch.imported_rows = imported
    batch.skipped_rows = skipped
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def import_products(db: Session, path: Path, filename: str) -> ImportBatch:
    headers, rows = read_table(path)
    mapping = _map_headers(headers, PRODUCT_COLUMNS, ["tulip_code", "designation"])
    batch = ImportBatch(kind="products", filename=filename, total_rows=len(rows), errors=[])
    seen: set[str] = set()
    imported = 0
    skipped = 0
    for row_number, row in enumerate(rows, start=2):
        code = _row_value(row, mapping.get("tulip_code"))
        designation = _row_value(row, mapping.get("designation"))
        if not code and not designation and not any(_cell_to_text(cell) for cell in row):
            continue
        if not code or not designation:
            skipped += 1
            batch.errors.append(
                {
                    "row": row_number,
                    "field": "tulip_code" if not code else "designation",
                    "message": "Code article Tulip et désignation sont obligatoires.",
                }
            )
            continue
        if code in seen:
            skipped += 1
            batch.errors.append({"row": row_number, "field": "tulip_code", "message": f"Code article « {code} » en doublon dans le fichier."})
            continue
        seen.add(code)
        vat_raw = _row_value(row, mapping.get("default_vat_rate"))
        vat = parse_decimal(vat_raw) if vat_raw else None
        product = db.scalar(select(Product).where(Product.tulip_code == code))
        if product is None:
            product = Product(tulip_code=code, designation=designation, normalized_designation=name_key(designation))
            db.add(product)
        product.designation = designation
        product.normalized_designation = name_key(designation)
        product.supplier_ref = _row_value(row, mapping.get("supplier_ref")) or None
        product.barcode = _row_value(row, mapping.get("barcode")) or None
        product.brand = _row_value(row, mapping.get("brand")) or None
        product.packaging = _row_value(row, mapping.get("packaging")) or None
        product.stock_unit = _row_value(row, mapping.get("stock_unit")) or None
        product.default_vat_rate = vat
        imported += 1
    batch.imported_rows = imported
    batch.skipped_rows = skipped
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch
