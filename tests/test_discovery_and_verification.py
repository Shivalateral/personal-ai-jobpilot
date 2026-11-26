"""Tests for ATS/API/RSS/Career discovery parsers, anti-LinkedIn policy, and verification/deduplication."""

from backend.agents.verification_agent import JobVerificationAgent
from backend.services.discovery_sources import (
    RawDiscoveredJob,
    is_allowed_domain,
    parse_arbeitnow_payload,
    parse_ashby_payload,
    parse_career_page_html,
    parse_greenhouse_payload,
    parse_lever_payload,
    parse_remotive_payload,
    parse_rss_feed_content,
)


def test_disallowed_scraping_domains():
    assert is_allowed_domain("https://boards.greenhouse.io/acme/jobs/123") is True
    assert is_allowed_domain("https://jobs.lever.co/acme/abc") is True
    assert is_allowed_domain("https://www.linkedin.com/jobs/view/12345") is False
    assert is_allowed_domain("https://lnkd.in/abc") is False
    assert is_allowed_domain("https://www.glassdoor.com/job-listing/123") is False
    assert is_allowed_domain("ftp://example.com/job") is False


def test_ats_and_public_api_parsers():
    gh_jobs = parse_greenhouse_payload(
        "acme-ai",
        {
            "jobs": [
                {
                    "id": 101,
                    "title": "Junior Data Scientist (New Grad)",
                    "location": {"name": "Remote - US"},
                    "absolute_url": "https://boards.greenhouse.io/acme-ai/jobs/101",
                    "updated_at": "2026-11-20T10:00:00Z",
                    "content": "<p>Seeking Python, SQL, Scikit-learn, and PyTorch skills. 0-2 years experience.</p>",
                },
                {
                    "id": 102,
                    "title": "Office Facilities Coordinator",
                    "location": {"name": "New York"},
                    "absolute_url": "https://boards.greenhouse.io/acme-ai/jobs/102",
                    "content": "<p>Manage office snacks and mail.</p>",
                },
            ]
        },
    )
    assert len(gh_jobs) == 2
    assert gh_jobs[0].seniority_level == "new_grad"
    assert gh_jobs[0].is_entry_level_priority is True
    assert "PyTorch" in gh_jobs[0].required_skills

    lever_jobs = parse_lever_payload(
        "data-corp",
        [
            {
                "id": "lv-1",
                "text": "AI/ML Engineer Intern",
                "categories": {"location": "San Francisco, CA", "commitment": "Internship"},
                "applyUrl": "https://jobs.lever.co/data-corp/lv-1/apply",
                "hostedUrl": "https://jobs.lever.co/data-corp/lv-1",
                "descriptionPlain": "Work on LLM and RAG systems with Python and FastAPI.",
                "createdAt": 1763596800000,
            }
        ],
    )
    assert len(lever_jobs) == 1
    assert lever_jobs[0].role_category == "AI & Machine Learning"
    assert lever_jobs[0].seniority_level == "intern"
    assert lever_jobs[0].fresher_eligible is True

    ashby_jobs = parse_ashby_payload(
        "ml-startup",
        {
            "jobs": [
                {
                    "id": "ash-1",
                    "title": "Entry-Level Data Analyst",
                    "location": "Remote",
                    "isRemote": True,
                    "applyUrl": "https://jobs.ashbyhq.com/ml-startup/ash-1",
                    "descriptionPlain": "SQL, Tableau, Pandas, A/B testing.",
                    "publishedAt": "2026-11-22T00:00:00Z",
                }
            ]
        },
    )
    assert len(ashby_jobs) == 1
    assert ashby_jobs[0].role_category == "Data & Analytics"

    rem_jobs = parse_remotive_payload(
        {
            "jobs": [
                {
                    "id": 99,
                    "company_name": "RemoteData",
                    "title": "Junior Machine Learning Engineer",
                    "candidate_required_location": "Worldwide",
                    "url": "https://remotive.com/remote-jobs/data/ml-99",
                    "description": "Python, Docker, Hugging Face.",
                    "publication_date": "2026-11-21T00:00:00",
                }
            ]
        }
    )
    assert len(rem_jobs) == 1

    arb_jobs = parse_arbeitnow_payload(
        {
            "data": [
                {
                    "slug": "ai-intern-berlin",
                    "company_name": "EuroAI",
                    "title": "Data Science Intern",
                    "location": "Berlin",
                    "remote": False,
                    "url": "https://www.arbeitnow.com/view/ai-intern-berlin",
                    "description": "Python, Pandas, Statistics.",
                    "created_at": 1763596800,
                }
            ]
        }
    )
    assert len(arb_jobs) == 1


