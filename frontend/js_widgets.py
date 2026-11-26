"""Interactive HTML5 + CSS3 + ES6+ JavaScript components inspired by the SaaS reference UI."""

import html
from typing import Any, Dict, List

import streamlit.components.v1 as components


def _palette(theme: str) -> Dict[str, str]:
    if (theme or "dark").lower() == "light":
        return {
            "bg": "#ffffff",
            "bg2": "#f8fafc",
            "border": "rgba(15, 23, 42, 0.12)",
            "text": "#0f172a",
            "muted": "#64748b",
            "accent": "#4f46e5",
            "cyan": "#0891b2",
            "emerald": "#059669",
            "amber": "#d97706",
            "row_hover": "#f1f5f9",
        }
    return {
        "bg": "rgba(15, 23, 48, 0.86)",
        "bg2": "rgba(9, 14, 32, 0.94)",
        "border": "rgba(99, 102, 241, 0.24)",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "accent": "#7c7cff",
        "cyan": "#38bdf8",
        "emerald": "#34d399",
        "amber": "#fbbf24",
        "row_hover": "rgba(99, 102, 241, 0.14)",
    }


def render_kpi_strip_html(kpis: Dict[str, Any], theme: str = "dark") -> None:
    """Render the 4 reference-inspired top KPI micro-chart cards (particle wave, dot matrix, area, trend line)."""
    p = _palette(theme)
    total_jobs = int(kpis.get("total_jobs", 0))
    fresher = int(kpis.get("fresher_eligible_jobs", 0))
    avg_match = float(kpis.get("avg_match_score", 0.0))
    max_match = float(kpis.get("max_match_score", 0.0))
    tracked = int(kpis.get("saved_jobs", 0)) + int(kpis.get("applied_jobs", 0))
    india_jobs = int(kpis.get("india_jobs", 0))
    remote_jobs = int(kpis.get("remote_jobs", 0))

    dots_svg = "".join(
        f'<circle cx="{12 + c * 15}" cy="{10 + r * 11}" r="2.1" fill="{"#818cf8" if (r + c) % 3 == 0 else ("#38bdf8" if c % 2 == 0 else "rgba(148,163,184,0.35)")}" />'
        for r in range(5)
        for c in range(14)
    )
    particle_wave = "".join(
        f'<circle cx="{8 + i * 7}" cy="{32 + ((i * 19) % 24) - 10}" r="{1.5 if i % 2 == 0 else 2.2}" fill="{"#38bdf8" if i > 16 else "#818cf8"}" opacity="0.85"/>'
        for i in range(30)
    )

    markup = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * {{ box-sizing: border-box; font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; }}
      body {{ margin: 0; padding: 2px; background: transparent; }}
      .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
      .card {{
        background: linear-gradient(180deg, {p['bg']} 0%, {p['bg2']} 100%);
        border: 1px solid {p['border']};
        border-radius: 16px;
        padding: 16px 16px 10px 16px;
        color: {p['text']};
        position: relative;
        overflow: hidden;
        transition: transform 0.2s ease, border-color 0.2s ease;
      }}
      .card:hover {{ transform: translateY(-2px); border-color: {p['accent']}; }}
      .top-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
      .title {{ font-size: 13px; font-weight: 600; color: {p['muted']}; }}
      .live {{
        font-size: 11px; font-weight: 700; color: #34d399;
        background: rgba(16,185,129,0.14); border: 1px solid rgba(16,185,129,0.35);
        border-radius: 999px; padding: 2px 8px;
      }}
      .val {{ font-size: 28px; font-weight: 800; letter-spacing: -0.02em; line-height: 1.15; }}
      .delta {{ font-size: 12px; color: {p['emerald']}; margin-top: 4px; font-weight: 600; }}
      .delta span {{ color: {p['muted']}; font-weight: 500; }}
      svg {{ width: 100%; height: 56px; margin-top: 6px; display: block; }}
      @media (max-width: 900px) {{ .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
      @media (max-width: 520px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    </style>
    </head>
    <body>
      <div class="grid">
        <div class="card">
          <div class="top-row"><span class="title">Total Verified Jobs</span><span class="live">● Live</span></div>
          <div class="val">{total_jobs:,}</div>
          <div class="delta">▲ {india_jobs:,} India <span>· {remote_jobs:,} remote</span></div>
          <svg viewBox="0 0 220 56" preserveAspectRatio="none">
            {particle_wave}
          </svg>
        </div>
        <div class="card">
          <div class="top-row"><span class="title">Fresher-Eligible Jobs</span></div>
          <div class="val">{fresher:,}</div>
          <div class="delta">▲ {(round((fresher / max(1, total_jobs)) * 100, 1))}% <span>of verified pool</span></div>
          <svg viewBox="0 0 220 60" preserveAspectRatio="none">
            {dots_svg}
          </svg>
        </div>
        <div class="card">
          <div class="top-row"><span class="title">Average Match Score</span></div>
          <div class="val">{avg_match:.1f}%</div>
          <div class="delta">Peak {max_match:.1f}% <span>· ML + Tokenizer</span></div>
          <svg viewBox="0 0 220 56" preserveAspectRatio="none">
            <defs>
              <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#34d399" stop-opacity="0.52" />
                <stop offset="100%" stop-color="#34d399" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <path d="M0,44 C35,28 55,14 90,26 C125,38 155,10 190,16 L220,12 L220,56 L0,56 Z" fill="url(#areaGrad)" />
            <path d="M0,44 C35,28 55,14 90,26 C125,38 155,10 190,16 L220,12" fill="none" stroke="#34d399" stroke-width="2.2" />
          </svg>
        </div>
        <div class="card">
          <div class="top-row"><span class="title">Saved & Applied</span></div>
          <div class="val">{tracked:,}</div>
          <div class="delta">{int(kpis.get('saved_jobs', 0))} Saved <span>· {int(kpis.get('applied_jobs', 0))} Applied</span></div>
          <svg viewBox="0 0 220 56" preserveAspectRatio="none">
            <polyline points="8,16 42,24 76,34 112,42 148,38 184,28 212,18" fill="none" stroke="#818cf8" stroke-width="2" />
            <circle cx="8" cy="16" r="2.8" fill="#818cf8" /><circle cx="76" cy="34" r="2.8" fill="#818cf8" />
            <circle cx="148" cy="38" r="2.8" fill="#38bdf8" /><circle cx="212" cy="18" r="3" fill="#34d399" />
          </svg>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(markup, height=195)


def render_funnel_and_skills_html(
    funnel: List[Dict[str, Any]],
    top_matching: List[Dict[str, Any]],
    top_missing: List[Dict[str, Any]],
    recent_activity: List[Dict[str, Any]],
    theme: str = "dark",
) -> None:
    """Render reference-inspired Pipeline Funnel, Skill Breakdown Bubbles, and Activity Feed with ES6 tooltips."""
    p = _palette(theme)
    s0 = max(1, int(funnel[0]["count"]) if funnel else 1)
    stage_cards = []
    for idx, st_item in enumerate(funnel[:4]):
        cnt = int(st_item.get("count", 0))
        pct = round((cnt / s0) * 100.0, 1) if s0 else 0.0
        stage_cards.append(
            f"""
            <div class="stage">
              <div class="st-label">{idx + 1}. {html.escape(str(st_item.get('stage', '')))}</div>
              <div class="st-val">{cnt:,}</div>
              <div class="st-pill">{pct}%</div>
            </div>
            """
        )

    skill_rows = top_matching[:5]
    max_sk = max([int(x.get("count", 1)) for x in skill_rows], default=1)
    bars_html = ""
    for item in skill_rows:
        w = max(8, int((int(item["count"]) / max(1, max_sk)) * 100))
        bars_html += f"""
        <div class="bar-row" title="{html.escape(item['skill'])}: matched across {item['count']} jobs">
          <div class="bar-top"><span>{html.escape(item['skill'])}</span><span>{item['count']:,}</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:{w}%"></div></div>
        </div>
        """
    if not bars_html:
        bars_html = f'<div style="color:{p["muted"]};font-size:13px;">Upload your resume to populate real skill demand bars.</div>'

    act_html = ""
    for act in recent_activity[:5]:
        act_html += f"""
        <div class="act-row">
          <div><strong>{html.escape(str(act.get('event', '')))}</strong> <span style="color:{p['muted']};">· {html.escape(str(act.get('detail', '')))}</span></div>
          <span style="color:{p['muted']};font-size:11px;">{html.escape(str(act.get('timestamp', ''))[:10])}</span>
        </div>
        """
    if not act_html:
        act_html = f'<div style="color:{p["muted"]};font-size:13px;">No application actions recorded yet in this session.</div>'

    gap_badges = "".join(
        f'<span class="gap-chip">{html.escape(x["skill"])} ({x["count"]})</span>'
        for x in top_missing[:8]
    ) or f'<span style="color:{p["muted"]};font-size:12px;">Upload a resume to inspect top missing skills.</span>'

    markup = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * {{ box-sizing: border-box; font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; }}
      body {{ margin: 0; padding: 2px; background: transparent; color: {p['text']}; }}
      .layout {{ display: grid; grid-template-columns: 1.35fr 1fr 1fr; gap: 14px; }}
      .panel {{
        background: linear-gradient(180deg, {p['bg']} 0%, {p['bg2']} 100%);
        border: 1px solid {p['border']};
        border-radius: 16px;
        padding: 16px;
      }}
      .p-title {{ font-size: 14px; font-weight: 700; margin-bottom: 12px; }}
      .stages {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 8px; }}
      .stage {{ text-align: center; }}
      .st-label {{ font-size: 11px; color: {p['muted']}; }}
      .st-val {{ font-size: 18px; font-weight: 800; margin: 3px 0; }}
      .st-pill {{
        display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 8px;
        border: 1px solid {p['border']}; color: {p['text']}; background: {p['row_hover']};
      }}
      .bar-row {{ margin-bottom: 10px; cursor: default; }}
      .bar-top {{ display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; color: {p['text']}; }}
      .bar-track {{ height: 7px; border-radius: 999px; background: rgba(148,163,184,0.16); overflow: hidden; }}
      .bar-fill {{ height: 100%; border-radius: 999px; background: linear-gradient(90deg, {p['accent']}, {p['emerald']}); transition: width 0.35s ease; }}
      .act-row {{ display: flex; justify-content: space-between; align-items: center; padding: 7px 0; border-bottom: 1px solid {p['border']}; font-size: 12px; }}
      .gap-wrap {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
      .gap-chip {{
        font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
        background: rgba(245,158,11,0.14); color: {p['amber']}; border: 1px solid rgba(245,158,11,0.34);
      }}
      @media (max-width: 960px) {{ .layout {{ grid-template-columns: 1fr; }} }}
    </style>
    </head>
    <body>
      <div class="layout">
        <div class="panel">
          <div class="p-title">Job Discovery to Application Funnel</div>
          <div class="stages">{''.join(stage_cards)}</div>
          <svg viewBox="0 0 360 72" width="100%" height="72" preserveAspectRatio="none">
            <defs>
              <linearGradient id="funnelGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="#6366f1" stop-opacity="0.88" />
                <stop offset="55%" stop-color="#38bdf8" stop-opacity="0.72" />
                <stop offset="100%" stop-color="#34d399" stop-opacity="0.82" />
              </linearGradient>
            </defs>
            <path d="M0,6 C90,10 140,22 220,28 C290,32 330,34 360,36 L360,38 C330,40 290,42 220,46 C140,52 90,64 0,68 Z" fill="url(#funnelGrad)" />
          </svg>
        </div>
        <div class="panel">
          <div class="p-title">Most Requested Matching Skills</div>
          {bars_html}
        </div>
        <div class="panel">
          <div class="p-title">Skill Gaps & Recent Activity</div>
          <div class="gap-wrap">{gap_badges}</div>
          <div style="margin-top:12px;">{act_html}</div>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(markup, height=255)


def render_kanban_board_html(tracked_jobs: List[Dict[str, Any]], theme: str = "dark") -> None:
    """Render an interactive HTML5/CSS3/ES6 Kanban Pipeline Board across all 8 tracker stages."""
    p = _palette(theme)
    columns = ["Interested", "Saved", "Pending Confirmation", "Applied", "Assessment", "Interview", "Offer", "Rejected", "Withdrawn"]
    grouped: Dict[str, List[Dict[str, Any]]] = {col: [] for col in columns}
    for job in tracked_jobs:
        st_name = (job.get("application") or {}).get("status") or "Saved"
        if st_name not in grouped:
            st_name = "Saved"
        grouped[st_name].append(job)

    cols_html = ""
    for col in columns:
        cards = ""
        for j in grouped[col]:
            sc = (j.get("match") or {}).get("match_score")
            sc_txt = f"{sc:.0f}%" if sc is not None else "—"
            cards += f"""
            <div class="k-card" data-search="{html.escape((j['title'] + ' ' + j['company']).lower())}">
              <div class="k-title">{html.escape(j['title'])}</div>
              <div class="k-sub">{html.escape(j['company'])} · {html.escape(j.get('work_mode', ''))}</div>
              <div class="k-meta"><span class="k-score">{sc_txt} Match</span><span>{html.escape(j['source'])}</span></div>
            </div>
            """
        cols_html += f"""
        <div class="k-col">
          <div class="k-col-head"><span>{col}</span><span class="k-cnt">{len(grouped[col])}</span></div>
          {cards if cards else '<div class="k-empty">Empty</div>'}
        </div>
        """

    markup = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * {{ box-sizing: border-box; font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; }}
      body {{ margin: 0; padding: 2px; background: transparent; color: {p['text']}; }}
      .toolbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 10px; }}
      .search {{
        width: 280px; padding: 7px 12px; border-radius: 10px; border: 1px solid {p['border']};
        background: {p['bg2']}; color: {p['text']}; font-size: 12px; outline: none;
      }}
      .board {{ display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }}
      .k-col {{
        min-width: 205px; flex: 0 0 205px; background: {p['bg2']}; border: 1px solid {p['border']};
        border-radius: 14px; padding: 10px;
      }}
      .k-col-head {{ display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; margin-bottom: 8px; }}
      .k-cnt {{ background: {p['row_hover']}; padding: 1px 7px; border-radius: 999px; font-size: 11px; }}
      .k-card {{
        background: {p['bg']}; border: 1px solid {p['border']}; border-radius: 10px;
        padding: 9px; margin-bottom: 8px; transition: transform 0.15s ease;
      }}
      .k-card:hover {{ transform: translateY(-1px); border-color: {p['accent']}; }}
      .k-title {{ font-size: 12px; font-weight: 700; margin-bottom: 3px; }}
      .k-sub {{ font-size: 11px; color: {p['muted']}; margin-bottom: 6px; }}
      .k-meta {{ display: flex; justify-content: space-between; font-size: 11px; color: {p['muted']}; }}
      .k-score {{ color: {p['emerald']}; font-weight: 700; }}
      .k-empty {{ font-size: 11px; color: {p['muted']}; text-align: center; padding: 16px 4px; }}
    </style>
    </head>
    <body>
      <div class="toolbar">
        <span style="font-size:13px;font-weight:700;">Interactive Pipeline Kanban Board</span>
        <input id="kbFilter" class="search" type="text" placeholder="Quick filter cards by title or company..." />
      </div>
      <div class="board">{cols_html}</div>
      <script>
        const input = document.getElementById('kbFilter');
        input.addEventListener('input', () => {{
          const q = input.value.trim().toLowerCase();
          document.querySelectorAll('.k-card').forEach(card => {{
            const hay = card.getAttribute('data-search') || '';
            card.style.display = (!q || hay.includes(q)) ? 'block' : 'none';
          }});
        }});
      </script>
    </body>
    </html>
    """
    components.html(markup, height=340)
