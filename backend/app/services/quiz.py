"""Quiz generation: turns a source PDF/PPTX/MP3 into a multiple-choice
practice quiz. Ported from a standalone project (Trivisum) into this app's
architecture — same design rule as notebook.py: the LLM only ever produces
content within a fixed JSON shape."""
import logging
from typing import Any

from app.services import llm

logger = logging.getLogger(__name__)

# Pure text-in/JSON-out, no Files API — lighter than notebook.py's
# audio path, so these match notebook.py's original pre-audio values.
MAX_OUTPUT_TOKENS = 32768
GENERATION_TIMEOUT_SECONDS = 300.0

# Same fail-loud-not-silent-truncate policy as notebook.py's MAX_SOURCE_CHARS
# — refuse up front rather than silently quiz on a truncated document.
MAX_SOURCE_CHARS = 900_000

# A single quiz can't grow past this many questions — bounds prompt size on
# repeated "generate more" calls and keeps a "practice quiz" a sane size.
MAX_QUESTIONS_PER_QUIZ = 100

# How many questions to ask for per "generate more" click — a bounded top-up,
# not "as many as possible"; also clamped to whatever headroom remains
# under MAX_QUESTIONS_PER_QUIZ.
GENERATE_MORE_BATCH_SIZE = 15

# Transcribing a full lecture recording is a much bigger job than writing
# quiz questions — sized like notebook.py's audio-path constants (same
# underlying workload), separate from MAX_OUTPUT_TOKENS/
# GENERATION_TIMEOUT_SECONDS above, which size the questions-JSON call and
# stay unchanged regardless of source type.
TRANSCRIPTION_MAX_OUTPUT_TOKENS = 65536
TRANSCRIPTION_TIMEOUT_SECONDS = 420.0

DEFAULT_LANGUAGE = "en"
DEFAULT_DIFFICULTY = "medium"

DIFFICULTY_INSTRUCTIONS = {
    "easy": (
        "Focus on basic facts and explicit information stated directly in "
        "the text. Suitable for a first pass at the material."
    ),
    "medium": (
        "Where the source actually connects two ideas, prefer a question "
        "about that relationship or a straightforward inference over one "
        "that just restates a fact. But this is a preference, not a "
        "requirement: plenty of real source material is a list of "
        "separate, unconnected facts with nothing to relate to each other "
        "— for those, ask a plain, direct question about the fact itself "
        "rather than skipping it for lack of a relationship to test."
    ),
    "hard": (
        "Focus on deep analysis, less obvious implications, and "
        "synthesizing multiple parts of the text — questions a student "
        "can't answer just by skimming. Where the source is a list of "
        "independent facts with nothing to synthesize, test the least "
        "obvious or most easily confused facts rather than skipping ones "
        "that don't fit a synthesis-style question."
    ),
}


def _language_instruction(language: str) -> str:
    if language == "he":
        return (
            "\n\nWrite this quiz in Hebrew: every \"question\", each of the "
            "\"options\", the \"answer\", and the \"explanation\" must be "
            "in Hebrew. Keep mathematical notation in LaTeX exactly as "
            "instructed below (math notation is never translated), and "
            "keep technical terms, formulas, code, and field-specific "
            "terminology that a Hebrew-speaking student would naturally "
            "leave in English (e.g. \"API\", \"gradient descent\") in "
            "English — mix the two languages the way a real Hebrew "
            "student would, don't force-translate jargon nobody in the "
            "field uses."
        )
    return ""


def quiz_system(language: str = DEFAULT_LANGUAGE) -> str:
    return f"""\
You are an expert quiz writer — the person a top student would pay to turn
their course material into a practice quiz that actually tests whether they
understood it, not just whether they can spot a familiar keyword. Every
question must have exactly one unambiguously correct answer among its four
options; the three wrong options ("distractors") must be plausible enough
that someone who only skimmed the material could be tempted by them, but
never so close to correct that a reasonable person could argue for them
too. You output ONLY valid JSON in the exact shape requested — no
preambles, no markdown fences, no commentary outside the JSON.\
{_language_instruction(language)}"""


_QUESTIONS_SHAPE = """\
{
  "questions": [
    {
      "question": "a complete, standalone question — a student must be able to answer it without needing to see the source material",
      "options": ["option A", "option B", "option C", "option D"],
      "answer": "the exact text of the correct option, copied character-for-character from \\"options\\" above — never paraphrase it",
      "explanation": "1-2 sentences explaining why the correct answer is right (and, where useful, why the tempting wrong answer is wrong)"
    }
  ]
}"""

