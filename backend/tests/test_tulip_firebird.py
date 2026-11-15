from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.tulip.catalog import TulipCatalog
from app.services.tulip.firebird import FirebirdConfig, FirebirdError, FirebirdIsql
from app.services.tulip.sync import sync_suppliers
from app.services.tulip.writer import BeWriter, BeHeader, LineItem


def _line(name: str, value: str) -> str:
    return f"{name:<32}{value}"


def _config(**overrides) -> FirebirdConfig:
    values = {
        "enabled": True,
        "host": "localhost",
        "port": 3050,
        "database": "test.fdb",
        "user": "sysdba",
        "password": "secret",
        "isql_path": sys.executable,
        "firebird_home": str(Path(sys.executable).parent),
        "write_enabled": False,
    }
    values.update(overrides)
    return FirebirdConfig(**values)


def test_parse_list_handles_nulls_and_values():
    output = "\n".join(
        [
            "",
            _line("CODE", "1"),
            _line("NAME", "<null>"),
            _line("LABEL", "Article test"),
            "",
            _line("CODE", "2"),
            _line("NAME", "Fournisseur"),
            _line("LABEL", "<null>"),
            "",
        ]
    )
    rows = FirebirdIsql._parse_list(output, ("CODE", "NAME", "LABEL"))
    assert rows == [
        {"CODE": "1", "NAME": None, "LABEL": "Article test"},
        {"CODE": "2", "NAME": "Fournisseur", "LABEL": None},
    ]


def test_query_rejects_write_statements():
    client = FirebirdIsql(_config())
    with pytest.raises(FirebirdError, match="lecture seule"):
        client.query("DELETE FROM BE", ("CODE",))


def test_execute_requires_write_enabled():
    client = FirebirdIsql(_config(write_enabled=False))
    with pytest.raises(FirebirdError, match="écritures"):
        client.execute("UPDATE BE SET TTC = 0")


def test_status_without_configuration_is_not_connected():
    status = TulipCatalog(FirebirdIsql(_config(enabled=False))).status()
    assert status["connected"] is False
    assert status["configured"] is False
    assert status["write_enabled"] is False


def test_supplier_payload_maps_tulip_fields():
    client = FakeClient(
        [
            [{"TOTAL": "1"}],
            [
                {
                    "CODE": "-2147483648",
                    "PRINCIPAL": "000001",
                    "NAME": "MOLFIX",
                    "ADDRESS1": "Rue 1",
                    "ZIPCODE": "16000",
                    "CITY": "Alger",
                    "PHONE": "021",
                    "EMAIL": "contact@example.dz",
                    "NRC": "NRC1",
                    "MF": "MF1",
                    "NIS": "NIS1",
                }
            ],
        ]
    )
    result = TulipCatalog(client).suppliers(page_size=10)
    assert result["total"] == 1
    supplier = result["items"][0]
    assert supplier["id"] == -2147483648
    assert supplier["tulip_code"] == "-2147483648"
    assert supplier["code"] == "000001"
    assert supplier["name"] == "MOLFIX"
    assert supplier["address"] == "Rue 1 16000 Alger"
    assert supplier["tax_id"] == "NRC1"
    assert supplier["source"] == "tulip"


def test_product_payload_maps_tulip_fields():
    client = FakeClient(
        [
            [{"TOTAL": "1"}],
            [
                {
                    "CODE": "-2147483646",
                    "REF": "MO01",
                    "DESIGNATION": "MOLFIX 1P 12",
                    "REF_O": None,
                    "LOT": "0",
                    "TVA": "19.0000000000000000",
                    "RECEP": "12.000000000000000",
                    "MPRIXRECEP": "0.5000000000000000",
                    "STOCK": "5.000000000000000",
                    "CMUP": "284.3662500050000",
                    "UM": "U",
                    "BARCODE": "6130793004054",
                }
            ],
        ]
    )
    result = TulipCatalog(client).products(q="MOLFIX", page_size=10)
    assert result["total"] == 1
    product = result["items"][0]
    assert product["id"] == -2147483646
    assert product["tulip_code"] == "MO01"
    assert product["designation"] == "MOLFIX 1P 12"
    assert product["packaging"] == "12"
    assert product["default_vat_rate"] == 19.0
    assert product["purchase_factor"] == 12.0
    assert product["purchase_price_factor"] == 0.5
    assert product["stock"] == 5.0
    assert product["source"] == "tulip"
    assert "ESCAPE" in client.queries[0]


