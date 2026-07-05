"""Job-board source adapters.

Each adapter implements JobSource (base.py). To add a board, drop a new
module here and include it in get_active_sources() — the worker iterates
that list and nothing else changes.
"""
from app.core.config import get_settings
from app.services.job_sources.base import FetchedJob, JobSource
from app.services.job_sources.brightdata import BrightDataLinkedInSource
from app.services.job_sources.remotive import RemotiveSource


def get_active_sources() -> list[JobSource]:
    """Bright Data (LinkedIn student jobs) when configured; otherwise fall
    back to Remotive, which needs no key — useful for local development."""
    if get_settings().brightdata_api_key:
        return [BrightDataLinkedInSource()]
    return [RemotiveSource()]


__all__ = ["FetchedJob", "JobSource", "get_active_sources"]
