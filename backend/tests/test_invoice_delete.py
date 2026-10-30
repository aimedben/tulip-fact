from __future__ import annotations

import io


def test_delete_invoice_consent_and_file(client, seeded):
    path = io.BytesIO(b"%PDF-1.4 test")
    response = client.post("/api/invoices/import", files={"file": ("suppr.pdf", path, "application/pdf")})
    assert response.status_code == 201, response.text
    invoice_id = response.json()["id"]

    refused = client.delete(f"/api/invoices/{invoice_id}")
    assert refused.status_code == 400

    deleted = client.delete(f"/api/invoices/{invoice_id}?confirm=true")
    assert deleted.status_code in (200, 204)

    missing = client.get(f"/api/invoices/{invoice_id}")
    assert missing.status_code == 404


def test_delete_validated_invoice_allowed_with_trace(client, seeded, tmp_path):
    from tests.test_api_e2e import _process, create_invoice_pdf

    pdf = tmp_path / "facture-del.pdf"
    create_invoice_pdf(pdf, "DEMO-FA-2026-DEL")
    with pdf.open("rb") as handle:
        invoice_id = client.post(
            "/api/invoices/import",
            files={"file": ("facture-del.pdf", handle, "application/pdf")},
        ).json()["id"]
    _process(client, invoice_id)
    validated = client.post(f"/api/invoices/{invoice_id}/validate", json={"actor": "test"})
    assert validated.status_code == 200, validated.text

    refused = client.delete(f"/api/invoices/{invoice_id}?confirm=true")
    assert refused.status_code == 200
    assert refused.json()["trace"]["status_avant"] == "VALIDEE"
    assert client.get(f"/api/invoices/{invoice_id}").status_code == 404
