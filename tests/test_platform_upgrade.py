"""Comprehensive integration tests for the platform UI/UX upgrade, tracking, utilization, preferences & IDF tokenizer."""

from unittest.mock import patch

from backend.db.models import JobListing, Resume
from backend.services.discovery_sources import RawDiscoveredJob
from backend.services.matching_engine import _tokenize_domain_terms, compute_corpus_idf, exact_term_in_text
from tests.helpers import build_sample_pdf_bytes


def test_preferences_user_isolation_and_email_verify(api_client):
    alice = {"X-User-Id": "alice"}
    bob = {"X-User-Id": "bob"}

    # Distinct preferences persisted per user
    r1 = api_client.put(
        "/api/v1/profile/preferences",
        headers=alice,
        json={
            "theme": "light",
            "preferred_roles": ["Data Scientist"],
            "preferred_locations": ["Hyderabad"],
            "min_experience": 0.0,
            "max_experience": 1.5,
            "salary_preference": "12 LPA",
            "fresher_filter_default": False,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["theme"] == "light"

    r2 = api_client.put(
        "/api/v1/profile/preferences",
        headers=bob,
        json={"theme": "dark", "preferred_roles": ["Backend Engineer"]},
    )
    assert r2.status_code == 200

    assert api_client.get("/api/v1/profile/preferences", headers=alice).json()["preferred_roles"] == ["Data Scientist"]
    assert api_client.get("/api/v1/profile/preferences", headers=bob).json()["preferred_roles"] == ["Backend Engineer"]
    assert api_client.get("/api/v1/profile/preferences", headers=bob).json()["theme"] == "dark"

    # Email verification endpoint
    bad = api_client.post("/api/v1/profile/email/verify", headers=alice, json={"email_address": "not-an-email"})
    assert bad.status_code == 400
    good = api_client.post("/api/v1/profile/email/verify", headers=alice, json={"email_address": "alice@example.com"})
    assert good.status_code == 200
    assert good.json()["email_verified"] is True
    assert api_client.get("/api/v1/profile/preferences", headers=alice).json()["email_verified"] is True


def test_two_step_apply_non_destructive_unsave_and_utilization(api_client, db_session):
    sess_hdr = {"X-Session-Id": "sess-upg-1"}

    # Seed verified job
    mock_job = RawDiscoveredJob(
        source="greenhouse",
        external_id="upg-1",
        company="VectorScale",
        title="Junior Python & Kubernetes Engineer",
        location="Bengaluru, India",
        description="Build FastAPI microservices using Python, SQL, and Docker/Kubernetes.",
        apply_url="https://boards.greenhouse.io/vectorscale/jobs/upg-1",
        required_skills=["Python", "SQL", "FastAPI", "Docker", "Kubernetes"],
        role_category="Software / Backend Engineer",
        seniority_level="entry_level",
        is_entry_level_priority=True,
    )
    with patch(
        "backend.services.discovery_sources.DiscoverySourcesClient.fetch_all",
        return_value=([mock_job], ["greenhouse:vectorscale"]),
    ):
        assert api_client.post("/api/v1/pipeline/run", json={"trigger_type": "manual"}).status_code == 200

    # Privacy-first upload: persist=False must NOT write Resume row to DB
    up_priv = api_client.post(
        "/api/v1/resume/upload",
        headers=sess_hdr,
        params={"persist": False},
        files={"file": ("alex.pdf", build_sample_pdf_bytes(), "application/pdf")},
    )
    assert up_priv.status_code == 201
    assert db_session.query(Resume).count() == 0

    # Explicit consent upload: persist=True stores encrypted Resume row
    up_cons = api_client.post(
        "/api/v1/resume/upload",
        headers=sess_hdr,
        params={"persist": True},
        files={"file": ("alex.pdf", build_sample_pdf_bytes(), "application/pdf")},
    )
    assert up_cons.status_code == 201
    assert db_session.query(Resume).count() == 1

    # Resume utilization analytics endpoint uses real computed matches
    util = api_client.get("/api/v1/resume/utilization", headers=sess_hdr)
    assert util.status_code == 200
    u_data = util.json()
    assert u_data["total_jobs_analyzed"] == 1
    assert len(u_data["most_requested_matching_skills"]) >= 1
    assert any(x["skill"] == "Kubernetes" for x in u_data["missing_skills_gap"])

    jobs = api_client.get("/api/v1/jobs", headers=sess_hdr).json()
    jid = jobs["items"][0]["id"]

    # Clicking external link marks 'Pending Confirmation', NOT 'Applied'
    clk = api_client.patch(f"/api/v1/jobs/{jid}/application", headers=sess_hdr, json={"clicked_apply": True})
    assert clk.status_code == 200
    assert clk.json()["status"] == "Pending Confirmation"
    assert clk.json()["clicked_apply_at"] is not None

    # Save + record notes, then move to Offer, then remove from Saved Jobs
    api_client.patch(f"/api/v1/jobs/{jid}/application", headers=sess_hdr, json={"is_saved": True, "notes": "Strong fit"})
    saved_list = api_client.get("/api/v1/jobs", headers=sess_hdr, params={"saved_only": True}).json()
    assert saved_list["total"] == 1
    assert saved_list["items"][0]["application"]["saved_at"] is not None

    conf = api_client.patch(
        f"/api/v1/jobs/{jid}/application",
        headers=sess_hdr,
        json={"status": "Offer", "user_approved": True},
    )
    assert conf.status_code == 200
    assert conf.json()["status"] == "Offer"

    # Non-destructive removal from Saved Jobs preserves Offer status, notes, history & shared job
    unsave = api_client.patch(f"/api/v1/jobs/{jid}/application", headers=sess_hdr, json={"is_saved": False})
    assert unsave.status_code == 200
    assert unsave.json()["is_saved"] is False
    assert unsave.json()["status"] == "Offer"
    assert unsave.json()["notes"] == "Strong fit"
    assert len(unsave.json()["status_history"]) >= 2
    assert db_session.query(JobListing).filter(JobListing.id == jid).count() == 1


def test_tokenizer_synonyms_and_corpus_idf():
    tokens = _tokenize_domain_terms("Built K8s microservices in JS & Py with LLM RAG pipelines")
    assert "kubernetes" in tokens
    assert "javascript" in tokens
    assert "python" in tokens
    assert "retrieval augmented generation" in tokens

    class _DummyJob:
        def __init__(self, title, skills, role_category):
            self.title = title
            self.required_skills_json = skills
            self.role_category = role_category

    idf = compute_corpus_idf(
        [
            _DummyJob("Python Engineer", ["Python", "SQL"], "Backend"),
            _DummyJob("Python ML Engineer", ["Python", "PyTorch"], "AI/ML"),
            _DummyJob("Python Platform Engineer", ["Python", "FastAPI"], "Backend"),
        ]
    )
    # Rare term ('pytorch') must have higher IDF than universal term ('python')
    assert idf["pytorch"] > idf["python"]

    # Boundary-exact matching: 'Java' must NOT falsely match 'JavaScript'
    assert exact_term_in_text("Java", "looking for javascript and react developer") is False
    assert exact_term_in_text("Java", "looking for core java and spring boot developer") is True
    assert exact_term_in_text("C++", "experience with c++ and embedded linux") is True
