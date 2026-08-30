"""Marks model.

The discovered course-details endpoint returns course registration rows with
attendance + remarks only — the sanitized capture (``tests/fixtures/
courses.html``) contains no mark or assessment-component columns. The parser
therefore reports that marks are not available from the current endpoint
rather than fabricating any assessment data.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MarksInfo(BaseModel):
    """Marks information currently attainable from the tool's VTOP source."""

    available: bool = Field(
        default=False,
        description="True when the VTOP source response contains parseable marks/component data.",
    )
    components: list[dict] = Field(
        default_factory=list,
        description="Assessment components with their marks, only when VTOP supplies them.",
    )
    note: Optional[str] = Field(
        default="The current course-details endpoint returns attendance/remarks only; "
        "no marks or assessment components are exposed in the captured response.",
        description="Human-readable statement about marks availability.",
    )