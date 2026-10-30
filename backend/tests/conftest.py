from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATA = Path(tempfile.mkdtemp(prefix="tulip-factures-tests-"))
os.environ["TULIP_APP_MODE"] = "production"
os.environ["TULIP_DATA_DIR"] = str(TEST_DATA)
os.environ["TULIP_DISABLE_WORKER"] = "1"
os.environ["TULIP_LLM_ENABLED"] = "false"
os.environ["TESSDATA_PREFIX"] = str(PROJECT_ROOT / "tessdata")
os.environ["TULIP_FB_ENABLED"] = "false"
os.environ["TULIP_FB_WRITE_ENABLED"] = "false"
os.environ["TULIP_FB_DATABASE"] = ""
os.environ["TULIP_FB_PASSWORD"] = ""
os.environ.pop("TULIP_FB_ISQL_PATH", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.synthetic import create_invoice_pdf, seed_demo_referential  # noqa: E402


@pytest.fixture(scope="session")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded(db):
    seed_demo_referential(db)
    return db


@pytest.fixture()
def invoice_factory(client):
    def factory(path: Path, expected_number: str | None = None) -> int:
        with path.open("rb") as handle:
            response = client.post(
                "/api/invoices/import",
                files={"file": (path.name, handle, "application/pdf" if path.suffix == ".pdf" else "image/png")},
            )
        assert response.status_code == 201, response.text
        payload = response.json()
        if expected_number:
            assert payload["status"] == "IMPORTEE"
        return payload["id"]

    return factory


@pytest.fixture()
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "facture-demo.pdf"
    create_invoice_pdf(path, "DEMO-FA-2026-101")
    return path
