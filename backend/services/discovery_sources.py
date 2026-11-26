"""Universal authorized job discovery connectors with India-wide geography and strict fresher verification."""

import hashlib
import html
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from bs4 import BeautifulSoup

from backend.core.config import get_settings
from backend.services.india_geography import resolve_geography
from backend.services.resume_parser import extract_skills_from_text

logger = logging.getLogger(__name__)

# Prohibited unauthenticated scraping targets per ToS/anti-bot policy
DISALLOWED_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com",
    "lnkd.in",
    "indeed.com",
    "www.indeed.com",
    "glassdoor.com",
    "www.glassdoor.com",
    "naukri.com",
    "www.naukri.com",
}

_INTERN_RE = re.compile(
    r"(?:^|[\s_\-/(])(?:intern|interns|internship|internships|co-op|coop|trainee|trainees|"
    r"apprentice|apprenticeship|apprentices|summer analyst|winter analyst)(?:$|[\s_\-/),.:])"
)
_FRESHER_TITLE_RE = re.compile(
    r"(?:^|[\s_\-/(])(?:fresher|freshers|fresh graduate|fresh graduates|new grad|new grads|"
    r"recent graduate|recent graduates|graduates|2025 grad|2026 grad|2027 grad|university grad|"
    r"graduate trainee|graduate engineer|early career|early talent|campus|entry[- ]level|"
    r"junior|jr\.?|associate|trainee|apprentice|sde[- ]?1|sde[- ]?i|swe[- ]?1|"
    r"engineer[- ]1|engineer[- ]i|analyst[- ]1|analyst[- ]i|developer[- ]1|developer[- ]i|"
    r"level[- ]?1|get)(?:$|[\s_\-/),.:])"
)
_SENIOR_TITLE_RE = re.compile(
    r"(?:^|[\s_\-/(])(?:senior|sr\.?|staff|principal|lead|director|vp|vice president|"
    r"head of|manager|architect|distinguished|executive|intermediate|expert|"
    r"deputy manager|asst\.?\s*manager|ii|iii|iv|l[4-9])(?:$|[\s_\-/),.:])"
)
# Experience requirement detector: captures optional "0 - " / "0 to " prefix so 0-1 / 0-2 yrs isn't falsely excluded
_EXP_YEARS_RE = re.compile(
    r"(0\s*(?:[-–]|to)\s*)?\b([1-9]\d?)\s*(?:\+|to|-|–)?\s*(?:\d+\s*)?years?\s+"
    r"(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+|hands[- ]on\s+)?experience\b"
)

UNIVERSAL_CATEGORY_RULES: List[tuple[str, List[str]]] = [
    ("AI & Machine Learning", ["machine learning", "ml engineer", "ai engineer", "artificial intelligence", "deep learning", "nlp", "computer vision", "llm", "generative ai", "applied scientist", "research scientist", "research engineer", "mlops", "ai/ml", "ai intern", "ml intern"]),
    ("Data & Analytics", ["data analyst", "data scientist", "data science", "analytics", "business intelligence", "bi analyst", "power bi", "tableau", "reporting analyst", "mis analyst", "data operations", "data engineer", "quantitative"]),
    ("Software Engineering", ["software engineer", "software developer", "full stack", "fullstack", "backend", "front end", "frontend", "python developer", "java developer", "c++", ".net", "react", "angular", "node.js", "sql developer", "mobile developer", "ios", "android", "web developer"]),
    ("Cloud & DevOps", ["devops", "cloud engineer", "sre", "site reliability", "platform engineer", "kubernetes", "aws", "azure", "gcp", "infrastructure"]),
    ("Cybersecurity", ["cybersecurity", "cyber security", "security engineer", "soc analyst", "infosec", "penetration", "network security"]),
    ("QA & Testing", ["qa ", "quality assurance", "test engineer", "sdet", "automation tester", "manual testing", "software tester"]),
    ("Customer Support & BPO", ["customer support", "customer service", "voice process", "non-voice", "chat support", "email support", "bpo", "telecaller", "process associate", "client support", "service desk", "help desk"]),
    ("IT & Technical Support", ["it support", "technical support", "desktop support", "system administrator", "network engineer", "helpdesk"]),
    ("Business & Product", ["business analyst", "product manager", "product analyst", "product owner", "scrum master", "program manager"]),
    ("Finance & Accounting", ["finance", "accountant", "accounting", "audit", "tax", "financial analyst", "bookkeeping", "accounts payable", "accounts receivable"]),
    ("Human Resources", ["human resources", "hr ", "recruiter", "recruiting", "talent acquisition", "people operations", "payroll"]),
    ("Marketing & Content", ["marketing", "seo", "sem", "social media", "content writer", "technical writer", "copywriter", "growth"]),
    ("Sales & Business Development", ["sales", "business development", "account executive", "lead generation", "inside sales", "customer success"]),
    ("Design & UI/UX", ["ui/ux", "ux designer", "ui designer", "product designer", "graphic designer", "figma"]),
    ("Operations & Supply Chain", ["operations", "supply chain", "logistics", "procurement", "inventory", "coordinator"]),
]


