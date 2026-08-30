"""CGPA / credit models derived from the live VTOP dashboard response.

Real response shape (``tests/fixtures/cgpa.html``):
* label/value rows: "Total Credits Required", "Earned Credits", "Current CGPA".
* VTOP currently does not return GPA or per-semester credits via this endpoint,
  so no ``gpa`` field is fabricated.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .course import Course


class CGPA(BaseModel):
    """Aggregate grade/credit state as reported by VTOP."""

    current_cgpa: Optional[float] = Field(
        None, description="The student's current cumulative CGPA as shown by VTOP."
    )
    earned_credits: Optional[float] = Field(None, description="Credits earned so far, per VTOP.")
    total_credits_required: Optional[float] = Field(
        None, description="Total credits required for the programme, per VTOP."
    )
    gpa: Optional[float] = Field(
        None,
        description="Current semester GPA. Present only if VTOP supplies it (not returned by the "
        "captured current-credits response).",
    )

    @property
    def has_data(self) -> bool:
        return any(v is not None for v in (self.current_cgpa, self.earned_credits, self.total_credits_required))


class AttendanceSummary(BaseModel):
    """A compact single-student attendance overview (derived from course rows)."""

    course_count: int = Field(default=0, description="Number of course rows returned by VTOP.")
    courses_with_attendance: int = Field(
        default=0, description="How many of those rows carry an attendance percentage."
    )
    flagged_courses: list[str] = Field(
        default_factory=list,
        description="Course codes whose attendance remark indicates caution/risk, per VTOP's own remark.",
    )


class CGPAComposite(BaseModel):
    """Aggregated academic summary combining CGPA and course data.

    Only fields VTOP actually provides are populated.
    """

    cgpa: Optional[float] = None
    earned_credits: Optional[float] = None
    total_credits_required: Optional[float] = None
    courses: list[Course] = Field(default_factory=list)
    semester: Optional[str] = None
    summary: Optional[AttendanceSummary] = None


CGPAComposite.model_rebuild()