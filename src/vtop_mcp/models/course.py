"""Course / attendance models derived from the course-details response.

Real response shape (``tests/fixtures/courses.html``):
* header: current semester label (e.g. "FALLSEM2026-27")
* table rows: Code - Course Name, Type (LO/ELA/ETH/TH/SS ...), Attendance
  (a single percentage), Remarks (VTOP's own text such as "Excellent - Keep
  going", "Good", "Be cautious").

VTOP does not expose raw present/total class counts in this response, so the
attendance model carries only the percentage and remark VTOP already computed.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Attendance(BaseModel):
    """Attendance state for one course row, exactly as VTOP reports it."""

    percentage: Optional[float] = Field(
        None, description="Attendance percentage as shown by VTOP (do not re-derive)."
    )
    remark: Optional[str] = Field(None, description="VTOP's remark for this attendance level.")


class Course(BaseModel):
    """One current-semester course row returned by VTOP."""

    course_code: Optional[str] = Field(None, description="VTOP course code (e.g. BACSE102).")
    course_name: Optional[str] = Field(None, description="VTOP course title.")
    course_type: Optional[str] = Field(
        None, description="Course type label shown by VTOP (LO/ELA/ETH/TH/SS ...)."
    )
    attendance: Optional[Attendance] = Field(None, description="Attendance percentage + remark if provided.")

    @property
    def display_name(self) -> str:
        if self.course_code and self.course_name:
            return f"{self.course_code} - {self.course_name}"
        return self.course_code or self.course_name or ""


class CourseList(BaseModel):
    """Wrapper for the course-details response."""

    semester: Optional[str] = Field(None, description="Current semester label, e.g. FALLSEM2026-27.")
    courses: list[Course] = Field(default_factory=list, description="Courses returned for the current semester.")