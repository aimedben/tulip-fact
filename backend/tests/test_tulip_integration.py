from __future__ import annotations


def test_tulip_integration_is_not_claimed(client):
    status = client.get("/api/tulip/status").json()
    assert status["connected"] is False
    assert status["confirmed"] is False
    assert status["methods"]["import_officiel"]["supported"] is False
    assert status["methods"]["api_web_service"]["supported"] is False
    assert status["methods"]["automatisation_ui"]["supported"] is False
    assert "not confirmed" in status["message"].lower() or "n'est pas confirmée" in status["message"]
    assert status["missing_information"]


def test_ui_probe_is_disabled_by_default(client):
    response = client.post("/api/tulip/probe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["probe"]["performed"] is False
    assert payload["connected"] is False


def test_settings_never_expose_llm_key(client):
    payload = client.get("/api/settings").json()
    assert "api_key" not in payload["llm"]
    assert payload["llm"]["enabled"] is False
    assert payload["app"]["mode"] == "production"


def test_health_endpoint(client):
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["database"] is True
    assert payload["storage"] is True
