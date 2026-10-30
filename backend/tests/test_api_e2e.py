from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Invoice
from app.services.pipeline import run_pipeline
from app.services.synthetic import create_invoice_pdf


def _process(client, invoice_id: int):
    assert run_pipeline(invoice_id)
    response = client.get(f"/api/invoices/{invoice_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_full_workflow_upload_extract_validate_export(client, seeded, tmp_path: Path):
    pdf = tmp_path / "facture-e2e.pdf"
    create_invoice_pdf(pdf, "DEMO-FA-2026-101")
    with pdf.open("rb") as handle:
        upload = client.post(
            "/api/invoices/import",
            files={"file": ("facture-e2e.pdf", handle, "application/pdf")},
        )
    assert upload.status_code == 201
    invoice_id = upload.json()["id"]
    detail = _process(client, invoice_id)

    assert detail["status"] == "PRETE_A_VALIDER", detail
    assert detail["invoice_number"] == "DEMO-FA-2026-101"
    assert detail["supplier"]["code"] == "DEMO-F001"
    assert detail["page_count"] == 1
    assert len(detail["lines"]) == 3
    assert all(line["match_status"] == "RAPPROCHE" for line in detail["lines"])
    assert all(line["line_total_ht_calculated"] is not None for line in detail["lines"])
    assert detail["lines"][0]["line_total_ht_calculated"] == 10800.0
    assert detail["totals_extracted"]["total_ttc"] == "22569.54"
    assert detail["readiness"]["ready"] is True
    assert not any(check["severity"] == "error" for check in detail["checks"])

    correction = client.patch(
        f"/api/invoices/{invoice_id}",
        json={"invoice_date": "2026-03-11", "bl_number": "BL-SEPARE-2026"},
    )
    assert correction.status_code == 200, correction.text
    corrected = correction.json()
    assert corrected["invoice_date"] == "2026-03-11"
    assert corrected["bl_number"] == "BL-SEPARE-2026"
    assert corrected["bl_date"] == "2026-03-10"
    assert corrected["header_raw"]["invoice_date"]["source"] == "correction utilisateur"

    supplier = client.post(
        f"/api/invoices/{invoice_id}/supplier",
        json={"supplier_id": corrected["supplier"]["id"]},
    )
    assert supplier.status_code == 200, supplier.text

    line_id = supplier.json()["lines"][0]["id"]
    line_update = client.patch(
        f"/api/invoices/{invoice_id}/lines/{line_id}",
        json={"lot_number": "LOT-CORRIGE", "quantity": 25, "line_total_ht_extracted": 11250},
    )
    assert line_update.status_code == 200, line_update.text
    assert line_update.json()["lines"][0]["lot_number"] == "LOT-CORRIGE"
    assert line_update.json()["lines"][0]["user_modified"] is True
    assert line_update.json()["lines"][0]["original_values"]["corrections"]

    validation = client.post(
        f"/api/invoices/{invoice_id}/validate",
        json={"actor": "test", "acknowledge_totals": True},
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["status"] == "VALIDEE"

    exported = client.post(
        f"/api/invoices/{invoice_id}/export",
        json={"formats": ["csv", "xlsx", "json", "rapport"]},
    )
    assert exported.status_code == 200, exported.text
    records = exported.json()["records"]
    assert {record["format"] for record in records} == {"csv", "xlsx", "json", "rapport"}

    csv_record = next(record for record in records if record["format"] == "csv")
    csv_response = client.get(csv_record["download_url"])
    assert csv_response.status_code == 200
    assert "Code fournisseur" in csv_response.content.decode("utf-8-sig")
    assert "DEMO-F001" in csv_response.content.decode("utf-8-sig")
    assert "22569,54" in csv_response.content.decode("utf-8-sig")

    json_record = next(record for record in records if record["format"] == "json")
    json_data = client.get(json_record["download_url"]).json()
    assert json_data["facture"]["numero_facture"] == "DEMO-FA-2026-101"
    assert len(json_data["lignes"]) == 3

    detail_after = client.get(f"/api/invoices/{invoice_id}").json()
    assert detail_after["status"] == "EXPORTEE"
    assert detail_after["exports"]
    assert any(entry["action"] == "export" for entry in detail_after["audits"])

    with SessionLocal() as db:
        persisted = db.get(Invoice, invoice_id)
        assert persisted is not None
        assert persisted.status == "EXPORTEE"
        assert persisted.invoice_date.isoformat() == "2026-03-11"

    with TestClient(app) as reopened:
        again = reopened.get(f"/api/invoices/{invoice_id}")
        assert again.status_code == 200
        assert again.json()["status"] == "EXPORTEE"


def test_multipage_pdf(client, seeded, tmp_path: Path):
    pdf = tmp_path / "facture-multipage.pdf"
    create_invoice_pdf(pdf, "DEMO-FA-2026-102", split_pages=True)
    with pdf.open("rb") as handle:
        upload = client.post(
            "/api/invoices/import",
            files={"file": ("facture-multipage.pdf", handle, "application/pdf")},
        )
    invoice_id = upload.json()["id"]
    detail = _process(client, invoice_id)
    assert detail["page_count"] == 2
    assert len(detail["pages"]) == 2
    assert len(detail["lines"]) == 3
    assert detail["totals_extracted"]["total_ttc"] == "22569.54"
    assert client.get(f"/api/invoices/{invoice_id}/pages/2/image").status_code == 200


def test_reject_unsupported_file(client):
    response = client.post(
        "/api/invoices/import",
        files={"file": ("facture.txt", b"ceci n'est pas une facture", "text/plain")},
    )
    assert response.status_code == 415


def test_reject_fake_pdf(client):
    response = client.post(
        "/api/invoices/import",
        files={"file": ("facture.pdf", b"pas un pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_validated_invoice_can_be_deleted_with_audit(client, seeded, tmp_path: Path):
    pdf = tmp_path / "facture-locked.pdf"
    create_invoice_pdf(pdf, "DEMO-FA-2026-104")
    with pdf.open("rb") as handle:
        invoice_id = client.post(
            "/api/invoices/import",
            files={"file": ("facture-locked.pdf", handle, "application/pdf")},
        ).json()["id"]
    _process(client, invoice_id)
    validated = client.post(f"/api/invoices/{invoice_id}/validate", json={"actor": "test"})
    assert validated.status_code == 200, validated.text
    deleted = client.delete(f"/api/invoices/{invoice_id}", params={"confirm": True})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["trace"]["status_avant"] == "VALIDEE"
    assert client.get(f"/api/invoices/{invoice_id}").status_code == 404
    traces = client.get("/api/db/audit/entries").json()
    assert any(entry["action"] == "facture_supprimee" for entry in traces)

