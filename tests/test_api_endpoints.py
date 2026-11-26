"""FastAPI integration tests covering resume, jobs, manual approval constraint, pipeline, chat, and multi-user isolation."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from backend.services.discovery_sources import RawDiscoveredJob
from tests.helpers import build_sample_docx_bytes, build_sample_pdf_bytes


def test_full_api_workflow(api_client):
    # 1. Health check
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # 2. Upload PDF resume
    up1 = api_client.post(
        "/api/v1/resume/upload",
        files={"file": ("alex.pdf", build_sample_pdf_bytes(), "application/pdf")},
    )
    assert up1.status_code == 201
    assert up1.json()["replaced_previous"] is False
    assert "Python" in up1.json()["profile"]["skills"]

    # 3. Replace with DOCX resume
    up2 = api_client.post(
        "/api/v1/resume/upload",
        files={
            "file": (
                "jordan.docx",
                build_sample_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert up2.status_code == 201
    assert up2.json()["replaced_previous"] is True

    # 4. Run discovery pipeline with mocked official sources
    mock_job = RawDiscoveredJob(
        source="greenhouse",
        external_id="api-1",
        company="SynthData",
        title="Entry-Level Data Analyst",
        location="Remote",
        description="Analyze metrics using Python, SQL, and Tableau.",
        apply_url="https://boards.greenhouse.io/synthdata/jobs/api-1",
        required_skills=["Python", "SQL", "Tableau"],
        role_category="Data Analyst",
        seniority_level="entry_level",
        is_entry_level_priority=True,
    )
    with patch(
        "backend.services.discovery_sources.DiscoverySourcesClient.fetch_all",
        return_value=([mock_job], ["greenhouse:synthdata"]),
    ):
        run_resp = api_client.post("/api/v1/pipeline/run", json={"trigger_type": "manual"})
    assert run_resp.status_code == 200
    assert run_resp.json()["new_verified_jobs"] == 1

    # 5. List jobs and check strict min_match filter enforcement
    jobs_resp = api_client.get("/api/v1/jobs")
    assert jobs_resp.status_code == 200
    items = jobs_resp.json()["items"]
    assert len(items) == 1
    job_id = items[0]["id"]
    assert items[0]["apply_url"] == "https://boards.greenhouse.io/synthdata/jobs/api-1"
    assert items[0]["match"]["match_score"] > 0

    strict_80 = api_client.get("/api/v1/jobs", params={"min_match": 99.9})
    assert strict_80.status_code == 200
    assert strict_80.json()["total"] == 0

    # 6. Enforce manual review & approval before marking as 'Applied'
    bad_apply = api_client.patch(
        f"/api/v1/jobs/{job_id}/application",
        json={"status": "Applied", "user_approved": False},
    )
    assert bad_apply.status_code == 400

    good_apply = api_client.patch(
        f"/api/v1/jobs/{job_id}/application",
        json={"status": "Applied", "is_saved": True, "user_approved": True, "notes": "Reviewed and submitted manually"},
    )
    assert good_apply.status_code == 200
    assert good_apply.json()["status"] == "Applied"
    assert good_apply.json()["user_approved"] is True

    # 7. Resume edit & reactivation endpoints
    edit_res = api_client.patch(
        f"/api/v1/resume/{up2.json()['profile']['id']}",
        json={"graduation_year": 2026, "preferred_locations": ["Hyderabad", "Bangalore", "Remote"]},
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["profile"]["graduation_year"] == 2026

    act_res = api_client.post(f"/api/v1/resume/{up1.json()['profile']['id']}/activate")
    assert act_res.status_code == 200
    assert act_res.json()["profile"]["id"] == up1.json()["profile"]["id"]

    # 8. Overview analytics endpoint
    ov = api_client.get("/api/v1/analytics/overview")
    assert ov.status_code == 200
    assert ov.json()["kpis"]["total_jobs"] == 1

    # 7. Notifications & Chat endpoints
    notifs = api_client.get("/api/v1/notifications").json()
    assert len(notifs) == 1

    chat_resp = api_client.post(
        "/api/v1/chat",
        json={"message": "Explain this Data Analyst role", "job_id": job_id},
    )
    assert chat_resp.status_code == 200
    assert "SynthData" in chat_resp.json()["reply"]


def test_multiuser_isolation_shared_jobs(api_client):
    """Concurrent ephemeral sessions share the verified JobListing pool while user data clears cleanly on logout."""
    alice_hdr = {"X-Session-Id": "session-alice"}
    bob_hdr = {"X-Session-Id": "session-bob"}

    # Fresh sessions start empty with no login or stored resume
    assert api_client.get("/api/v1/resume/active", headers=alice_hdr).status_code == 404
    assert api_client.get("/api/v1/resume/active", headers=bob_hdr).status_code == 404

    # Upload separate resumes for Alice and Bob in RAM
    r_alice = api_client.post(
        "/api/v1/resume/upload",
        headers=alice_hdr,
        files={"file": ("alice.pdf", build_sample_pdf_bytes(), "application/pdf")},
    )
    r_bob = api_client.post(
        "/api/v1/resume/upload",
        headers=bob_hdr,
        files={
            "file": (
                "bob.docx",
                build_sample_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert r_alice.status_code == 201
    assert r_bob.status_code == 201
    alice_resume_id = r_alice.json()["profile"]["id"]

    # Bob's session only contains Bob's resume history
    bob_hist = api_client.get("/api/v1/resume/history", headers=bob_hdr).json()
    assert len(bob_hist) == 1
    assert bob_hist[0]["filename"] == "bob.docx"
    assert api_client.delete(f"/api/v1/resume/{alice_resume_id + 99}", headers=bob_hdr).status_code == 404

    # Discover shared verified jobs once into persistent shared repository
    mock_jobs = [
        RawDiscoveredJob(
            source="greenhouse",
            external_id="shared-1",
            company="SharedCorp",
            title="Junior Python Backend Engineer",
            location="Bengaluru, Karnataka, India",
            description="Entry-level role working with Python, SQL, FastAPI, and REST APIs.",
            apply_url="https://boards.greenhouse.io/sharedcorp/jobs/shared-1",
            required_skills=["Python", "SQL", "FastAPI"],
            role_category="Software / Backend Engineer",
            seniority_level="entry_level",
            is_entry_level_priority=True,
        ),
        RawDiscoveredJob(
            source="lever",
            external_id="shared-2",
            company="SharedAI",
            title="Data Science Intern",
            location="Remote, India",
            description="Internship covering Python, Pandas, Machine Learning, and analytics.",
            apply_url="https://jobs.lever.co/sharedai/shared-2",
            required_skills=["Python", "Pandas", "Machine Learning"],
            role_category="Data Science / ML / AI",
            seniority_level="intern",
            is_entry_level_priority=True,
        ),
    ]
    with patch(
        "backend.services.discovery_sources.DiscoverySourcesClient.fetch_all",
        return_value=(mock_jobs, ["greenhouse:sharedcorp", "lever:sharedai"]),
    ):
        run_resp = api_client.post("/api/v1/pipeline/run", json={"trigger_type": "manual"})
    assert run_resp.status_code == 200
    assert run_resp.json()["new_verified_jobs"] == 2

    # Re-upload Alice's resume to score the 2 shared jobs
    api_client.post(
        "/api/v1/resume/upload",
        headers=alice_hdr,
        files={"file": ("alice.pdf", build_sample_pdf_bytes(), "application/pdf")},
    )
    api_client.post(
        "/api/v1/resume/upload",
        headers=bob_hdr,
        files={
            "file": (
                "bob.docx",
                build_sample_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    alice_jobs = api_client.get("/api/v1/jobs", headers=alice_hdr).json()
    bob_jobs = api_client.get("/api/v1/jobs", headers=bob_hdr).json()
    assert alice_jobs["total"] >= 2
    assert bob_jobs["total"] == alice_jobs["total"]
    job_id = alice_jobs["items"][0]["id"]
    assert "token_overlap_score" in alice_jobs["items"][0]["match"]["score_breakdown"]

    # Alice saves & applies to job #1; Bob's state remains isolated ('new')
    patch_alice = api_client.patch(
        f"/api/v1/jobs/{job_id}/application",
        headers=alice_hdr,
        json={"status": "Applied", "is_saved": True, "user_approved": True, "notes": "Alice applied"},
    )
    assert patch_alice.status_code == 200
    assert patch_alice.json()["status"] == "Applied"

    alice_detail = api_client.get(f"/api/v1/jobs/{job_id}", headers=alice_hdr).json()
    bob_detail = api_client.get(f"/api/v1/jobs/{job_id}", headers=bob_hdr).json()
    assert alice_detail["application"]["status"] == "Applied"
    assert alice_detail["application"]["is_saved"] is True
    assert bob_detail["application"]["status"] == "new"
    assert bob_detail["application"]["is_saved"] is False

    # Chat remains isolated per session
    c_alice = api_client.post(
        "/api/v1/chat",
        headers=alice_hdr,
        json={"message": "Summarize my top match", "session_id": "shared-sess", "job_id": job_id},
    )
    assert c_alice.status_code == 200
    assert len(api_client.get("/api/v1/chat/history?session_id=shared-sess", headers=alice_hdr).json()) == 2
    assert api_client.get("/api/v1/chat/history?session_id=shared-sess", headers=bob_hdr).json() == []

    # Concurrent multi-session reads
    def _fetch_overview(hdr):
        return api_client.get("/api/v1/analytics/overview", headers=hdr)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_fetch_overview, [alice_hdr, bob_hdr, alice_hdr, bob_hdr]))
    assert all(r.status_code == 200 for r in results)
    assert [r.json()["kpis"]["applied_jobs"] for r in results] == [1, 0, 1, 0]

    # Alice logs out -> all personal session data wiped immediately with zero data persisted
    out = api_client.post("/api/v1/session/logout", headers=alice_hdr)
    assert out.status_code == 200
    assert out.json()["logged_out"] is True
    assert out.json()["persisted_user_data"] is False
    assert api_client.get("/api/v1/resume/active", headers=alice_hdr).status_code == 404
    assert api_client.get("/api/v1/analytics/overview", headers=alice_hdr).json()["kpis"]["applied_jobs"] == 0
    assert api_client.get("/api/v1/chat/history?session_id=shared-sess", headers=alice_hdr).json() == []
    assert api_client.get("/api/v1/resume/active", headers=bob_hdr).status_code == 200


def test_remote_worldwide_and_entry_level_filter_semantics(api_client):
    """Remote country filters include Remote / Global by default, and entry_level matches new_grad + entry_level."""
    mock_jobs = [
        RawDiscoveredJob(
            source="greenhouse",
            external_id="rem-ww-1",
            company="RemoteStartup",
            title="Software Engineer - New Grad",
            location="Worldwide",
            description="No prior experience required. Remote anywhere.",
            apply_url="https://boards.greenhouse.io/remotestartup/jobs/1",
            required_skills=["Python", "SQL"],
            role_category="Software / Backend Engineer",
            seniority_level="new_grad",
            is_entry_level_priority=True,
            fresher_eligible=True,
            is_remote=True,
            work_mode="remote",
            country="Remote / Global",
        ),
        RawDiscoveredJob(
            source="ashby",
            external_id="rem-ca-1",
            company="CanadaMNC",
            title="Associate Developer",
            location="Toronto, Canada",
            description="0-1 years experience. Remote across Canada.",
            apply_url="https://jobs.ashbyhq.com/canadamnc/1",
            required_skills=["Python"],
            role_category="Software / Backend Engineer",
            seniority_level="entry_level",
            is_entry_level_priority=True,
            fresher_eligible=True,
            is_remote=True,
            work_mode="remote",
            city="Toronto",
            country="Canada",
        ),
    ]
    with patch(
        "backend.services.discovery_sources.DiscoverySourcesClient.fetch_all",
        return_value=(mock_jobs, ["greenhouse:remotestartup", "ashby:canadamnc"]),
    ):
        run_resp = api_client.post("/api/v1/pipeline/run", json={"trigger_type": "manual"})
        assert run_resp.status_code == 200

    # Canada + remote + entry_level returns Canada exact match first + Remote / Global
    ca_res = api_client.get(
        "/api/v1/jobs",
        params={"work_mode": "remote", "country": "Canada", "seniority_level": "entry_level", "fresher_only": True},
    )
    assert ca_res.status_code == 200
    assert ca_res.json()["total"] == 2
    assert ca_res.json()["items"][0]["country"] == "Canada"

    # India + remote + entry_level includes Worldwide Remote / Global unless include_worldwide_remote=false
    in_res = api_client.get(
        "/api/v1/jobs",
        params={"work_mode": "remote", "country": "India", "seniority_level": "entry_level", "fresher_only": True},
    )
    assert in_res.status_code == 200
    assert in_res.json()["total"] == 1
    in_strict = api_client.get(
        "/api/v1/jobs",
        params={
            "work_mode": "remote",
            "country": "India",
            "seniority_level": "entry_level",
            "fresher_only": True,
            "include_worldwide_remote": False,
        },
    )
    assert in_strict.status_code == 200
    assert in_strict.json()["total"] == 0
