from __future__ import annotations


def test_db_tables_endpoint(client):
    response = client.get("/api/db/tables")
    assert response.status_code == 200, response.text
    names = {item["name"] for item in response.json()}
    assert "invoices" in names and "suppliers" in names


def test_db_table_rows_and_search(client):
    response = client.get("/api/db/tables/suppliers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"] == "suppliers"
    assert payload["total"] >= 1

    searched = client.get("/api/db/tables/suppliers?q=MOLFIX").json()
    assert isinstance(searched["items"], list)

    unknown = client.get("/api/db/tables/sqlite_master")
    assert unknown.status_code == 404


def test_backup_increment(client):
    first = client.post("/api/db/backups").json()
    assert first["created"].startswith("tulip_factures-")
    listing = client.get("/api/db/backups").json()
    assert listing["items"], "sauvegarde listée"


def test_clear_table_guard(client):
    assert client.delete("/api/db/tables/invoices?confirm=true").status_code == 403
    assert client.delete("/api/db/tables/audit_entries").status_code == 400
