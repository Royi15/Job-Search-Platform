"""Simulated interview engine.

Design rule: the backend owns the interview flow (how many questions, which
stage, when to grade) — the LLM is only ever asked for ONE question at a
time, or for a rubric-based evaluation of the finished transcript. Letting
the model direct the flow makes it drift; keeping it on a leash doesn't.

The final X/100 is computed in code from the rubric's dimension scores, so
the number is deterministic given the LLM's per-dimension judgments.
"""
import random
from datetime import datetime, timezone
from typing import Any

from app.services import llm

BEHAVIORAL_QUESTIONS = 3          # stage 1 length (first is always "tell me about yourself")
TECHNICAL_QUESTIONS = 3           # stage 2 length
TECHNICAL_TIME_LIMIT_SECONDS = 900  # per stage-2 question (15 min — real-interview weight)
OVERTIME_GRACE_SECONDS = 15       # network/clock-skew allowance

FIRST_QUESTION = (
    "Tell me about yourself — walk me through your background and what "
    "brings you to this role."
)

# Short acknowledgment lines shown before the next question, so questions
# don't just snap in instantly — no LLM call, picked without repeats within
# a session for as long as the pool allows.
REGULAR_TRANSITIONS = [
    "Got it, thanks for sharing.",
    "Nice, that's helpful context.",
    "Good — thanks, let's keep going.",
    "Appreciate the detail there.",
    "Interesting, thanks for that.",
    "Okay, noted. Moving on.",
    "Thanks, that gives me a good picture.",
    "Solid answer — let's continue.",
    "Great, thanks for explaining that.",
    "Cool, let's move to the next one.",
]

STAGE_TRANSITIONS = [
    "That wraps up the intro questions — nice work. Let's shift into the "
    "technical round. Each question below is timed, so take a breath first.",
    "Thanks, that's a great foundation. Now for the technical part — this "
    "section is timed, so read carefully before you start typing.",
    "Good, that covers the background. Time for the technical questions — "
    "you'll have a timer on each one, so pace yourself.",
]


def _pick_transition(pool: list[str], transcript: list[dict[str, Any]]) -> str:
    """Avoid repeating a transition line within the same session."""
    used = {e.get("transition") for e in transcript if e.get("transition")}
    remaining = [t for t in pool if t not in used]
    return random.choice(remaining or pool)


def pick_regular_transition(transcript: list[dict[str, Any]]) -> str:
    return _pick_transition(REGULAR_TRANSITIONS, transcript)


def pick_stage_transition(transcript: list[dict[str, Any]]) -> str:
    return _pick_transition(STAGE_TRANSITIONS, transcript)

INTERVIEWER_SYSTEM = """\
You are a professional but friendly interviewer at the company hiring for the
job below. You interview students and junior candidates: rigorous, never
condescending. You output ONLY what you are asked to output — no preambles,
no meta commentary."""


def new_entry(
    stage: str,
    question: str,
    time_limit: int | None = None,
    transition: str | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "question": question,
        "transition": transition,
        "asked_at": datetime.now(timezone.utc).isoformat(),
        "time_limit_seconds": time_limit,
        "answer": None,
        "answered_at": None,
        "overtime": False,
    }


def _format_transcript(transcript: list[dict[str, Any]]) -> str:
    lines = []
    for i, entry in enumerate(transcript, 1):
        lines.append(f"Q{i} [{entry['stage']}]: {entry['question']}")
        answer = entry.get("answer")
        lines.append(f"A{i}: {answer if answer else '(no answer)'}")
        if entry.get("overtime"):
            lines.append(f"(note: candidate exceeded the time limit on Q{i})")
    return "\n".join(lines)


async def next_behavioral_question(
    resume_text: str, job_description: str, transcript: list[dict[str, Any]]
) -> str:
    prompt = f"""\
You are in stage 1 of the interview (behavioral / getting to know the
candidate). Based on the candidate's resume, ask ONE short behavioral
question — for example about a project they built, a challenge they faced,
teamwork, or their motivation for this specific role. Ground it in something
concrete from their resume when possible. Do not repeat or rephrase questions
already asked.

Questions already asked:
{_format_transcript(transcript)}

JOB DESCRIPTION:
---
{job_description[:6000]}
---

CANDIDATE RESUME:
---
{resume_text[:10000]}
---

Output: the question text only, one or two sentences."""
    question = await llm.generate(prompt, system=INTERVIEWER_SYSTEM, temperature=0.8)
    return question.strip().strip('"')


