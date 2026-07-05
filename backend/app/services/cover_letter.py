"""Magic Cover Letter / LinkedIn message generation."""
from typing import Any

from app.models.generation import GenerationKind
from app.services import llm

SYSTEM_PROMPT = """\
You write outreach for students and junior engineers. Voice: confident but
not arrogant, specific, zero clichés ("I am writing to express my interest"
is banned). Ground every claim in the candidate's actual resume. Address the
company's needs from the job description directly."""

COVER_LETTER_PROMPT = """\
Write a cover letter (220-320 words, 3-4 short paragraphs) for this candidate
and job. Structure: a hook tying the candidate to the company's problem; 1-2
concrete proof points from the resume mapped to the job's requirements; a
confident close with a call to action. Do not repeat the resume — interpret it.

Return JSON: {{"text": "<the letter>", "subject": "<email subject line>"}}

RESUME:
---
{resume}
---

JOB DESCRIPTION:
---
{job_description}
---
"""

LINKEDIN_PROMPT = """\
Write a LinkedIn direct message (60-110 words) from this candidate to the
hiring manager / recruiter for the job below. Friendly, specific, one clear
proof point from the resume, ends with a low-friction ask (a short chat).
No "Dear Sir/Madam", no formal letter structure.

Return JSON: {{"text": "<the message>"}}

RESUME:
---
{resume}
---

JOB DESCRIPTION:
---
{job_description}
---
"""


async def generate_outreach(
    kind: GenerationKind, resume_text: str, job_description: str
) -> dict[str, Any]:
    template = (
        LINKEDIN_PROMPT
        if kind == GenerationKind.LINKEDIN_MESSAGE
        else COVER_LETTER_PROMPT
    )
    return await llm.generate_json(
        template.format(
            resume=resume_text[:15000], job_description=job_description[:15000]
        ),
        system=SYSTEM_PROMPT,
        temperature=0.7,
    )
