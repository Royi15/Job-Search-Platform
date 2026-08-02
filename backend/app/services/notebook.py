"""Notebook generation: turns a source document/recording into structured
study notes. Same design rule as interview.py — the LLM only ever produces
content within a fixed JSON shape; it never decides the notebook's structure
or invents sections outside what's asked for."""
from typing import Any

from app.services import llm

# Comprehensive notes on a long document can run long — give the model
# plenty of room so the response doesn't get cut off mid-JSON, and enough
# request time to actually produce it. Raised from 32768/300s after a
# 100-page source only produced ~15 short pages — the model wasn't hitting
# the old cap (no MAX_TOKENS finishReason), it was self-limiting well below
# it, but a higher ceiling plus the strengthened prompt above gives a
# genuinely long response somewhere to land instead of a token budget that
# quietly implies "keep it moderate." Verify MAX_OUTPUT_TOKENS empirically
# against whatever model is actually configured; lower it if the API
# rejects the value. GENERATION_TIMEOUT_SECONDS must stay comfortably under
# half of the worker's job_timeout (settings.py) — one retry happens on
# timeout, so two attempts must still fit inside the job's overall ceiling.
MAX_OUTPUT_TOKENS = 65536
GENERATION_TIMEOUT_SECONDS = 420.0

# Extracted PDF/PPTX text used to be silently sliced at 200k characters —
# past that point, the model was summarizing a truncated document while the
# notebook looked complete, with no sign anything was cut off. Silent data
# loss that looks like success is worse than a loud failure: past this
# ceiling, generation refuses up front (before spending an API call) with a
# clear error instead of quietly summarizing only part of the source. This
# number is a deliberately generous, round guess at a safe fraction of the
# configured model's real context window — verify against it empirically
# and adjust if it's ever actually hit by a legitimate document.
MAX_SOURCE_CHARS = 900_000

DEFAULT_LANGUAGE = "en"


def _language_instruction(language: str) -> str:
    if language == "he":
        return (
            "\n\nWrite this notebook in Hebrew: \"title\", \"subject\", "
            "\"summary\", every page \"heading\", and all \"text\"/\"bullets\"/"
            "\"table\"/key_terms content must be in Hebrew. Keep mathematical "
            "notation in LaTeX exactly as instructed below (math notation is "
            "never translated), and keep technical terms, formulas, code, and "
            "field-specific terminology that a Hebrew-speaking student would "
            "naturally leave in English (e.g. \"API\", \"gradient descent\") "
            "in English — mix the two languages the way a real Hebrew "
            "student's notes actually do, don't force-translate jargon into "
            "Hebrew words nobody in the field uses. For any \"diagram\" "
            "block, prefer \"flowchart RL\" over \"flowchart LR\" so the "
            "flow direction matches Hebrew reading order (\"flowchart TD\" "
            "is still fine either way, since it has no horizontal "
            "direction)."
        )
    return ""


def notebook_system(language: str = DEFAULT_LANGUAGE) -> str:
    return f"""\
You are a professional notebook maker — the person a top student would pay
to turn their course material into the notebook they'll actually learn
from. Three things make you good at this, not just competent:

1. You mix formats freely WITHIN a page. A real page of good notes is not
   "this whole topic is bullets" or "this whole topic is prose" — it's a
   sentence or two of context, then a tight list where the content is
   genuinely a list, then maybe a table, then more prose connecting to the
   next idea. Alternating mechanically between "one page all prose, one
   page all bullets" is exactly what a bad, formulaic notebook looks like —
   avoid that pattern specifically. Decide block by block, not section by
   section.
2. You decide how content is paced across pages, the way a person
   handwriting notes naturally would — not one rigid topic per page. A
   short topic might share a page with the next one; a dense topic might
   spread across two or three pages; a worked derivation might get its own
   page because it needs the room. You are laying out an actual notebook,
   not filling in a template.
3. You SUMMARIZE — you understand each idea and re-explain it in your own
   plain words, the way a student writes after they've actually understood
   something, not the way a stenographer transcribes it. Never lift the
   source's own sentences or restate it point-by-point in the same order of
   detail; distill each idea down to what actually matters and say it
   simply. A reader should feel like someone who understood the material
   explained it to them clearly — not like they're reading a rearranged
   transcript.

The notebook must be COMPLETE in coverage — every topic, concept, and
formula the source spends real time on should be represented somewhere, so
a student never has to go back to the source to learn something it taught —
but each one gets a concise, clear explanation, not an exhaustive
blow-by-blow reproduction of every sentence and example the source used.
Completeness means nothing important is missing, not that everything is
elaborated at length. If the source is long and covers many topics, your
notebook will naturally have many pages because there's a lot of ground to
summarize — not because any single topic needs paragraphs of elaboration.
You output ONLY valid JSON in the exact shape requested — no preambles, no
markdown fences, no commentary outside the JSON.\
{_language_instruction(language)}"""