def test_product_filter_keeps_nature_4_articles():
    # La base SUPERETTE contient 148 articles actifs de nature 4 (dont 101
    # effectivement vendus, avec code-barres) : ils doivent apparaitre dans
    # le catalogue, exactement comme dans la liste des articles de Tulip.
    client = FakeClient([[{"TOTAL": "0"}], []])
    TulipCatalog(client).products(page_size=10)
    assert "NATURE IN (1, 2, 4, 5, 10)" in client.queries[0]


class FakeClient:
    config = _config(enabled=False, write_enabled=True)

    def __init__(self, responses: list[list[dict[str, str | None]]]) -> None:
        self.responses = list(responses)
        self.queries: list[str] = []
        self.executions: list[str] = []

    def query(self, sql: str, columns: tuple[str, ...]) -> list[dict[str, str | None]]:
        self.queries.append(sql)
        return self.responses.pop(0)

    def execute(self, sql: str) -> str:
        if not self.config.write_enabled:
            raise FirebirdError("Les écritures Firebird Tulip sont désactivées.")
        self.executions.append(sql)
        return ""


def _writer(respond: dict[str, str] | None = None) -> tuple[BeWriter, FakeClient]:
    respond = respond or {"BE": "-2147478100", "LINEBE": "-2147451000", "NEXT_NUM": "2405"}
    client = FakeClient(
        [
            [{"NEXT_VALUE": respond["BE"]}],
            [{"USED": "0"}],
            [{"NEXT_NUM": respond["NEXT_NUM"]}],
            [{"NEXT_VALUE": respond["LINEBE"]}],
            [{"USED": "0"}],
        ]
    )
    return BeWriter(client), client


_HEADER = BeHeader(fournisseur=-2147483342, opdate=date(2026, 10, 25), nbc="FACT-001")
_LINES = [LineItem(product_code=-2147478181, quantity=Decimal("1"), unit_price_ht=Decimal("10"))]


def _columns_of(header_sql: str) -> list[str]:
    inner = header_sql[header_sql.index("(") + 1 : header_sql.index(")")]
    return [part.strip() for part in inner.split(",")]


def test_create_be_dry_run_never_writes():
    writer, client = _writer()
    result = writer.create_be(_HEADER, _LINES, dry_run=True)
    assert result["dry_run"] is True
    assert result["numero"] == 2405
    assert client.executions == []


def test_create_be_write_sequence_and_columns():
    writer, client = _writer()
    result = writer.create_be(_HEADER, _LINES, dry_run=False)
    assert result["success"] is True
    assert result["be_code"] == -2147478100
    assert len(client.executions) == 1
    script = client.executions[0]
    insert_at = script.index("INSERT INTO BE (")
    dette_at = script.index("DETTE = 1")
    lines_at = script.index("INSERT INTO DETAILSBR (")
    assert 0 <= insert_at < dette_at < lines_at
    header_sql = script[insert_at:]
    columns = _columns_of(header_sql)
    for computed in ("TTC", "STOCK", "INVOICE", "INVOICEDATE"):
        assert computed not in columns
    assert "-2147478100" in script
    line_columns = _columns_of(script[lines_at:])
    for computed in ("QX", "QE", "PRIXHT", "BALANCE", "HT"):
        assert computed not in line_columns
    assert client.responses == []


def test_create_be_requires_lines():
    writer, _ = _writer()
    with pytest.raises(FirebirdError, match="Aucune ligne"):
        writer.create_be(_HEADER, [], dry_run=True)


def test_create_be_writes_prix_vente_as_mprix():
    """Le prix de vente saisi sur la ligne est écrit dans DETAILSBR.MPRIX."""
    lines = [
        LineItem(
            product_code=-2147478181,
            quantity=Decimal("1"),
            unit_price_ht=Decimal("10"),
            mprix=Decimal("15.50"),
        )
    ]
    writer, client = _writer()

    dry = writer.create_be(_HEADER, lines, dry_run=True)
    assert dry["lines"][0]["mprix"] == Decimal("15.50")

    writer2, client2 = _writer()
    writer2.create_be(_HEADER, lines, dry_run=False)
    script = client2.executions[0]
    line_sql = script[script.index("INSERT INTO DETAILSBR (") :]
    assert "MPRIX" in _columns_of(line_sql)
    assert "15.50" in line_sql


def test_create_be_mprix_null_when_absent():
    writer, client = _writer()
    writer.create_be(_HEADER, _LINES, dry_run=False)
    script = client.executions[0]
    line_sql = script[script.index("INSERT INTO DETAILSBR (") :]
    assert "NULL" in line_sql


def test_write_requires_flag():
    client = FakeClient([])
    client.config = _config(write_enabled=False)
    writer = BeWriter(client)
    with pytest.raises(FirebirdError):
        writer.create_be(_HEADER, _LINES, dry_run=False)


