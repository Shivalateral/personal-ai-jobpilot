"""Job Verification Agent: validates links, detects expired postings, deduplicates, and batch-indexes jobs."""

from concurrent.futures import ThreadPoolExecutor
import gc
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.models import ApplicationRecord, JobListing
from backend.db.vector_store import VectorStore, get_vector_store
from backend.services.discovery_sources import (
    RawDiscoveredJob,
    compute_canonical_key,
    is_allowed_domain,
)
from backend.services.matching_engine import build_job_profile_text

logger = logging.getLogger(__name__)


class JobVerificationAgent:
    """Verifies official URLs, blocks prohibited sources, deduplicates, and batch-indexes jobs."""

    def __init__(self, vector_store: Optional[VectorStore] = None) -> None:
        self.settings = get_settings()
        self.vector_store = vector_store or get_vector_store()

    def _check_url_reachable(self, url: str) -> tuple[bool, str]:
        """Live HTTP check verifying the official application link is active and not 404/410."""
        try:
            with httpx.Client(
                timeout=8.0,
                follow_redirects=True,
                headers={"User-Agent": self.settings.discovery_user_agent},
            ) as client:
                resp = client.head(url)
                if resp.status_code in (405, 403):
                    resp = client.get(url)
                if 200 <= resp.status_code < 400:
                    return True, f"HTTP {resp.status_code} verified"
                return False, f"HTTP {resp.status_code}"
        except Exception as exc:
            return False, f"Reachability check error: {exc}"

    def check_expired_links(self, db: Session, limit: int = 30) -> int:
        """Check oldest-verified active listings to detect expired/404 postings."""
        candidates = (
            db.query(JobListing)
            .filter(JobListing.is_active.is_(True), JobListing.is_expired.is_(False))
            .order_by(JobListing.last_verified_at.asc().nullsfirst())
            .limit(limit)
            .all()
        )
        expired_count = 0
        now = datetime.now(timezone.utc)
        for job in candidates:
            ok, note = self._check_url_reachable(job.apply_url)
            job.last_verified_at = now
            if not ok and ("404" in note or "410" in note):
                job.is_expired = True
                job.verification_notes = f"Expired ({note})"
                expired_count += 1
        db.commit()
        return expired_count

    def verify_and_persist(
        self,
        db: Session,
        raw_jobs: List[RawDiscoveredJob],
        verify_urls_live: bool = False,
    ) -> tuple[List[JobListing], int, int]:
        """Verify, deduplicate, store new jobs, and batch-index in ChromaDB."""
        persisted: List[JobListing] = []
        duplicates_skipped = 0
        rejected_unverified = 0
        seen_keys_in_batch: set[str] = set()

        existing_keys = {row[0] for row in db.query(JobListing.canonical_key).all()}
        existing_urls = {row[0] for row in db.query(JobListing.apply_url).all()}
        now = datetime.now(timezone.utc)

        candidates: List[tuple[RawDiscoveredJob, str]] = []
        for raw in raw_jobs:
            if not raw.title.strip() or not raw.company.strip() or not raw.apply_url.strip():
                rejected_unverified += 1
                continue
            if not is_allowed_domain(raw.apply_url):
                rejected_unverified += 1
                logger.warning("Rejected disallowed job URL domain: %s", raw.apply_url)
                continue

            canonical_key = compute_canonical_key(raw.source, raw.apply_url, raw.company, raw.title)
            if canonical_key in seen_keys_in_batch or canonical_key in existing_keys or raw.apply_url in existing_urls:
                duplicates_skipped += 1
                continue
            seen_keys_in_batch.add(canonical_key)
            candidates.append((raw, canonical_key))

        live_results: Dict[str, tuple[bool, str]] = {}
        if verify_urls_live and candidates:
            unique_urls = list({raw.apply_url for raw, _ in candidates})
            with ThreadPoolExecutor(max_workers=16) as pool:
                for url, res in zip(unique_urls, pool.map(self._check_url_reachable, unique_urls)):
                    live_results[url] = res

        for raw, canonical_key in candidates:
            verification_notes = f"Verified from authorized {raw.source} source."
            if verify_urls_live:
                ok, note = live_results.get(raw.apply_url, (False, "Not checked"))
                if not ok:
                    rejected_unverified += 1
                    continue
                verification_notes = f"{verification_notes} ({note})"

            job = JobListing(
                canonical_key=canonical_key,
                external_id=raw.external_id,
                source=raw.source,
                company=raw.company,
                company_logo_url=raw.company_logo_url,
                title=raw.title,
                location=raw.location,
                city=raw.city,
                state=raw.state,
                country=raw.country,
                city_tier=raw.city_tier,
                work_mode=raw.work_mode,
                is_remote=(raw.work_mode == "remote"),
                role_category=raw.role_category,
                domain_tags_json=raw.domain_tags,
                seniority_level=raw.seniority_level,
                is_entry_level_priority=raw.is_entry_level_priority,
                fresher_eligible=(
                    raw.fresher_eligible
                    if raw.fresher_eligible is not None
                    else raw.is_entry_level_priority
                ),
                experience_requirement=raw.experience_requirement,
                salary_or_stipend=raw.salary_or_stipend,
                employment_type=raw.employment_type,
                description=raw.description,
                required_skills_json=raw.required_skills,
                apply_url=raw.apply_url,
                source_url=raw.source_url,
                posted_at=raw.posted_at,
                last_verified_at=now if verify_urls_live else None,
                verified=True,
                is_expired=False,
                verification_notes=verification_notes,
                is_active=True,
            )
            db.add(job)
            persisted.append(job)

        if persisted:
            db.flush()
            batch_size = 250
            for start in range(0, len(persisted), batch_size):
                chunk = persisted[start : start + batch_size]
                batch_items = [
                    (
                        job.id,
                        build_job_profile_text(job),
                        {
                            "job_id": job.id,
                            "company": job.company,
                            "title": job.title,
                            "role_category": job.role_category,
                            "seniority_level": job.seniority_level,
                            "work_mode": job.work_mode,
                            "source": job.source,
                        },
                    )
                    for job in chunk
                ]
                self.vector_store.upsert_jobs_batch(batch_items)
                gc.collect()

        db.commit()
        logger.info(
            "Verification complete: %d new verified, %d duplicates skipped, %d rejected.",
            len(persisted),
            duplicates_skipped,
            rejected_unverified,
        )
        return persisted, duplicates_skipped, rejected_unverified
