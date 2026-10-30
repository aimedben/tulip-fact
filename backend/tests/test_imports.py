from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from app.models import Product, Supplier


def test_supplier_csv_import_preserves_leading_zero(client):
    content = (
        "Code;Nom;Variantes;NIF\n"
        "000123;ALPHA DISTRIBUTION SARL;ALPHA|ALPHA DISTRIB;000216000000111\n"
        "000124;BETA COMMERCE;;\n"
        "000123;DOUBLON; ;\n"
        "000125;;;\n"
    )
    response = client.post(
        "/api/suppliers/import",
        files={"file": ("fournisseurs.csv", content.encode("utf-8-sig"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["imported_rows"] == 2
    assert report["skipped_rows"] == 2
    assert any(error["row"] == 4 for error in report["errors"])

    listing = client.get("/api/suppliers", params={"q": "000123"}).json()
    assert listing["items"][0]["code"] == "000123"


def test_product_xlsx_import_and_missing_columns(client):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Code article", "Désignation", "Réf fournisseur", "Code-barres", "TVA", "Colisage"])
    sheet.append(["DEMO-X-1", "PRODUIT FICTIF UN", "X-1", "6130000000999", 19, "1 carton = 6"])
    sheet.append(["", "SANS CODE", "", "", "", ""])
    buffer = BytesIO()
    workbook.save(buffer)

    response = client.post(
        "/api/products/import",
        files={
            "file": (
                "articles.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["imported_rows"] == 1
    assert report["skipped_rows"] == 1
    listing = client.get("/api/products", params={"q": "DEMO-X-1"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["packaging"] == "1 carton = 6"

    invalid = client.post(
        "/api/suppliers/import",
        files={"file": ("mauvais.csv", b"code;tel\n1;000\n", "text/csv")},
    )
    assert invalid.status_code == 422
    assert "Nom fournisseur" in invalid.text


def test_unsupported_catalog_format(client):
    response = client.post(
        "/api/products/import",
        files={"file": ("articles.txt", b"code;designation\n", "text/plain")},
    )
    assert response.status_code == 415