@dataclass
class RawDiscoveredJob:
    """Universal normalized representation of a job fetched from an authorized source."""

    source: str
    external_id: str
    company: str
    title: str
    location: str
    description: str
    apply_url: str
    source_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    employment_type: Optional[str] = None
    posted_at: Optional[datetime] = None
    is_remote: bool = False
    work_mode: str = "unknown"  # remote | hybrid | onsite | unknown
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    city_tier: Optional[str] = None  # Metro | Tier-2 | Other
    fresher_eligible: Optional[bool] = None
    experience_requirement: Optional[str] = None
    salary_or_stipend: Optional[str] = None
    required_skills: List[str] = field(default_factory=list)
    domain_tags: List[str] = field(default_factory=list)
    role_category: str = "General & Other"
    seniority_level: str = "entry_level"
    is_entry_level_priority: bool = False


def clean_html_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    unescaped = html.unescape(raw_html)
    if "<" in unescaped and ">" in unescaped:
        soup = BeautifulSoup(unescaped, "html.parser")
        text = soup.get_text(separator="\n")
    else:
        text = unescaped
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_datetime_safe(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value) / 1000.0 if value > 1e11 else float(value)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                dt = parsedate_to_datetime(value)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def classify_work_mode(
    location: str,
    title: str,
    description: str,
    explicit_remote: Optional[bool] = None,
    explicit_hybrid: Optional[bool] = None,
    workplace_type: Optional[str] = None,
) -> str:
    """Classify work mode from actual job data without assuming remote when unknown."""
    if explicit_hybrid is True:
        return "hybrid"
    wp = (workplace_type or "").lower().strip()
    if "hybrid" in wp:
        return "hybrid"
    if "remote" in wp:
        return "remote"
    if any(k in wp for k in ("on-site", "onsite", "in-person", "office")):
        return "onsite"

    loc_l = (location or "").lower()
    title_l = (title or "").lower()
    desc_l = (description or "")[:1800].lower()

    if "hybrid" in loc_l or "hybrid" in title_l or re.search(r"\bhybrid\b", desc_l):
        return "hybrid"
    if explicit_remote is True or "remote" in loc_l or "remote" in title_l or "work from home" in desc_l or "fully remote" in desc_l:
        return "remote"
    if any(k in loc_l for k in ("on-site", "onsite", "in-office")) or re.search(r"\b(on-site|onsite|in office|in-person)\b", desc_l):
        return "onsite"
    if location and location.lower() not in ("unspecified", "unknown", "anywhere", "worldwide", "global"):
        if "," in location or len(location.split()) >= 1:
            return "onsite"
    return "unknown"


def extract_salary_or_stipend(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"((?:₹|INR|Rs\.?)\s*\d[\d,]*(?:\.\d+)?\s*(?:-|to|–)?\s*(?:\d[\d,]*(?:\.\d+)?)?\s*(?:LPA|lakhs?|k|/month|per month|pm)?)",
        r"(\$\s*\d[\d,]*(?:\.\d+)?(?:k|K)?\s*(?:-|to|–)\s*\$?\s*\d[\d,]*(?:\.\d+)?(?:k|K)?(?:\s*(?:per year|annually|/yr|/hr|per hour|/month))?)",
        r"(\$\s*\d[\d,]*(?:k|K)?\s*(?:/hr|per hour|/month|per year))",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip()
            if len(val) >= 4:
                return val[:120]
    return None


def extract_experience_requirement(title: str, description: str) -> Optional[str]:
    title_l = title.lower()
    desc_l = (description or "")[:3000].lower()
    m = re.search(r"(\d+\s*(?:-|–|to)\s*\d+\+?\s*years?)", desc_l)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d+\+\s*years?\s*(?:of\s+)?(?:relevant\s+|professional\s+)?experience)", desc_l)
    if m2:
        return m2.group(1)
    if _INTERN_RE.search(title_l):
        return "Internship (0 yrs)"
    if any(k in title_l or k in desc_l for k in ("fresher", "fresh graduate", "new grad", "2025 graduate", "2026 graduate", "0 years", "no prior experience")):
        return "0 years / Fresh Graduate"
    return None


def classify_role_category(title: str, description: str) -> str:
    """Dynamically classify ANY legitimate career category without hardcoded Data/AI restrictions."""
    title_l = f" {title.lower()} "
    for category, keywords in UNIVERSAL_CATEGORY_RULES:
        if any(kw in title_l for kw in keywords):
            return category

    desc_l = (description or "")[:1200].lower()
    for category, keywords in UNIVERSAL_CATEGORY_RULES:
        if any(kw in desc_l for kw in keywords):
            return category

    return "General & Other"