async def next_technical_question(
    resume_text: str, job_description: str, transcript: list[dict[str, Any]]
) -> str:
    prompt = f"""\
You are in stage 2 of the interview (technical, timed) — this should feel
like a REAL technical interview, not a warm-up quiz. Ask ONE substantial
technical question targeting the core skills this job description requires,
calibrated for a strong student/junior candidate but genuinely challenging:
- For software/coding-heavy roles: a real algorithmic problem (LeetCode
  medium-equivalent difficulty) that requires explaining an approach,
  reasoning about time/space complexity, and writing pseudocode or actual
  code in the text answer — not a trivia question.
- For system/infrastructure/networking-heavy roles: a system design or
  troubleshooting scenario with real depth (e.g. "design X for Y constraints",
  "walk through diagnosing Z") that requires multiple steps of reasoning.
- For other technical roles: a meaty applied problem from that domain that
  takes real thought, not a one-line definition question.
The candidate has {TECHNICAL_TIME_LIMIT_SECONDS // 60} minutes and can write
code/pseudocode/diagrams-as-text — do NOT require actually running code.
Do not repeat topics already covered.

Questions already asked:
{_format_transcript(transcript)}

JOB DESCRIPTION:
---
{job_description[:6000]}
---

CANDIDATE RESUME (for calibration):
---
{resume_text[:10000]}
---

Output: the question text only."""
    question = await llm.generate(prompt, system=INTERVIEWER_SYSTEM, temperature=0.8)
    return question.strip().strip('"')


GRADING_PROMPT = """\
You are grading a finished simulated job interview. Be honest and specific —
an inflated grade helps nobody. Quote or reference the candidate's actual
words as evidence. Empty or off-topic answers score 0-2. For technical
questions, give partial credit for correct approach/reasoning even if the
final answer has gaps — that mirrors how real interviewers grade — but a
technically wrong approach presented confidently should score low.

Return JSON exactly in this shape:
{{
  "behavioral": {{
    "communication": <0-10>,
    "structure": <0-10, did answers have a clear beginning/point/result>,
    "relevance": <0-10, tailored to THIS role vs generic>,
    "comments": "2-3 sentences on stage 1 overall"
  }},
  "technical_reviews": [
    {{
      "question_index": <1-based index among the TECHNICAL questions only>,
      "score": <0-10>,
      "review": "what was right, what was missing or wrong — specific",
      "better_answer_hint": "one concrete thing a stronger answer would include"
    }}
  ],
  "summary": "3-4 sentences: overall impression as an interviewer",
  "strengths": ["2-4 short bullets"],
  "improvements": ["2-4 short bullets, actionable"]
}}

JOB DESCRIPTION:
---
{job_description}
---

CANDIDATE RESUME:
---
{resume}
---

FULL INTERVIEW TRANSCRIPT:
---
{transcript}
---
"""


def _clamp(value: Any, default: float = 5.0) -> float:
    if not isinstance(value, (int, float)):
        return default
    return max(0.0, min(10.0, float(value)))


async def grade_transcript(
    resume_text: str, job_description: str, transcript: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run the rubric evaluation, then compute the 0-100 score in code:
    behavioral dimensions -> 40 points, technical questions -> 60 points,
    with a -2 penalty on any technical question that ran overtime."""
    analysis = await llm.generate_json(
        GRADING_PROMPT.format(
            job_description=job_description[:6000],
            resume=resume_text[:10000],
            transcript=_format_transcript(transcript),
        ),
        system=INTERVIEWER_SYSTEM,
        temperature=0.2,
    )

    behavioral = analysis.get("behavioral", {})
    behavioral_avg = (
        _clamp(behavioral.get("communication"))
        + _clamp(behavioral.get("structure"))
        + _clamp(behavioral.get("relevance"))
    ) / 3

    reviews = analysis.get("technical_reviews", [])
    technical_entries = [e for e in transcript if e["stage"] == "technical"]
    technical_scores: list[float] = []
    for index, entry in enumerate(technical_entries, 1):
        review = next(
            (r for r in reviews if isinstance(r, dict) and r.get("question_index") == index),
            None,
        )
        score = _clamp(review.get("score") if review else None)
        if entry.get("overtime"):
            score = max(0.0, score - 2.0)
            if review is not None:
                review["overtime_penalty_applied"] = True
        technical_scores.append(score)
    technical_avg = sum(technical_scores) / len(technical_scores) if technical_scores else 5.0

    return {
        "score": round(behavioral_avg * 4 + technical_avg * 6),
        "behavioral": behavioral,
        "technical_reviews": reviews,
        "summary": analysis.get("summary", ""),
        "strengths": analysis.get("strengths", []),
        "improvements": analysis.get("improvements", []),
    }
