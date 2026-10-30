from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.models import Invoice, InvoiceLine, Product, Supplier


class _Cfg:
    enabled = True
    configured = True
    database = "D:/Temp/superette.tfe"
    user = "sysdba"
    password = "x"
    isql_path = "C:/isql.exe"
    write_enabled = False

    def __init__(self, write_enabled: bool) -> None:
        self.write_enabled = write_enabled

    def public_status(self):
        return {"configured": True}


class FakeClient:
    def __init__(self, write_enabled: bool = False) -> None:
        self.config = _Cfg(write_enabled)
        self.queries: list[str] = []

    def query(self, sql, columns):
        self.queries.append(sql)
        if "GEN_ID(" in sql:
            return [{"NEXT_VALUE": "2408"}]
        if "MAX(NUMERO)" in sql:
            return [{"NEXT_NUM": "2408"}]
        if "COUNT(*)" in sql:
            return [{"USED": "0"}]
        if "PRODUITS P" in sql:
            return [
                {
                    "CODE": "-2147478181",
                    "REF": "MO01",
                    "DESIGNATION": "PRODUIT TEST",
                    "REF_O": None,
                    "LOT": None,
                    "TVA": "19",
                    "RECEP": "12",
                    "MPRIXRECEP": None,
                    "STOCK": "0",
                    "CMUP": None,
                    "UM": "UN",
                    "BARCODE": None,
                }
            ]
        return []

    def execute(self, sql):
        return "OK"


_SEED_COUNTER = {"n": 0}


def _seed(db) -> Invoice:
    _SEED_COUNTER["n"] += 1
    n = _SEED_COUNTER["n"]
    unique = f"a{n}".ljust(32, "0")
    supplier = Supplier(code=f"-214748334{n}", name="MOLFIX", normalized_name=f"molfix {n}")
    product = Product(
        tulip_code=f"MO{n:02d}",
        designation="PRODUIT TEST",
        normalized_designation=f"produit test {n}",
    )
    db.add_all([supplier, product])
    db.flush()
    invoice = Invoice(
        uuid=f"aaaaaaaa-1111-2222-3333-{unique[:12]}"[:36].replace("a", "a"),
        original_filename="facture.pdf",
        stored_path="x.pdf",
        sha256=unique[:64],
        file_size=100,
        mime_type="application/pdf",
        status="VALIDEE",
        supplier_id=supplier.id,
        invoice_number=f"FA-2026-{n:02d}",
        invoice_date=dt.date(2026, 10, 25),
        bc_number=f"BC-{n}",
        bc_date=dt.date(2026, 10, 24),
        bl_number=f"BL-{n}",
    )
    invoice.lines.append(
        InvoiceLine(
            position=1,
            raw_designation="PRODUIT TEST",
            quantity=Decimal("3"),
            unit_price_ht=Decimal("10.5"),
            vat_rate=Decimal("19"),
            discount_value=Decimal("5"),
            discount_type="value",
            tulip_product_id=product.id,
            match_status="RAPPROCHE",
        )
    )
    db.add(invoice)
    db.commit()
    return invoice


def test_tulip_be_dry_run_maps_invoice(db, client, monkeypatch):
    from app.api import invoices as api

    fake = FakeClient()
    monkeypatch.setattr(api, "firebird_client", lambda: fake)
    invoice = _seed(db)
    fournisseur = int(invoice.supplier.code)

    response = client.post(f"/api/invoices/{invoice.id}/tulip/be?dry_run=true")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["numero"] == 2408
    assert payload["fournisseur"] == fournisseur
    assert payload["nbc"] == invoice.bc_number
    lines = payload["lines"]
    assert len(lines) == 1
    assert lines[0]["product_code"] == -2147478181
    assert float(lines[0]["puht"]) == 10.5
    assert float(lines[0]["qte"]) == 3
    assert float(lines[0]["remise"]) == 5
    assert payload["skipped_lines"] == []


def test_tulip_be_blocked_when_invoice_not_validated(db, client, monkeypatch):
    from app.api import invoices as api

    monkeypatch.setattr(api, "firebird_client", lambda: FakeClient())
    invoice = _seed(db)
    invoice.status = "IMPORTEE"
    db.commit()

    response = client.post(f"/api/invoices/{invoice.id}/tulip/be?dry_run=true")
    assert response.status_code == 409


def test_tulip_be_refused_without_matched_lines(db, client, monkeypatch):
    from app.api import invoices as api

    fake = FakeClient()
    monkeypatch.setattr(api, "firebird_client", lambda: fake)
    invoice = _seed(db)
    line = invoice.lines[0]
    line.tulip_product_id = None
    db.commit()

    response = client.post(f"/api/invoices/{invoice.id}/tulip/be?dry_run=true")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["skipped_lines"][0]["reason"] == "PRODUIT_NON_RAPPROCHE"


def test_tulip_be_write_requires_enabled_flag(db, client, monkeypatch):
    from app.api import invoices as api

    monkeypatch.setattr(api, "firebird_client", lambda: FakeClient(write_enabled=False))
    invoice = _seed(db)

    response = client.post(f"/api/invoices/{invoice.id}/tulip/be?dry_run=false")
    assert response.status_code == 502