def test_live_status_endpoint_is_disabled_by_default(client):
    payload = client.get("/api/tulip/live/status").json()
    assert payload["configured"] is False
    assert payload["connected"] is False
    assert payload["write_enabled"] is False
    assert "password" not in payload


def test_live_catalog_requires_configuration(client):
    response = client.get("/api/tulip/live/products")
    assert response.status_code == 503
    assert "password" not in response.text.lower()


def test_live_summary_counts_tulip_entities():
    client = FakeClient(
        [[{"TOTAL": "9"}], [{"TOTAL": "500"}], [{"TOTAL": "120"}], [{"TOTAL": "118"}]]
    )
    summary = TulipCatalog(client).summary()
    assert summary == {"suppliers": 9, "products": 500, "be_total": 120, "be_dette": 118}


def test_be_documents_payload_maps_fields():
    client = FakeClient(
        [
            [{"TOTAL": "1"}],
            [
                {
                    "CODE": "-2147478186",
                    "NUMERO": "2267",
                    "NBC": "BL-1",
                    "LIVFACT": None,
                    "SUPPLIER_CODE": "-2147483342",
                    "SUPPLIER_NAME": "MOLFIX",
                    "OPDATE": "2026-10-25 00:00:00",
                    "DATEBC": "2026-10-25 00:00:00",
                    "DETTE": "1",
                    "STOCK": "1",
                    "MHT": "9080.00000000000000",
                    "MTVA": "0.0000000000000000",
                    "TTC": "9080.00000000000000",
                }
            ],
        ]
    )
    result = TulipCatalog(client).be_documents(page=1, page_size=10)
    assert result["total"] == 1
    document = result["items"][0]
    assert document["id"] == -2147478186
    assert document["numero"] == 2267
    assert document["supplier_id"] == -2147483342
    assert document["dette"] is True
    assert document["stock"] is True
    assert document["ttc"] == 9080.0
    assert document["livfact"] is None


def test_live_create_be_defaults_to_dry_run(client):
    payload = {
        "header": {"fournisseur": -2147483342, "opdate": "2026-10-25", "nbc": "FACT-1"},
        "lines": [
            {"product_code": -2147478181, "quantity": "2", "unit_price_ht": "12.5"}
        ],
    }
    response = client.post("/api/tulip/live/be", json=payload)
    assert response.status_code == 503
    data = response.json()
    assert "OK" not in data or data.get("detail")


def test_live_create_be_rejects_empty_lines(client):
    payload = {
        "header": {"fournisseur": -2147483342, "opdate": "2026-10-25"},
        "lines": [],
    }
    response = client.post("/api/tulip/live/be", json=payload)
    assert response.status_code == 422


class FakeSupplierCatalog:
    def __init__(self, pages: list[list[dict]], total: int) -> None:
        self.pages = list(pages)
        self.total = total

    def suppliers(self, page: int = 1, page_size: int = 50):
        items = self.pages[page - 1] if page <= len(self.pages) else []
        return {
            "items": items,
            "total": self.total,
            "page": page,
            "page_size": page_size,
        }


def test_sync_suppliers_creates_and_updates(db):
    from app.models import Supplier

    catalog = FakeSupplierCatalog(
        [
            [
                {"tulip_code": "-2147483546", "code": "000102", "name": "1004 LEGUMES SECS LUNDI", "tax_id": None,
                 "phone": "021", "email": None, "address": "Rue 1"},
                {"tulip_code": "-2147483408", "code": "000238", "name": "AFIA", "tax_id": "NRC-1",
                 "phone": None, "email": "a@b.dz", "address": None},
            ]
        ],
        total=2,
    )
    result = sync_suppliers(db, catalog)
    assert result["created"] == 2
    assert result["total"] == 2
    foreign = db.query(Supplier).filter_by(code="-2147483546").one()
    assert foreign.name == "1004 LEGUMES SECS LUNDI"
    assert foreign.address == "Rue 1"
    assert foreign.notes == "Code principal Tulip: 000102"

    second = FakeSupplierCatalog(
        [
            [
                {"tulip_code": "-2147483546", "code": "000102", "name": "1004 LEGUMES SECS", "tax_id": "NRC-X",
                 "phone": "021", "email": None, "address": "Rue 1"},
            ]
        ],
        total=1,
    )
    result = sync_suppliers(db, second)
    assert result["created"] == 0
    assert result["updated"] == 1
    assert foreign.name == "1004 LEGUMES SECS"
    assert foreign.normalized_name != ""
    assert foreign.tax_id == "NRC-X"

