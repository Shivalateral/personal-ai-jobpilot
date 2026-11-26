"""Universal explainable AI job matching engine (career-agnostic, uninflated, all-MiniLM-L6-v2)."""

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from backend.db.models import JobListing, Resume
from backend.db.vector_store import EmbeddingService, get_embedding_service
from backend.services.llm_client import LLMClient
from backend.services.resume_parser import (
    CANONICAL_SKILLS,
    extract_skills_from_text,
    extract_soft_skills_from_text,
)


_STOPWORDS = {
    "and", "the", "for", "with", "that", "this", "from", "your", "you", "are",
    "our", "will", "have", "has", "was", "were", "work", "working", "team",
    "role", "jobs", "job", "looking", "candidate", "skills", "experience",
    "years", "year", "about", "into", "using", "across", "including", "strong",
    "good", "ability", "required", "preferred", "plus", "must", "should",
}


_SYNONYM_MAP = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "llm": "large language model",
    "llms": "large language model",
    "rag": "retrieval augmented generation",
    "postgres": "postgresql",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node",
    "node.js": "node",
    "nextjs": "next.js",
    "cicd": "ci/cd",
    "restful": "rest api",
    "gcp": "google cloud",
    "aws": "amazon web services",
    "powerbi": "power bi",
    "genai": "generative ai",
    "fullstack": "full stack",
    "full-stack": "full stack",
}


def _tokenize_domain_terms(text: str) -> Set[str]:
    """Tokenize domain unigrams, canonical synonyms, bigrams, and trigrams for exact resume-to-JD matching."""
    raw = re.findall(r"[a-z0-9][a-z0-9+#./-]{1,}", (text or "").lower())
    unigrams: List[str] = []
    for tok in raw:
        clean = tok.strip(".-/")
        if len(clean) < 2 or clean in _STOPWORDS:
            continue
        mapped = _SYNONYM_MAP.get(clean, clean)
        unigrams.extend(mapped.split())

    tokens: Set[str] = set(unigrams)
    for i in range(len(unigrams) - 1):
        tokens.add(f"{unigrams[i]} {unigrams[i + 1]}")
    for i in range(len(unigrams) - 2):
        tokens.add(f"{unigrams[i]} {unigrams[i + 1]} {unigrams[i + 2]}")
    return tokens


