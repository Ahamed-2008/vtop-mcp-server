"""Assignment model derived from the upcoming digital assignments response.

Real response shape (``tests/fixtures/assignments.html``):
* table columns: #, Course Name, Title, Last Date, Uploaded
* note: VTOP's HTML for this endpoint is slightly malformed (a stray ``<<td``
  opens the date cell), so the parser uses a strict table/row/column walk and
  tolerates the malformation instead of relying on well-formed markup.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Assignment(BaseModel):
    """One upcoming digital assignment."""

    course_name: Optional[str] = Field(None, description="Course the assignment belongs to.")
    title: Optional[str] = Field(None, description="Assignment title shown by VTOP.")
    last_date: Optional[str] = Field(None, description="Due/last date as printed by VTOP (DD-MM-YYYY).")
    uploaded: Optional[str] = Field(None, description="Upload indicator if VTOP provides one.")


class AssignmentList(BaseModel):
    assignments: list[Assignment] = Field(default_factory=list)