JSON_SHAPE_INSTRUCTIONS = """\
Return JSON exactly in this shape:
{
  "title": "short descriptive title for this notebook",
  "subject": "the specific academic/professional field this belongs to, e.g. Chemistry, Machine Learning, World History, Corporate Finance — pick the most specific field that actually fits",
  "paper_style": "grid or lined — which real notebook paper a student would actually pick for this subject. Use grid for anything with diagrams, matrices, graphs, chemical structures, geometry, or circuits (math, physics, chemistry, engineering, CS, statistics). Use lined for prose-heavy writing subjects with no diagrams (languages, literature, history, law, business writing).",
  "summary": "2-3 sentence overview of the material",
  "pages": [
    {
      "heading": "what this page covers",
      "icon": "one emoji that best represents THIS page's specific topic (not a generic bullet/book emoji — pick one that actually relates to the content, e.g. a flask for a chemistry page, a brain for a neuroscience page, a chart for a statistics page)",
      "blocks": [
        {"type": "text", "content": "a paragraph of real prose — context, an explanation, how this connects to the next idea"},
        {"type": "bullets", "items": ["a full, explanatory point — a sentence or two, not a fragment", "another point"]},
        {"type": "table", "headers": ["Category", "Option A", "Option B"], "rows": [["Speed", "Fast", "Slow"], ["Cost", "High", "Low"]]},
        {"type": "callout", "content": "the single most important takeaway, warning, or common mistake on this page — only when one genuinely stands out"},
        {"type": "diagram", "content": "flowchart TD\\n  A[Input] --> B{Decision}\\n  B -->|Yes| C[Outcome 1]\\n  B -->|No| D[Outcome 2]"}
      ]
    }
  ],
  "key_terms": [{"term": "...", "definition": "short definition"}]
}

Rules:
- "subject", "paper_style", and each page's "icon" drive the notebook's
  visual theme in the app — they must genuinely reflect this specific
  material, not be a generic placeholder. A notebook about polymer
  chemistry and one about neural networks should end up tagged completely
  differently; a notebook about French grammar and one about linear algebra
  must get different "paper_style" values.
- "paper_style" must be exactly "grid" or "lined" — no other value.
- A page's "blocks" array can contain any number of blocks, in any order,
  mixing "text" / "bullets" / "table" / "callout" / "diagram" freely —
  that's the whole point, use whatever sequence actually fits the content
  on that page. A page can be a single block if that's all it needs, or
  five blocks if the topic is rich. Don't settle into a repeating pattern
  (e.g. always text-then-bullets) — vary it based on the actual content,
  the way a person actually would.
  - "table" only when the material compares two or more things across
    shared attributes/categories (approaches, options, versions).
  - "bullets" for discrete points that genuinely stand alone — definitions,
    step-by-step sequences, lists of properties/rules.
  - "text" for anything that's naturally a continuous explanation —
    motivation, how a concept connects to the next, worked reasoning,
    conceptual overviews. Use this often — a notebook that's nothing but
    bullets reads like a highlight reel, not something a person wrote to
    learn from.
  - "callout" is a spotlighted box for the ONE thing on that page that
    genuinely deserves special attention — a common mistake, an
    exam-critical formula, a rule with no exceptions, a warning about a
    subtle gotcha. Use it RARELY: most pages should have zero callouts,
    and a notebook with a callout on every page has failed to actually
    prioritize anything. Never use it for a routine fact or definition
    that a bullet would handle just as well.
  - "diagram" renders a Mermaid.js flowchart and must be used ONLY when
    the content is genuinely shaped like a graph of connected
    steps/nodes — a pipeline, an algorithm's control flow, a decision
    process, a hierarchy/taxonomy. Do NOT use it for an ordinary ordered
    list of steps that "bullets" would represent just as clearly; most
    notebooks will have few or zero diagrams, and forcing one in when the
    material isn't actually relational is worse than skipping it. When
    used, "content" must be valid Mermaid flowchart syntax starting with
    "flowchart TD" (top-down) or "flowchart LR" (left-right), with lines
    joined by "\\n". Keep node labels short and simple; if a label needs
    punctuation, wrap it in quotes, e.g. A["Rate, then adjust"]. Prefer
    the basic shapes [Rectangle], {Decision}, (Rounded) and plain
    "-->"/"-->|label|" edges — nothing fancier, since it has to parse
    correctly with no chance to fix a mistake. NEVER put a literal " "
    character inside a label unless it's the pair of quotes wrapping the
    entire label — this breaks parsing instantly. This includes Hebrew
    abbreviations written with a gershayim mark (e.g. תנ"ך, רמב"ם): spell
    the word out in full instead (e.g. "תנך") rather than risk the
    gershayim being read as a stray quote.
- YOU decide the page breaks — there is no fixed mapping of topics to
  pages. Group content the way it would actually sit well on one physical
  notebook page: related short topics can share a page; a dense or long
  topic can spread across several pages. Use as many pages as the material
  needs — a short handout might need 3, a full course's worth might need
  20+. Do not compress the material down to fit a small page count, and do
  not pad it out to inflate the count either.
- Every distinct topic the source covers should show up somewhere,
  explained in your own words as a concise summary of the idea — not a
  restatement of the source's exact sentences or a reproduction of every
  supporting detail and example it used. A student should be able to study
  from this notebook alone and not miss a topic the source covered, while
  reading something noticeably shorter and easier to digest than the
  source itself.
- Write any mathematical notation in LaTeX, delimited so it can be rendered:
  inline math like "$O(n \\log n)$" or "$\\sigma^2$" within a normal sentence,
  and standalone/display formulas on their own using "$$...$$", e.g.
  "$$P(y|x) = \\frac{e^{w^Tx}}{\\sum_j e^{w_j^Tx}}$$". Use this for every
  formula, equation, or mathematical expression the source contains — don't
  describe a formula in words when you can write it in LaTeX.
- CRITICAL — this is going inside a JSON string, so every backslash in your
  LaTeX must be written as TWO backslashes. To render \\frac you must write
  \\\\frac in the JSON. To render \\sigma you must write \\\\sigma. Every
  single LaTeX command (\\alpha, \\sum, \\int, \\cdot, \\times, ...) needs
  its backslash doubled, with no exceptions — a single un-doubled backslash
  makes the entire JSON response invalid and the whole notebook fails.
- CRITICAL — if any text needs an actual double-quote character for any
  reason (quoting a term, or a Hebrew abbreviation written with a
  gershayim mark, e.g. תנ"ך, רמב"ם), you MUST escape it as \\" inside the
  JSON string. A bare, un-escaped " in the middle of a string ends that
  string early and makes the entire JSON response fail to parse — there
  is no recovery from this, unlike a missed backslash. When in doubt,
  prefer spelling the word out without the abbreviation mark instead of
  risking an unescaped quote.
- "key_terms" is optional — include it only if the material has genuine
  jargon/terminology worth a quick-reference glossary; omit it (empty list)
  otherwise.
- EVERY block object must include its "type" field, exactly as shown above
  — never drop it or shorten a block to just its content key (e.g. never
  write {"text": "..."} on its own; it must be {"type": "text", "content":
  "..."}). This applies to every single block in every page, including
  ones deep into a long response — do not let the pattern drift partway
  through; a block missing "type" cannot be shown to the student at all,
  so it isn't a shortcut, it silently deletes that block.
- Output the JSON object only, nothing else."""

