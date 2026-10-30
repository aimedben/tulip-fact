from __future__ import annotations

import io


def test_bulk_delete_mixed_invoices(client, seeded, tmp_path):
    from tests.test_api_e2e import _process, create_invoice_pdf

    ids: list[int] = []
    for index, tag in enumerate(("BULK-1", "BULK-2")):
        pdf = tmp_path / f"facture-bulk-{index}.pdf"
        create_invoice_pdf(pdf, tag)
        with pdf.open("rb") as handle:
            ids.append(
                client.post(
                    "/api/invoices/import",
                    files={"file": (f"facture-bulk-{index}.pdf", handle, "application/pdf")},
                ).json()["id"]
            )
    _process(client, ids[0])
    validated = client.post(f"/api/invoices/{ids[0]}/validate", json={"actor": "test"})
    assert validated.status_code == 200, validated.text

    response = client.post("/api/invoices/delete-bulk", json={"ids": ids + [999999]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["deleted"]) == sorted(ids)
    assert body["refused"] == [{"invoice_id": 999999, "reason": "introuvable"}]
    for invoice_id in ids:
        assert client.get(f"/api/invoices/{invoice_id}").status_code == 404

    traces = client.get("/api/db/audit/entries?limit=100").json()
    assert sum(1 for entry in traces if entry["action"] == "facture_supprimee") >= 2