def test_rss_and_career_page_jsonld_parsers():
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>AI Careers</title>
    <item>
      <title>Data Analyst - New Grad</title>
      <link>https://careers.example.org/jobs/da-1</link>
      <description>SQL, Python, Power BI required.</description>
      <pubDate>Fri, 20 Nov 2026 10:00:00 GMT</pubDate>
    </item>
    </channel></rss>"""
    rss_jobs = parse_rss_feed_content("https://careers.example.org/feed.xml", rss_xml)
    assert len(rss_jobs) == 1
    assert rss_jobs[0].apply_url == "https://careers.example.org/jobs/da-1"

    html_doc = """<html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org/",
      "@type": "JobPosting",
      "title": "Graduate Machine Learning Engineer",
      "description": "Build PyTorch and LangGraph pipelines.",
      "hiringOrganization": {"@type": "Organization", "name": "OpenLab"},
      "jobLocation": {"@type": "Place", "address": {"addressLocality": "London"}},
      "url": "https://openlab.example.com/careers/grad-ml",
      "datePosted": "2026-11-22"
    }
    </script></head><body></body></html>"""
    career_jobs = parse_career_page_html("https://openlab.example.com/careers", html_doc)
    assert len(career_jobs) == 1
    assert career_jobs[0].company == "OpenLab"
    assert "LangGraph" in career_jobs[0].required_skills


def test_work_mode_and_non_tech_filtering():
    from backend.services.discovery_sources import (
        classify_role_category,
        classify_work_mode,
        parse_smartrecruiters_payload,
        verify_fresher_eligibility,
    )
    from backend.services.india_geography import ALL_INDIA_STATES_AND_UTS, resolve_geography

    assert len(ALL_INDIA_STATES_AND_UTS) == 36  # 28 states + 8 UTs
    city, state, country, tier = resolve_geography("Visakhapatnam, India")
    assert (city, state, country, tier) == ("Visakhapatnam", "Andhra Pradesh", "India", "Tier-2")
    city2, state2, country2, tier2 = resolve_geography("Hyderabad, Telangana, India")
    assert (city2, state2, country2, tier2) == ("Hyderabad", "Telangana", "India", "Metro")

    assert classify_work_mode("Remote - India", "Data Analyst", "Work from home") == "remote"
    assert classify_work_mode("Hyderabad, India (Hybrid)", "AI Engineer", "Hybrid schedule") == "hybrid"
    assert classify_work_mode("Bangalore, India", "Data Scientist", "On-site office role") == "onsite"
    assert classify_work_mode("Unspecified", "Data Analyst", "Great team environment") == "unknown"

    # Universal career classification (including BPO/Sales/Software)
    assert classify_role_category("Customer Support Executive (Voice)", "Inbound customer care") == "Customer Support & BPO"
    assert classify_role_category("Data Analyst Intern", "SQL and Python analytics") == "Data & Analytics"

    # Strict fresher check: mandatory 2+ years experience excludes fresher eligibility even if title says Junior/Intern
    sen, prio, fresher = verify_fresher_eligibility("Junior Associate Analyst", "Requires minimum 3 years experience in SQL.")
    assert fresher is False
    assert prio is False

    sen2, prio2, fresher2 = verify_fresher_eligibility("Engineering Manager - Internal Systems Automations Platform", "Lead team")
    assert sen2 == "senior"
    assert fresher2 is False

    # Mandatory 1+ year experience or unmarked role must not be flagged fresher_eligible
    _, _, fresher_1yr = verify_fresher_eligibility("Associate Software Engineer", "Requires minimum 1+ years experience in Python.")
    assert fresher_1yr is False
    _, _, fresher_unmarked = verify_fresher_eligibility("Software Engineer", "Build backend services in Python.")
    assert fresher_unmarked is False
    _, _, fresher_0yr = verify_fresher_eligibility("Software Engineer", "Fresh graduate welcome, no prior experience required.")
    assert fresher_0yr is True

    # Plural internships, 0-2 yrs with spaces, and Associate/Product Manager Intern edge cases
    sen_int, prio_int, fr_int = verify_fresher_eligibility("Engineering Internships 2027", "Early career internship-to-hire.")
    assert (sen_int, prio_int, fr_int) == ("intern", True, True)
    sen_pm, _, fr_pm = verify_fresher_eligibility("Associate Product Manager Intern", "Summer program for university students.")
    assert (sen_pm, fr_pm) == ("intern", True)
    sen_02, _, fr_02 = verify_fresher_eligibility("Junior Backend Developer", "0 - 2 years experience in Python.")
    assert (sen_02, fr_02) == ("entry_level", True)

    # Expanded global & Canadian geography resolution
    assert resolve_geography("Vancouver, BC")[2] == "Canada"
    assert resolve_geography("Montreal, QC, Canada")[2] == "Canada"
    assert resolve_geography("Dublin, Ireland")[2] == "Ireland"
    assert resolve_geography("Tokyo, Japan")[2] == "Japan"
    assert resolve_geography("Worldwide")[2] == "Remote / Global"

    sr = parse_smartrecruiters_payload(
        "BoschGroup",
        {
            "content": [
                {
                    "id": "sr-1",
                    "name": "Graduate Engineer Trainee - Python",
                    "company": {"name": "Bosch Group"},
                    "location": {"city": "Coimbatore", "region": "TN", "country": "in", "remote": False, "hybrid": True, "fullLocation": "Coimbatore, TN, India"},
                    "typeOfEmployment": {"label": "Full-time"},
                    "experienceLevel": {"label": "Entry Level"},
                }
            ]
        },
    )
    assert len(sr) == 1
    assert sr[0].state == "Tamil Nadu"
    assert sr[0].city_tier == "Tier-2"
    assert sr[0].work_mode == "hybrid"


def test_verification_deduplication_and_policy_rejection(db_session):
    verifier = JobVerificationAgent()
    batch = [
        RawDiscoveredJob(
            source="greenhouse",
            external_id="1",
            company="AcmeAI",
            title="AI/ML Intern",
            location="Remote",
            description="Python, PyTorch, RAG.",
            apply_url="https://boards.greenhouse.io/acmeai/jobs/1",
            required_skills=["Python", "PyTorch", "RAG"],
            role_category="ML/Data Intern",
            seniority_level="intern",
            is_entry_level_priority=True,
        ),
        # Duplicate URL in same batch
        RawDiscoveredJob(
            source="greenhouse",
            external_id="1",
            company="AcmeAI",
            title="AI/ML Intern",
            location="Remote",
            description="Python, PyTorch, RAG.",
            apply_url="https://boards.greenhouse.io/acmeai/jobs/1",
            required_skills=["Python", "PyTorch", "RAG"],
            role_category="ML/Data Intern",
            seniority_level="intern",
            is_entry_level_priority=True,
        ),
        # Prohibited LinkedIn URL must be rejected
        RawDiscoveredJob(
            source="rss",
            external_id="li-1",
            company="BlockedCo",
            title="Data Scientist",
            location="NYC",
            description="Python, SQL",
            apply_url="https://www.linkedin.com/jobs/view/999999",
            required_skills=["Python", "SQL"],
            role_category="Data Scientist",
            seniority_level="entry_level",
            is_entry_level_priority=True,
        ),
    ]
    persisted, dupes, rejected = verifier.verify_and_persist(db_session, batch)
    assert len(persisted) == 1
    assert dupes == 1
    assert rejected == 1

    # Re-running same job later must be skipped as duplicate against DB
    persisted2, dupes2, rejected2 = verifier.verify_and_persist(db_session, [batch[0]])
    assert len(persisted2) == 0
    assert dupes2 == 1
    assert rejected2 == 0