_BLOCK_SHORTHAND_KEYS = {
    "text": "content",
    "content": "content",  # bare {"content": "..."} with no "type" — treat as text
    "bullets": "items",
    "items": "items",
    "callout": "content",
    "diagram": "content",
}


def _normalize_block(block: dict[str, Any]) -> dict[str, Any] | None:
    """Repairs a real failure mode seen in practice: partway into a long
    response the model drops "type" and shortens a block to just its
    content key — {"text": "..."} instead of {"type": "text", "content":
    "..."}. The frontend switches on "type" to pick a renderer, so a block
    missing it doesn't error, it just silently renders as nothing — the
    student loses that whole block with no visible sign anything's wrong.
    Recovers the block from whichever known key is present; returns None
    only if nothing recognizable is there to recover."""
    block_type = block.get("type")
    if block_type in ("text", "bullets", "table", "callout", "diagram"):
        return block
    if "headers" in block and "rows" in block:
        return {"type": "table", "headers": block["headers"], "rows": block["rows"]}
    if isinstance(block.get("table"), dict):
        table = block["table"]
        return {"type": "table", "headers": table.get("headers", []), "rows": table.get("rows", [])}
    for key, field in _BLOCK_SHORTHAND_KEYS.items():
        if key in block:
            inferred_type = "text" if key == "content" else key
            return {"type": inferred_type, field: block[key]}
    return None


