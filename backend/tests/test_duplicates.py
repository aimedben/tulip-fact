from __future__ import annotations

from pathlib import Path

from app.services.pipeline import run_pipeline
from app.services.synthetic import create_invoice_pdf


def _upload(client, path: Path, name: str) -> int:
    with path.open("rb") as handle:
        response = client.post(
            "/api/invoices/import",
            files={"file": (name, handle, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_same_file_is_flagged_as_duplicate(client, seeded, tmp_path: Path):
    pdf = tmp_path / "doublon.pdf"
    create_invoice_pdf(pdf, "DEMO-FA-2026-201")
    first = _upload(client, pdf, "doublon.pdf")
    assert run_pipeline(first)
    second = _upload(client, pdf, "doublon-copie.pdf")
    assert run_pipeline(second)

    detail = client.get(f"/api/invoices/{second}").json()
    assert detail["is_duplicate"] is True
    assert detail["duplicate_of_id"] == first
    assert any(warning["code"] == "DOUBLON_POSSIBLE" for warning in detail["warnings"])

    blocked = client.post(f"/api/invoices/{second}/validate", json={"actor": "test"})
    assert blocked.status_code == 422
    forced = client.post(
        f"/api/invoices/{second}/validate",
        json={"actor": "test", "acknowledge_duplicate": True},
    )
    assert forced.status_code == 200, forced.text


def test_same_number_other_supplier_is_not_a_duplicate(client, seeded, tmp_path: Path):
    supplier = client.post(
        "/api/suppliers",
        json={"code": "OTHER-001", "name": "AUTRE FOURNISSEUR DEMO"},
    )
    assert supplier.status_code == 201
    supplier_id = supplier.json()["id"]

    first_pdf = tmp_path / "meme-numero-a.pdf"
    create_invoice_pdf(first_pdf, "FAC-COMMUNE-001", date_fr="12/03/2026")
    first = _upload(client, first_pdf, "a.pdf")
    assert run_pipeline(first)

    second_pdf = tmp_path / "meme-numero-b.pdf"
    create_invoice_pdf(second_pdf, "FAC-COMMUNE-001", date_fr="14/03/2026")
    second = _upload(client, second_pdf, "b.pdf")
    assert run_pipeline(second)

    detail = client.get(f"/api/invoices/{second}").json()
    confirmed = client.post(
        f"/api/invoices/{second}/supplier",
        json={"supplier_id": supplier_id},
    )
    assert confirmed.status_code == 200, confirmed.text
    final = client.get(f"/api/invoices/{second}").json()
    assert final["supplier"]["code"] == "OTHER-001"
    assert final["is_duplicate"] is False, detail
