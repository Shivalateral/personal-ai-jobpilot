"""Tests for the LangGraph Conversational AI Assistant grounded in resume and job context."""

from backend.agents.chat_agent import ConversationalAIAgent
from backend.agents.discovery_agent import JobDiscoveryAgent
from backend.agents.pipeline_graph import DiscoveryPipelineOrchestrator
from backend.agents.resume_agent import ResumeIntelligenceAgent
from backend.db.models import ChatMessage
from backend.services.discovery_sources import RawDiscoveredJob
from tests.helpers import build_sample_pdf_bytes


class _StubChatSources:
    def fetch_all(self):
        return (
            [
                RawDiscoveredJob(
                    source="ashby",
                    external_id="c-1",
                    company="NeuralFlow",
                    title="Junior AI Engineer",
                    location="San Francisco",
                    description="Build RAG pipelines using Python, LangGraph, ChromaDB, and Kubernetes.",
                    apply_url="https://jobs.ashbyhq.com/neuralflow/c-1",
                    required_skills=["Python", "LangGraph", "ChromaDB", "Kubernetes"],
                    role_category="AI/ML Engineer",
                    seniority_level="entry_level",
                    is_entry_level_priority=True,
                )
            ],
            ["ashby:neuralflow"],
        )


def test_chat_agent_grounds_reply_in_resume_and_jobs(db_session):
    ResumeIntelligenceAgent().ingest_resume(
        db=db_session,
        file_bytes=build_sample_pdf_bytes(),
        filename="alex.pdf",
        rescore_existing_jobs=False,
    )
    orchestrator = DiscoveryPipelineOrchestrator(
        discovery_agent=JobDiscoveryAgent(sources_client=_StubChatSources())
    )
    orchestrator.run(db=db_session, trigger_type="manual")

    agent = ConversationalAIAgent()
    reply, ref_ids, used_llm = agent.answer(
        db=db_session,
        message="What skills am I missing and how can I improve my resume?",
        session_id="test-session",
    )
    assert used_llm is False
    assert len(ref_ids) >= 1
    assert "NeuralFlow" in reply
    assert "Kubernetes" in reply
    assert db_session.query(ChatMessage).filter(ChatMessage.session_id == "test-session").count() == 2
