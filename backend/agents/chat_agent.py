"""Conversational AI Agent: LangGraph RAG assistant grounded in stored resume & verified jobs."""

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from backend.core.security import ResumeVault
from backend.db.models import ChatMessage, JobListing, JobMatch, Resume
from backend.db.vector_store import VectorStore, get_vector_store
from backend.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ChatGraphState(TypedDict, total=False):
    user_id: int
    user_message: str
    session_id: str
    focused_job_id: Optional[int]
    resume_context: str
    jobs_context: str
    referenced_job_ids: List[int]
    history_messages: List[Dict[str, str]]
    reply: str
    used_llm: bool


class ConversationalAIAgent:
    """Grounded RAG assistant for job matches, skill gaps, fresher hiring, and job comparisons."""

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        llm_client: Optional[LLMClient] = None,
        vault: Optional[ResumeVault] = None,
    ) -> None:
        self.vector_store = vector_store or get_vector_store()
        self.llm_client = llm_client or LLMClient()
        self.vault = vault or ResumeVault()

    def _build_resume_context(self, db: Session, user_id: int = 1) -> tuple[Optional[Resume], str]:
        resume = (
            db.query(Resume)
            .filter(Resume.user_id == user_id, Resume.is_active.is_(True))
            .order_by(Resume.created_at.desc())
            .first()
        )
        if not resume:
            return None, "No resume has been uploaded yet."

        raw_excerpt = ""
        try:
            raw_excerpt = self.vault.decrypt(resume.encrypted_raw_text)[:2200]
        except Exception:
            raw_excerpt = resume.summary

        ctx = (
            f"Candidate Name: {resume.candidate_name or 'Candidate'} | Graduation Year: {resume.graduation_year or 'Not specified'}\n"
            f"Experience Level: {resume.experience_level}\n"
            f"Target Roles: {', '.join(resume.target_roles_json or [])}\n"
            f"Preferred Locations: {', '.join(resume.preferred_locations_json or [])}\n"
            f"Skills: {', '.join(resume.skills_json or [])}\n"
            f"Summary: {resume.summary}\n"
            f"Education: {resume.education_json}\n"
            f"Experience: {resume.experience_json}\n"
            f"Projects: {resume.projects_json}\n"
            f"Resume Text Excerpt:\n{raw_excerpt}"
        )
        return resume, ctx

    def _retrieve_relevant_jobs(
        self,
        db: Session,
        resume: Optional[Resume],
        query: str,
        focused_job_id: Optional[int],
    ) -> tuple[List[JobListing], Dict[int, JobMatch], str]:
        candidate_ids: List[int] = []
        if focused_job_id is not None:
            candidate_ids.append(focused_job_id)

        similar = self.vector_store.query_similar_jobs(query_text=query, top_k=6)
        for item in similar:
            jid = item.get("job_id")
            if jid and jid not in candidate_ids:
                candidate_ids.append(jid)

        jobs: List[JobListing] = []
        if candidate_ids:
            fetched = (
                db.query(JobListing)
                .filter(JobListing.id.in_(candidate_ids), JobListing.is_expired.is_(False))
                .all()
            )
            by_id = {j.id: j for j in fetched}
            jobs = [by_id[jid] for jid in candidate_ids if jid in by_id]

        # Supplement with top-matched entry-level/fresher jobs from SQL
        if resume is not None and len(jobs) < 8:
            top_matches = (
                db.query(JobMatch)
                .filter(JobMatch.resume_id == resume.id)
                .order_by(JobMatch.match_score.desc())
                .limit(8)
                .all()
            )
            top_ids = [m.job_id for m in top_matches if m.job_id not in {j.id for j in jobs}]
            if top_ids:
                extra = (
                    db.query(JobListing)
                    .filter(JobListing.id.in_(top_ids), JobListing.is_active.is_(True), JobListing.is_expired.is_(False))
                    .all()
                )
                extra_by_id = {j.id: j for j in extra}
                for jid in top_ids:
                    if jid in extra_by_id:
                        jobs.append(extra_by_id[jid])
        elif len(jobs) < 5:
            extra = (
                db.query(JobListing)
                .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
                .order_by(JobListing.discovered_at.desc())
                .limit(5)
                .all()
            )
            seen = {j.id for j in jobs}
            for j in extra:
                if j.id not in seen:
                    jobs.append(j)

        matches_by_job: Dict[int, JobMatch] = {}
        if resume and jobs:
            match_rows = (
                db.query(JobMatch)
                .filter(JobMatch.resume_id == resume.id, JobMatch.job_id.in_([j.id for j in jobs]))
                .all()
            )
            matches_by_job = {m.job_id: m for m in match_rows}

        if not jobs:
            return [], {}, "No discovered jobs are currently stored in the database."

        blocks: List[str] = []
        for job in jobs[:8]:
            match = matches_by_job.get(job.id)
            match_line = (
                f"Match Score: {match.match_score:.1f}% | Eligibility: {match.eligibility_status} | "
                f"Matching: {', '.join(match.matching_skills_json)} | Missing: {', '.join(match.missing_skills_json)}"
                if match
                else "Match Score: Not yet computed"
            )
            blocks.append(
                f"[Job #{job.id}] {job.title} at {job.company} ({job.location}, work_mode={job.work_mode}, {job.seniority_level})\n"
                f"Category: {job.role_category} | Fresher Eligible: {job.fresher_eligible} | Salary/Stipend: {job.salary_or_stipend or 'Not stated'}\n"
                f"Source: {job.source} | Apply URL: {job.apply_url}\n"
                f"Required Skills: {', '.join(job.required_skills_json or [])}\n"
                f"{match_line}\n"
                f"Description Excerpt: {(job.description or '')[:700]}"
            )
        return jobs[:8], matches_by_job, "\n\n---\n\n".join(blocks)

    def _deterministic_reply(
        self,
        user_message: str,
        resume: Optional[Resume],
        jobs: List[JobListing],
        matches_by_job: Dict[int, JobMatch],
    ) -> str:
        lowered = user_message.lower()
        lines: List[str] = []

        if not resume:
            lines.append("No active resume found. Upload a PDF or DOCX resume in **Resume Intelligence** so I can analyze your profile.")
        else:
            lines.append(
                f"**Active Profile:** `{resume.experience_level}` (Class of {resume.graduation_year or '2026'}) | "
                f"Skills: {', '.join((resume.skills_json or [])[:12]) or 'None'}."
            )

        if any(k in lowered for k in ("missing", "gap", "improve", "recommend", "skill")):
            missing_counts: Dict[str, int] = {}
            for job in jobs:
                m = matches_by_job.get(job.id)
                if m:
                    for skill in m.missing_skills_json:
                        missing_counts[skill] = missing_counts.get(skill, 0) + 1
            if missing_counts:
                top_missing = sorted(missing_counts.items(), key=lambda x: x[1], reverse=True)[:6]
                formatted = ", ".join(f"{s} ({c} jobs)" for s, c in top_missing)
                lines.append(f"**Top Missing Skills Across Matched Jobs:** {formatted}.")
                lines.append("**Recommended Profile Improvements:** Add measurable metrics to your SQL/Python/ML projects and build 1-2 portfolio projects covering the missing tools above.")

        filtered = jobs
        if "remote" in lowered:
            filtered = [j for j in filtered if j.work_mode == "remote"]
        if "intern" in lowered:
            filtered = [j for j in filtered if j.seniority_level == "intern"] or filtered
        if "fresher" in lowered or "entry" in lowered:
            filtered = [j for j in filtered if j.fresher_eligible] or filtered

        if filtered:
            lines.append("\n**Top Grounded Opportunities in Your Database:**")
            for job in filtered[:5]:
                m = matches_by_job.get(job.id)
                score_str = f" — **{m.match_score:.1f}% ({m.eligibility_status})**" if m else ""
                lines.append(
                    f"- **#{job.id} {job.title}** at **{job.company}** ({job.location} · `{job.work_mode}` · `{job.seniority_level}`){score_str}\n"
                    f"  Official Link: {job.apply_url}"
                )
        else:
            lines.append("\nNo stored verified jobs matched that specific filter in the current database.")

        return "\n".join(lines)

    def answer(
        self,
        db: Session,
        message: str,
        session_id: str = "default",
        focused_job_id: Optional[int] = None,
        user_id: int = 1,
    ) -> tuple[str, List[int], bool]:
        resume_obj: Optional[Resume] = None
        retrieved_jobs: List[JobListing] = []
        matches_map: Dict[int, JobMatch] = {}

        def node_retrieve(state: ChatGraphState) -> ChatGraphState:
            nonlocal resume_obj, retrieved_jobs, matches_map
            uid = state.get("user_id", 1)
            resume_obj, resume_ctx = self._build_resume_context(db, user_id=uid)
            retrieved_jobs, matches_map, jobs_ctx = self._retrieve_relevant_jobs(
                db=db,
                resume=resume_obj,
                query=state["user_message"],
                focused_job_id=state.get("focused_job_id"),
            )
            recent_history = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == uid, ChatMessage.session_id == state["session_id"])
                .order_by(ChatMessage.created_at.desc())
                .limit(6)
                .all()
            )
            history_msgs = [{"role": m.role, "content": m.content} for m in reversed(recent_history)]
            return {
                "resume_context": resume_ctx,
                "jobs_context": jobs_ctx,
                "referenced_job_ids": [j.id for j in retrieved_jobs],
                "history_messages": history_msgs,
            }

        def node_generate(state: ChatGraphState) -> ChatGraphState:
            system_prompt = (
                "You are Personal AI JobPilot's Career & Job Intelligence Assistant. "
                "Answer ONLY using the stored resume profile and verified job listings provided below. "
                "NEVER fabricate companies, salaries, job descriptions, or URLs. "
                "If requested information is missing in the context, state that clearly. "
                "Always remind the user to review official links manually before applying.\n\n"
                f"=== STORED RESUME PROFILE ===\n{state['resume_context']}\n\n"
                f"=== VERIFIED STORED JOBS (RAG CONTEXT) ===\n{state['jobs_context']}"
            )
            messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
            messages.extend(state.get("history_messages", []))
            messages.append({"role": "user", "content": state["user_message"]})

            llm_reply = self.llm_client.chat(messages, max_tokens=900)
            if llm_reply:
                return {"reply": llm_reply, "used_llm": True}

            fallback = self._deterministic_reply(
                user_message=state["user_message"],
                resume=resume_obj,
                jobs=retrieved_jobs,
                matches_by_job=matches_map,
            )
            return {"reply": fallback, "used_llm": False}

        graph = StateGraph(ChatGraphState)
        graph.add_node("retrieve", node_retrieve)
        graph.add_node("generate", node_generate)
        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", END)
        compiled = graph.compile()

        result: Dict[str, Any] = compiled.invoke(
            {
                "user_id": user_id,
                "user_message": message,
                "session_id": session_id,
                "focused_job_id": focused_job_id,
            }
        )

        ref_ids = result.get("referenced_job_ids", [])
        reply = result.get("reply", "")
        used_llm = bool(result.get("used_llm", False))

        db.add(ChatMessage(user_id=user_id, session_id=session_id, role="user", content=message, referenced_job_ids_json=ref_ids))
        db.add(ChatMessage(user_id=user_id, session_id=session_id, role="assistant", content=reply, referenced_job_ids_json=ref_ids))
        db.commit()

        return reply, ref_ids, used_llm

    def answer_ephemeral(
        self,
        db: Session,
        resume: Optional[Any],
        matches_by_job: Dict[int, Any],
        history: List[Dict[str, str]],
        message: str,
        focused_job_id: Optional[int] = None,
    ) -> tuple[str, List[int], bool]:
        """Answer using shared SQLite jobs + in-RAM ephemeral resume/match state without writing to DB."""
        if not resume:
            resume_ctx = "No resume has been uploaded yet in this session."
        else:
            raw_excerpt = (getattr(resume, "raw_text", "") or getattr(resume, "summary", ""))[:2200]
            resume_ctx = (
                f"Candidate Name: {resume.candidate_name or 'Candidate'} | Graduation Year: {resume.graduation_year or 'Not specified'}\n"
                f"Experience Level: {resume.experience_level}\n"
                f"Target Roles: {', '.join(resume.target_roles_json or [])}\n"
                f"Preferred Locations: {', '.join(resume.preferred_locations_json or [])}\n"
                f"Skills: {', '.join(resume.skills_json or [])}\n"
                f"Summary: {resume.summary}\n"
                f"Education: {resume.education_json}\n"
                f"Experience: {resume.experience_json}\n"
                f"Projects: {resume.projects_json}\n"
                f"Resume Text Excerpt:\n{raw_excerpt}"
            )

        candidate_ids: List[int] = []
        if focused_job_id is not None:
            candidate_ids.append(focused_job_id)

        similar = self.vector_store.query_similar_jobs(query_text=message, top_k=6)
        for item in similar:
            jid = item.get("job_id")
            if jid and jid not in candidate_ids:
                candidate_ids.append(jid)

        jobs: List[JobListing] = []
        if candidate_ids:
            fetched = (
                db.query(JobListing)
                .filter(JobListing.id.in_(candidate_ids), JobListing.is_expired.is_(False))
                .all()
            )
            by_id = {j.id: j for j in fetched}
            jobs = [by_id[jid] for jid in candidate_ids if jid in by_id]

        if len(jobs) < 8 and matches_by_job:
            top_ids = [
                jid
                for jid, _ in sorted(matches_by_job.items(), key=lambda kv: kv[1].match_score, reverse=True)[:8]
                if jid not in {j.id for j in jobs}
            ]
            if top_ids:
                extra = (
                    db.query(JobListing)
                    .filter(JobListing.id.in_(top_ids), JobListing.is_active.is_(True), JobListing.is_expired.is_(False))
                    .all()
                )
                extra_by_id = {j.id: j for j in extra}
                for jid in top_ids:
                    if jid in extra_by_id:
                        jobs.append(extra_by_id[jid])
        elif len(jobs) < 5:
            extra = (
                db.query(JobListing)
                .filter(JobListing.is_active.is_(True), JobListing.verified.is_(True), JobListing.is_expired.is_(False))
                .order_by(JobListing.discovered_at.desc())
                .limit(5)
                .all()
            )
            seen = {j.id for j in jobs}
            for j in extra:
                if j.id not in seen:
                    jobs.append(j)

        jobs = jobs[:8]
        rel_matches = {j.id: matches_by_job[j.id] for j in jobs if j.id in matches_by_job}
        if not jobs:
            jobs_ctx = "No discovered jobs are currently stored in the database."
        else:
            blocks: List[str] = []
            for job in jobs:
                match = rel_matches.get(job.id)
                match_line = (
                    f"Match Score: {match.match_score:.1f}% | Eligibility: {match.eligibility_status} | "
                    f"Matching: {', '.join(match.matching_skills_json)} | Missing: {', '.join(match.missing_skills_json)}"
                    if match
                    else "Match Score: Not yet computed"
                )
                blocks.append(
                    f"[Job #{job.id}] {job.title} at {job.company} ({job.location}, work_mode={job.work_mode}, {job.seniority_level})\n"
                    f"Category: {job.role_category} | Fresher Eligible: {job.fresher_eligible} | Salary/Stipend: {job.salary_or_stipend or 'Not stated'}\n"
                    f"Source: {job.source} | Apply URL: {job.apply_url}\n"
                    f"Required Skills: {', '.join(job.required_skills_json or [])}\n"
                    f"{match_line}\n"
                    f"Description Excerpt: {(job.description or '')[:700]}"
                )
            jobs_ctx = "\n\n---\n\n".join(blocks)

        system_prompt = (
            "You are Personal AI JobPilot's Career & Job Intelligence Assistant. "
            "Answer ONLY using the current session's resume profile and verified job listings provided below. "
            "NEVER fabricate companies, salaries, job descriptions, or URLs. "
            "If requested information is missing in the context, state that clearly. "
            "Always remind the user to review official links manually before applying.\n\n"
            f"=== CURRENT SESSION RESUME PROFILE ===\n{resume_ctx}\n\n"
            f"=== VERIFIED STORED JOBS (RAG CONTEXT) ===\n{jobs_ctx}"
        )
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": message})

        llm_reply = self.llm_client.chat(messages, max_tokens=900)
        if llm_reply:
            return llm_reply, [j.id for j in jobs], True

        fallback = self._deterministic_reply(
            user_message=message,
            resume=resume,
            jobs=jobs,
            matches_by_job=rel_matches,
        )
        return fallback, [j.id for j in jobs], False