def _extract_mandatory_min_years(desc_l: str) -> Optional[int]:
    """Return max mandatory minimum-years requirement found in JD, ignoring 0-1 / 0-2 / up-to ranges."""
    mandatory_years: List[int] = []
    for match in _EXP_YEARS_RE.finditer(desc_l):
        zero_prefix, yrs_str = match.group(1), match.group(2)
        if zero_prefix:
            # Explicit '0-1 years' / '0 - 2 years' / '0 to 2 years' welcomes 0-experience candidates
            continue
        start_idx = max(0, match.start() - 20)
        preceding = desc_l[start_idx : match.start()]
        if any(tok in preceding for tok in ("up to", "less than", "under", "max", "maximum", "<", "<=")):
            continue
        yrs = int(yrs_str)
        if yrs <= 25:
            mandatory_years.append(yrs)
    return max(mandatory_years) if mandatory_years else None


def verify_fresher_eligibility(
    title: str,
    description: str,
    ats_experience_hint: Optional[str] = None,
) -> tuple[str, bool, bool]:
    """Strictly verify zero-experience / fresher eligibility from title + JD criteria.

    Excludes roles requiring mandatory 1+ years of experience (unless 0-1 / 0-2 min=0),
    or senior/mid/management titles, accepting only genuine fresher/intern/zero-experience openings.
    Returns: (seniority_level, is_entry_level_priority, fresher_eligible)
    """
    title_l = f" {title.lower()} "
    desc_l = (description or "")[:3500].lower()
    is_intern_title = bool(_INTERN_RE.search(title_l))

    # Explicit senior/management/lead titles (except explicit Intern titles like 'Product Manager Intern')
    if _SENIOR_TITLE_RE.search(title_l) and not is_intern_title:
        return "senior", False, False
    if re.search(r"\b\d+\+\s*years?\b", title_l):
        return "senior", False, False

    max_req = _extract_mandatory_min_years(desc_l)
    if max_req is not None:
        # Internships occasionally mention unrelated multi-year programs in company blurbs; only block 2+ yr requirements
        if is_intern_title and max_req < 2:
            return "intern", True, True
        if max_req >= 4:
            return "senior", False, False
        return "mid", False, False

    if is_intern_title:
        return "intern", True, True

    if _FRESHER_TITLE_RE.search(title_l):
        if any(
            k in title_l
            for k in (
                "new grad",
                "new grads",
                "fresher",
                "freshers",
                "fresh graduate",
                "recent graduate",
                "graduates",
                "campus",
                "graduate trainee",
                "graduate engineer",
                "university grad",
                "2025 grad",
                "2026 grad",
                "2027 grad",
            )
        ):
            return "new_grad", True, True
        return "entry_level", True, True

    zero_exp_desc_markers = (
        "0-1 year",
        "0 - 1 year",
        "0 to 1 year",
        "0–1 year",
        "0 years",
        "0-2 years",
        "0 - 2 years",
        "0 to 2 years",
        "0–2 years",
        "fresher",
        "freshers",
        "fresh graduate",
        "new grad",
        "recent graduate",
        "university graduate",
        "college graduate",
        "2025 graduate",
        "2026 graduate",
        "2027 graduate",
        "2025 graduates",
        "2026 graduates",
        "2027 graduates",
        "no prior experience",
        "no previous experience",
        "no experience required",
        "without experience",
        "entry level",
        "entry-level",
        "early career",
        "early-career",
        "early talent",
        "internship-to-hire",
        "intern-to-hire",
        "ideal for graduates",
    )
    if any(k in desc_l for k in zero_exp_desc_markers):
        return "new_grad", True, True

    if ats_experience_hint:
        hint_l = ats_experience_hint.lower()
        if any(k in hint_l for k in ("director", "executive", "mid-senior", "mid level", "senior")):
            return "senior", False, False
        if any(k in hint_l for k in ("intern", "entry", "graduate", "student")):
            return "entry_level", True, True

    # Unknown jobs without fresher/zero-experience signals are NOT flagged fresher_eligible
    return "mid", False, False


