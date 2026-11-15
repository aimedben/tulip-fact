from __future__ import annotations

from decimal import Decimal

from app.models import Product
from app.normalization import name_key
from app.services.tulip.sync import sync_products


class FakeProductClient:
    def __init__(self, pages: list[list[dict]], total: int) -> None:
        self.pages = list(pages)
        self.total = total

    def query(self, sql, columns):
        return [{"TOTAL": str(self.total)}]

    def execute(self, sql):
        return "OK"


class FakeProductCatalog:
    def __init__(self, client: FakeProductClient) -> None:
        self.client = client

    def products(self, page: int = 1, page_size: int = 50):
        items = self.client.pages[page - 1] if page - 1 < len(self.client.pages) else []
        return {"items": items, "total": self.client.total, "page": page, "page_size": page_size}


def test_sync_products_creates_and_upserts(client, db):
    catalog = FakeProductCatalog(
        FakeProductClient(
            [
                [
                    {
                        "tulip_code": "BE72",
                        "designation": "BENTOUMIA ROTI DE VOLAILLE VRAC",
                        "supplier_ref": None,
                        "barcode": "6134495000338",
                        "packaging": "1",
                        "stock_unit": "U",
                        "default_vat_rate": 0.0,
                    },
                    {
                        "tulip_code": "LE76",
                        "designation": "LE MONT D'OR JUNIOR 3FR",
                        "supplier_ref": None,
                        "barcode": "6135231005198",
                        "packaging": "1",
                        "stock_unit": "U",
                        "default_vat_rate": 19.0,
                    },
                ],
            ],
            2,
        )
    )
    result = sync_products(db, catalog)
    assert result["created"] == 2
    assert result["total"] == 2
    assert result["local_total"] >= 2

    ben = db.query(Product).filter_by(tulip_code="BE72").one()
    assert ben.designation == "BENTOUMIA ROTI DE VOLAILLE VRAC"
    assert ben.barcode == "6134495000338"
    assert ben.default_vat_rate == Decimal("0.0")

    second = FakeProductCatalog(
        FakeProductClient(
            [
                [
                    {
                        "tulip_code": "BE72",
                        "designation": "BENTOUMIA ROTI VOLAILLE",
                        "barcode": "6134495000339",
                        "packaging": "1",
                        "stock_unit": "U",
                        "default_vat_rate": 9.0,
                    }
                ],
            ],
            1,
        )
    )
    result2 = sync_products(db, second)
    assert result2["created"] == 0
    assert result2["updated"] == 1
    assert ben.designation == "BENTOUMIA ROTI VOLAILLE"
    assert ben.barcode == "6134495000339"
    assert ben.default_vat_rate == Decimal("9.0")


def test_sync_matches_local_numeric_code_and_avoids_duplicate(client, db):
    """Le listing Tulip s'identifie par la REF (« ART12445 ») ; un article créé
    localement porte son code numérique (« 12445 »). Sans matching par code
    interne, chaque resynchronisation recréait l'article : doublon local."""
    local = Product(tulip_code="12445", designation="ramit", normalized_designation=name_key("ramit"))
    db.add(local)
    db.commit()

    catalog = FakeProductCatalog(
        FakeProductClient(
            [
                [
                    {
                        "tulip_code": "ART12445",
                        "tulip_id": 12445,
                        "ref": "ART12445",
                        "designation": "ramit",
                        "supplier_ref": None,
                        "barcode": None,
                        "packaging": "1",
                        "stock_unit": "U",
                        "default_vat_rate": 0.0,
                    }
                ],
            ],
            1,
        )
    )
    result = sync_products(db, catalog)
    assert result["created"] == 0
    remains = db.query(Product).filter_by(designation="ramit").all()
    assert len(remains) == 1
    assert remains[0].tulip_code == "12445"
    assert remains[0].reference == "ART12445"
