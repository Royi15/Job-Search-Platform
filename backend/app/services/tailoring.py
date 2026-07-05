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


async def tailor_resume(resume_text: str, job_description: str) -> dict[str, Any]:
    before = keyword_coverage(resume_text, job_description)

    analysis = await llm.generate_json(
        PROMPT_TEMPLATE.format(
            missing=", ".join(before["missing"]) or "(none — focus on phrasing)",
            resume=resume_text[:15000],
            job_description=job_description[:15000],
        ),
        system=SYSTEM_PROMPT,
    )

    rewrites = analysis.get("rewrites", [])
    after = keyword_coverage(_apply_rewrites(resume_text, rewrites), job_description)

    return {
        "ats_score_before": before["score"],
        "ats_score_after": after["score"],
        "keywords_matched": before["matched"],
        "keywords_missing": before["missing"],
        "gap_summary": analysis.get("gap_summary", ""),
        "rewrites": rewrites,
        "keywords_not_injectable": analysis.get("keywords_not_injectable", []),
        "extra_tips": analysis.get("extra_tips", []),
    }
