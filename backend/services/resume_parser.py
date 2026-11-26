"""Universal resume parsing service supporting PDF (PyMuPDF) and DOCX (python-docx) across all careers."""

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import docx
import fitz  # PyMuPDF

from backend.core.config import get_settings
from backend.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


# Universal multi-domain canonical skill, tool, language, and platform taxonomy
CANONICAL_SKILLS: Dict[str, List[str]] = {
    # Programming Languages & Frameworks
    "Python": ["python", "python3"],
    "Java": ["java", "core java", "j2ee"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp"],
    ".NET": [".net", "dotnet", "asp.net"],
    "JavaScript": ["javascript", "ecmascript"],
    "TypeScript": ["typescript"],
    "React": ["react", "reactjs", "react.js"],
    "Angular": ["angular", "angularjs"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Node.js": ["node.js", "nodejs", "express.js"],
    "Next.js": ["next.js", "nextjs"],
    "Spring Boot": ["spring boot", "spring framework"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Streamlit": ["streamlit"],
    "REST API": ["rest api", "restful", "rest apis"],
    "GraphQL": ["graphql"],
    # Data, Databases & AI/ML
    "SQL": ["sql", "postgresql", "postgres", "mysql", "sqlite", "t-sql", "pl/sql", "ms sql"],
    "MongoDB": ["mongodb", "nosql"],
    "Redis": ["redis"],
    "R": [" r ", "rstudio", "tidyverse", "ggplot2"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Polars": ["polars"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow", "keras"],
    "XGBoost": ["xgboost"],
    "LightGBM": ["lightgbm"],
    "Hugging Face": ["huggingface", "hugging face", "transformers"],
    "LangChain": ["langchain"],
    "LangGraph": ["langgraph"],
    "LLM": ["llm", "large language model", "large language models", "generative ai", "genai"],
    "RAG": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "NLP": ["nlp", "natural language processing", "spacy", "nltk"],
    "Computer Vision": ["computer vision", "opencv", "yolo", "cnn"],
    "Deep Learning": ["deep learning", "neural network", "neural networks"],
    "Machine Learning": ["machine learning", "ml"],
    "Statistics": ["statistics", "statistical analysis", "a/b testing", "ab testing", "hypothesis testing"],
    "Data Visualization": ["data visualization", "matplotlib", "seaborn", "plotly", "altair"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["excel", "microsoft excel", "ms excel", "pivot tables", "vlookup"],
    "Apache Spark": ["spark", "pyspark", "apache spark"],
    "dbt": ["dbt"],
    "Airflow": ["airflow", "apache airflow"],
    "Snowflake": ["snowflake"],
    "BigQuery": ["bigquery", "google bigquery"],
    "ChromaDB": ["chromadb", "chroma"],
    "Vector Databases": ["vector database", "vector databases", "pinecone", "faiss", "weaviate", "qdrant"],
    "MLOps": ["mlops", "mlflow", "wandb", "weights & biases"],
    "ETL": ["etl", "elt", "data pipeline", "data pipelines"],
    "Feature Engineering": ["feature engineering"],
    "MIS Reporting": ["mis", "mis reporting", "management information system"],
    # Cloud, DevOps & Cybersecurity & QA
    "AWS": ["aws", "amazon web services", "sagemaker", "ec2", "s3"],
    "GCP": ["gcp", "google cloud", "cloud run", "vertex ai"],
    "Azure": ["azure", "microsoft azure", "azure ml"],
    "Docker": ["docker", "containers"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "CI/CD": ["ci/cd", "cicd", "github actions", "jenkins", "gitlab ci"],
    "Linux": ["linux", "ubuntu", "bash", "shell scripting"],
    "Git": ["git", "github", "gitlab"],
    "Cybersecurity": ["cybersecurity", "cyber security", "infosec", "siem", "soc analyst", "owasp", "penetration testing", "vulnerability"],
    "Networking": ["networking", "tcp/ip", "dns", "vpn", "firewall"],
    "QA & Testing": ["qa", "quality assurance", "manual testing", "automation testing", "selenium", "cypress", "playwright", "pytest", "junit", "postman"],
    "IT Support": ["it support", "technical support", "help desk", "helpdesk", "troubleshooting", "active directory", "service desk", "ticketing"],
    # BPO, Customer Support & Operations
    "Customer Support": ["customer support", "customer service", "client support", "customer care", "customer handling"],
    "Voice Support": ["voice process", "voice support", "inbound calls", "outbound calls", "telecalling", "call center", "bpo"],
    "Non-Voice Support": ["non-voice", "non voice", "chat support", "email support", "back office", "data entry"],
    "CRM": ["crm", "salesforce", "zendesk", "freshdesk", "hubspot", "zoho crm", "servicenow"],
    "SLA Management": ["sla", "tat", "escalation handling", "ticket resolution", "csat", "nps"],
    "MS Office": ["ms office", "microsoft office", "ms word", "powerpoint", "outlook"],
    "Operations": ["operations", "process improvement", "sop", "workflow management"],
    "Supply Chain & Logistics": ["supply chain", "logistics", "inventory management", "procurement", "sap mm"],
    # Business, Finance, HR, Marketing, Sales, Product & Design
    "Business Analysis": ["business analysis", "brd", "frd", "requirements gathering", "stakeholder management"],
    "Finance & Accounting": ["accounting", "financial modeling", "tally", "gst", "bookkeeping", "accounts payable", "accounts receivable", "reconciliation", "sap fico", "auditing"],
    "Human Resources": ["human resources", "recruitment", "talent acquisition", "hr operations", "onboarding", "payroll", "screening", "sourcing"],
    "Digital Marketing": ["digital marketing", "seo", "sem", "google ads", "meta ads", "google analytics", "social media marketing", "email marketing"],
    "Sales & BD": ["sales", "business development", "lead generation", "cold calling", "b2b sales", "account management", "negotiation"],
    "Product Management": ["product management", "roadmap", "agile", "scrum", "jira", "user stories"],
    "UI/UX & Design": ["ui/ux", "figma", "wireframing", "prototyping", "adobe xd", "photoshop", "illustrator", "canva", "graphic design"],
    "Technical Writing": ["technical writing", "documentation", "api documentation", "content writing", "copywriting"],
}

SOFT_SKILLS: Dict[str, List[str]] = {
    "Communication": ["communication", "verbal communication", "written communication", "english proficiency", "fluent english"],
    "Problem Solving": ["problem solving", "problem-solving", "troubleshooting", "critical thinking"],
    "Teamwork": ["teamwork", "team player", "collaboration", "cross-functional"],
    "Time Management": ["time management", "multitasking", "prioritization", "punctual"],
    "Adaptability": ["adaptability", "fast learner", "quick learner", "flexible"],
    "Leadership": ["leadership", "mentoring", "ownership"],
    "Customer Empathy": ["empathy", "active listening", "patience", "conflict resolution"],
    "Attention to Detail": ["attention to detail", "accuracy", "detail-oriented"],
}

LANGUAGES_AND_FRAMEWORKS = {
    "Python", "Java", "C++", "C#", ".NET", "JavaScript", "TypeScript", "React", "Angular", "Vue.js",
    "Node.js", "Next.js", "Spring Boot", "Django", "Flask", "FastAPI", "Streamlit", "SQL", "R",
    "Pandas", "NumPy", "Scikit-learn", "PyTorch", "TensorFlow", "XGBoost", "LangChain", "LangGraph",
}

ROLE_INFERENCE_RULES: List[tuple[str, set[str], List[str]]] = [
    ("Data & Analytics", {"SQL", "Power BI", "Tableau", "Excel", "Pandas", "MIS Reporting", "ETL", "Statistics"}, ["Data Analyst", "Junior Data Analyst", "BI Analyst", "Reporting Analyst", "MIS Analyst"]),
    ("AI & Machine Learning", {"PyTorch", "TensorFlow", "Scikit-learn", "Machine Learning", "LLM", "RAG", "NLP", "Computer Vision", "Deep Learning"}, ["Data Scientist", "AI/ML Engineer", "Machine Learning Intern", "AI/ML Intern"]),
    ("Software Engineering", {"Java", "C++", "C#", ".NET", "JavaScript", "TypeScript", "React", "Angular", "Node.js", "Spring Boot", "Django", "Flask", "FastAPI"}, ["Software Engineer", "Full Stack Developer", "Backend Developer", "Frontend Developer", "Python Developer"]),
    ("Cloud & DevOps", {"AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "CI/CD", "Linux"}, ["Cloud Engineer", "DevOps Engineer", "Site Reliability Associate"]),
    ("Cybersecurity & Networking", {"Cybersecurity", "Networking"}, ["Cybersecurity Analyst", "SOC Analyst", "Network Support Engineer"]),
    ("QA & Testing", {"QA & Testing"}, ["QA Engineer", "Software Tester", "Automation Test Analyst"]),
    ("Customer Support & BPO", {"Customer Support", "Voice Support", "Non-Voice Support", "CRM", "SLA Management"}, ["Customer Support Executive", "BPO Voice / Non-Voice Associate", "Technical Support Associate", "Process Associate"]),
    ("IT & Technical Support", {"IT Support", "Networking", "Linux"}, ["IT Support Engineer", "Service Desk Analyst", "Technical Support Engineer"]),
    ("Business & Product", {"Business Analysis", "Product Management"}, ["Business Analyst", "Associate Product Manager", "Product Analyst"]),
    ("Finance & Accounting", {"Finance & Accounting"}, ["Accounts Executive", "Financial Analyst", "Audit Trainee"]),
    ("Human Resources", {"Human Resources"}, ["HR Executive", "Talent Acquisition Associate", "HR Operations Trainee"]),
    ("Marketing & Content", {"Digital Marketing", "Technical Writing"}, ["Digital Marketing Executive", "SEO Analyst", "Content / Technical Writer"]),
    ("Sales & BD", {"Sales & BD"}, ["Business Development Associate", "Inside Sales Executive"]),
    ("Design & UI/UX", {"UI/UX & Design"}, ["UI/UX Designer", "Graphic Designer"]),
    ("Operations & Supply Chain", {"Operations", "Supply Chain & Logistics"}, ["Operations Executive", "Supply Chain Analyst"]),
]

SECTION_HEADERS = {
    "summary": ["summary", "objective", "profile", "about me", "career objective", "professional summary"],
    "skills": ["skills", "technical skills", "core competencies", "technologies", "tools", "key skills", "strengths"],
    "education": ["education", "academic background", "academics", "academic qualifications"],
    "experience": ["experience", "work experience", "employment", "internships", "professional experience"],
    "projects": ["projects", "key projects", "academic projects", "personal projects"],
    "qualifications": ["certifications", "certificates", "qualifications", "awards", "achievements", "coursework"],
}


@dataclass
class ParsedResumeData:
    """Universal structured intelligence extracted from any career resume."""

    raw_text: str
    file_type: str
    candidate_name: Optional[str] = None
    graduation_year: Optional[int] = None
    summary: str = ""
    skills: List[str] = field(default_factory=list)
    soft_skills: List[str] = field(default_factory=list)
    languages_frameworks: List[str] = field(default_factory=list)
    domain_knowledge: List[str] = field(default_factory=list)
    achievements: List[str] = field(default_factory=list)
    education: List[Dict[str, Any]] = field(default_factory=list)
    experience: List[Dict[str, Any]] = field(default_factory=list)
    projects: List[Dict[str, Any]] = field(default_factory=list)
    qualifications: List[str] = field(default_factory=list)
    target_roles: List[str] = field(default_factory=list)
    preferred_locations: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    experience_level: str = "entry_level"


def extract_skills_from_text(text: str) -> List[str]:
    """Extract canonical multi-domain skills deterministically from text."""
    lowered = f" {(text or '').lower()} "
    normalized = re.sub(r"[,;/()\[\]\n\r\t|]+", " ", lowered)
    found: List[str] = []

    short_tokens = {"r", "ml", "qa", "c#", "ai"}
    for canonical, aliases in CANONICAL_SKILLS.items():
        for alias in aliases:
            a = alias.strip()
            if a in short_tokens or len(a) <= 3:
                if re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", normalized):
                    found.append(canonical)
                    break
            elif a in normalized:
                found.append(canonical)
                break
    return sorted(set(found))


def extract_soft_skills_from_text(text: str) -> List[str]:
    lowered = f" {(text or '').lower()} "
    found = [
        canonical
        for canonical, aliases in SOFT_SKILLS.items()
        if any(alias in lowered for alias in aliases)
    ]
    return sorted(set(found))


def _extract_pdf_text(file_bytes: bytes) -> str:
    text_parts: List[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text("text")
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def _extract_docx_text(file_bytes: bytes) -> str:
    document = docx.Document(io.BytesIO(file_bytes))
    lines: List[str] = []
    for para in document.paragraphs:
        if para.text and para.text.strip():
            lines.append(para.text.strip())
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                lines.append(row_text)
    return "\n".join(lines).strip()


def _split_into_sections(raw_text: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"header": []}
    current_section = "header"

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        clean_header = re.sub(r"[:\-_|]+$", "", line.lower()).strip()
        matched_section = None
        if len(clean_header) <= 45:
            for sec_name, keywords in SECTION_HEADERS.items():
                if clean_header in keywords:
                    matched_section = sec_name
                    break
        if matched_section:
            current_section = matched_section
            sections.setdefault(current_section, [])
        else:
            sections.setdefault(current_section, []).append(line)
    return sections


def _extract_graduation_year(raw_text: str, education_lines: List[str]) -> Optional[int]:
    edu_blob = " ".join(education_lines) + "\n" + raw_text[:2500]
    m = re.search(r"(?:class of|expected|graduation|graduating|20\d{2}\s*[-–]\s*)(202[4-9])", edu_blob, re.IGNORECASE)
    if m:
        return int(m.group(1))
    years = re.findall(r"\b(202[4-9])\b", " ".join(education_lines))
    if years:
        return max(int(y) for y in years)
    return None


def _infer_experience_level(raw_text: str, experience_lines: List[str]) -> str:
    lowered = raw_text.lower()
    if any(k in lowered for k in ["fresher", "fresh graduate", "class of 202", "expected graduation", "b.tech", "b.com", "b.sc", "bba", "bca", "b.a", "b.e", "m.s.", "undergraduate"]):
        if len(experience_lines) <= 8 and not re.search(r"\b([3-9]|1\d)\+?\s+years?\b", lowered):
            return "fresh_grad"
    if any(k in lowered for k in ["intern", "internship", "student", "trainee"]):
        if not re.search(r"\b([3-9]|1\d)\+?\s+years?\b", lowered):
            return "entry_level"
    years_match = re.findall(r"\b(\d+)\+?\s+years?\s+(?:of\s+)?experience\b", lowered)
    if years_match:
        max_years = max(int(y) for y in years_match)
        if max_years >= 5:
            return "senior"
        if max_years >= 2:
            return "mid"
    return "entry_level"


def _infer_domains_and_roles(skills: List[str], raw_text: str) -> tuple[List[str], List[str]]:
    """Dynamically infer career domains and target roles strictly from the actual resume."""
    skill_set = set(skills)
    lowered = raw_text.lower()
    domains: List[str] = []
    roles: List[str] = []

    for domain_name, trigger_skills, suggested_roles in ROLE_INFERENCE_RULES:
        matched_skills = skill_set & trigger_skills
        keyword_hit = any(r.lower() in lowered for r in suggested_roles)
        if matched_skills or keyword_hit:
            domains.append(domain_name)
            for r in suggested_roles:
                if r not in roles:
                    roles.append(r)

    if not domains:
        # Generic fallback without assuming Data Analyst
        if any(k in lowered for k in ("support", "voice", "customer", "bpo", "calling")):
            domains.append("Customer Support & BPO")
            roles.extend(["Customer Support Executive", "Process Associate", "Operations Executive"])
        else:
            domains.append("General Entry-Level / Graduate")
            roles.extend(["Graduate Trainee", "Associate", "Operations Executive"])

    return domains, roles[:8]


def _extract_achievements(raw_text: str, sections: Dict[str, List[str]]) -> List[str]:
    achievements: List[str] = []
    for line in sections.get("qualifications", []) + sections.get("experience", []) + sections.get("projects", []):
        if re.search(r"\b(\d+%|award|winner|top|rank|reduced|increased|achieved|certified|resolved)\b", line, re.IGNORECASE):
            achievements.append(line[:200])
    return achievements[:8]


def _extract_candidate_name(header_lines: List[str]) -> Optional[str]:
    skip_words = {"resume", "curriculum", "vitae", "cv", "agreement", "internship", "certificate", "bio"}
    for line in header_lines[:4]:
        clean = line.replace("\xa0", " ").strip()
        if "@" in clean or "http" in clean.lower() or any(ch.isdigit() for ch in clean):
            continue
        words = clean.split()
        if any(w.lower() in skip_words for w in words):
            continue
        if 1 <= len(words) <= 5 and all(w.replace("-", "").replace(".", "").isalpha() for w in words):
            return clean
    return None


class ResumeParserService:
    """Extracts universal, career-agnostic resume intelligence from PDF and DOCX files."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def extract_text(self, file_bytes: bytes, filename: str) -> tuple[str, str]:
        lower_name = (filename or "").lower()
        if lower_name.endswith(".pdf"):
            text = _extract_pdf_text(file_bytes)
            file_type = "pdf"
        elif lower_name.endswith(".docx"):
            text = _extract_docx_text(file_bytes)
            file_type = "docx"
        else:
            raise ValueError("Unsupported file format. Please upload a PDF or DOCX resume.")

        if not text or len(text.strip()) < 20:
            raise ValueError("Could not extract readable text from the uploaded resume.")
        return text, file_type

    def parse(self, file_bytes: bytes, filename: str) -> ParsedResumeData:
        settings = get_settings()
        raw_text, file_type = self.extract_text(file_bytes, filename)
        sections = _split_into_sections(raw_text)

        skills = extract_skills_from_text(raw_text)
        soft_skills = extract_soft_skills_from_text(raw_text)
        lang_fw = sorted(s for s in skills if s in LANGUAGES_AND_FRAMEWORKS)
        education = [{"details": line} for line in sections.get("education", [])[:10]]
        experience = [{"details": line} for line in sections.get("experience", [])[:15]]
        projects = [{"details": line} for line in sections.get("projects", [])[:12]]
        qualifications = sections.get("qualifications", [])[:10]
        achievements = _extract_achievements(raw_text, sections)
        summary_lines = sections.get("summary", [])
        summary = " ".join(summary_lines[:4]) if summary_lines else raw_text[:400].replace("\n", " ")
        candidate_name = _extract_candidate_name(sections.get("header", []))
        grad_year = _extract_graduation_year(raw_text, sections.get("education", []))
        exp_level = _infer_experience_level(raw_text, sections.get("experience", []))
        domains, target_roles = _infer_domains_and_roles(skills, raw_text)
        keywords = sorted(set(skills + soft_skills + target_roles + domains))

        parsed = ParsedResumeData(
            raw_text=raw_text,
            file_type=file_type,
            candidate_name=candidate_name,
            graduation_year=grad_year,
            summary=summary,
            skills=skills,
            soft_skills=soft_skills,
            languages_frameworks=lang_fw,
            domain_knowledge=domains,
            achievements=achievements,
            education=education,
            experience=experience,
            projects=projects,
            qualifications=qualifications,
            target_roles=target_roles,
            preferred_locations=settings.preferred_location_list,
            keywords=keywords,
            experience_level=exp_level,
        )

        if self.llm_client.is_available:
            self._enrich_with_llm(parsed)

        return parsed

    def _enrich_with_llm(self, parsed: ParsedResumeData) -> None:
        prompt = (
            "Extract structured resume details as strict JSON with keys: "
            "candidate_name (string or null), graduation_year (integer or null), summary (string, max 3 sentences), "
            "skills (list of technical/platform skills present in text), soft_skills (list of non-technical skills), "
            "domain_knowledge (list of career domains), achievements (list of strings), "
            "education (list of objects), experience (list of objects), projects (list of objects), "
            "qualifications (list of strings), target_roles (list of suitable job titles strictly matching this candidate), "
            "keywords (list of strings), "
            "experience_level (one of: intern, fresh_grad, entry_level, mid, senior).\n\n"
            f"Resume Text:\n{parsed.raw_text[:7000]}"
        )
        result = self.llm_client.chat_json(
            [
                {"role": "system", "content": "You are an accurate multi-domain resume parser. Extract only facts present in the resume; never invent skills or assume Data Science if the resume is for another field."},
                {"role": "user", "content": prompt},
            ]
        )
        if not result:
            return

        if result.get("candidate_name"):
            parsed.candidate_name = str(result["candidate_name"]).replace("\xa0", " ").strip()[:255]
        if isinstance(result.get("graduation_year"), int):
            parsed.graduation_year = result["graduation_year"]
        if result.get("summary"):
            parsed.summary = str(result["summary"])
        text_lower = parsed.raw_text.lower()
        for key, attr in (("skills", "skills"), ("soft_skills", "soft_skills")):
            vals = result.get(key) or []
            if isinstance(vals, list):
                verified = [str(v).strip() for v in vals if str(v).strip() and str(v).strip().lower() in text_lower]
                setattr(parsed, attr, sorted(set(getattr(parsed, attr)) | set(verified)))

        for field_name in ("education", "experience", "projects"):
            val = result.get(field_name)
            if isinstance(val, list) and val:
                setattr(parsed, field_name, val)
        for list_field in ("qualifications", "target_roles", "domain_knowledge", "achievements"):
            val = result.get(list_field)
            if isinstance(val, list) and val:
                setattr(parsed, list_field, [str(x).strip() for x in val if str(x).strip()])
        if isinstance(result.get("keywords"), list) and result["keywords"]:
            parsed.keywords = sorted(set(parsed.keywords) | {str(k).strip() for k in result["keywords"] if str(k).strip()})
        if result.get("experience_level") in {"intern", "fresh_grad", "entry_level", "mid", "senior"}:
            parsed.experience_level = result["experience_level"]
