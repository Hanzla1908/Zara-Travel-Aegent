def test_list_jobs_returns_all(client):
    r = client.get("/api/jobs/")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 6
    assert len(body["jobs"]) == 6


def test_list_jobs_sorted_by_match(client):
    r = client.get("/api/jobs/?sort=match")
    jobs = r.json()["jobs"]
    scores = [j["match_score"] for j in jobs]
    assert scores == sorted(scores, reverse=True)


def test_filter_by_keyword(client):
    r = client.get("/api/jobs/?keyword=React")
    body = r.json()
    assert body["total"] > 0
    for job in body["jobs"]:
        text = (job["title"] + job["company"] + job["description"]).lower()
        assert "react" in text


def test_filter_by_source_linkedin(client):
    r = client.get("/api/jobs/?source=linkedin")
    body = r.json()
    assert all(j["source"] == "linkedin" for j in body["jobs"])


def test_filter_by_source_rozee(client):
    r = client.get("/api/jobs/?source=rozee")
    body = r.json()
    assert all(j["source"] == "rozee" for j in body["jobs"])


def test_filter_by_experience_senior(client):
    r = client.get("/api/jobs/?experience=Senior")
    body = r.json()
    assert body["total"] > 0
    assert all(j["experience"] == "Senior" for j in body["jobs"])


def test_filter_by_type_contract(client):
    r = client.get("/api/jobs/?type=Contract")
    body = r.json()
    assert all(j["type"] == "Contract" for j in body["jobs"])


def test_filter_no_results(client):
    r = client.get("/api/jobs/?keyword=XYZZY_NONEXISTENT_12345")
    assert r.json()["total"] == 0


def test_pagination(client):
    r = client.get("/api/jobs/?page=1&page_size=2")
    body = r.json()
    assert body["total"] == 6
    assert len(body["jobs"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_get_job_by_id(client):
    jobs_r = client.get("/api/jobs/")
    first_id = jobs_r.json()["jobs"][0]["id"]

    r = client.get(f"/api/jobs/{first_id}")
    assert r.status_code == 200
    job = r.json()
    assert job["id"] == first_id
    assert "title" in job
    assert "requirements" in job
    assert isinstance(job["requirements"], list)
    assert "saved" in job


def test_get_job_not_found(client):
    r = client.get("/api/jobs/99999")
    assert r.status_code == 404


def test_job_has_expected_fields(client):
    r = client.get("/api/jobs/")
    job = r.json()["jobs"][0]
    for field in ["id", "title", "company", "location", "match_score", "source",
                  "tags", "matching_skills", "missing_skills", "saved"]:
        assert field in job, f"Missing field: {field}"


def test_seed_endpoint(client):
    r = client.post("/api/jobs/seed")
    assert r.status_code == 201
    body = r.json()
    assert "seeded" in body
    # Already seeded → count should be 0
    assert body["seeded"] == 0
