"""Feedback model derived from the "last five feedbacks" response.

Real response shape (``tests/fixtures/feedback.html``):
* table columns: #, Feedback, Category, Status ("Completed"/"Not Completed").
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Feedback(BaseModel):
    """One feedback entry."""

    feedback: Optional[str] = Field(None, description="Feedback description shown by VTOP.")
    category: Optional[str] = Field(None, description="Feedback category, e.g. General.")
    status: Optional[str] = Field(None, description="Completed / Not Completed.")


class FeedbackList(BaseModel):
    feedbacks: list[Feedback] = Field(default_factory=list)