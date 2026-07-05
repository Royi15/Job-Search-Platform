"""Resume ↔ job-description gap analysis and sentence rewriting.

Pipeline: score the resume with the simulated ATS (before), ask the LLM for
organic sentence-level rewrites that inject the missing keywords, then re-score
the patched text (after). Both scores are stored so the UI can show the lift.
"""
from typing import Any

from app.services import llm
from app.services.ats_parser import keyword_coverage

SYSTEM_PROMPT = """\
You are an expert resume writer who helps students and junior engineers pass
Applicant Tracking System (ATS) keyword filters — honestly. You rewrite
existing sentences to naturally include required keywords ONLY where the
candidate plausibly has that experience based on their resume. You never
invent employers, titles, degrees, or experience the resume does not support.
Keep every rewrite concise, action-verb-led, and truthful in spirit."""

PROMPT_TEMPLATE = """\
Below are a candidate's resume and a target job description.

ATS keyword scan already found these job-description keywords MISSING from
the resume: {missing}

Return JSON with exactly this shape:
{{
  "jd_keywords": ["the 10-18 most important concrete skills, technologies, tools or qualifications this job description asks for — short lowercase phrases"],
  "gap_summary": "2-3 sentences: the real semantic gap, not just keywords",
  "rewrites": [
    {{
      "original": "<exact sentence copied from the resume>",
      "rewritten": "<improved sentence with keywords woven in naturally>",
      "keywords_injected": ["<keyword>", ...]
    }}
  ],
  "keywords_not_injectable": ["keywords that would require lying — do NOT force these"],
  "extra_tips": ["1-3 short, specific suggestions for this application"]
}}

Rules:
- 3 to 8 rewrites. "original" must be copied VERBATIM from the resume so the
  UI can highlight it.
- Prefer weaving a missing keyword into a sentence describing related work.
- If a missing keyword has no honest home in this resume, list it under
  "keywords_not_injectable" instead of forcing it.

RESUME:
---
{resume}
---

JOB DESCRIPTION:
---
{job_description}
---
"""


def _apply_rewrites(resume_text: str, rewrites: list[dict[str, Any]]) -> str:
    patched = resume_text
    for rewrite in rewrites:
        original = rewrite.get("original", "")
        if original and original in patched:
            patched = patched.replace(original, rewrite.get("rewritten", original), 1)
    return patched


def _coverage(text: str, keywords: list[str]) -> tuple[list[str], list[str], int]:
    """Which keywords appear in the text, which don't, and the percentage."""
    text_lower = text.lower()
    matched = sorted(k for k in keywords if k in text_lower)
    missing = sorted(k for k in keywords if k not in text_lower)
    score = round(100 * len(matched) / len(keywords)) if keywords else 100
    return matched, missing, score


async def tailor_resume(resume_text: str, job_description: str) -> dict[str, Any]:
    # Dictionary-based scan feeds the prompt a first hint of what's missing.
    dict_scan = keyword_coverage(resume_text, job_description)

    analysis = await llm.generate_json(
        PROMPT_TEMPLATE.format(
            missing=", ".join(dict_scan["missing"]) or "(none — focus on phrasing)",
            resume=resume_text[:15000],
            job_description=job_description[:15000],
        ),
        system=SYSTEM_PROMPT,
    )
    rewrites = analysis.get("rewrites", [])

    # Score against this JD's actual vocabulary: the requirements the LLM
    # extracted plus our tech dictionary hits. A fixed dictionary alone
    # saturates at 100% on jobs whose stack it doesn't cover.
    llm_keywords = {
        k.strip().lower()
        for k in analysis.get("jd_keywords", [])
        if isinstance(k, str) and k.strip()
    }
    keywords = sorted(llm_keywords | set(dict_scan["matched"]) | set(dict_scan["missing"]))
    matched, missing, score_before = _coverage(resume_text, keywords)
    _, _, score_after = _coverage(_apply_rewrites(resume_text, rewrites), keywords)

    return {
        "ats_score_before": score_before,
        "ats_score_after": score_after,
        "keywords_matched": matched,
        "keywords_missing": missing,
        "gap_summary": analysis.get("gap_summary", ""),
        "rewrites": rewrites,
        "keywords_not_injectable": analysis.get("keywords_not_injectable", []),
        "extra_tips": analysis.get("extra_tips", []),
    }