def infer_company_logo(apply_url: str, company_name: str) -> Optional[str]:
    try:
        parsed = urlparse(apply_url)
        host = (parsed.hostname or "").lower()
        ats_hosts = ("greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "myworkdayjobs.com", "remotive.com", "arbeitnow.com", "jobicy.com", "himalayas.app", "remoteok.com")
        if host and not any(ats in host for ats in ats_hosts):
            return f"https://www.google.com/s2/favicons?domain={host}&sz=64"
        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        if slug:
            return f"https://www.google.com/s2/favicons?domain={slug}.com&sz=64"
    except Exception:
        return None
    return None


def compute_canonical_key(source: str, apply_url: str, company: str, title: str) -> str:
    norm_url = (apply_url or "").split("?")[0].rstrip("/").lower()
    raw = f"{norm_url}|{company.strip().lower()}|{title.strip().lower()}" if norm_url else f"{source}|{company}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_allowed_domain(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        for blocked in DISALLOWED_DOMAINS:
            if host == blocked or host.endswith(f".{blocked}"):
                return False
        return True
    except Exception:
        return False


class RobotsPolicyChecker:
    def __init__(self, user_agent: str, timeout: int = 8) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: Dict[str, Optional[RobotFileParser]] = {}

    def can_fetch(self, url: str, client: Optional[httpx.Client] = None) -> bool:
        if not is_allowed_domain(url):
            return False
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            robots_url = f"{origin}/robots.txt"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                http = client or httpx.Client(timeout=self.timeout, headers={"User-Agent": self.user_agent})
                resp = http.get(robots_url)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                    self._cache[origin] = parser
                elif resp.status_code in (401, 403):
                    self._cache[origin] = None
                    return False
                else:
                    parser.parse([])
                    self._cache[origin] = parser
            except Exception:
                parser.parse([])
                self._cache[origin] = parser

        cached = self._cache.get(origin)
        if cached is None:
            return False
        return cached.can_fetch(self.user_agent, url)


class RateLimiter:
    def __init__(self, min_interval_seconds: float = 0.35) -> None:
        self.min_interval = max(0.0, min_interval_seconds)
        self._last_request: Dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str) -> None:
        if self.min_interval <= 0:
            return
        host = urlparse(url).hostname or "default"
        with self._lock:
            now = time.monotonic()
            last = self._last_request.get(host)
            sleep_for = 0.0
            if last is not None:
                elapsed = now - last
                if elapsed < self.min_interval:
                    sleep_for = self.min_interval - elapsed
            self._last_request[host] = now + sleep_for
        if sleep_for > 0:
            time.sleep(sleep_for)


def _finalize_raw_job(
    source: str,
    external_id: str,
    company: str,
    title: str,
    location: str,
    description: str,
    apply_url: str,
    source_url: Optional[str] = None,
    company_logo_url: Optional[str] = None,
    employment_type: Optional[str] = None,
    posted_at: Optional[datetime] = None,
    explicit_remote: Optional[bool] = None,
    explicit_hybrid: Optional[bool] = None,
    workplace_type: Optional[str] = None,
    salary_hint: Optional[str] = None,
    region_hint: Optional[str] = None,
    city_hint: Optional[str] = None,
    country_hint: Optional[str] = None,
    ats_experience_hint: Optional[str] = None,
) -> Optional[RawDiscoveredJob]:
    """Normalize any legitimate job posting without hardcoded career restrictions."""
    if not title or not apply_url or not is_allowed_domain(apply_url):
        return None
    clean_desc = clean_html_text(description)
    role_category = classify_role_category(title, clean_desc)
    seniority, is_priority, fresher_ok = verify_fresher_eligibility(title, clean_desc, ats_experience_hint)
    work_mode = classify_work_mode(location, title, clean_desc, explicit_remote, explicit_hybrid, workplace_type)
    city, state, country, city_tier = resolve_geography(location, region_hint, city_hint, country_hint)
    skills = extract_skills_from_text(f"{title}\n{clean_desc}")
    exp_req = extract_experience_requirement(title, clean_desc)
    salary = salary_hint or extract_salary_or_stipend(clean_desc)
    logo = company_logo_url or infer_company_logo(apply_url, company)

    return RawDiscoveredJob(
        source=source,
        external_id=str(external_id),
        company=company.strip() or "Unknown Company",
        title=title.strip(),
        location=location.strip() or "Unspecified",
        description=clean_desc[:6000],
        apply_url=apply_url.strip(),
        source_url=source_url,
        company_logo_url=logo,
        employment_type=employment_type or ("Internship" if seniority == "intern" else "Full-time"),
        posted_at=posted_at,
        is_remote=(work_mode == "remote"),
        work_mode=work_mode,
        city=city,
        state=state,
        country=country,
        city_tier=city_tier,
        fresher_eligible=fresher_ok,
        experience_requirement=exp_req,
        salary_or_stipend=salary,
        required_skills=skills,
        domain_tags=[role_category],
        role_category=role_category,
        seniority_level=seniority,
        is_entry_level_priority=is_priority,
    )


