"""Reusable UI components, Plotly charts, and job cards for Personal AI JobPilot."""

import html
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import httpx
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from frontend.api_client import JobPilotAPIClient

TRACKER_STATUSES = [
    "new",
    "Interested",
    "Saved",
    "Pending Confirmation",
    "Applied",
    "Assessment",
    "Interview",
    "Offer",
    "Rejected",
    "Withdrawn",
]


def format_date(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "Not specified"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(iso_str)[:10]


def render_kpi_card(label: str, value: Any, hint: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{html.escape(str(label))}</div>
            <div class="kpi-value">{html.escape(str(value))}</div>
            <div class="kpi-hint">{html.escape(str(hint))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_badges(items: List[str], css_class: str, limit: int = 10) -> str:
    if not items:
        return "<span style='color:#64748b;font-size:0.82rem;'>None listed</span>"
    return " ".join(
        f"<span class='badge {css_class}'>{html.escape(str(item))}</span>" for item in items[:limit]
    )


def _work_mode_badge(work_mode: str) -> str:
    wm = (work_mode or "unknown").lower()
    mapping = {
        "remote": ("🌐 Remote", "badge-green"),
        "hybrid": ("🏢 Hybrid", "badge-blue"),
        "onsite": ("📍 On-site", "badge-amber"),
        "unknown": ("❔ Mode Unspecified", "badge-slate"),
    }
    label, cls = mapping.get(wm, ("❔ Mode Unspecified", "badge-slate"))
    return f"<span class='badge {cls}'>{label}</span>"


def _eligibility_badge(status: str) -> str:
    mapping = {
        "Eligible": ("✅ Fresher / Entry Eligible", "badge-green"),
        "Stretch": ("⚡ Stretch Role", "badge-amber"),
        "Ineligible": ("⏳ Experienced Role", "badge-rose"),
    }
    label, cls = mapping.get(status, (status, "badge-slate"))
    return f"<span class='badge {cls}'>{html.escape(label)}</span>"


def render_overview_charts(charts: Dict[str, Any], theme: str = "dark") -> None:
    """Render interactive Plotly analytics charts styled for active dark or light theme."""
    plotly_tpl = "plotly_white" if (theme or "dark").lower() == "light" else "plotly_dark"
    c1, c2 = st.columns(2)
    with c1:
        buckets = charts.get("score_buckets") or {}
        if buckets:
            fig = px.bar(
                x=list(buckets.keys()),
                y=list(buckets.values()),
                labels={"x": "Match Score Range", "y": "Jobs"},
                title="Resume-to-Job Match Score Distribution",
                color=list(buckets.keys()),
                color_discrete_sequence=["#ef4444", "#f59e0b", "#3b82f6", "#6366f1", "#10b981", "#34d399"],
            )
            fig.update_layout(
                template=plotly_tpl,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                height=320,
                margin=dict(l=20, r=20, t=45, b=20),
            )
            st.plotly_chart(fig, config={"responsive": True})

    with c2:
        wm = charts.get("work_modes") or {}
        if wm:
            total_wm = sum(wm.values())
            fig = px.pie(
                names=[k.title() for k in wm.keys()],
                values=list(wm.values()),
                hole=0.58,
                title="Opportunities by Work Mode",
                color_discrete_sequence=["#10b981", "#6366f1", "#38bdf8", "#64748b"],
            )
            fig.update_layout(
                template=plotly_tpl,
                paper_bgcolor="rgba(0,0,0,0)",
                height=320,
                margin=dict(l=20, r=20, t=45, b=20),
                annotations=[dict(text=f"<b>{total_wm:,}</b><br>Jobs", x=0.5, y=0.5, font_size=14, showarrow=False)],
            )
            st.plotly_chart(fig, config={"responsive": True})

    c3, c4 = st.columns(2)
    with c3:
        roles = charts.get("role_categories") or {}
        if roles:
            sorted_roles = sorted(roles.items(), key=lambda x: x[1], reverse=True)
            fig = px.bar(
                x=[v for _, v in sorted_roles],
                y=[k for k, _ in sorted_roles],
                orientation="h",
                labels={"x": "Verified Jobs", "y": ""},
                title="Jobs by Target Role Category",
                color_discrete_sequence=["#6366f1"],
            )
            fig.update_layout(
                template=plotly_tpl,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=320,
                margin=dict(l=20, r=20, t=45, b=20),
            )
            st.plotly_chart(fig, config={"responsive": True})

    with c4:
        top_companies = charts.get("top_companies") or []
        if top_companies:
            fig = px.bar(
                x=[item["count"] for item in top_companies],
                y=[item["company"] for item in top_companies],
                orientation="h",
                labels={"x": "Open Roles", "y": ""},
                title="Top Hiring Companies (Verified)",
                color_discrete_sequence=["#14b8a6"],
            )
            fig.update_layout(
                template=plotly_tpl,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis={"categoryorder": "total ascending"},
                height=320,
                margin=dict(l=20, r=20, t=45, b=20),
            )
            st.plotly_chart(fig, config={"responsive": True})


def render_job_card(
    client: JobPilotAPIClient,
    job: Dict[str, Any],
    key_prefix: str,
    on_mutation: Callable[[], None],
    show_tracker_controls: bool = False,
) -> None:
    match = job.get("match") or {}
    app_state = job.get("application") or {}
    score = match.get("match_score")

    with st.container(border=True):
        col_logo, col_main, col_score = st.columns([0.8, 6.4, 2.2])
        with col_logo:
            logo_url = job.get("company_logo_url")
            if logo_url:
                st.image(logo_url, width=46)
            else:
                initials = (job.get("company") or "CO")[:2].upper()
                st.markdown(f"### `{initials}`")

        with col_main:
            st.markdown(f"#### {job['title']}")
            loc_parts = [p for p in [job.get("city"), job.get("state"), job.get("country")] if p]
            loc_str = ", ".join(loc_parts) if loc_parts else (job.get("location") or "Unspecified")
            emp = job.get("employment_type") or "Full-time"
            exp_req = job.get("experience_requirement") or ("0 yrs / Entry" if job.get("fresher_eligible") else "Experience required")
            sal = job.get("salary_or_stipend") or "Not disclosed"
            st.caption(
                f"**{job['company']}** · 📍 {loc_str} · 💼 {emp} · 🎓 {exp_req} · 💰 {sal}"
            )
            badges_html = _work_mode_badge(job.get("work_mode", "unknown"))
            if job.get("city_tier"):
                badges_html += f"<span class='badge badge-blue'>🏙️ {html.escape(job['city_tier'])}</span>"
            badges_html += f"<span class='badge badge-purple'>{html.escape(job.get('role_category', ''))}</span>"
            badges_html += f"<span class='badge badge-slate'>{html.escape(job.get('seniority_level', ''))}</span>"
            if match:
                badges_html += _eligibility_badge(match.get("eligibility_status", "Eligible"))
            st.markdown(badges_html, unsafe_allow_html=True)
            last_chk = format_date(job.get("last_verified_at") or job.get("discovered_at"))
            saved_dt = format_date(app_state.get("saved_at")) if app_state.get("saved_at") else None
            meta_line = f"Posted: {format_date(job.get('posted_at'))} · Last Checked: {last_chk} · Source: `{job['source']}`"
            if saved_dt:
                meta_line += f" · Saved: {saved_dt}"
            st.caption(meta_line)

        with col_score:
            if score is not None:
                cls = "score-high" if score >= 70 else ("score-mid" if score >= 50 else "score-low")
                st.markdown(f"<div class='score-pill {cls}'>{score:.1f}%</div>", unsafe_allow_html=True)
            else:
                st.info("Unscored")

        if match:
            st.markdown(f"**Match Rationale:** {match.get('explanation', '')}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Matching Skills**")
                st.markdown(render_badges(match.get("matching_skills") or [], "badge-green"), unsafe_allow_html=True)
            with c2:
                st.markdown("**Missing Skills**")
                st.markdown(render_badges(match.get("missing_skills") or [], "badge-amber"), unsafe_allow_html=True)
            recs = match.get("recommended_improvements") or []
            if recs:
                st.caption(f"💡 **Recommended:** {recs[0]}")
        else:
            st.markdown(render_badges(job.get("required_skills") or [], "badge-blue"), unsafe_allow_html=True)

        # Lazy-load full job description only when requested
        with st.expander("📄 Details, Score Breakdown & Official Description"):
            if match and match.get("score_breakdown"):
                bd = match["score_breakdown"]
                b1, b2, b3, b4 = st.columns(4)
                b1.metric("Semantic Similarity", f"{bd.get('semantic_score', 0):.1f}%")
                b2.metric("Skill Overlap", f"{bd.get('skill_score', 0):.1f}%")
                b3.metric("Entry/Fresher Bonus", f"{bd.get('entry_level_bonus', 0):+.1f}")
                b4.metric("Location + Role Bonus", f"{(bd.get('location_bonus', 0) + bd.get('role_alignment_bonus', 0)):+.1f}")

            detail_key = f"full_desc_{job['id']}"
            if detail_key not in st.session_state:
                st.write(job.get("description") or "")
                if st.button("Load Full Job Description", key=f"{key_prefix}_load_desc_{job['id']}"):
                    full = client.get_job_detail(job["id"])
                    st.session_state[detail_key] = full.get("description") or ""
                    st.rerun()
            else:
                st.write(st.session_state[detail_key])

        # Action Bar (Two-Step Apply Verification + Non-Destructive Save + Dismiss)
        a1, a2, a3, a4, a5, a6 = st.columns([2.0, 1.2, 1.9, 1.7, 1.4, 0.9])
        with a1:
            st.link_button("🔗 Apply Link", job["apply_url"], width="stretch")
            if app_state.get("status") not in ("Applied", "Assessment", "Interview", "Offer"):
                if st.button("Mark Link Clicked", key=f"{key_prefix}_clk_{job['id']}", width="stretch"):
                    client.update_application(job["id"], {"clicked_apply": True})
                    st.toast("Marked Pending Confirmation — confirm submission after finishing on site.")
                    on_mutation()
                    st.rerun()
        with a2:
            saved_now = bool(app_state.get("is_saved", False))
            if st.button("★ Saved" if saved_now else "☆ Save", key=f"{key_prefix}_save_{job['id']}", width="stretch"):
                client.update_application(job["id"], {"is_saved": not saved_now})
                st.toast("Removed from Saved Jobs (tracker history preserved)." if saved_now else "Job bookmarked.")
                on_mutation()
                st.rerun()
        with a3:
            approved_val = st.checkbox(
                "Submitted & confirmed",
                value=bool(app_state.get("user_approved", False)),
                key=f"{key_prefix}_app_{job['id']}",
            )
        with a4:
            curr_status = app_state.get("status", "new")
            idx = TRACKER_STATUSES.index(curr_status) if curr_status in TRACKER_STATUSES else 0
            new_status = st.selectbox(
                "Status",
                TRACKER_STATUSES,
                index=idx,
                key=f"{key_prefix}_st_{job['id']}",
                label_visibility="collapsed",
            )
        with a5:
            if st.button("Save Status", key=f"{key_prefix}_upd_{job['id']}", width="stretch"):
                try:
                    client.update_application(job["id"], {"status": new_status, "user_approved": approved_val})
                    st.toast(f"Status updated to {new_status}")
                    on_mutation()
                    st.rerun()
                except httpx.HTTPStatusError as exc:
                    st.error(exc.response.json().get("detail", str(exc)))
        with a6:
            if st.button("✕", help="Dismiss from feed", key=f"{key_prefix}_dis_{job['id']}", width="stretch"):
                client.update_application(job["id"], {"dismissed": True})
                st.toast("Job dismissed from feed.")
                on_mutation()
                st.rerun()

        if show_tracker_controls:
            t1, t2 = st.columns([3, 1.5])
            with t1:
                note_val = st.text_input(
                    "Application Notes",
                    value=app_state.get("notes") or "",
                    key=f"{key_prefix}_note_{job['id']}",
                )
            with t2:
                curr_fu = format_date(app_state.get("follow_up_date"))
                fu_default = None
                if curr_fu != "Not specified":
                    try:
                        fu_default = datetime.strptime(curr_fu, "%Y-%m-%d").date()
                    except Exception:
                        fu_default = None
                fu_date = st.date_input(
                    "Follow-up Date",
                    value=fu_default,
                    key=f"{key_prefix}_fu_{job['id']}",
                )
            if st.button("Save Notes & Follow-up", key=f"{key_prefix}_save_meta_{job['id']}"):
                payload: Dict[str, Any] = {"notes": note_val}
                if fu_date:
                    payload["follow_up_date"] = f"{fu_date.isoformat()}T09:00:00+05:30"
                client.update_application(job["id"], payload)
                on_mutation()
                st.success("Tracker details saved.")
                st.rerun()
            if app_state.get("applied_at"):
                st.caption(f"Applied on: {format_date(app_state['applied_at'])}")
