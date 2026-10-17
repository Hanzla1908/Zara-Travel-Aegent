import pytest


def _get_first_job_id(client) -> int:
    return client.get("/api/jobs/").json()["jobs"][0]["id"]


def test_saved_list_initially_empty(client):
    r = client.get("/api/saved/?user_id=test_user_saved")
    assert r.status_code == 200
    assert r.json() == []


def test_save_job(client):
    job_id = _get_first_job_id(client)
    r = client.post(f"/api/saved/{job_id}?user_id=test_user_saved")
    assert r.status_code == 201
    assert r.json()["job_id"] == job_id


def test_saved_job_appears_in_list(client):
    job_id = _get_first_job_id(client)
    r = client.get("/api/saved/?user_id=test_user_saved")
    ids = [j["id"] for j in r.json()]
    assert job_id in ids


def test_job_shows_saved_true(client):
    job_id = _get_first_job_id(client)
    r = client.get(f"/api/jobs/{job_id}?user_id=test_user_saved")
    assert r.json()["saved"] is True


def test_save_duplicate_returns_409(client):
    job_id = _get_first_job_id(client)
    r = client.post(f"/api/saved/{job_id}?user_id=test_user_saved")
    assert r.status_code == 409


def test_save_nonexistent_job_returns_404(client):
    r = client.post("/api/saved/99999?user_id=test_user_saved")
    assert r.status_code == 404


def test_unsave_job(client):
    job_id = _get_first_job_id(client)
    r = client.delete(f"/api/saved/{job_id}?user_id=test_user_saved")
    assert r.status_code == 200

    r = client.get("/api/saved/?user_id=test_user_saved")
    assert r.json() == []


def test_unsave_nonexistent_returns_404(client):
    r = client.delete("/api/saved/99999?user_id=test_user_saved")
    assert r.status_code == 404
