"""Next-Generation SaaS Dashboard for Personal AI JobPilot (16-Page Collapsible Navigation)."""

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(_PROJECT_ROOT) / ".env")

from frontend.api_client import JobPilotAPIClient
from frontend.components import (
    TRACKER_STATUSES,
    format_date,
    render_badges,
    render_job_card,
    render_kpi_card,
    render_overview_charts,
)
from frontend.js_widgets import (
    render_funnel_and_skills_html,
    render_kanban_board_html,
    render_kpi_strip_html,
)
from frontend.styles import get_theme_css

st.set_page_config(
    page_title="Personal AI JobPilot",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAV_GROUPS = {
    "MAIN MENU": [
        ("📊", "Dashboard"),
        ("🎯", "AI Job Matching"),
        ("🔥", "Daily Job Feed"),
        ("🎓", "Fresher Jobs"),
        ("🌐", "Remote Jobs"),
        ("🏢", "Hybrid Jobs"),
        ("📍", "On-site Jobs"),
        ("⭐", "Saved Jobs"),
        ("📌", "Application Tracker"),
    ],
    "CAREER INTELLIGENCE": [
        ("📄", "Resume Analyzer"),
        ("📈", "Resume Utilization"),
        ("🧬", "Career Profile"),
        ("💬", "AI Career Assistant"),
    ],
    "PREFERENCES": [
        ("⚙️", "Settings"),
        ("🔔", "Notifications"),
        ("🔐", "Account and Security"),
    ],
}


@st.cache_resource
def get_client(session_id: str = "ephemeral-default", username: str = "default") -> JobPilotAPIClient:
    return JobPilotAPIClient(
        base_url=os.getenv("FRONTEND_API_URL", "http://127.0.0.1:8000"),
        auth_token=os.getenv("API_AUTH_TOKEN", ""),
        session_id=session_id,
        username=username,
    )


@st.cache_data(ttl=20, show_spinner=False)
def cached_health(_ver: int) -> Dict[str, Any]:
    return get_client().health()


@st.cache_data(ttl=45, show_spinner=False)
def cached_overview(_ver: int, session_id: str, username: str) -> Dict[str, Any]:
    return get_client(session_id, username).get_overview_analytics()


@st.cache_data(ttl=45, show_spinner=False)
def cached_active_resume(_ver: int, session_id: str, username: str) -> Optional[Dict[str, Any]]:
    return get_client(session_id, username).get_active_resume()


@st.cache_data(ttl=45, show_spinner=False)
def cached_utilization(_ver: int, session_id: str, username: str) -> Optional[Dict[str, Any]]:
    return get_client(session_id, username).get_resume_utilization()


@st.cache_data(ttl=45, show_spinner=False)
def cached_preferences(_ver: int, session_id: str, username: str) -> Dict[str, Any]:
    return get_client(session_id, username).get_preferences()


@st.cache_data(ttl=45, show_spinner=False)
def cached_notifications(_ver: int, session_id: str, username: str) -> list:
    return get_client(session_id, username).list_notifications(unread_only=False)


@st.cache_data(ttl=45, show_spinner=False)
def cached_jobs(_ver: int, session_id: str, username: str, **params) -> Dict[str, Any]:
    return get_client(session_id, username).list_jobs(**params)


def bump_data_version() -> None:
    st.session_state["data_version"] = st.session_state.get("data_version", 0) + 1
    st.cache_data.clear()


def _init_session_defaults() -> None:
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = uuid.uuid4().hex[:16]
    defaults = {
        "data_version": 0,
        "active_page": "Dashboard",
        "active_username": "default",
        "theme": "dark",
        "chat_session_id": "default",
        "default_fresher_only": True,
        "default_min_match": 0,
        "default_page_size": 15,
        "hide_dismissed": True,
        "persist_resume_consent": False,
        "logged_out_notice": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _logout_current_session(client: JobPilotAPIClient) -> None:
    try:
        client.logout_session()
    except Exception:
        pass
    for key in list(st.session_state.keys()):
        if key.startswith("full_desc_"):
            del st.session_state[key]
    st.session_state["session_id"] = uuid.uuid4().hex[:16]
    st.session_state["logged_out_notice"] = True
    bump_data_version()
    st.rerun()


def render_filtered_job_section(
    client: JobPilotAPIClient,
    section_key: str,
    title: str,
    subtitle: str,
    filter_options: Optional[Dict[str, Any]] = None,
    fixed_work_mode: Optional[str] = None,
    saved_only: bool = False,
    fresher_default: Optional[bool] = None,
    fixed_match_tier: str = "all",
    min_match_default: Optional[int] = None,
) -> None:
    st.subheader(title)
    st.caption(subtitle)

    opts = filter_options or {}
    all_states: List[str] = opts.get("all_india_states") or []
    cities: List[str] = opts.get("cities") or []
    countries: List[str] = ["All"] + (opts.get("countries") or [])
    role_categories: List[str] = ["All"] + (opts.get("role_categories") or [])

    with st.expander("🔍 Search, Geography, Skills & Match Filters", expanded=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns([2.2, 1.3, 1.3, 1.4])
        search_q = r1c1.text_input("Keyword / Title", placeholder="Search role, company, or skill...", key=f"{section_key}_q")
        company_q = r1c2.text_input("Company", placeholder="e.g., Stripe, Sarvam, Bosch", key=f"{section_key}_comp")
        skill_q = r1c3.text_input("Skill", placeholder="e.g., Python, SQL, PyTorch", key=f"{section_key}_skill")
        role_cat = r1c4.selectbox("Category", role_categories, key=f"{section_key}_role")

        r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns([1.1, 1.1, 1.4, 1.3, 1.2])
        seniority = r2c1.selectbox("Experience", ["All", "intern", "new_grad", "entry_level", "mid", "senior"], key=f"{section_key}_sen")
        emp_type = r2c2.selectbox("Employment Type", ["All", "Full-time", "Internship", "Contract"], key=f"{section_key}_emp")
        selected_states = r2c3.multiselect("India States / UTs", all_states, key=f"{section_key}_states")
        selected_cities = r2c4.multiselect("Cities", cities, key=f"{section_key}_cities")
        country = "All" if selected_states else r2c5.selectbox("Country", countries, key=f"{section_key}_country")

        r3c1, r3c2, r3c3, r3c4, r3c5, r3c6 = st.columns([1.6, 1.0, 1.2, 1.3, 1.1, 1.3])
        default_mm = min_match_default if min_match_default is not None else int(st.session_state["default_min_match"])
        min_match = r3c1.slider("Minimum Match % (Strict)", 0, 100, default_mm, step=5, key=f"{section_key}_min_match")
        all_india_only = r3c2.checkbox("India Only", value=False, key=f"{section_key}_india")
        default_fr = fresher_default if fresher_default is not None else bool(st.session_state["default_fresher_only"])
        fresher_only = r3c3.checkbox("Fresher / 0-1 Yrs", value=default_fr, key=f"{section_key}_fresher")
        include_global_remote = r3c4.checkbox(
            "Include Worldwide Remote",
            value=True,
            key=f"{section_key}_ww_remote",
            help="When filtering by a Country (e.g. India or Canada) on Remote jobs, also include Remote / Global openings hiring worldwide.",
        )
        posted_choice = r3c5.selectbox("Posted", ["Any time", "Last 24h", "Last 7 days", "Last 30 days"], key=f"{section_key}_posted")
        if fixed_work_mode is None:
            work_mode = r3c6.selectbox("Work Mode", ["All", "remote", "hybrid", "onsite", "unknown"], key=f"{section_key}_wm")
        else:
            work_mode = fixed_work_mode
            r3c6.info(f"Mode: **{fixed_work_mode.title()}**")

    posted_days_map = {"Any time": None, "Last 24h": 1, "Last 7 days": 7, "Last 30 days": 30}
    page_key = f"{section_key}_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    feed = cached_jobs(
        st.session_state["data_version"],
        client.session_id,
        client.username,
        role_category=role_cat,
        seniority_level=seniority,
        work_mode=work_mode,
        cities=",".join(selected_cities) if selected_cities else None,
        states=",".join(selected_states) if selected_states else None,
        country=country,
        all_india_only=all_india_only,
        include_worldwide_remote=include_global_remote,
        company=company_q,
        skill=skill_q,
        employment_type=emp_type,
        fresher_only=fresher_only,
        posted_days=posted_days_map[posted_choice],
        saved_only=saved_only,
        hide_dismissed=bool(st.session_state["hide_dismissed"]),
        min_match=min_match,
        match_tier=fixed_match_tier,
        include_closest_fallback=(min_match >= 60 or fixed_match_tier in ("90-100", "80-89")),
        search=search_q,
        include_description=False,
        page=st.session_state[page_key],
        page_size=int(st.session_state["default_page_size"]),
    )

    jobs = feed.get("items", [])
    closest = feed.get("closest_matches", [])
    total = feed.get("total", 0)
    curr_page = feed.get("page", 1)
    total_pages = feed.get("total_pages", 1)

    p_left, p_mid, p_right = st.columns([4, 1.5, 1.5])
    p_left.markdown(f"**{total:,} verified opportunities** (Showing {len(jobs)} · Page {curr_page} / {total_pages})")
    if p_mid.button("⬅ Previous", disabled=(curr_page <= 1), key=f"{section_key}_prev", width="stretch"):
        st.session_state[page_key] = max(1, curr_page - 1)
        st.rerun()
    if p_right.button("Next ➡", disabled=(curr_page >= total_pages), key=f"{section_key}_next", width="stretch"):
        st.session_state[page_key] = min(total_pages, curr_page + 1)
        st.rerun()

    if not jobs:
        st.info("No genuine verified jobs matched this strict threshold/filter combination.")
        if closest:
            st.markdown("### 🔎 Closest Genuine Matches Below Threshold")
            for c_job in closest[:6]:
                render_job_card(client, c_job, key_prefix=f"{section_key}_closest", on_mutation=bump_data_version)
        return

    for job in jobs:
        render_job_card(client, job, key_prefix=section_key, on_mutation=bump_data_version)


def main() -> None:
    _init_session_defaults()
    sid = st.session_state["session_id"]
    uname = st.session_state["active_username"]
    client = get_client(sid, uname)

    # Load theme preference cleanly before injecting CSS
    try:
        ver = st.session_state["data_version"]
        prefs = cached_preferences(ver, sid, uname)
        active_theme = prefs.get("theme") or st.session_state.get("theme", "dark")
        st.session_state["theme"] = active_theme
        st.session_state["default_fresher_only"] = bool(prefs.get("fresher_filter_default", True))
        st.session_state["persist_resume_consent"] = bool(prefs.get("persist_resume_consent", False))
    except Exception:
        prefs = {}
        active_theme = st.session_state.get("theme", "dark")

    st.markdown(get_theme_css(active_theme), unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 🧭 JobPilot AI")
        st.caption("Privacy-First Career Intelligence · Verified Shared Feed")

        for group_name, items in NAV_GROUPS.items():
            st.markdown(f"<div class='sidebar-group-label'>{group_name}</div>", unsafe_allow_html=True)
            for icon, label in items:
                is_active = st.session_state["active_page"] == label
                btn_type = "primary" if is_active else "secondary"
                if st.button(f"{icon}  {label}", key=f"nav_{label}", type=btn_type, width="stretch"):
                    st.session_state["active_page"] = label
                    st.rerun()

        st.divider()
        t_col1, t_col2 = st.columns(2)
        if t_col1.button("🌙 Dark" if active_theme == "light" else "☀️ Light", width="stretch", key="quick_theme_toggle"):
            new_theme = "light" if active_theme == "dark" else "dark"
            try:
                client.update_preferences({"theme": new_theme})
            except Exception:
                pass
            st.session_state["theme"] = new_theme
            bump_data_version()
            st.rerun()
        if t_col2.button("🚪 Clear", help="Log out & wipe session resume/activity", width="stretch", key="btn_sidebar_logout"):
            _logout_current_session(client)

    try:
        health = cached_health(ver)
        active_resume = cached_active_resume(ver, sid, uname)
        overview = cached_overview(ver, sid, uname)
        all_notifications = cached_notifications(ver, sid, uname)
    except Exception as exc:
        st.warning(f"Backend temporarily unreachable or busy at `{client.base_url}` ({exc}).")
        if st.button("🔄 Retry Connection", width="content"):
            st.cache_data.clear()
            st.rerun()
        return

    unread_notifs = [n for n in all_notifications if not n.get("is_read")]
    llm_info = health.get("llm") or {}

    st.markdown(
        f"""
        <div class="jp-hero-banner">
            <div>
                <div class="jp-hero-title">🧭 Personal AI JobPilot</div>
                <p class="jp-hero-sub">Tokenized + {health.get('embedding_model', 'all-MiniLM-L6-v2')} Matching · Official Verified Job Pool · Gemini Assistant</p>
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <span class="jp-live-pill"><span class="jp-live-dot"></span> Live · {len(unread_notifs)} Alerts</span>
                <span class="badge badge-purple">{llm_info.get('model', 'LLM Ready')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.pop("logged_out_notice", False):
        st.success("Session cleared cleanly — uploaded resume, scores, and temporary state wiped.")

    # Quick Search Bar & Upload Prompt on Dashboard if no active resume
    selected_page = st.session_state["active_page"]
    filter_opts = overview.get("filter_options") or {}
    kpis = overview.get("kpis") or {}
    charts = overview.get("charts") or {}

    if not active_resume and selected_page not in ("Resume Analyzer", "Account and Security"):
        with st.expander("📄 Upload Your Resume to Unlock Personalized Match Predictions (Session-Only by Default)", expanded=True):
            c_up1, c_up2 = st.columns([3, 1.5])
            qup = c_up1.file_uploader("Upload PDF or DOCX resume", type=["pdf", "docx"], key="quick_top_uploader")
            consent_box = c_up2.checkbox(
                "Persist encrypted resume across restarts",
                value=bool(st.session_state["persist_resume_consent"]),
                key="quick_persist_consent",
            )
            if qup is not None and c_up2.button("⚡ Match Shared Jobs", type="primary", width="stretch", key="btn_quick_upload"):
                with st.spinner("Tokenizing & embedding resume against verified opportunities..."):
                    res = client.upload_resume(
                        filename=qup.name,
                        file_bytes=qup.getvalue(),
                        content_type=qup.type or "application/octet-stream",
                        persist=consent_box,
                    )
                    bump_data_version()
                    st.toast(f"Scored {res['jobs_rescored']:,} jobs for {qup.name}")
                    st.rerun()

    # =========================================================================
    # 1. DASHBOARD
    # =========================================================================
    if selected_page == "Dashboard":
        render_kpi_strip_html(kpis, theme=active_theme)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            render_kpi_card("Remote / Hybrid / On-site", f"{kpis.get('remote_jobs', 0)} / {kpis.get('hybrid_jobs', 0)} / {kpis.get('onsite_jobs', 0)}", "Verified work modes")
        with m2:
            render_kpi_card("High Match (70%+)", kpis.get("high_match_jobs", 0), f"90%+: {kpis.get('tier_90_100', 0)} · 80-89%: {kpis.get('tier_80_89', 0)}")
        with m3:
            render_kpi_card("Applications Tracked", kpis.get("applied_jobs", 0), f"Saved: {kpis.get('saved_jobs', 0)} · Two-step confirmed")
        with m4:
            top_skill = (charts.get("top_matching_skills") or [{}])[0].get("skill", "Upload resume")
            render_kpi_card("Top Resume Utilization Skill", top_skill, f"Peak Score: {kpis.get('max_match_score', 0.0)}%")

        render_funnel_and_skills_html(
            funnel=charts.get("pipeline_funnel") or [],
            top_matching=charts.get("top_matching_skills") or [],
            top_missing=charts.get("top_missing_skills") or [],
            recent_activity=overview.get("recent_activity") or [],
            theme=active_theme,
        )

        qa1, qa2, qa3, qa4 = st.columns(4)
        if qa1.button("🎯 Open AI Job Matching", type="primary", width="stretch"):
            st.session_state["active_page"] = "AI Job Matching"
            st.rerun()
        if qa2.button("🚀 Run Daily Discovery", width="stretch"):
            run = client.trigger_pipeline(verify_urls_live=False, background=True)
            bump_data_version()
            st.toast(f"Discovery Run #{run['id']} started in background.")
        if qa3.button("📈 Inspect Resume Utilization", width="stretch"):
            st.session_state["active_page"] = "Resume Utilization"
            st.rerun()
        if qa4.button("💬 Ask AI Assistant", width="stretch"):
            st.session_state["active_page"] = "AI Career Assistant"
            st.rerun()

        render_overview_charts(charts, theme=active_theme)

        st.markdown("### 🔥 Recommended Zero-Experience & Fresher Opportunities")
        rec_feed = cached_jobs(
            ver, sid, uname, fresher_only=True, hide_dismissed=True, page=1, page_size=5
        )
        for job in rec_feed.get("items", []):
            render_job_card(client, job, key_prefix="dash_rec", on_mutation=bump_data_version)

    # =========================================================================
    # 2. AI JOB MATCHING
    # =========================================================================
    elif selected_page == "AI Job Matching":
        st.subheader("AI Job Matching (Embedding + IDF Tokenizer)")
        st.caption(
            f"90%–100%: **{kpis.get('tier_90_100', 0)}** · 80%–89%: **{kpis.get('tier_80_89', 0)}** · 70%–79%: **{kpis.get('tier_70_79', 0)}**"
        )
        tier_choice = st.radio(
            "Match Score Band",
            ["All Scored Roles", "90-100", "80-89", "70-79"],
            horizontal=True,
            key="ai_match_tier",
        )
        tier_val = "all" if tier_choice == "All Scored Roles" else tier_choice
        render_filtered_job_section(
            client=client,
            section_key="aimatch",
            title="Explainable AI Recommendations (Freshers / Zero Experience)",
            subtitle="Scores computed strictly by semantic embeddings, curated skill overlap, and IDF-weighted tokenization.",
            filter_options=filter_opts,
            fresher_default=True,
            fixed_match_tier=tier_val,
            min_match_default=0 if tier_val != "all" else 40,
        )

    # =========================================================================
    # 3. DAILY JOB FEED
    # =========================================================================
    elif selected_page == "Daily Job Feed":
        c_top1, c_top2 = st.columns([3.5, 1.5])
        with c_top1:
            st.subheader("Daily Verified Job Discovery Feed")
            st.caption("Showing official ATS and verified public API listings checked against domain & expiry policies.")
        with c_top2:
            if st.button("🔄 Refresh / Trigger Discovery", type="primary", width="stretch", key="feed_trigger_btn"):
                run = client.trigger_pipeline(verify_urls_live=False, background=True)
                bump_data_version()
                st.toast(f"Discovery Run #{run['id']} queued in background.")
        render_filtered_job_section(
            client=client,
            section_key="daily",
            title="Live Verified Feed",
            subtitle="Filter, sort by genuine match score, bookmark, dismiss, or review official apply links.",
            filter_options=filter_opts,
        )

    # =========================================================================
    # 4. FRESHER JOBS
    # =========================================================================
    elif selected_page == "Fresher Jobs":
        render_filtered_job_section(
            client=client,
            section_key="fresher",
            title="Fresher & Entry-Level Jobs",
            subtitle="Opportunities verified as welcoming 0–1 years, intern, or recent graduate profiles.",
            filter_options=filter_opts,
            fresher_default=True,
        )

    # =========================================================================
    # 5-7. WORK MODE FEEDS (REMOTE / HYBRID / ON-SITE)
    # =========================================================================
    elif selected_page == "Remote Jobs":
        render_filtered_job_section(
            client=client,
            section_key="remote",
            title="Remote Fresher Opportunities",
            subtitle="Verified remote jobs accepting freshers without prior experience.",
            filter_options=filter_opts,
            fixed_work_mode="remote",
            fresher_default=True,
        )

    elif selected_page == "Hybrid Jobs":
        render_filtered_job_section(
            client=client,
            section_key="hybrid",
            title="Hybrid Fresher Opportunities",
            subtitle="Verified hybrid jobs accepting freshers without prior experience.",
            filter_options=filter_opts,
            fixed_work_mode="hybrid",
            fresher_default=True,
        )

    elif selected_page == "On-site Jobs":
        render_filtered_job_section(
            client=client,
            section_key="onsite",
            title="On-site Fresher Opportunities",
            subtitle="Verified office jobs accepting freshers without prior experience.",
            filter_options=filter_opts,
            fixed_work_mode="onsite",
            fresher_default=True,
        )

    # =========================================================================
    # 8. SAVED JOBS
    # =========================================================================
    elif selected_page == "Saved Jobs":
        render_filtered_job_section(
            client=client,
            section_key="saved",
            title="Saved Jobs",
            subtitle="Bookmarked opportunities with saved dates. Removing a bookmark preserves application history & shared listings.",
            filter_options=filter_opts,
            saved_only=True,
            fresher_default=False,
        )

    # =========================================================================
    # 9. APPLICATION TRACKER (KANBAN + TABLE + DETAILS)
    # =========================================================================
    elif selected_page == "Application Tracker":
        st.subheader("Application Tracker")
        st.caption("Two-step safe submission confirmation: external apply links enter Pending Confirmation until you confirm.")

        tracked_resp = cached_jobs(ver, sid, uname, tracked_only=True, hide_dismissed=False, fresher_only=False, page=1, page_size=100)
        tracked_jobs = tracked_resp.get("items", [])

        app_counts = charts.get("application_statuses") or {}
        stage_cols = st.columns(8)
        for idx, s_name in enumerate(["Interested", "Saved", "Applied", "Assessment", "Interview", "Offer", "Rejected", "Withdrawn"]):
            stage_cols[idx].metric(s_name, app_counts.get(s_name, 0))

        tab_kb, tab_tbl, tab_cards = st.tabs(["🗂️ Kanban Board", "📊 Table View", "📝 Details & Follow-ups"])
        with tab_kb:
            render_kanban_board_html(tracked_jobs, theme=active_theme)

        with tab_tbl:
            if not tracked_jobs:
                st.info("No tracked applications yet.")
            else:
                df = pd.DataFrame(
                    [
                        {
                            "ID": j["id"],
                            "Company": j["company"],
                            "Title": j["title"],
                            "Status": (j.get("application") or {}).get("status", "new"),
                            "Match %": (j.get("match") or {}).get("match_score"),
                            "Work Mode": j.get("work_mode"),
                            "Applied Date": format_date((j.get("application") or {}).get("applied_at")),
                            "Follow-up": format_date((j.get("application") or {}).get("follow_up_date")),
                            "Notes": (j.get("application") or {}).get("notes") or "",
                        }
                        for j in tracked_jobs
                    ]
                )
                st.dataframe(df, width="stretch", hide_index=True)

        with tab_cards:
            st_filter = st.selectbox("Filter by Stage", ["All"] + TRACKER_STATUSES[1:], key="tracker_stage_filter")
            filtered_cards = [
                j for j in tracked_jobs
                if st_filter == "All" or (j.get("application") or {}).get("status") == st_filter
            ]
            if not filtered_cards:
                st.info("No tracked jobs in this stage yet.")
            for job in filtered_cards:
                render_job_card(client, job, key_prefix="tracker", on_mutation=bump_data_version, show_tracker_controls=True)

    # =========================================================================
    # 10. RESUME ANALYZER
    # =========================================================================
    elif selected_page == "Resume Analyzer":
        st.subheader("Resume Analyzer & Intelligence")
        c_u, c_h = st.columns(2)
        with c_u:
            uploaded = st.file_uploader("Upload PDF or DOCX Resume", type=["pdf", "docx"], key="analyzer_uploader")
            persist_flag = st.checkbox(
                "Store uploaded resume encrypted in database (Explicit Consent)",
                value=bool(st.session_state["persist_resume_consent"]),
                help="Unchecked keeps your resume purely in temporary session memory.",
            )
            if uploaded is not None and st.button("⚡ Analyze & Match Resume", type="primary", width="stretch"):
                with st.spinner("Parsing resume sections & running tokenizer + embedding matcher..."):
                    res = client.upload_resume(
                        filename=uploaded.name,
                        file_bytes=uploaded.getvalue(),
                        content_type=uploaded.type or "application/octet-stream",
                        persist=persist_flag,
                    )
                    bump_data_version()
                    st.success(f"{res['message']} ({res['jobs_rescored']:,} jobs scored)")
                    st.rerun()

        with c_h:
            history = client.get_resume_history()
            if history:
                opts = {f"#{r['id']} - {r['filename']} ({'ACTIVE' if r['is_active'] else 'inactive'})": r["id"] for r in history}
                chosen = st.selectbox("Session Upload History", list(opts.keys()))
                if st.button("Activate Selected Resume", width="stretch"):
                    res = client.activate_resume(opts[chosen])
                    bump_data_version()
                    st.success(res["message"])
                    st.rerun()

        st.divider()
        if active_resume:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Candidate", active_resume.get("candidate_name") or "Extracted")
            k2.metric("Classification", active_resume.get("experience_level", "entry_level"))
            k3.metric("Graduation Year", active_resume.get("graduation_year") or 2026)
            k4.metric("Skills Count", len(active_resume.get("skills") or []))

            st.markdown("**Preferred / Inferred Roles:** " + (", ".join(active_resume.get("target_roles") or []) or "Not specified"))
            st.markdown("**Extracted Technical Skills**")
            st.markdown(render_badges(active_resume.get("skills") or [], "badge-blue", limit=35), unsafe_allow_html=True)
            st.markdown("**Soft / Professional Skills**")
            st.markdown(render_badges(active_resume.get("soft_skills") or [], "badge-green", limit=20), unsafe_allow_html=True)

            with st.expander("✏️ Edit Extracted Profile & Re-score Jobs"):
                with st.form("edit_resume_analyzer_form"):
                    new_roles = st.text_input("Target Roles (comma-separated)", value=", ".join(active_resume.get("target_roles") or []))
                    new_skills = st.text_input("Skills (comma-separated)", value=", ".join(active_resume.get("skills") or []))
                    new_summary = st.text_area("Summary", value=active_resume.get("summary") or "")
                    if st.form_submit_button("Save Corrections & Re-score", type="primary"):
                        res = client.update_resume_profile(
                            active_resume["id"],
                            {
                                "target_roles": [x.strip() for x in new_roles.split(",") if x.strip()],
                                "skills": [x.strip() for x in new_skills.split(",") if x.strip()],
                                "summary": new_summary.strip(),
                            },
                        )
                        bump_data_version()
                        st.success(f"{res['message']} ({res['jobs_rescored']:,} jobs re-scored)")
                        st.rerun()

            cl, cr = st.columns(2)
            with cl:
                st.markdown("**Education**")
                for e in active_resume.get("education") or []:
                    st.write(f"- {e.get('details') if isinstance(e, dict) else e}")
                st.markdown("**Qualifications**")
                for q in active_resume.get("qualifications") or []:
                    st.write(f"- {q}")
            with cr:
                st.markdown("**Experience**")
                for e in active_resume.get("experience") or []:
                    st.write(f"- {e.get('details') if isinstance(e, dict) else e}")
                st.markdown("**Projects**")
                for p in active_resume.get("projects") or []:
                    st.write(f"- {p.get('details') if isinstance(p, dict) else p}")

    # =========================================================================
    # 11. RESUME UTILIZATION
    # =========================================================================
    elif selected_page == "Resume Utilization":
        st.subheader("Resume Utilization & Compatibility Analytics")
        util = cached_utilization(ver, sid, uname)
        if not util:
            st.info("Upload a resume in Resume Analyzer first to inspect real skill utilization across verified jobs.")
        else:
            u1, u2, u3 = st.columns(3)
            u1.metric("Verified Jobs Analyzed", f"{util['total_jobs_analyzed']:,}")
            u2.metric("Average Compatibility", f"{util['avg_compatibility']:.1f}%")
            u3.metric("Peak Compatibility", f"{util['max_compatibility']:.1f}%")

            for s_txt in util.get("strengths") or []:
                st.success(s_txt)
            for r_txt in util.get("recommended_improvements") or []:
                st.info(r_txt)

            uc1, uc2 = st.columns(2)
            plotly_tpl = "plotly_white" if active_theme == "light" else "plotly_dark"
            with uc1:
                req_skills = util.get("most_requested_matching_skills") or []
                if req_skills:
                    fig = px.bar(
                        x=[x["count"] for x in req_skills],
                        y=[x["skill"] for x in req_skills],
                        orientation="h",
                        title="Most Requested Matching Resume Skills",
                        labels={"x": "Matching Jobs", "y": ""},
                        color_discrete_sequence=["#10b981"],
                    )
                    fig.update_layout(template=plotly_tpl, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis={"categoryorder": "total ascending"}, height=340)
                    st.plotly_chart(fig, config={"responsive": True})
            with uc2:
                miss_skills = util.get("missing_skills_gap") or []
                if miss_skills:
                    fig = px.bar(
                        x=[x["count"] for x in miss_skills],
                        y=[x["skill"] for x in miss_skills],
                        orientation="h",
                        title="Top Missing / High-Demand Skills Gap",
                        labels={"x": "Jobs Requesting", "y": ""},
                        color_discrete_sequence=["#f59e0b"],
                    )
                    fig.update_layout(template=plotly_tpl, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis={"categoryorder": "total ascending"}, height=340)
                    st.plotly_chart(fig, config={"responsive": True})

            st.markdown("### Relevant Job Categories")
            cats = util.get("relevant_categories") or []
            if cats:
                st.dataframe(pd.DataFrame(cats), width="stretch", hide_index=True)

            if util.get("unused_resume_skills"):
                st.markdown("**Rarely Matched Resume Skills in Current Pool**")
                st.markdown(render_badges(util["unused_resume_skills"], "badge-slate"), unsafe_allow_html=True)

    # =========================================================================
    # 12. CAREER PROFILE
    # =========================================================================
    elif selected_page == "Career Profile":
        st.subheader("Career Profile & Personal Preferences")
        st.caption("Persisted cleanly to your isolated profile in the database.")
        with st.form("career_profile_form"):
            c1, c2 = st.columns(2)
            pref_roles = c1.text_input("Preferred Job Titles (comma-separated)", value=", ".join(prefs.get("preferred_roles") or []))
            pref_locs = c2.text_input("Preferred Locations / Cities", value=", ".join(prefs.get("preferred_locations") or []))
            c3, c4 = st.columns(2)
            pref_countries = c3.text_input("Countries", value=", ".join(prefs.get("countries") or ["India"]))
            pref_wms = c4.multiselect("Preferred Work Modes", ["remote", "hybrid", "onsite"], default=[w for w in (prefs.get("work_modes") or ["remote", "hybrid", "onsite"]) if w in ("remote", "hybrid", "onsite")])

            e1, e2, e3 = st.columns(3)
            min_exp = e1.number_input("Min Experience (years)", 0.0, 40.0, float(prefs.get("min_experience", 0.0)), step=0.5)
            max_exp = e2.number_input("Max Experience (years)", 0.0, 40.0, float(prefs.get("max_experience", 2.0)), step=0.5)
            emp_types = e3.multiselect("Employment Types", ["Full-time", "Internship", "Contract", "Part-time"], default=[t for t in (prefs.get("employment_types") or ["Full-time", "Internship"]) if t in ("Full-time", "Internship", "Contract", "Part-time")])

            skills_txt = st.text_input("Core Skills (comma-separated)", value=", ".join(prefs.get("skills") or []))
            c5, c6 = st.columns(2)
            salary_pref = c5.text_input("Salary / CTC Expectation", value=prefs.get("salary_preference") or "")
            edu_qual = c6.text_input("Education Qualifications", value=prefs.get("education_qualifications") or "")

            if st.form_submit_button("💾 Save Career Profile", type="primary"):
                client.update_preferences(
                    {
                        "preferred_roles": [x.strip() for x in pref_roles.split(",") if x.strip()],
                        "preferred_locations": [x.strip() for x in pref_locs.split(",") if x.strip()],
                        "countries": [x.strip() for x in pref_countries.split(",") if x.strip()],
                        "work_modes": pref_wms,
                        "min_experience": float(min_exp),
                        "max_experience": float(max_exp),
                        "employment_types": emp_types,
                        "skills": [x.strip() for x in skills_txt.split(",") if x.strip()],
                        "salary_preference": salary_pref.strip(),
                        "education_qualifications": edu_qual.strip(),
                    }
                )
                bump_data_version()
                st.success("Career Profile saved.")
                st.rerun()

    # =========================================================================
    # 13. AI CAREER ASSISTANT
    # =========================================================================
    elif selected_page == "AI Career Assistant":
        st.subheader("AI Career Assistant (Gemini RAG)")
        st.caption("Grounded strictly in retrieved resume/job facts (highlighted clearly from AI recommendations).")

        chat_jobs = cached_jobs(ver, sid, uname, fresher_only=False, page=1, page_size=40).get("items", [])
        job_options = {"All Top Session Matches": None}
        for j in chat_jobs:
            job_options[f"#{j['id']} - {j['title']} @ {j['company']} ({j['work_mode']})"] = j["id"]

        c1, c2 = st.columns([3.5, 1])
        chosen_job = c1.selectbox("Focus Job (Retrieved SQLite Context)", list(job_options.keys()))
        focused_id = job_options[chosen_job]
        if c2.button("Clear Chat", width="stretch"):
            client.clear_chat_history(st.session_state["chat_session_id"])
            st.rerun()

        b1, b2, b3, b4 = st.columns(4)
        qp = None
        if b1.button("Explain top matches", width="stretch"):
            qp = "Explain my top matching jobs and why they fit my resume."
        if b2.button("Missing skill roadmap", width="stretch"):
            qp = "Which missing skills appear most frequently across my matches?"
        if b3.button("Improve my resume", width="stretch"):
            qp = "What concrete improvements would raise my compatibility score?"
        if b4.button("Interview prep checklist", width="stretch"):
            qp = "Give me an interview prep checklist tailored to my best matching roles."

        for msg in client.get_chat_history(st.session_state["chat_session_id"]):
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant" and msg.get("referenced_job_ids"):
                    st.caption(f"📚 Retrieved Job IDs: {', '.join(f'#{jid}' for jid in msg['referenced_job_ids'][:6])} · 🤖 AI Guidance Below")
                st.markdown(msg["content"])

        user_p = st.chat_input("Ask about job descriptions, matching scores, missing skills, or interview prep...")
        prompt = qp or user_p
        if prompt:
            with st.spinner("Retrieving grounded resume & verified job context..."):
                client.chat(prompt, session_id=st.session_state["chat_session_id"], job_id=focused_id)
            st.rerun()

    # =========================================================================
    # 14. SETTINGS (THEME + AUTOMATION + SOURCES)
    # =========================================================================
    elif selected_page == "Settings":
        st.subheader("Platform Settings & Automatic Discovery")
        with st.form("platform_settings_form"):
            theme_choice = st.selectbox("UI Theme", ["dark", "light"], index=0 if active_theme == "dark" else 1)
            auto_disc = st.checkbox("Automatic Daily Job Discovery (Asia/Kolkata)", value=bool(prefs.get("auto_daily_discovery", True)))
            fresher_def = st.checkbox("Default Feeds to Fresher-Eligible Filter", value=bool(st.session_state["default_fresher_only"]))
            dedup_on = st.checkbox("Duplicate Job Detection Across Sources", value=bool(prefs.get("dedup_enabled", True)))
            page_sz = st.selectbox("Jobs per Page", [10, 15, 25, 50], index=[10, 15, 25, 50].index(int(st.session_state["default_page_size"])))
            hide_dis = st.checkbox("Hide Dismissed Jobs from Feeds", value=bool(st.session_state["hide_dismissed"]))

            if st.form_submit_button("💾 Save Settings", type="primary"):
                client.update_preferences(
                    {
                        "theme": theme_choice,
                        "auto_daily_discovery": auto_disc,
                        "fresher_filter_default": fresher_def,
                        "dedup_enabled": dedup_on,
                    }
                )
                st.session_state["theme"] = theme_choice
                st.session_state["default_fresher_only"] = fresher_def
                st.session_state["default_page_size"] = page_sz
                st.session_state["hide_dismissed"] = hide_dis
                bump_data_version()
                st.success("Settings saved.")
                st.rerun()

        st.divider()
        st.markdown("### Scheduler & Pipeline Telemetry")
        sched = client.get_scheduler_status()
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Scheduler", "Running" if sched["running"] else "Stopped")
        sc2.metric("Cron (Asia/Kolkata)", sched["cron_expression"])
        sc3.metric("Next Scheduled Run", format_date(sched.get("next_run_time")))

        runs = client.list_pipeline_runs()
        if runs:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Run ID": r["id"],
                            "Trigger": r["trigger_type"],
                            "Status": r["status"],
                            "Fetched": r["total_fetched"],
                            "New Verified": r["new_verified_jobs"],
                            "Duplicates": r["duplicates_skipped"],
                            "Started": format_date(r.get("started_at")),
                        }
                        for r in runs[:15]
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    # =========================================================================
    # 15. NOTIFICATIONS
    # =========================================================================
    elif selected_page == "Notifications":
        st.subheader("Notifications & Alert Channel Settings")
        st.caption("Dashboard and DB remain the single source of truth; verified email is used as a duplicate-safe notification channel.")

        with st.form("email_verify_form"):
            c_e1, c_e2 = st.columns([3, 1.5])
            email_val = c_e1.text_input("Notification Email", value=prefs.get("email_address") or "", placeholder="you@example.com")
            notif_on = c_e2.checkbox("Enable Alerts", value=bool(prefs.get("notifications_enabled", True)))
            if st.form_submit_button("✅ Verify & Save Email Channel", type="primary"):
                client.verify_email(email_val)
                client.update_preferences({"notifications_enabled": notif_on})
                bump_data_version()
                st.success(f"Verified alert email set to {email_val}")
                st.rerun()

        if prefs.get("email_verified"):
            st.success(f"Verified Email Channel: `{prefs.get('email_address')}`")
        else:
            st.info("No verified alert email configured yet.")

        st.markdown(f"### Session Alerts ({len(all_notifications)})")
        if not all_notifications:
            st.caption("No alerts triggered yet in this session.")
        for n in all_notifications:
            with st.container(border=True):
                c1, c2 = st.columns([4.5, 1])
                c1.markdown(f"**{n['title']}**")
                c1.caption(n["message"])
                if not n.get("is_read"):
                    if c2.button("Mark Read", key=f"np_{n['id']}", width="stretch"):
                        client.mark_notification_read(n["id"])
                        bump_data_version()
                        st.rerun()
                else:
                    c2.caption("Read")

    # =========================================================================
    # 16. ACCOUNT AND SECURITY
    # =========================================================================
    elif selected_page == "Account and Security":
        st.subheader("Account, Privacy Consent & Session Management")
        st.caption("Operate immediately in Ephemeral Privacy Mode or switch isolated profile workspaces.")

        c_sec1, c_sec2 = st.columns(2)
        with c_sec1:
            st.markdown("#### 🔒 Privacy & Data Retention Controls")
            consent = st.checkbox(
                "Persist uploaded resumes encrypted at rest (Default: Off / RAM-only)",
                value=bool(st.session_state["persist_resume_consent"]),
                key="sec_persist_consent",
            )
            if st.button("Update Privacy Setting", width="stretch"):
                client.update_preferences({"persist_resume_consent": consent})
                st.session_state["persist_resume_consent"] = consent
                bump_data_version()
                st.success("Privacy setting updated.")

            if st.button("🚪 Clear Current Session & Log Out", type="primary", width="stretch", key="sec_logout_btn"):
                _logout_current_session(client)

        with c_sec2:
            st.markdown("#### 👤 Profile Workspace Switcher (Optional)")
            try:
                users = client.list_users()
            except Exception:
                users = [{"username": "default", "display_name": "Default Workspace"}]
            usernames = [u["username"] for u in users] or ["default"]
            if uname not in usernames:
                usernames.append(uname)
            chosen_u = st.selectbox("Active Preference Profile", usernames, index=usernames.index(uname))
            if chosen_u != uname:
                st.session_state["active_username"] = chosen_u
                bump_data_version()
                st.rerun()

            new_u = st.text_input("Create Isolated Profile Workspace", placeholder="e.g., alice")
            if st.button("Create & Switch Profile", width="stretch") and new_u.strip():
                created = client.create_user(new_u.strip())
                st.session_state["active_username"] = created["username"]
                bump_data_version()
                st.rerun()


if __name__ == "__main__":
    main()