def parse_greenhouse_payload(board_token: str, payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    company = board_token.replace("-", " ").title()
    for item in payload.get("jobs", []):
        loc = (item.get("location") or {}).get("name") or "Unspecified"
        job = _finalize_raw_job(
            source="greenhouse",
            external_id=str(item.get("id", "")),
            company=company,
            title=item.get("title", ""),
            location=loc,
            description=item.get("content", ""),
            apply_url=item.get("absolute_url", ""),
            source_url=f"https://boards.greenhouse.io/{board_token}",
            posted_at=parse_datetime_safe(item.get("updated_at") or item.get("first_published")),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_lever_payload(company_slug: str, payload: List[Dict[str, Any]]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    company = company_slug.replace("-", " ").title()
    if not isinstance(payload, list):
        return jobs
    for item in payload:
        categories = item.get("categories") or {}
        loc = categories.get("location") or "Unspecified"
        commitment = categories.get("commitment")
        workplace = item.get("workplaceType")
        desc = item.get("descriptionPlain") or item.get("description") or ""
        lists_text = "\n".join(f"{sec.get('text', '')}\n{sec.get('content', '')}" for sec in (item.get("lists") or []))
        job = _finalize_raw_job(
            source="lever",
            external_id=str(item.get("id", "")),
            company=company,
            title=item.get("text", ""),
            location=loc,
            description=f"{desc}\n{lists_text}".strip(),
            apply_url=item.get("applyUrl") or item.get("hostedUrl") or "",
            source_url=item.get("hostedUrl"),
            employment_type=commitment,
            posted_at=parse_datetime_safe(item.get("createdAt")),
            workplace_type=workplace,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_ashby_payload(company_slug: str, payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    company = company_slug.replace("-", " ").title()
    for item in payload.get("jobs", []):
        job = _finalize_raw_job(
            source="ashby",
            external_id=str(item.get("id", "")),
            company=company,
            title=item.get("title", ""),
            location=item.get("location") or ("Remote" if item.get("isRemote") else "Unspecified"),
            description=item.get("descriptionHtml") or item.get("descriptionPlain") or "",
            apply_url=item.get("applyUrl") or item.get("jobUrl") or "",
            source_url=item.get("jobUrl"),
            employment_type=item.get("employmentType"),
            posted_at=parse_datetime_safe(item.get("publishedAt")),
            explicit_remote=item.get("isRemote"),
            workplace_type=item.get("workplaceType"),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_smartrecruiters_payload(company_id: str, payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    """Parse official SmartRecruiters public postings API response (India-wide & global)."""
    jobs: List[RawDiscoveredJob] = []
    for item in payload.get("content", []):
        comp_obj = item.get("company") or {}
        company = comp_obj.get("name") or company_id
        loc_obj = item.get("location") or {}
        full_loc = loc_obj.get("fullLocation") or loc_obj.get("city") or "India"
        exp_obj = item.get("experienceLevel") or {}
        emp_obj = item.get("typeOfEmployment") or {}
        func_obj = item.get("function") or {}
        ind_obj = item.get("industry") or {}
        pid = str(item.get("id", ""))
        posting_url = f"https://jobs.smartrecruiters.com/{company_id}/{pid}"
        desc_parts = [
            item.get("name", ""),
            f"Function: {func_obj.get('label', '')}" if func_obj.get("label") else "",
            f"Industry: {ind_obj.get('label', '')}" if ind_obj.get("label") else "",
            f"Experience Level: {exp_obj.get('label', '')}" if exp_obj.get("label") else "",
            f"Location: {loc_obj.get('address') or full_loc}",
        ]
        job = _finalize_raw_job(
            source="smartrecruiters",
            external_id=pid,
            company=company,
            title=item.get("name", ""),
            location=full_loc,
            description="\n".join(p for p in desc_parts if p),
            apply_url=posting_url,
            source_url=posting_url,
            employment_type=emp_obj.get("label"),
            posted_at=parse_datetime_safe(item.get("releasedDate")),
            explicit_remote=loc_obj.get("remote"),
            explicit_hybrid=loc_obj.get("hybrid"),
            region_hint=loc_obj.get("region"),
            city_hint=loc_obj.get("city"),
            country_hint=loc_obj.get("country"),
            ats_experience_hint=exp_obj.get("label"),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_workday_payload(base_origin: str, payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    """Parse official Workday CXS JSON response when permitted."""
    jobs: List[RawDiscoveredJob] = []
    company = urlparse(base_origin).hostname.split(".")[0].title()
    for item in payload.get("jobPostings", []):
        ext_path = item.get("externalPath") or ""
        apply_url = f"{base_origin.rstrip('/')}{ext_path}" if ext_path.startswith("/") else ext_path
        job = _finalize_raw_job(
            source="workday",
            external_id=str(item.get("bulletFields", [ext_path])[0] if item.get("bulletFields") else ext_path),
            company=company,
            title=item.get("title", ""),
            location=item.get("locationsText") or "Unspecified",
            description=f"{item.get('title', '')}\n{item.get('locationsText', '')}",
            apply_url=apply_url,
            source_url=base_origin,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_remotive_payload(payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    for item in payload.get("jobs", []):
        job = _finalize_raw_job(
            source="remotive",
            external_id=str(item.get("id", "")),
            company=item.get("company_name", "Unknown"),
            title=item.get("title", ""),
            location=item.get("candidate_required_location") or "Remote",
            description=item.get("description", ""),
            apply_url=item.get("url", ""),
            source_url=item.get("url"),
            company_logo_url=item.get("company_logo_url") or item.get("company_logo"),
            employment_type=item.get("job_type"),
            posted_at=parse_datetime_safe(item.get("publication_date")),
            explicit_remote=True,
            salary_hint=item.get("salary") or None,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_arbeitnow_payload(payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    for item in payload.get("data", []):
        job = _finalize_raw_job(
            source="arbeitnow",
            external_id=str(item.get("slug", "")),
            company=item.get("company_name", "Unknown"),
            title=item.get("title", ""),
            location=item.get("location") or ("Remote" if item.get("remote") else "Unspecified"),
            description=item.get("description", ""),
            apply_url=item.get("url", ""),
            source_url=item.get("url"),
            employment_type=", ".join(item.get("job_types") or []) or None,
            posted_at=parse_datetime_safe(item.get("created_at")),
            explicit_remote=bool(item.get("remote")),
        )
        if job:
            jobs.append(job)
    return jobs


def parse_jobicy_payload(payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    for item in payload.get("jobs", []):
        salary = None
        if item.get("annualSalaryMin") and item.get("annualSalaryMax"):
            curr = item.get("salaryCurrency") or "USD"
            salary = f"{curr} {item['annualSalaryMin']} - {item['annualSalaryMax']}"
        job = _finalize_raw_job(
            source="jobicy",
            external_id=str(item.get("id", "")),
            company=item.get("companyName", "Unknown"),
            title=item.get("jobTitle", ""),
            location=item.get("jobGeo") or "Remote",
            description=item.get("jobDescription") or item.get("jobExcerpt") or "",
            apply_url=item.get("url", ""),
            source_url=item.get("url"),
            company_logo_url=item.get("companyLogo"),
            employment_type=", ".join(item.get("jobType") or []) if isinstance(item.get("jobType"), list) else item.get("jobType"),
            posted_at=parse_datetime_safe(item.get("pubDate")),
            explicit_remote=True,
            salary_hint=salary,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_himalayas_payload(payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    for item in payload.get("jobs", []):
        salary = None
        if item.get("minSalary") and item.get("maxSalary"):
            curr = item.get("currency") or "USD"
            salary = f"{curr} {item['minSalary']} - {item['maxSalary']}"
        locs = item.get("locationRestrictions") or []
        loc = ", ".join(locs) if locs else "Remote"
        job = _finalize_raw_job(
            source="himalayas",
            external_id=str(item.get("guid") or item.get("applicationLink") or ""),
            company=item.get("companyName", "Unknown"),
            title=item.get("title", ""),
            location=loc,
            description=item.get("description") or item.get("excerpt") or "",
            apply_url=item.get("applicationLink") or item.get("guid") or "",
            source_url=item.get("guid"),
            company_logo_url=item.get("companyLogo"),
            employment_type=item.get("employmentType"),
            posted_at=parse_datetime_safe(item.get("pubDate")),
            explicit_remote=True,
            salary_hint=salary,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_remoteok_payload(payload: Any) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    if not isinstance(payload, list):
        return jobs
    for item in payload:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        salary = None
        if item.get("salary_min") and item.get("salary_max"):
            salary = f"USD {item['salary_min']} - {item['salary_max']}"
        job = _finalize_raw_job(
            source="remoteok",
            external_id=str(item.get("id") or item.get("slug") or ""),
            company=item.get("company", "Unknown"),
            title=item.get("position", ""),
            location=item.get("location") or "Remote",
            description=item.get("description", ""),
            apply_url=item.get("apply_url") or item.get("url") or "",
            source_url=item.get("url"),
            company_logo_url=item.get("company_logo"),
            posted_at=parse_datetime_safe(item.get("date")),
            explicit_remote=True,
            salary_hint=salary,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_adzuna_payload(payload: Dict[str, Any]) -> List[RawDiscoveredJob]:
    jobs: List[RawDiscoveredJob] = []
    for item in payload.get("results", []):
        company = (item.get("company") or {}).get("display_name") or "Unknown"
        loc = (item.get("location") or {}).get("display_name") or "India"
        salary = None
        if item.get("salary_min") or item.get("salary_max"):
            salary = f"{item.get('salary_min', '')} - {item.get('salary_max', '')}".strip(" -")
        job = _finalize_raw_job(
            source="adzuna",
            external_id=str(item.get("id", "")),
            company=company,
            title=item.get("title", ""),
            location=loc,
            description=item.get("description", ""),
            apply_url=item.get("redirect_url", ""),
            source_url=item.get("redirect_url"),
            employment_type=item.get("contract_type") or item.get("contract_time"),
            posted_at=parse_datetime_safe(item.get("created")),
            salary_hint=salary,
            country_hint="India",
        )
        if job:
            jobs.append(job)
    return jobs


def parse_rss_feed_content(feed_url: str, xml_content: str) -> List[RawDiscoveredJob]:
    parsed = feedparser.parse(xml_content)
    jobs: List[RawDiscoveredJob] = []
    feed_title = (parsed.feed.get("title") or urlparse(feed_url).hostname or "RSS Feed").strip()
    is_remote_feed = any(k in feed_url.lower() for k in ("remote", "weworkremotely", "remotive"))

    for entry in parsed.entries:
        raw_title = (entry.get("title") or "").strip()
        link = entry.get("link") or ""
        company = (entry.get("author") or "").strip()
        title = raw_title
        if not company and ": " in raw_title:
            maybe_comp, maybe_title = raw_title.split(": ", 1)
            if len(maybe_comp) <= 45:
                company, title = maybe_comp.strip(), maybe_title.strip()
        company = company or feed_title
        summary = entry.get("summary") or entry.get("description") or ""
        posted = parse_datetime_safe(entry.get("published") or entry.get("updated"))
        ext_id = entry.get("id") or link
        loc = entry.get("region") or entry.get("location") or ("Worldwide" if is_remote_feed else "Unspecified")
        job = _finalize_raw_job(
            source="rss",
            external_id=str(ext_id),
            company=company,
            title=title,
            location=loc,
            description=summary,
            apply_url=link,
            source_url=feed_url,
            posted_at=posted,
            explicit_remote=True if is_remote_feed else None,
        )
        if job:
            jobs.append(job)
    return jobs


def parse_career_page_html(page_url: str, html_content: str) -> List[RawDiscoveredJob]:
    soup = BeautifulSoup(html_content, "html.parser")
    jobs: List[RawDiscoveredJob] = []
    host = urlparse(page_url).hostname or "company"
    default_company = host.replace("www.", "").replace("careers.", "").split(".")[0].title()

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for obj in items:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") == "JobPosting":
                org = obj.get("hiringOrganization") or {}
                company = org.get("name") if isinstance(org, dict) else default_company
                loc_obj = obj.get("jobLocation") or {}
                loc = "Unspecified"
                if isinstance(loc_obj, dict):
                    addr = loc_obj.get("address") or {}
                    if isinstance(addr, dict):
                        loc = addr.get("addressLocality") or addr.get("addressCountry") or "Unspecified"
                apply_url = obj.get("url") or page_url
                explicit_remote = obj.get("jobLocationType") == "TELECOMMUTE"
                job = _finalize_raw_job(
                    source="career_page",
                    external_id=hashlib.md5(f"{apply_url}|{obj.get('title','')}".encode()).hexdigest(),
                    company=company or default_company,
                    title=obj.get("title", ""),
                    location=loc,
                    description=obj.get("description", ""),
                    apply_url=apply_url,
                    source_url=page_url,
                    employment_type=obj.get("employmentType"),
                    posted_at=parse_datetime_safe(obj.get("datePosted")),
                    explicit_remote=explicit_remote,
                )
                if job:
                    jobs.append(job)

    return jobs


class DiscoverySourcesClient:
    """Concurrent, universal fetcher across authorized ATS, public API, India-wide, RSS, and career sources."""

    def __init__(self, http_client: Optional[httpx.Client] = None) -> None:
        self.settings = get_settings()
        self.headers = {"User-Agent": self.settings.discovery_user_agent}
        self._client = http_client
        self.robots = RobotsPolicyChecker(self.settings.discovery_user_agent)
        self.rate_limiter = RateLimiter(self.settings.discovery_rate_limit_seconds)

    def _client_ctx(self):
        if self._client is not None:
            return nullcontext(self._client)
        return httpx.Client(
            timeout=float(self.settings.discovery_request_timeout),
            headers=self.headers,
            follow_redirects=True,
            trust_env=False,
        )

    def _new_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=float(self.settings.discovery_request_timeout),
            headers=self.headers,
            follow_redirects=True,
            trust_env=False,
        )

    def fetch_all(self) -> tuple[List[RawDiscoveredJob], List[str]]:
        """Fetch universal jobs across all configured authorized sources."""
        tasks: List[tuple[str, str, Any]] = []

        for token in self.settings.greenhouse_board_list:
            tasks.append((
                f"greenhouse:{token}",
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
                lambda r, tok=token: parse_greenhouse_payload(tok, r.json()),
            ))

        for company in self.settings.lever_company_list:
            tasks.append((
                f"lever:{company}",
                f"https://api.lever.co/v0/postings/{company}?mode=json",
                lambda r, comp=company: parse_lever_payload(comp, r.json()),
            ))

        for company in self.settings.ashby_company_list:
            tasks.append((
                f"ashby:{company}",
                f"https://api.ashbyhq.com/posting-api/job-board/{company}",
                lambda r, comp=company: parse_ashby_payload(comp, r.json()),
            ))

        is_render = bool(os.getenv("RENDER"))
        for company in self.settings.smartrecruiters_company_list:
            for sr_country in ("in", "ca", "global"):
                q_suffix = f"&country={sr_country}" if sr_country != "global" else ""
                offsets = (0,) if is_render else ((0, 100) if (sr_country == "in" or company == "BoschGroup") else (0,))
                for offset in offsets:
                    tasks.append((
                        f"smartrecruiters:{company}:{sr_country}:{offset}",
                        f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset={offset}{q_suffix}",
                        lambda r, comp=company: parse_smartrecruiters_payload(comp, r.json()),
                    ))

        if self.settings.enable_remotive_api:
            tasks.append((
                "remotive:all",
                "https://remotive.com/api/remote-jobs?limit=200",
                lambda r: parse_remotive_payload(r.json()),
            ))
            for category in ("software-dev", "data", "customer-support", "marketing", "finance-legal", "hr", "qa", "devops-sysadmin"):
                tasks.append((
                    f"remotive:{category}",
                    f"https://remotive.com/api/remote-jobs?category={category}&limit=50",
                    lambda r: parse_remotive_payload(r.json()),
                ))

        if self.settings.enable_arbeitnow_api:
            for page_no in (1, 2, 3):
                tasks.append((
                    f"arbeitnow:p{page_no}",
                    f"https://www.arbeitnow.com/api/job-board-api?page={page_no}",
                    lambda r: parse_arbeitnow_payload(r.json()),
                ))

        if self.settings.enable_jobicy_api:
            tasks.append((
                "jobicy",
                "https://jobicy.com/api/v2/remote-jobs?count=100",
                lambda r: parse_jobicy_payload(r.json()),
            ))

        if self.settings.enable_himalayas_api:
            for offset in (0, 100, 200):
                tasks.append((
                    f"himalayas:{offset}",
                    f"https://himalayas.app/jobs/api?limit=100&offset={offset}",
                    lambda r: parse_himalayas_payload(r.json()),
                ))

        if self.settings.enable_remoteok_api:
            tasks.append((
                "remoteok",
                "https://remoteok.com/api",
                lambda r: parse_remoteok_payload(r.json()),
            ))

        if self.settings.adzuna_app_id and self.settings.adzuna_app_key:
            for what in ("fresher", "entry level", "intern", "graduate trainee"):
                url = (
                    f"https://api.adzuna.com/v1/api/jobs/{self.settings.adzuna_country}/search/1"
                    f"?app_id={self.settings.adzuna_app_id}&app_key={self.settings.adzuna_app_key}"
                    f"&results_per_page=25&what={what.replace(' ', '%20')}"
                )
                tasks.append((f"adzuna:{what}", url, lambda r: parse_adzuna_payload(r.json())))

        for feed_url in self.settings.rss_feed_list:
            tasks.append((
                f"rss:{feed_url}",
                feed_url,
                lambda r, u=feed_url: parse_rss_feed_content(u, r.text),
            ))

        for page_url in self.settings.career_page_list:
            tasks.append((
                f"career_page:{page_url}",
                page_url,
                lambda r, u=page_url: parse_career_page_html(u, r.text),
            ))

        discovered: List[RawDiscoveredJob] = []
        sources_checked = [label for label, _, _ in tasks]

        def _worker(label: str, url: str, parser_fn: Any) -> List[RawDiscoveredJob]:
            with self._client_ctx() as client:
                if label.startswith(("rss:", "career_page:")) and not self.robots.can_fetch(url, client):
                    return []
                self.rate_limiter.wait(url)
                resp = client.get(url)
                if resp.status_code == 200:
                    return parser_fn(resp)
                logger.info("Source '%s' returned status %s", label, resp.status_code)
                return []

        pool_workers = 4 if is_render else 10
        with ThreadPoolExecutor(max_workers=pool_workers) as pool:
            futures = {pool.submit(_worker, lbl, u, fn): lbl for lbl, u, fn in tasks}
            for fut in as_completed(futures):
                lbl = futures[fut]
                try:
                    discovered.extend(fut.result())
                except Exception as exc:
                    logger.warning("Discovery fetch failed for '%s': %s", lbl, exc)

        # Respectful optional Workday CXS POST endpoints if configured
        for wd_url in self.settings.workday_endpoint_list:
            sources_checked.append(f"workday:{wd_url}")
            try:
                with self._client_ctx() as client:
                    self.rate_limiter.wait(wd_url)
                    resp = client.post(wd_url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "India"})
                    if resp.status_code == 200:
                        origin = f"{urlparse(wd_url).scheme}://{urlparse(wd_url).netloc}"
                        discovered.extend(parse_workday_payload(origin, resp.json()))
            except Exception as exc:
                logger.warning("Workday fetch failed for '%s': %s", wd_url, exc)

        return discovered, sources_checked
