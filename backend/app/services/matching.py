"""Match fetched jobs against user search preferences.

Pure functions — no I/O — so this is trivially unit-testable. At student
scale (thousands of prefs × dozens of new jobs per cycle) plain Python is
fine; past that, move to Postgres full-text search.
"""
from app.models import Job, SearchPreference


def _contains_any(haystack: str, needles: list[str]) -> bool:
    return any(n.lower() in haystack for n in needles)


def _contains_all(haystack: str, needles: list[str]) -> bool:
    return all(n.lower() in haystack for n in needles)


def job_matches_preference(job: Job, pref: SearchPreference) -> bool:
    full_text = f"{job.title} {job.company or ''} {job.description or ''}".lower()
    location = (job.location or "").lower()

    if pref.exclude_keywords and _contains_any(full_text, pref.exclude_keywords):
        return False
    # Title keywords match against title OR description: many relevant
    # postings have vague titles ("Software Engineer 2026 Program") and only
    # say "student" in the body. exclude_keywords is the noise valve.
    if pref.title_keywords and not _contains_any(full_text, pref.title_keywords):
        return False
    if pref.must_have_keywords and not _contains_all(full_text, pref.must_have_keywords):
        return False
    if pref.locations:
        location_ok = _contains_any(location, pref.locations)
        remote_ok = pref.remote_ok and job.is_remote
        if not (location_ok or remote_ok):
            return False
    return True
