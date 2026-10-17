import pytest

USER = "test_user_alerts"

ALERT_PAYLOAD = {
    "name": "React Jobs Lahore",
    "keywords": "React, TypeScript",
    "location": "Lahore",
    "frequency": "Daily",
    "sources": ["linkedin", "rozee"],
}


def test_list_alerts_initially_empty(client):
    r = client.get(f"/api/alerts/?user_id={USER}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_alert(client):
    r = client.post(f"/api/alerts/?user_id={USER}", json=ALERT_PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == ALERT_PAYLOAD["name"]
    assert body["active"] is True
    assert "id" in body
    assert "created_at" in body


def test_alert_appears_in_list(client):
    r = client.get(f"/api/alerts/?user_id={USER}")
    alerts = r.json()
    assert len(alerts) == 1
    assert alerts[0]["name"] == ALERT_PAYLOAD["name"]


def test_toggle_alert_inactive(client):
    alerts = client.get(f"/api/alerts/?user_id={USER}").json()
    alert_id = alerts[0]["id"]

    r = client.patch(f"/api/alerts/{alert_id}?user_id={USER}", json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_toggle_alert_active(client):
    alerts = client.get(f"/api/alerts/?user_id={USER}").json()
    alert_id = alerts[0]["id"]

    r = client.patch(f"/api/alerts/{alert_id}?user_id={USER}", json={"active": True})
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_create_alert_missing_name_returns_422(client):
    r = client.post(f"/api/alerts/?user_id={USER}", json={"keywords": "React"})
    assert r.status_code == 422


def test_update_nonexistent_alert_returns_404(client):
    r = client.patch(f"/api/alerts/99999?user_id={USER}", json={"active": False})
    assert r.status_code == 404


def test_delete_alert(client):
    alerts = client.get(f"/api/alerts/?user_id={USER}").json()
    alert_id = alerts[0]["id"]

    r = client.delete(f"/api/alerts/{alert_id}?user_id={USER}")
    assert r.status_code == 200
    assert r.json()["id"] == alert_id

    remaining = client.get(f"/api/alerts/?user_id={USER}").json()
    assert remaining == []


def test_delete_nonexistent_alert_returns_404(client):
    r = client.delete(f"/api/alerts/99999?user_id={USER}")
    assert r.status_code == 404
