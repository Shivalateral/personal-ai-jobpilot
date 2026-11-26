"""Dual Dark & Light SaaS Design System CSS3 for Personal AI JobPilot."""


def get_theme_css(theme: str = "dark") -> str:
    is_light = (theme or "dark").lower() == "light"
    if is_light:
        vars_block = """
        :root {
            --bg-app: #f4f7fb;
            --bg-radial: radial-gradient(circle at 12% 8%, rgba(79, 70, 229, 0.08), transparent 45%),
                         radial-gradient(circle at 88% 12%, rgba(16, 185, 129, 0.08), transparent 40%),
                         #f4f7fb;
            --bg-sidebar: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%);
            --bg-card: rgba(255, 255, 255, 0.92);
            --bg-card-hover: #ffffff;
            --border-subtle: rgba(15, 23, 42, 0.10);
            --border-accent: rgba(79, 70, 229, 0.35);
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #64748b;
            --accent-indigo: #4f46e5;
            --accent-cyan: #0891b2;
            --accent-emerald: #059669;
            --shadow-card: 0 8px 24px rgba(15, 23, 42, 0.06);
        }
        """
        st_app_override = """
        .stApp { background: var(--bg-radial) !important; color: var(--text-primary) !important; }
        section[data-testid="stSidebar"] { background: var(--bg-sidebar) !important; border-right: 1px solid var(--border-subtle) !important; }
        """
    else:
        vars_block = """
        :root {
            --bg-app: #050914;
            --bg-radial: radial-gradient(circle at 10% 6%, rgba(79, 70, 229, 0.22), transparent 38%),
                         radial-gradient(circle at 85% 10%, rgba(14, 165, 233, 0.14), transparent 34%),
                         radial-gradient(circle at 50% 90%, rgba(16, 185, 129, 0.08), transparent 42%),
                         #050914;
            --bg-sidebar: linear-gradient(180deg, #070d1f 0%, #050914 100%);
            --bg-card: linear-gradient(180deg, rgba(17, 25, 48, 0.84) 0%, rgba(10, 15, 31, 0.92) 100%);
            --bg-card-hover: linear-gradient(180deg, rgba(24, 35, 66, 0.92) 0%, rgba(13, 20, 42, 0.96) 100%);
            --border-subtle: rgba(148, 163, 184, 0.15);
            --border-accent: rgba(99, 102, 241, 0.38);
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --accent-indigo: #6366f1;
            --accent-cyan: #38bdf8;
            --accent-emerald: #34d399;
            --shadow-card: 0 12px 32px rgba(0, 0, 0, 0.36);
        }
        """
        st_app_override = """
        .stApp { background: var(--bg-radial) !important; color: var(--text-primary) !important; }
        section[data-testid="stSidebar"] { background: var(--bg-sidebar) !important; border-right: 1px solid rgba(99, 102, 241, 0.18) !important; }
        """

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

{vars_block}
{st_app_override}

html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}

.block-container {{
    padding-top: 1.15rem;
    padding-bottom: 2.5rem;
    max-width: 1460px;
    animation: jpFadeIn 0.28s ease-out;
}}

@keyframes jpFadeIn {{
    from {{ opacity: 0; transform: translateY(4px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}

@keyframes jpPulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.45; transform: scale(1.22); }}
}}

.jp-hero-banner {{
    background: var(--bg-card);
    border: 1px solid var(--border-accent);
    border-radius: 16px;
    padding: 1.1rem 1.5rem;
    margin-bottom: 1.05rem;
    box-shadow: var(--shadow-card);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    backdrop-filter: blur(12px);
}}

.jp-hero-title {{
    font-size: 1.55rem;
    font-weight: 800;
    letter-spacing: -0.025em;
    color: var(--text-primary);
    margin: 0;
}}

.jp-hero-sub {{
    color: var(--text-muted);
    font-size: 0.88rem;
    margin: 0.15rem 0 0 0;
}}

.jp-live-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 11px;
    border-radius: 999px;
    font-size: 0.74rem;
    font-weight: 700;
    background: rgba(16, 185, 129, 0.14);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    white-space: nowrap;
}}

.jp-live-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10b981;
    animation: jpPulse 1.8s infinite;
}}

.kpi-card {{
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 0.9rem 1.05rem;
    margin-bottom: 0.7rem;
    box-shadow: var(--shadow-card);
    transition: transform 0.18s ease, border-color 0.18s ease;
}}

.kpi-card:hover {{
    transform: translateY(-2px);
    border-color: var(--border-accent);
}}

.kpi-label {{
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
}}

.kpi-value {{
    font-size: 1.55rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.15;
}}

.kpi-hint {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.2rem;
}}

.sidebar-group-label {{
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin: 0.75rem 0 0.3rem 0.2rem;
}}

.badge {{
    display: inline-block;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 0.74rem;
    font-weight: 600;
    margin-right: 5px;
    margin-bottom: 5px;
    line-height: 1.35;
}}

.badge-green {{ background: rgba(16, 185, 129, 0.14); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35); }}
.badge-blue {{ background: rgba(59, 130, 246, 0.14); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.35); }}
.badge-amber {{ background: rgba(245, 158, 11, 0.14); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.35); }}
.badge-purple {{ background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.38); }}
.badge-rose {{ background: rgba(244, 63, 94, 0.14); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.35); }}
.badge-slate {{ background: rgba(148, 163, 184, 0.14); color: var(--text-secondary); border: 1px solid rgba(148, 163, 184, 0.30); }}

.score-pill {{
    text-align: center;
    padding: 0.55rem 0.75rem;
    border-radius: 12px;
    font-weight: 800;
    font-size: 1.2rem;
    margin-bottom: 0.45rem;
}}
.score-high {{ background: rgba(16, 185, 129, 0.16); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.42); }}
.score-mid {{ background: rgba(59, 130, 246, 0.16); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.42); }}
.score-low {{ background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.38); }}

.skeleton-box {{
    height: 16px;
    border-radius: 8px;
    background: linear-gradient(90deg, rgba(148,163,184,0.12) 25%, rgba(148,163,184,0.24) 50%, rgba(148,163,184,0.12) 75%);
    background-size: 200% 100%;
    animation: jpShimmer 1.4s infinite;
}}

@keyframes jpShimmer {{
    0% {{ background-position: 200% 0; }}
    100% {{ background-position: -200% 0; }}
}}

@media (max-width: 768px) {{
    .jp-hero-banner {{ flex-direction: column; align-items: flex-start; padding: 0.9rem 1rem; }}
    .jp-hero-title {{ font-size: 1.25rem; }}
    .kpi-value {{ font-size: 1.3rem; }}
}}
</style>
"""


CUSTOM_CSS = get_theme_css("dark")
