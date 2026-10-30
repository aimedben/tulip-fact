from __future__ import annotations

from decimal import Decimal

from app.models import Product
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
