"""Tests for PDF & DOCX resume parsing, encryption, and replacement."""

from backend.agents.resume_agent import ResumeIntelligenceAgent
from backend.core.security import ResumeVault
from backend.db.models import Resume
from backend.services.resume_parser import ResumeParserService
from tests.helpers import build_sample_docx_bytes, build_sample_pdf_bytes


def test_parse_pdf_and_docx():
    parser = ResumeParserService()

    pdf_data = parser.parse(build_sample_pdf_bytes(), "alex_resume.pdf")
    assert pdf_data.file_type == "pdf"
    assert "Python" in pdf_data.skills
    assert "SQL" in pdf_data.skills
    assert "PyTorch" in pdf_data.skills
    assert "LangGraph" in pdf_data.skills
    assert pdf_data.experience_level in ("fresh_grad", "entry_level")
    assert len(pdf_data.education) >= 1
    assert len(pdf_data.projects) >= 1

    docx_data = parser.parse(build_sample_docx_bytes(), "jordan_resume.docx")
    assert docx_data.file_type == "docx"
    assert "Python" in docx_data.skills
    assert "TensorFlow" in docx_data.skills
    assert "XGBoost" in docx_data.skills


def test_resume_encryption_and_replacement(db_session):
    agent = ResumeIntelligenceAgent()

    first, replaced1, _ = agent.ingest_resume(
        db=db_session,
        file_bytes=build_sample_pdf_bytes(),
        filename="v1.pdf",
        rescore_existing_jobs=False,
    )
    assert replaced1 is False
    assert first.is_active is True
    # Raw email/text must be encrypted at rest, never stored in plaintext
    assert "alex.rivera@example.com" not in first.encrypted_raw_text
    assert "alex.rivera@example.com" in agent.decrypt_raw_text(first)

    second, replaced2, _ = agent.ingest_resume(
        db=db_session,
        file_bytes=build_sample_docx_bytes(),
        filename="v2.docx",
        rescore_existing_jobs=False,
    )
    assert replaced2 is True
    assert second.is_active is True

    refreshed_first = db_session.query(Resume).filter(Resume.id == first.id).first()
    assert refreshed_first.is_active is False
    assert agent.get_active_resume(db_session).id == second.id


def test_universal_resume_differentiation():
    import docx, io

    doc = docx.Document()
    doc.add_paragraph("Shaik Umar")
    doc.add_paragraph("Summary")
    doc.add_paragraph("Fresher seeking Customer Support Voice and Non-Voice Process Associate roles in BPO.")
    doc.add_paragraph("Skills")
    doc.add_paragraph("Customer Support, Voice Support, CRM, MS Office, Communication")
    buf = io.BytesIO()
    doc.save(buf)

    parser = ResumeParserService()
    bpo_data = parser.parse(buf.getvalue(), "bpo.docx")
    assert "Customer Support & BPO" in bpo_data.domain_knowledge
    assert "Data Analyst" not in bpo_data.target_roles


def test_vault_roundtrip():
    vault = ResumeVault()
    secret = "Sensitive candidate phone +1-555-0199"
    token = vault.encrypt(secret)
    assert token != secret
    assert vault.decrypt(token) == secret