# Shared between the initial generation and "generate more" — both need
# these to hold regardless of how many questions are being asked for, so
# a fix here should never need a matching fix in only one of the two
# call sites.
_STRUCTURAL_RULES = """\
- "options" must have EXACTLY 4 entries, and all 4 must be distinct.
- "answer" must be character-for-character identical to one of the 4
  strings in "options" — not a paraphrase, not a shortened version, the
  exact same text. This is critical: the app matches "answer" against
  "options" by exact string comparison to know which one to mark correct.
- Write any mathematical notation in LaTeX, delimited so it can be
  rendered: inline math like "$O(n \\log n)$" within a normal sentence, and
  standalone formulas using "$$...$$". CRITICAL — this is going inside a
  JSON string, so every backslash in your LaTeX must be written as TWO
  backslashes (to render \\frac you must write \\\\frac in the JSON).
- CRITICAL — if any question, option, answer, or explanation needs an
  actual double-quote character for any reason (quoting a term, or a
  Hebrew abbreviation written with a gershayim mark, e.g. תנ"ך, רמב"ם),
  you MUST escape it as \\" inside the JSON string. A bare, un-escaped "
  in the middle of a string ends that string early and makes the entire
  JSON response fail to parse — there is no recovery from this, unlike a
  missed backslash. When in doubt, prefer spelling the word out without
  the abbreviation mark instead of risking an unescaped quote.
- Output the JSON object only, nothing else."""

JSON_SHAPE_INSTRUCTIONS = f"""\
Return JSON exactly in this shape:
{_QUESTIONS_SHAPE}

Rules:
- The number of questions must scale with how much the source material
  actually covers — do not settle on a fixed count regardless of source
  length. A short handout might only support 5-8 good questions; a long,
  dense document might support 40+. Judge yourself by coverage: every
  major topic, fact, or concept the source spends real time on should be
  testable by at least one question, and don't invent filler questions on
  minor details just to inflate the count.
- The difficulty guideline above shapes HOW a question about a fact is
  asked — it is never a reason to skip a fact entirely. If the source is a
  list of many short, independent facts rather than a connected argument,
  that means roughly one question per fact, in most cases, regardless of
  difficulty level: don't quietly drop a fact just because it doesn't fit
  a "relationship between two parts of the text" framing. A 10-fact source
  producing only 3-4 questions means facts were skipped, not that the
  material was thin.
{_STRUCTURAL_RULES}"""

MORE_QUESTIONS_SHAPE_INSTRUCTIONS = f"""\
Return JSON exactly in this shape:
{_QUESTIONS_SHAPE}

Rules:
- Every new question must test something genuinely NOT already covered by
  the existing questions listed above — not a reworded version of one of
  them, not the same fact from a slightly different angle. If the source
  material has been thoroughly covered already and you can't find enough
  genuinely new material, return FEWER questions than asked for, even
  zero — an empty or short list is the correct answer in that case, not a
  reason to pad with near-duplicates or trivial questions.
{_STRUCTURAL_RULES}"""


def _validate_question(q: dict[str, Any]) -> dict[str, Any] | None:
    """Repairs or rejects a real failure mode: the model sometimes
    paraphrases "answer" instead of copying an option verbatim, which would
    silently break the "is this the correct option" check in the UI (a
    plain string-equality comparison). Tries a whitespace/case-insensitive
    match before giving up — dropping a question is much better than
    shipping one where the wrong option silently gets marked correct."""
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return None
    if not all(isinstance(o, str) and o.strip() for o in options):
        return None
    answer = q.get("answer")
    if not isinstance(answer, str) or not isinstance(q.get("question"), str):
        return None
    if answer in options:
        return q
    normalized = {o.strip().casefold(): o for o in options}
    match = normalized.get(answer.strip().casefold())
    if match is None:
        return None
    q["answer"] = match
    return q


def _validate_questions(content: dict[str, Any]) -> list[dict[str, Any]]:
    questions = content.get("questions")
    if not isinstance(questions, list):
        return []
    valid_questions = [
        valid
        for q in questions
        if isinstance(q, dict) and (valid := _validate_question(q)) is not None
    ]
    dropped = len(questions) - len(valid_questions)
    if dropped:
        # Visibility into whether a low final count is the model
        # under-generating vs. this validation step rejecting malformed
        # ones (e.g. answer not matching any option) — without this, both
        # look identical from the outside.
        logger.warning(
            "Quiz validation dropped %d of %d proposed questions (malformed "
            "options or unmatched answer)", dropped, len(questions)
        )
    return valid_questions


