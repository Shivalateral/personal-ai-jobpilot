"""Shared test data builders (PDF and DOCX resume generators)."""

import io

import docx
import fitz


def build_sample_pdf_bytes() -> bytes:
    """Create a realistic in-memory PDF resume using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "Alex Rivera\n"
        "alex.rivera@example.com\n\n"
        "Summary\n"
        "Recent Data Science & AI/ML graduate skilled in Python, SQL, PyTorch, and LangGraph.\n\n"
        "Education\n"
        "B.S. in Data Science, State University, Class of 2026\n\n"
        "Skills\n"
        "Python, SQL, Pandas, NumPy, Scikit-learn, PyTorch, FastAPI, Streamlit, Docker, Git\n\n"
        "Experience\n"
        "Data Analyst Intern, FinTech Labs (Summer 2025)\n"
        "- Built SQL and Python ETL pipelines reducing reporting time by 35%.\n\n"
        "Projects\n"
        "RAG Career Assistant using ChromaDB, Hugging Face Transformers, and FastAPI\n\n"
        "Certifications\n"
        "DeepLearning.AI Machine Learning Specialization\n"
    )
    page.insert_text((50, 50), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_sample_docx_bytes() -> bytes:
    """Create a realistic in-memory DOCX resume using python-docx."""
    document = docx.Document()
    document.add_paragraph("Jordan Lee")
    document.add_paragraph("Summary")
    document.add_paragraph(
        "Aspiring AI/ML Engineer and Data Analyst with internship experience in NLP and SQL."
    )
    document.add_paragraph("Education")
    document.add_paragraph("M.S. in Computer Science (AI Track), Expected Graduation 2026")
    document.add_paragraph("Skills")
    document.add_paragraph("Python, SQL, TensorFlow, PyTorch, Hugging Face, LangGraph, Tableau, AWS")
    document.add_paragraph("Experience")
    document.add_paragraph("ML Research Intern, VisionLab (2025)")
    document.add_paragraph("Projects")
    document.add_paragraph("Customer Churn Prediction with XGBoost and Streamlit")
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
