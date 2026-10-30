from __future__ import annotations

from app.models import Invoice, Supplier

_SEED = {"n": 0}


def _make_invoice() -> Invoice:
    _SEED["n"] += 1
    n = _SEED["n"]
    return Invoice(
        uuid=f"77777777-7777-7777-7777-{n:012d}".replace("7", "7"),
        original_filename=f"fa{n}.pdf",
        stored_path=f"fa{n}.pdf",
        sha256=("b" * 63) + str(n),
        file_size=10,
        mime_type="application/pdf",
        status="A_VERIFIER",
        raw_text=(
            "SARL IFRUIT BOISSONS\n"
            "Facture N° FA-URING-2026-3365\n"
            "Date: 12/09/2026\n"
            "R.C. 08/00-1032126 Memory\n"
            "\n"
            "Designation                 Qte   P.U   Mont.Ht\n"
            "BLITERE 8 ORANGE 1 LT       10    0.00 65,00"
        ),
    )



def _seed_supplier(db) -> None:
    existing = db.query(Supplier).filter_by(name="IFRUIT BOISSONS").one_or_none()
    if existing is None:
        _SEED["n"] += 1
        n = _SEED["n"]
        db.add(
            Supplier(
                code=f"-21474834{n:02d}",
                name="IFRUIT BOISSONS",
                normalized_name="ifruit boissons",
            )
        )
        db.commit()


def test_analyze_without_llm_builds_proposal(db, client, monkeypatch):
    from app.api import invoices as api
    from app.services.extraction import llm as llm_module

    monkeypatch.setattr(llm_module.settings, "llm_enabled", False)
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "")
    _seed_supplier(db)
    invoice = _make_invoice()
    db.add(invoice)
    db.commit()

    response = client.post(f"/api/invoices/{invoice.id}/ai/analyze")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["llm_available"] is False
    proposal = payload["proposal"]
    assert proposal["header"]["invoice_number"]["proposed"] == "FA-URING-2026-3365"
    assert proposal["header"]["invoice_number"]["status"] == "fill"
    assert any("FRUIT" in c["name"] for c in payload["supplier_candidates"])


def test_apply_fills_header_and_adds_lines_without_overwrite(db, client, monkeypatch):
    from app.api import invoices as api
    from app.services.extraction import llm as llm_module

    monkeypatch.setattr(llm_module.settings, "llm_enabled", False)
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "")
    _seed_supplier(db)
    invoice = _make_invoice()
    db.add(invoice)
    db.commit()

    response = client.post(f"/api/invoices/{invoice.id}/ai/apply")
    assert response.status_code == 200, response.text
    payload = response.json()
    changes = payload["changes"]
    assert changes["header"].get("invoice_number") == "FA-URING-2026-3365"
    assert changes["lines"] == 1
    assert payload["invoice"]["totals_calculated"]["line_count"] == 1

    before = invoice.id
    response = client.post(f"/api/invoices/{invoice.id}/ai/apply")
    changes = response.json()["changes"]
    assert changes["lines"] == 0, "lignes existantes ne doivent jamais être écrasées"
    assert before == invoice.id
