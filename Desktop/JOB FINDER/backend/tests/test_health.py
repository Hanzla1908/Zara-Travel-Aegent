def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_docs_reachable(client):
    r = client.get("/docs")
    assert r.status_code == 200
