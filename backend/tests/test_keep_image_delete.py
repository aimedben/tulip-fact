from pathlib import Path

from app.config import settings


def _archives(name: str) -> Path:
    path = settings.data_dir / f"archives-test-{name}"
    path.mkdir(parents=True, exist_ok=True)
    settings.archives_dir = path
    return path


def test_delete_keeps_archived_image(invoice_factory: object, sample_pdf, client) -> None:
    archives = _archives("keep")
    invoice_id = invoice_factory(sample_pdf)
    response = client.delete(f"/api/invoices/{invoice_id}?confirm=true&keep_image=true")
    assert response.status_code == 200, response.text
    trace = response.json()["trace"]
    assert trace["photo_conservee"], trace
    archived_path = settings.data_dir / trace["photo_conservee"]
    assert archived_path.is_file()
    assert archived_path.name.endswith(".pdf")


def test_delete_without_option_removes_document(invoice_factory: object, sample_pdf, client) -> None:
    archives = _archives("none")
    invoice_id = invoice_factory(sample_pdf)
    response = client.delete(f"/api/invoices/{invoice_id}?confirm=true")
    assert response.status_code == 200, response.text
    trace = response.json()["trace"]
    assert trace["photo_conservee"] is None
    assert len(list(archives.glob("*"))) == 0
