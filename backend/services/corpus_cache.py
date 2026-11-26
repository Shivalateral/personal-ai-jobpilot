"""Thread-safe shared read-only in-memory cache of verified jobs, embeddings matrix, and IDF weights.

Eliminates per-request SQLite full-table ORM deserialization and repeated tokenization
across concurrent multi-user traffic, enabling sub-20ms feed/overview queries and
vectorized numpy resume matching over thousands of listings.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.models import DiscoveryRun, JobListing
from backend.db.vector_store import get_vector_store
from backend.services.india_geography import ALL_INDIA_STATES_AND_UTS
from backend.services.matching_engine import _tokenize_domain_terms, build_job_profile_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CachedJobItem:
    id: int
    source: str
    company: str
    company_logo_url: Optional[str]
    title: str
    location: str
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    city_tier: Optional[str]
    work_mode: str
    is_remote: bool
    role_category: str
    domain_tags_json: Tuple[str, ...]
    seniority_level: str
    is_entry_level_priority: bool
    fresher_eligible: bool
    experience_requirement: Optional[str]
    salary_or_stipend: Optional[str]
    employment_type: Optional[str]
    required_skills_json: Tuple[str, ...]
    apply_url: str
    source_url: Optional[str]
    posted_at: Optional[datetime]
    discovered_at: datetime
    discovered_ts: float
    last_verified_at: Optional[datetime]
    verified: bool
    is_expired: bool
    signature: Tuple[str, str, str]
    haystack_lower: str
    skills_joined_lower: str
    company_lower: str
    emp_lower: str
    city_lower: str
    state_lower: str
    loc_blob_lower: str
    title_lower: str
    cat_lower: str
    desc_excerpt_lower: str
    tokens_set: FrozenSet[str]


@dataclass
class CorpusSnapshot:
    signature_key: Tuple[str, int, int, int]
    built_at: float
    jobs: List[CachedJobItem]
    dedup_jobs: List[CachedJobItem]
    jobs_by_id: Dict[int, CachedJobItem]
    emb_matrix: Optional[np.ndarray]
    emb_job_ids: List[int]
    id_to_row: Dict[int, int]
    idf_weights: Dict[str, float]
    global_kpis: Dict[str, Any]
    global_charts: Dict[str, Any]
    filter_options: Dict[str, Any]


class SharedJobCorpusCache:
    """Process-wide lock-guarded cache refreshed automatically when shared JobListing state changes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: Optional[CorpusSnapshot] = None
        self._last_check_ts: float = 0.0
        self._check_interval_sec: float = 4.0

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None
            self._last_check_ts = 0.0

    def _compute_db_signature(self, db: Session) -> Tuple[str, int, int, int]:
        db_url = get_settings().database_url
        cnt, max_id = (
            db.query(func.count(JobListing.id), func.max(JobListing.id))
            .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
            .one()
        )
        fresher_cnt = (
            db.query(func.count(JobListing.id))
            .filter(
                JobListing.is_active.is_(True),
                JobListing.verified.is_(True),
                JobListing.is_expired.is_(False),
                JobListing.fresher_eligible.is_(True),
            )
            .scalar()
        )
        return (db_url, int(cnt or 0), int(max_id or 0), int(fresher_cnt or 0))

    def get_snapshot(self, db: Session, force_check: bool = False) -> CorpusSnapshot:
        now = time.monotonic()
        with self._lock:
            if (
                self._snapshot is not None
                and not force_check
                and (now - self._last_check_ts) < self._check_interval_sec
                and self._snapshot.signature_key[0] == get_settings().database_url
            ):
                return self._snapshot

            sig = self._compute_db_signature(db)
            self._last_check_ts = now
            if self._snapshot is not None and self._snapshot.signature_key == sig:
                return self._snapshot

            self._snapshot = self._build_snapshot(db, sig)
            return self._snapshot

    def _build_snapshot(self, db: Session, sig: Tuple[str, int, int, int]) -> CorpusSnapshot:
        t0 = time.perf_counter()
        raw_rows = (
            db.query(JobListing)
            .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
            .all()
        )

        vs = get_vector_store()
        job_ids = [r.id for r in raw_rows]
        cached_embs = vs.get_job_embeddings(job_ids) if job_ids else {}
        missing_rows = [r for r in raw_rows if r.id not in cached_embs]
        if missing_rows:
            missing_embs = vs.embedding_service.embed_batch([build_job_profile_text(r) for r in missing_rows])
            for r, emb in zip(missing_rows, missing_embs):
                cached_embs[r.id] = emb

        ist = ZoneInfo("Asia/Kolkata")
        today_ist = datetime.now(ist).date()
        new_today = 0
        work_mode_counts: Counter = Counter()
        role_counts: Counter = Counter()
        seniority_counts: Counter = Counter()
        company_counts: Counter = Counter()
        city_counts: Counter = Counter()
        state_counts: Counter = Counter()
        countries_set = set()
        india_jobs = 0
        fresher_count = 0
        doc_freq: Counter = Counter()

        jobs: List[CachedJobItem] = []
        dedup_jobs: List[CachedJobItem] = []
        seen_sigs: set[Tuple[str, str, str]] = set()
        jobs_by_id: Dict[int, CachedJobItem] = {}

        emb_rows: List[List[float]] = []
        emb_job_ids: List[int] = []
        id_to_row: Dict[int, int] = {}

        for r in raw_rows:
            disc = r.discovered_at
            disc_ts = 0.0
            if disc is not None:
                d_utc = disc.replace(tzinfo=timezone.utc) if disc.tzinfo is None else disc
                disc_ts = d_utc.timestamp()
                if d_utc.astimezone(ist).date() == today_ist:
                    new_today += 1

            wm = r.work_mode or ("remote" if r.is_remote else "unknown")
            work_mode_counts[wm] += 1
            role_counts[r.role_category] += 1
            seniority_counts[r.seniority_level] += 1
            company_counts[r.company] += 1
            if r.city:
                city_counts[r.city] += 1
            if getattr(r, "state", None):
                state_counts[r.state] += 1
            if r.country:
                countries_set.add(r.country)
                if r.country == "India":
                    india_jobs += 1
            if r.fresher_eligible:
                fresher_count += 1

            req_skills = tuple(r.required_skills_json or ())
            dom_tags = tuple(getattr(r, "domain_tags_json", None) or ())
            skills_joined = " ".join(req_skills)
            desc_excerpt = (r.description or "")[:2400].lower()
            loc_blob = f"{r.location} {r.city or ''} {getattr(r, 'state', '') or ''} {r.country or ''} {wm}".lower()
            haystack = (
                f"{r.title} {r.company} {r.location} {r.city or ''} "
                f"{getattr(r, 'state', '') or ''} {r.country or ''} {wm} "
                f"{r.role_category} {skills_joined}"
            ).lower()
            tokens = frozenset(
                _tokenize_domain_terms(f"{r.title} {skills_joined} {r.role_category} {desc_excerpt[:1600]}")
            )
            for tok in _tokenize_domain_terms(f"{r.title} {skills_joined} {r.role_category}"):
                doc_freq[tok] += 1

            item_sig = (
                (r.company or "").strip().lower(),
                (r.title or "").strip().lower(),
                (r.location or "").strip().lower(),
            )
            item = CachedJobItem(
                id=r.id,
                source=r.source,
                company=r.company,
                company_logo_url=r.company_logo_url,
                title=r.title,
                location=r.location,
                city=r.city,
                state=getattr(r, "state", None),
                country=r.country,
                city_tier=getattr(r, "city_tier", None),
                work_mode=wm,
                is_remote=r.is_remote,
                role_category=r.role_category,
                domain_tags_json=dom_tags,
                seniority_level=r.seniority_level,
                is_entry_level_priority=r.is_entry_level_priority,
                fresher_eligible=bool(getattr(r, "fresher_eligible", r.is_entry_level_priority)),
                experience_requirement=getattr(r, "experience_requirement", None),
                salary_or_stipend=getattr(r, "salary_or_stipend", None),
                employment_type=r.employment_type,
                required_skills_json=req_skills,
                apply_url=r.apply_url,
                source_url=r.source_url,
                posted_at=r.posted_at,
                discovered_at=r.discovered_at,
                discovered_ts=disc_ts,
                last_verified_at=getattr(r, "last_verified_at", None),
                verified=r.verified,
                is_expired=bool(getattr(r, "is_expired", False)),
                signature=item_sig,
                haystack_lower=haystack,
                skills_joined_lower=skills_joined.lower(),
                company_lower=r.company.lower(),
                emp_lower=(r.employment_type or "").lower(),
                city_lower=(r.city or "").lower(),
                state_lower=(getattr(r, "state", None) or "").lower(),
                loc_blob_lower=loc_blob,
                title_lower=r.title.lower(),
                cat_lower=(r.role_category or "").lower(),
                desc_excerpt_lower=desc_excerpt,
                tokens_set=tokens,
            )
            jobs.append(item)
            jobs_by_id[item.id] = item
            if item_sig not in seen_sigs:
                seen_sigs.add(item_sig)
                dedup_jobs.append(item)

            emb = cached_embs.get(r.id)
            if emb:
                row_idx = len(emb_rows)
                emb_rows.append(emb)
                emb_job_ids.append(r.id)
                id_to_row[r.id] = row_idx

        total_docs = max(1, len(jobs))
        idf_weights = {
            tok: round(math.log((total_docs + 1.0) / (df + 1.0)) + 1.0, 4)
            for tok, df in doc_freq.items()
        }

        emb_matrix: Optional[np.ndarray] = None
        if emb_rows:
            mat = np.asarray(emb_rows, dtype=np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            emb_matrix = mat / norms

        global_kpis = {
            "total_jobs": len(jobs),
            "new_today": new_today,
            "verified_jobs": len(jobs),
            "india_jobs": india_jobs,
            "remote_jobs": work_mode_counts.get("remote", 0),
            "hybrid_jobs": work_mode_counts.get("hybrid", 0),
            "onsite_jobs": work_mode_counts.get("onsite", 0),
            "unknown_mode_jobs": work_mode_counts.get("unknown", 0),
            "fresher_eligible_jobs": fresher_count,
        }
        global_charts = {
            "work_modes": dict(work_mode_counts),
            "role_categories": dict(role_counts),
            "seniority_levels": dict(seniority_counts),
            "top_companies": [{"company": c, "count": n} for c, n in company_counts.most_common(10)],
            "top_cities": [{"city": c, "count": n} for c, n in city_counts.most_common(10)],
            "top_states": [{"state": s, "count": n} for s, n in state_counts.most_common(12)],
        }
        filter_options = {
            "all_india_states": ALL_INDIA_STATES_AND_UTS,
            "active_states": sorted(state_counts.keys()),
            "cities": sorted(city_counts.keys()),
            "countries": sorted(countries_set),
            "role_categories": sorted(role_counts.keys()),
            "companies": sorted(company_counts.keys()),
        }

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("SharedJobCorpusCache built (%d jobs, %d dedup) in %.1f ms", len(jobs), len(dedup_jobs), elapsed_ms)
        return CorpusSnapshot(
            signature_key=sig,
            built_at=time.monotonic(),
            jobs=jobs,
            dedup_jobs=dedup_jobs,
            jobs_by_id=jobs_by_id,
            emb_matrix=emb_matrix,
            emb_job_ids=emb_job_ids,
            id_to_row=id_to_row,
            idf_weights=idf_weights,
            global_kpis=global_kpis,
            global_charts=global_charts,
            filter_options=filter_options,
        )


_CORPUS_CACHE = SharedJobCorpusCache()


def get_corpus_cache() -> SharedJobCorpusCache:
    return _CORPUS_CACHE
