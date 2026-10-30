from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ocr.preprocessing import available_languages
from app.services.pipeline import run_pipeline
from app.services.synthetic import create_invoice_png


@pytest.mark.skipif("fra" not in available_languages(), reason="Tesseract français non installé")
def test_png_photo_ocr_end_to_end(client, seeded, tmp_path: Path):
    png = tmp_path / "facture-photo.png"
    create_invoice_png(png, "DEMO-FA-2026-301", date_fr="15/03/2026")
    with png.open("rb") as handle:
        upload = client.post(
            "/api/invoices/import",
            files={"file": ("facture-photo.png", handle, "image/png")},
        )
    assert upload.status_code == 201, upload.text
    invoice_id = upload.json()["id"]
    assert run_pipeline(invoice_id)

    detail = client.get(f"/api/invoices/{invoice_id}").json()
    assert detail["status"] != "ECHEC", detail.get("error_message")
    assert detail["page_count"] == 1
    assert detail["invoice_number"] == "DEMO-FA-2026-301"
    assert len(detail["lines"]) >= 1
    assert detail["pages"][0]["ocr_engine"] == "tesseract"
    assert detail["pages"][0]["image_url"].startswith("/api/invoices/")