@lru_cache(maxsize=4096)
def _compiled_boundary_pattern(cand: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9+#.])" + re.escape(cand) + r"(?![a-z0-9+#.])")


@lru_cache(maxsize=512)
def _skill_aliases(term_lower: str) -> tuple[str, ...]:
    for canon, syn_list in CANONICAL_SKILLS.items():
        canon_l = canon.lower()
        syns = [s.strip().lower() for s in syn_list if s.strip()]
        if term_lower == canon_l or term_lower in syns:
            return tuple(dict.fromkeys([canon_l] + syns + [term_lower]))
    return (term_lower,)


def exact_term_in_text(term: str, text_lower: str) -> bool:
    """Fast O(substring) + compiled word-boundary check (e.g., Java != JavaScript)."""
    clean = (term or "").strip().lower()
    if not clean or not text_lower:
        return False
    for cand in _skill_aliases(clean):
        if cand not in text_lower:
            continue
        if _compiled_boundary_pattern(cand).search(text_lower):
            return True
    return False


def compute_corpus_idf(jobs: Iterable[Any]) -> Dict[str, float]:
    """Compute smoothed IDF weights across the verified job corpus so rare technical/domain terms carry higher signal."""
    doc_freq: Counter = Counter()
    total_docs = 0
    for job in jobs:
        total_docs += 1
        snippet = (
            f"{getattr(job, 'title', '')} "
            f"{' '.join(getattr(job, 'required_skills_json', None) or [])} "
            f"{getattr(job, 'role_category', '')}"
        )
        for tok in _tokenize_domain_terms(snippet):
            doc_freq[tok] += 1
    if total_docs == 0:
        return {}
    return {
        tok: round(math.log((total_docs + 1.0) / (df + 1.0)) + 1.0, 4)
        for tok, df in doc_freq.items()
    }


@dataclass
class MatchComputation:
    match_score: float
    semantic_score: float
    skill_score: float
    entry_level_bonus: float
    eligibility_status: str
    matching_skills: List[str]
    missing_skills: List[str]
    recommended_improvements: List[str] = field(default_factory=list)
    explanation: str = ""
    score_breakdown: Dict[str, Any] = field(default_factory=dict)


def build_resume_profile_text(resume: Resume) -> str:
    """Create a universal profile text representation from any career resume."""
    skills = ", ".join((resume.skills_json or []) + (getattr(resume, "soft_skills_json", None) or []))
    roles = ", ".join(resume.target_roles_json or [])
    domains = ", ".join(getattr(resume, "domain_knowledge_json", None) or [])
    quals = ", ".join(resume.qualifications_json or [])
    locs = ", ".join(resume.preferred_locations_json or [])
    projects = " ".join(
        str(p.get("details") or p.get("description") or p.get("name") or "")
        for p in (resume.projects_json or [])
    )
    experience = " ".join(
        str(e.get("details") or e.get("highlights") or e.get("title") or "")
        for e in (resume.experience_json or [])
    )
    return (
        f"Domain Knowledge: {domains}\n"
        f"Target Roles: {roles}\n"
        f"Experience Level: {resume.experience_level} | Graduation Year: {resume.graduation_year or '2026'}\n"
        f"Preferred Locations: {locs}\n"
        f"Skills & Tools: {skills}\n"
        f"Summary: {resume.summary}\n"
        f"Projects: {projects}\n"
        f"Experience: {experience}\n"
        f"Qualifications: {quals}"
    ).strip()


def build_job_profile_text(job: JobListing) -> str:
    """Create a clean text representation of a job listing for semantic embedding."""
    skills = ", ".join(job.required_skills_json or [])
    return (
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Category: {job.role_category} | Work Mode: {job.work_mode}\n"
        f"Seniority: {job.seniority_level} | Fresher Eligible: {job.fresher_eligible}\n"
        f"Location: {job.location} ({job.city or ''} {getattr(job, 'state', '') or ''} {job.country or ''})\n"
        f"Required Skills: {skills}\n"
        f"Description: {(job.description or '')[:3500]}"
    ).strip()


class MatchingEngine:
    """Universal, uninflated matching engine using all-MiniLM-L6-v2 + skills + eligibility + domain."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.embedding_service = embedding_service or get_embedding_service()
        self.llm_client = llm_client or LLMClient()

    def compute_match(
        self,
        resume: Resume,
        job: JobListing,
        resume_embedding: Optional[List[float]] = None,
        job_embedding: Optional[List[float]] = None,
        use_llm_explanation: bool = True,
        idf_weights: Optional[Dict[str, float]] = None,
    ) -> MatchComputation:
        resume_text = build_resume_profile_text(resume)
        job_text = build_job_profile_text(job)

        res_emb = resume_embedding or self.embedding_service.embed(resume_text)
        job_emb = job_embedding or self.embedding_service.embed(job_text)
        cosine = self.embedding_service.cosine_similarity(res_emb, job_emb)
        semantic_score = round(cosine * 100.0, 2)

        # Step-by-step word-boundary exact skill extraction & bidirectional comparison (Resume <-> JD)
        resume_all_skills = list(
            dict.fromkeys(
                s.strip()
                for s in (
                    (resume.skills_json or [])
                    + (getattr(resume, "languages_frameworks_json", None) or [])
                    + (getattr(resume, "soft_skills_json", None) or [])
                    + (getattr(resume, "keywords_json", None) or [])
                )
                if s and s.strip()
            )
        )
        resume_text_lower = (
            f"{resume_text}\n{getattr(resume, 'raw_text', '') or ''}"
        ).lower()

        jd_skills = list(job.required_skills_json or [])
        if not jd_skills:
            jd_skills = extract_skills_from_text(f"{job.title or ''}\n{job.description or ''}")
        jd_soft = extract_soft_skills_from_text((job.description or "")[:1500]) if not jd_skills else []
        combined_job_skills = list(dict.fromkeys(jd_skills + jd_soft))
        job_blob_lower = (
            f"{job.title or ''}\n{' '.join(combined_job_skills)}\n{(job.description or '')[:3500]}"
        ).lower()

        resume_skills_lower = {s.lower() for s in resume_all_skills}
        matching_skills: List[str] = []
        missing_skills: List[str] = []
        matched_seen_lower: set[str] = set()

        for req in combined_job_skills:
            req_l = req.lower()
            if req_l in resume_skills_lower or exact_term_in_text(req, resume_text_lower):
                if req_l not in matched_seen_lower:
                    matching_skills.append(req)
                    matched_seen_lower.add(req_l)
            else:
                missing_skills.append(req)

        # Also check every explicit skill from the uploaded resume directly against the Job Description text
        for r_skill in resume_all_skills:
            r_l = r_skill.lower()
            if r_l not in matched_seen_lower and exact_term_in_text(r_skill, job_blob_lower):
                matching_skills.append(r_skill)
                matched_seen_lower.add(r_l)

        if combined_job_skills:
            jd_covered = sum(
                1 for req in combined_job_skills if req.lower() in matched_seen_lower
            )
            skill_score = round((jd_covered / len(combined_job_skills)) * 100.0, 2)
        elif matching_skills:
            skill_score = round(min(85.0, (len(matching_skills) / max(1, len(resume_all_skills))) * 100.0), 2)
        else:
            skill_score = round(min(45.0, semantic_score * 0.65), 2)

        # Exact tokenized unigram/bigram overlap between resume tokens and job title/skills/description
        resume_token_source = (
            f"{' '.join(resume_all_skills)} {' '.join(resume.target_roles_json or [])} "
            f"{' '.join(getattr(resume, 'domain_knowledge_json', None) or [])} {resume.summary or ''}"
        )
        job_token_source = (
            f"{job.title} {' '.join(combined_job_skills)} {job.role_category or ''} "
            f"{(job.description or '')[:1800]}"
        )
        res_tokens = _tokenize_domain_terms(resume_token_source)
        job_tokens = _tokenize_domain_terms(job_token_source)
        if res_tokens and job_tokens:
            shared = res_tokens & job_tokens
            if idf_weights:
                shared_weight = sum(idf_weights.get(t, 1.5 if " " in t else 1.0) for t in shared)
                target_weight = sum(idf_weights.get(t, 1.5 if " " in t else 1.0) for t in list(job_tokens)[:40])
                token_score = round(min(100.0, (shared_weight / max(6.0, min(target_weight, 48.0))) * 100.0), 2)
            else:
                denom = max(8, min(len(res_tokens), len(job_tokens), 45))
                token_score = round(min(100.0, (len(shared) / denom) * 100.0), 2)
        else:
            token_score = 0.0

        # Experience & fresher eligibility evaluation
        is_candidate_entry = resume.experience_level in ("intern", "fresh_grad", "entry_level")
        entry_bonus = 0.0
        if is_candidate_entry:
            if job.seniority_level in ("intern", "new_grad") and job.fresher_eligible:
                entry_bonus = 9.0
                eligibility_status = "Eligible"
            elif job.fresher_eligible and job.seniority_level == "entry_level":
                entry_bonus = 6.0
                eligibility_status = "Eligible"
            elif job.seniority_level == "mid" or not job.fresher_eligible:
                entry_bonus = -8.0 if job.seniority_level == "mid" else -18.0
                eligibility_status = "Stretch" if job.seniority_level == "mid" else "Ineligible"
            else:
                eligibility_status = "Eligible"
        else:
            eligibility_status = "Eligible"

        # Preferred location alignment (India states/cities + Remote)
        pref_locs = [p.lower() for p in (resume.preferred_locations_json or ["india", "remote"])]
        loc_blob = f"{job.location} {job.city or ''} {getattr(job, 'state', '') or ''} {job.country or ''} {job.work_mode}".lower()
        location_bonus = 4.0 if any(p in loc_blob for p in pref_locs) else 0.0

        # Universal domain & target role relevance (no hardcoded Data/AI bias!)
        resume_domains = " ".join(getattr(resume, "domain_knowledge_json", None) or []).lower()
        target_roles = [r.lower() for r in (resume.target_roles_json or [])]
        job_title_l = job.title.lower()
        job_cat_l = (job.role_category or "").lower()

        domain_bonus = 0.0
        if any(tok in job_cat_l for tok in resume_domains.split() if len(tok) > 3):
            domain_bonus = 6.0
        elif any(role in job_title_l for role in target_roles):
            domain_bonus = 6.0
        elif resume_domains and job_cat_l not in resume_domains and eligibility_status == "Eligible":
            domain_bonus = -4.0

        raw_composite = (
            (0.38 * semantic_score)
            + (0.40 * skill_score)
            + (0.14 * token_score)
            + entry_bonus
            + location_bonus
            + domain_bonus
        )
        match_score = round(max(0.0, min(100.0, raw_composite)), 2)

        improvements: List[str] = []
        if missing_skills:
            improvements.append(f"Highlight or build familiarity with: {', '.join(missing_skills[:4])}.")
        if job.work_mode == "unknown":
            improvements.append("Verify exact work mode (Remote/Hybrid/On-site) on the official company link.")
        if eligibility_status == "Stretch":
            improvements.append("Role expects 2-3 years experience; highlight relevant internships or measurable outcomes.")
        elif eligibility_status == "Ineligible":
            improvements.append("Role requires senior/experienced background; prioritize verified fresher roles first.")
        if not improvements:
            improvements.append("Tailor your resume summary and bullets to mirror the job's key responsibilities.")

        breakdown = {
            "semantic_weight": 0.38,
            "skill_weight": 0.40,
            "token_weight": 0.14,
            "semantic_score": semantic_score,
            "skill_score": skill_score,
            "token_overlap_score": token_score,
            "entry_level_bonus": entry_bonus,
            "location_bonus": location_bonus,
            "domain_alignment_bonus": domain_bonus,
            "eligibility_status": eligibility_status,
            "seniority_level": job.seniority_level,
            "work_mode": job.work_mode,
        }

        explanation = ""
        if use_llm_explanation and self.llm_client.is_available:
            explanation = self._generate_llm_explanation(
                resume, job, match_score, eligibility_status, matching_skills, missing_skills
            ) or ""

        if not explanation:
            explanation = self._deterministic_explanation(
                resume, job, match_score, semantic_score, skill_score, eligibility_status, matching_skills, missing_skills
            )

        return MatchComputation(
            match_score=match_score,
            semantic_score=semantic_score,
            skill_score=skill_score,
            entry_level_bonus=entry_bonus,
            eligibility_status=eligibility_status,
            matching_skills=sorted(matching_skills),
            missing_skills=sorted(missing_skills),
            recommended_improvements=improvements,
            explanation=explanation,
            score_breakdown=breakdown,
        )

    def compute_match_precomputed(
        self,
        resume: Resume,
        job_item: Any,
        semantic_cosine: float,
        resume_all_skills: List[str],
        resume_skills_lower: Set[str],
        resume_text_lower: str,
        res_tokens: Set[str],
        resume_domains: str,
        target_roles: List[str],
        pref_locs: List[str],
        is_candidate_entry: bool,
        idf_weights: Optional[Dict[str, float]] = None,
    ) -> MatchComputation:
        """Ultra-fast matching path reusing pre-computed cosine similarity, job tokens, and IDF weights."""
        semantic_score = round(max(0.0, min(1.0, float(semantic_cosine))) * 100.0, 2)
        jd_skills = list(job_item.required_skills_json or ())
        job_blob_lower = f"{job_item.title_lower}\n{job_item.skills_joined_lower}\n{job_item.desc_excerpt_lower}"

        matching_skills: List[str] = []
        missing_skills: List[str] = []
        matched_seen_lower: set[str] = set()

        for req in jd_skills:
            req_l = req.lower()
            if req_l in resume_skills_lower or exact_term_in_text(req, resume_text_lower):
                if req_l not in matched_seen_lower:
                    matching_skills.append(req)
                    matched_seen_lower.add(req_l)
            else:
                missing_skills.append(req)

        for r_skill in resume_all_skills:
            r_l = r_skill.lower()
            if r_l not in matched_seen_lower and exact_term_in_text(r_skill, job_blob_lower):
                matching_skills.append(r_skill)
                matched_seen_lower.add(r_l)

        if jd_skills:
            jd_covered = sum(1 for req in jd_skills if req.lower() in matched_seen_lower)
            skill_score = round((jd_covered / len(jd_skills)) * 100.0, 2)
        elif matching_skills:
            skill_score = round(min(85.0, (len(matching_skills) / max(1, len(resume_all_skills))) * 100.0), 2)
        else:
            skill_score = round(min(45.0, semantic_score * 0.65), 2)

        job_tokens = job_item.tokens_set
        if res_tokens and job_tokens:
            shared = res_tokens & job_tokens
            if idf_weights:
                shared_weight = sum(idf_weights.get(t, 1.5 if " " in t else 1.0) for t in shared)
                token_score = round(min(100.0, (shared_weight / 26.0) * 100.0), 2)
            else:
                denom = max(8, min(len(res_tokens), len(job_tokens), 45))
                token_score = round(min(100.0, (len(shared) / denom) * 100.0), 2)
        else:
            token_score = 0.0

        entry_bonus = 0.0
        if is_candidate_entry:
            if job_item.seniority_level in ("intern", "new_grad") and job_item.fresher_eligible:
                entry_bonus = 9.0
                eligibility_status = "Eligible"
            elif job_item.fresher_eligible and job_item.seniority_level == "entry_level":
                entry_bonus = 6.0
                eligibility_status = "Eligible"
            elif job_item.seniority_level == "mid" or not job_item.fresher_eligible:
                entry_bonus = -8.0 if job_item.seniority_level == "mid" else -18.0
                eligibility_status = "Stretch" if job_item.seniority_level == "mid" else "Ineligible"
            else:
                eligibility_status = "Eligible"
        else:
            eligibility_status = "Eligible"

        location_bonus = 4.0 if any(p in job_item.loc_blob_lower for p in pref_locs) else 0.0

        domain_bonus = 0.0
        if any(tok in job_item.cat_lower for tok in resume_domains.split() if len(tok) > 3):
            domain_bonus = 6.0
        elif any(role in job_item.title_lower for role in target_roles):
            domain_bonus = 6.0
        elif resume_domains and job_item.cat_lower not in resume_domains and eligibility_status == "Eligible":
            domain_bonus = -4.0

        raw_composite = (
            (0.38 * semantic_score)
            + (0.40 * skill_score)
            + (0.14 * token_score)
            + entry_bonus
            + location_bonus
            + domain_bonus
        )
        match_score = round(max(0.0, min(100.0, raw_composite)), 2)

        improvements: List[str] = []
        if missing_skills:
            improvements.append(f"Highlight or build familiarity with: {', '.join(missing_skills[:4])}.")
        if job_item.work_mode == "unknown":
            improvements.append("Verify exact work mode (Remote/Hybrid/On-site) on the official company link.")
        if eligibility_status == "Stretch":
            improvements.append("Role expects prior experience; highlight internships or measurable outcomes.")
        elif eligibility_status == "Ineligible":
            improvements.append("Role requires prior experience; prioritize verified zero-experience fresher roles first.")
        if not improvements:
            improvements.append("Tailor your resume summary and bullets to mirror the job's key responsibilities.")

        breakdown = {
            "semantic_weight": 0.38,
            "skill_weight": 0.40,
            "token_weight": 0.14,
            "semantic_score": semantic_score,
            "skill_score": skill_score,
            "token_overlap_score": token_score,
            "entry_level_bonus": entry_bonus,
            "location_bonus": location_bonus,
            "domain_alignment_bonus": domain_bonus,
            "eligibility_status": eligibility_status,
            "seniority_level": job_item.seniority_level,
            "work_mode": job_item.work_mode,
        }
        explanation = self._deterministic_explanation(
            resume, job_item, match_score, semantic_score, skill_score, eligibility_status, matching_skills, missing_skills
        )
        return MatchComputation(
            match_score=match_score,
            semantic_score=semantic_score,
            skill_score=skill_score,
            entry_level_bonus=entry_bonus,
            eligibility_status=eligibility_status,
            matching_skills=sorted(matching_skills),
            missing_skills=sorted(missing_skills),
            recommended_improvements=improvements,
            explanation=explanation,
            score_breakdown=breakdown,
        )

    def _generate_llm_explanation(
        self,
        resume: Resume,
        job: JobListing,
        match_score: float,
        eligibility_status: str,
        matching_skills: List[str],
        missing_skills: List[str],
    ) -> Optional[str]:
        prompt = (
            f"Candidate domains: {', '.join(getattr(resume, 'domain_knowledge_json', None) or [])}\n"
            f"Candidate skills: {', '.join(resume.skills_json or [])}\n"
            f"Candidate level: {resume.experience_level} (Graduation: {resume.graduation_year or '2026'})\n"
            f"Target roles: {', '.join(resume.target_roles_json or [])}\n\n"
            f"Job: {job.title} at {job.company} ({job.role_category}, {job.seniority_level}, {job.work_mode}, {job.location})\n"
            f"Computed Match Score: {match_score}% | Eligibility: {eligibility_status}\n"
            f"Matching skills: {', '.join(matching_skills) or 'None'}\n"
            f"Missing skills: {', '.join(missing_skills) or 'None'}\n"
            f"Job description excerpt:\n{(job.description or '')[:1400]}\n\n"
            "Write 2 concise sentences explaining why this job matches or misses the candidate's profile and the main gap to address."
        )
        return self.llm_client.chat(
            [
                {"role": "system", "content": "You are a concise, grounded career advisor. Cite only facts from above."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=180,
        )

    @staticmethod
    def _deterministic_explanation(
        resume: Resume,
        job: JobListing,
        match_score: float,
        semantic_score: float,
        skill_score: float,
        eligibility_status: str,
        matching_skills: List[str],
        missing_skills: List[str],
    ) -> str:
        parts = [
            f"Scored {match_score:.1f}% ({eligibility_status}: {skill_score:.0f}% skill match, {semantic_score:.0f}% semantic fit) for {job.title} at {job.company} [{job.role_category}, {job.work_mode}]."
        ]
        if matching_skills:
            parts.append(f"Matching skills: {', '.join(matching_skills[:6])}.")
        if missing_skills:
            parts.append(f"Missing skills: {', '.join(missing_skills[:5])}.")
        else:
            parts.append("Covers the detected skills in this posting.")
        return " ".join(parts)