def _normalize_content(content: dict[str, Any]) -> dict[str, Any]:
    for page in content.get("pages", []):
        blocks = page.get("blocks", [])
        page["blocks"] = [nb for b in blocks if (nb := _normalize_block(b)) is not None]
    return content


async def generate_from_text(text: str, language: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    if len(text) > MAX_SOURCE_CHARS:
        raise ValueError(
            f"This document is too long to summarize in one pass "
            f"({len(text):,} characters extracted, limit is "
            f"{MAX_SOURCE_CHARS:,}). Try a shorter document, or split it "
            f"into parts and upload them separately."
        )
    prompt = f"""\
Turn the following source material into a clear SUMMARY — not a condensed
copy of its sentences. Read and understand the ENTIRE document below,
start to finish — it may be long (tens of pages), that's expected — then
re-explain it in your own words, covering every topic it discusses so
nothing important is missing, but concisely per topic — without
reproducing its phrasing or every supporting detail and example verbatim.

The notebook's total length must scale with the source's length. A
notebook with only 10-15 short pages generated from a 50-100+ page source
is a sign you stopped covering it early or compressed too hard, not a sign
you wrote a good summary — that source has far more distinct topics than
10-15 pages can represent even at a concise, one-idea-per-block pace. Judge
yourself by topic coverage: if the source spends real time on 40 distinct
concepts, your notebook needs roughly that many distinct points made
somewhere across its pages, each explained briefly — not 10 concepts
described at slightly greater length.

SOURCE MATERIAL:
---
{text}
---

{JSON_SHAPE_INSTRUCTIONS}"""
    content = await llm.generate_json(
        prompt,
        system=notebook_system(language),
        temperature=0.3,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_seconds=GENERATION_TIMEOUT_SECONDS,
    )
    return _normalize_content(content)


async def generate_from_audio(
    audio_bytes: bytes, mime_type: str, language: str = DEFAULT_LANGUAGE
) -> dict[str, Any]:
    # Lecture-length recordings routinely exceed the ~20MB inline-request
    # ceiling, so audio always goes through the Files API (upload, then
    # reference by URI) rather than inline_data — one path that works for
    # both a 2MB clip and an 80MB lecture.
    file_uri = await llm.upload_file(audio_bytes, mime_type, display_name="notebook-audio")
    prompt = f"""\
Listen to the ENTIRE attached recording, start to finish — this is likely a
full lecture or class recording, potentially an hour or more, not a short
clip. Turn it into a clear SUMMARY of what was taught: every topic,
explanation, and example discussed anywhere in the recording — beginning,
middle, and end — should be represented somewhere in the notes, in the
order it was discussed, so nothing important from the lecture is missing.

But summarize it — re-explain each idea concisely in your own words, the
way a student writes notes after they've understood something, not a
transcript or a blow-by-blow account of everything said. There are two
failure modes here and both are equally wrong: (1) a brief highlight reel
that only names the general topics without actually explaining them, and
(2) an exhaustive near-transcript that restates everything said at length
without condensing it. Aim for genuine understanding, stated plainly and
briefly. A lecture-length recording will naturally produce a notebook with
several pages simply because it covers a lot of ground — not because any
single topic needs paragraphs of elaboration.

{JSON_SHAPE_INSTRUCTIONS}"""
    content = await llm.generate_json(
        prompt,
        system=notebook_system(language),
        temperature=0.3,
        file_ref=(file_uri, mime_type),
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_seconds=GENERATION_TIMEOUT_SECONDS,
    )
    return _normalize_content(content)
