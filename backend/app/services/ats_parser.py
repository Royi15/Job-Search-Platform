"""Simulated ATS parser.

Real applicant-tracking systems do embarrassingly crude things: extract raw
text, look for exact keyword hits against the job description, and detect
standard section headers. We reproduce that behaviour so users can see their
resume the way the machine sees it — that's the "before" picture the
tailoring engine improves.
"""
import re
from typing import Any

from pypdf import PdfReader

# Common tech-stack vocabulary an ATS keyword filter would match against.
# Extend freely — matching is case-insensitive on word boundaries.
KNOWN_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "react", "angular", "vue", "next.js", "node.js", "express", "fastapi",
    "django", "flask", "spring", ".net", "html", "css", "tailwind",
    "docker", "kubernetes", "terraform", "aws", "azure", "gcp", "linux",
    "git", "ci/cd", "jenkins", "github actions", "rest", "graphql", "grpc",
    "kafka", "rabbitmq", "microservices", "machine learning", "deep learning",
    "pytorch", "tensorflow", "pandas", "numpy", "data analysis", "nlp",
    "agile", "scrum", "tdd", "unit testing", "oop", "design patterns",
]

SECTION_HEADERS = [
    "experience", "work experience", "employment", "education", "skills",
    "projects", "certifications", "summary", "objective", "languages",
    "military service", "volunteering",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")


def _collapse_exploded_line(line: str) -> str:
    """Some PDF exporters (design tools especially) position every glyph
    separately, so extraction yields 'P y t h o n  a n d  J a v a' — single
    spaces between letters, wider gaps between words. Detect such lines and
    reassemble the words."""
    tokens = [t for t in line.split(" ") if t]
    if len(tokens) < 6:
        return line
    single_char = sum(1 for t in tokens if len(t) == 1)
    if single_char / len(tokens) < 0.7:
        return line  # normal text — leave untouched
    words = re.split(r"\s{2,}", line.strip())
    return " ".join(w.replace(" ", "") for w in words)


def extract_pdf_text(path: str) -> str:
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return "\n".join(_collapse_exploded_line(line) for line in text.splitlines())


def _find_skills(text_lower: str) -> list[str]:
    found = []
    for skill in KNOWN_SKILLS:
        # Escape regex chars in skill names like "c++" / ".net"
        pattern = r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])"
        if re.search(pattern, text_lower):
            found.append(skill)
    return found


def _find_sections(text_lower: str) -> list[str]:
    return [h for h in SECTION_HEADERS if re.search(rf"^\s*{h}\b", text_lower, re.M)]


def parse_resume_text(text: str) -> dict[str, Any]:
    """Return the structured view an ATS would extract from this resume."""
    text_lower = text.lower()
    return {
        "skills": _find_skills(text_lower),
        "sections_detected": _find_sections(text_lower),
        "emails": EMAIL_RE.findall(text)[:3],
        "phones": [p.strip() for p in PHONE_RE.findall(text)][:3],
        "word_count": len(text.split()),
    }


def keyword_coverage(resume_text: str, job_description: str) -> dict[str, Any]:
    """Which known skills appear in the JD, and which of those the resume hits.

    This is the naive exact-match scoring an ATS applies — the number the
    tailoring engine tries to raise.
    """
    jd_skills = set(_find_skills(job_description.lower()))
    resume_skills = set(_find_skills(resume_text.lower()))
    matched = sorted(jd_skills & resume_skills)
    missing = sorted(jd_skills - resume_skills)
    score = round(100 * len(matched) / len(jd_skills)) if jd_skills else 100
    return {"matched": matched, "missing": missing, "score": score}
