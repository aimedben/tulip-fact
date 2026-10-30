from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from app.models import Invoice, InvoiceLine, Product, Supplier
from app.normalization import name_key
from app.services.matching.products import confirm_product, match_lines, suggest_products
from app.services.matching.suppliers import confirm_supplier, find_supplier_candidates


def test_supplier_candidates_prefer_exact_and_keep_leading_zero(db):
    supplier = Supplier(code="000700", name="ZETA DISTRIBUTION SARL", normalized_name=name_key("ZETA DISTRIBUTION SARL"))
    other = Supplier(code="000701", name="BETA COMMERCE", normalized_name=name_key("BETA COMMERCE"))
    db.add_all([supplier, other])
    db.commit()
    candidates = find_supplier_candidates(db, "Zeta Distribution Sarl", ["Zeta Distribution"])
    assert candidates[0]["code"] == "000700"
    assert candidates[0]["score"] >= 0.98
    assert candidates[0]["auto"] is True


def test_supplier_confirmation_learns_alias(db):
    supplier = Supplier(code="000702", name="GAMMA FOURNITURES", normalized_name=name_key("GAMMA FOURNITURES"))
    db.add(supplier)
    db.commit()
    invoice = Invoice(
        uuid="test-supplier-alias",
        original_filename="x.pdf",
        stored_path="x",
        sha256="a" * 64,
        file_size=1,
        mime_type="application/pdf",
        supplier_name_raw="GAMMA FOURNITURE",
        status="A_VERIFIER",
        header_raw={},
        totals_extracted={},
        totals_calculated={},
        checks=[],
        warnings=[],
        document_meta={},
        supplier_match={},
    )
    db.add(invoice)
    db.commit()
    confirm_supplier(db, invoice, supplier.id)
    db.commit()
    candidates = find_supplier_candidates(db, "GAMMA FOURNITURE")
    assert candidates[0]["method"] == "alias"
    assert candidates[0]["auto"] is True


def test_product_matching_order_and_no_invention(db):
    supplier = Supplier(code="S1", name="SUPPLIER ONE", normalized_name=name_key("SUPPLIER ONE"))
    db.add(supplier)
    db.flush()
    product = Product(
        tulip_code="T-001",
        supplier_ref="REF-100",
        barcode="6130000000100",
        designation="CAFE MOULU 500G",
        normalized_designation=name_key("CAFE MOULU 500G"),
    )
    db.add(product)
    db.commit()

    invoice = Invoice(
        uuid="test-product-match",
        original_filename="x.pdf",
        stored_path="x",
        sha256="b" * 64,
        file_size=1,
        mime_type="application/pdf",
        supplier_id=supplier.id,
        status="A_VERIFIER",
        header_raw={},
        totals_extracted={},
        totals_calculated={},
        checks=[],
        warnings=[],
        document_meta={},
        supplier_match={},
    )
    line = InvoiceLine(
        position=1,
        raw_reference="REF-100",
        raw_designation="CAFE MOULU 500 G",
        quantity=Decimal("1"),
        unit_price_ht=Decimal("100"),
        match_candidates=[],
        confidence={},
        original_values={},
    )
    unknown = InvoiceLine(
        position=2,
        raw_reference="ZZZ-999",
        raw_designation="ARTICLE TOTALEMENT INCONNU XYZ",
        quantity=Decimal("1"),
        unit_price_ht=Decimal("10"),
        match_candidates=[],
        confidence={},
        original_values={},
    )
    invoice.lines.extend([line, unknown])
    db.add(invoice)
    db.commit()

    match_lines(db, invoice)
    assert line.tulip_product_id == product.id
    assert line.match_status == "RAPPROCHE"
    assert unknown.tulip_product_id is None
    assert unknown.match_status in {"NON_RAPPROCHE", "SUGGERE"}


def test_fuzzy_suggestion_requires_confirmation(db):
    product = Product(
        tulip_code="T-500",
        designation="HUILE D'OLIVE 5L",
        normalized_designation=name_key("HUILE D'OLIVE 5L"),
    )
    db.add(product)
    db.commit()
    candidates = suggest_products(db, "HUILE OLIVE 5 L", "HUILE OLIVE 5 L")
    assert candidates
    assert candidates[0]["tulip_code"] == "T-500"
    assert candidates[0]["method"] in {"similarité désignation", "désignation exacte"}


def test_confirm_product_creates_alias_and_is_reused(db):
    supplier = Supplier(code="S2", name="SUPPLIER TWO", normalized_name=name_key("SUPPLIER TWO"))
    product = Product(tulip_code="T-777", designation="THE VERT 200G", normalized_designation=name_key("THE VERT 200G"))
    db.add_all([supplier, product])
    db.flush()
    invoice = Invoice(
        uuid="test-product-alias",
        original_filename="x.pdf",
        stored_path="x",
        sha256="c" * 64,
        file_size=1,
        mime_type="application/pdf",
        supplier_id=supplier.id,
        status="A_VERIFIER",
        header_raw={},
        totals_extracted={},
        totals_calculated={},
        checks=[],
        warnings=[],
        document_meta={},
        supplier_match={},
    )
    line = InvoiceLine(
        position=1,
        raw_designation="THE VERT PARFUME 200G",
        match_candidates=[],
        confidence={},
        original_values={},
    )
    invoice.lines.append(line)
    db.add(invoice)
    db.commit()
    confirm_product(db, invoice, line, product.id)
    db.commit()
    candidates = suggest_products(db, None, "THE VERT PARFUME 200G", supplier.id)
    assert candidates[0]["product_id"] == product.id
    assert candidates[0]["method"] == "correspondance confirmée"


