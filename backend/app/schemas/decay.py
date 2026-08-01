"""Pydantic DTO for the manual decay-trigger response (`POST /admin/decay-now`)."""

from pydantic import BaseModel


class DecaySummary(BaseModel):
    """Summary of one time-based risk-decay pass.

    Same shape returned by both the manual trigger endpoint and logged (at
    INFO level) by the scheduled job — see app/scoring/decay_job.py.
    """

    profiles_processed: int
    profiles_decayed: int
    total_score_removed: float