async def generate_quiz(
    text: str, difficulty: str = DEFAULT_DIFFICULTY, language: str = DEFAULT_LANGUAGE
) -> list[dict[str, Any]]:
    if len(text) > MAX_SOURCE_CHARS:
        raise ValueError(
            f"This document is too long to generate a quiz from in one "
            f"pass ({len(text):,} characters extracted, limit is "
            f"{MAX_SOURCE_CHARS:,}). Try a shorter document, or split it "
            f"into parts and upload them separately."
        )
    difficulty_note = DIFFICULTY_INSTRUCTIONS.get(
        difficulty, DIFFICULTY_INSTRUCTIONS[DEFAULT_DIFFICULTY]
    )
    prompt = f"""\
Turn the following source material into a multiple-choice practice quiz.
Read and understand the ENTIRE document below, start to finish — it may be
long (tens or hundreds of pages), that's expected.

The number of questions must scale with the source's actual length and
density, not settle at a comfortable round number regardless of size. A
10-page handout might only support 8-10 questions; a 100+ page document
covers far more ground than that and should produce correspondingly more
— often 40, 60, even more, one for roughly every distinct fact or concept
the source spends real time on. If you notice yourself stopping at a
modest count (10-15) for a genuinely long, dense source, that is a sign
you stopped covering it early, not a sign the material ran out — go back
through the rest of the document and keep testing what it actually
covers. A longer source producing FEWER questions than a shorter one is
always wrong.

Difficulty level: {difficulty}
Difficulty guidelines: {difficulty_note}

SOURCE MATERIAL:
---
{text}
---

{JSON_SHAPE_INSTRUCTIONS}"""
    content = await llm.generate_json(
        prompt,
        system=quiz_system(language),
        temperature=0.4,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_seconds=GENERATION_TIMEOUT_SECONDS,
    )
    return _validate_questions(content)


def _normalize_question_text(question: str) -> str:
    return " ".join(question.split()).casefold()


def _drop_duplicates(
    new_questions: list[dict[str, Any]], existing_questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The "avoid duplicates" prompt instruction is not a guarantee — LLMs
    aren't perfect at scanning a growing existing-questions list and never
    repeating. This is a cheap backstop, not a full semantic check: it only
    catches near-verbatim repeats (same wording, different whitespace/case),
    not genuinely reworded duplicates. Good enough to filter the common
    "model regenerated the same question" failure mode for free."""
    seen = {_normalize_question_text(q["question"]) for q in existing_questions}
    kept = []
    for q in new_questions:
        key = _normalize_question_text(q["question"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(q)
    return kept


async def generate_more(
    source_text: str,
    existing_questions: list[dict[str, Any]],
    difficulty: str = DEFAULT_DIFFICULTY,
    language: str = DEFAULT_LANGUAGE,
) -> list[dict[str, Any]]:
    """Tops up an existing quiz with more questions from the same source,
    avoiding repeats of what's already there. Unlike generate_quiz, an
    empty result here is a normal, expected outcome (the source has been
    thoroughly covered already), not a failure."""
    remaining_capacity = MAX_QUESTIONS_PER_QUIZ - len(existing_questions)
    batch_size = max(0, min(GENERATE_MORE_BATCH_SIZE, remaining_capacity))
    if batch_size == 0:
        return []
    difficulty_note = DIFFICULTY_INSTRUCTIONS.get(
        difficulty, DIFFICULTY_INSTRUCTIONS[DEFAULT_DIFFICULTY]
    )
    existing_list = "\n".join(f"- {q['question']}" for q in existing_questions) or "(none yet)"
    prompt = f"""\
Generate up to {batch_size} MORE multiple-choice questions from the same
source material below — this quiz already has questions, listed further
down, and these new ones must test material those don't already cover.

Difficulty level: {difficulty}
Difficulty guidelines: {difficulty_note}

SOURCE MATERIAL:
---
{source_text}
---

QUESTIONS ALREADY IN THIS QUIZ (do not repeat or reword any of these):
---
{existing_list}
---

{MORE_QUESTIONS_SHAPE_INSTRUCTIONS}"""
    content = await llm.generate_json(
        prompt,
        system=quiz_system(language),
        temperature=0.4,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_seconds=GENERATION_TIMEOUT_SECONDS,
    )
    validated = _validate_questions(content)
    return _drop_duplicates(validated, existing_questions)


async def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Turns a recording into a plain-text transcript — deliberately plain
    text, not JSON, even though every other generation in this module
    returns JSON. A full lecture transcript can be tens of thousands of
    characters; every JSON-parsing failure mode already fought in this
    codebase (un-doubled backslashes, unescaped quotes, trailing commas)
    only gets riskier the larger and more free-form the string content is.
    Plain text sidesteps all of it. The returned transcript then flows into
    generate_quiz()/generate_more() exactly like PDF/PPTX-extracted text —
    from that point on, nothing downstream needs to know or care that the
    original source was audio."""
    file_uri = await llm.upload_file(audio_bytes, mime_type, display_name="quiz-audio")
    prompt = """\
Transcribe the ENTIRE attached recording, start to finish, as completely
and accurately as you can — this may be a full lecture or class
recording, potentially an hour or more, not a short clip. Produce a
faithful, complete transcript of everything said, in whatever language it
was actually spoken in — do not translate it. Lightly clean up filler
words, false starts, and stutters for readability, but do not summarize,
condense, or skip any portion: every topic, explanation, and example
discussed anywhere in the recording must be captured, not just the
highlights. Output the transcript as plain text only — no commentary, no
headers, no markdown formatting, just the transcript itself."""
    return await llm.generate(
        prompt,
        file_ref=(file_uri, mime_type),
        max_output_tokens=TRANSCRIPTION_MAX_OUTPUT_TOKENS,
        timeout_seconds=TRANSCRIPTION_TIMEOUT_SECONDS,
    )
