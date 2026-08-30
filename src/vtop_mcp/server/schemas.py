"""Tool-facing output models with explicit JSON schemas.

These wrap raw service-layer results into predictable, model-friendly shapes.
No secrets (cookies/CSRF/authorizedID) ever appear here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import AssignmentList, CGPA, CGPAComposite, CourseList, EventList, FeedbackList, MarksInfo, ProctorMessage


class AttendanceRow(BaseModel):
    course_code: str | None = Field(None, description="VTOP course code.")
    course_name: str | None = Field(None, description="VTOP course title.")
    course_type: str | None = Field(None, description="Course type label.")
    percentage: float | None = Field(None, description="Attendance percentage reported by VTOP.")
    remark: str | None = Field(None, description="VTOP attendance remark.")


class AttendanceRows(BaseModel):
    attendance: list[AttendanceRow] = Field(default_factory=list)


class SessionStatus(BaseModel):
    authenticated: bool = Field(..., description="Whether an authenticated, non-expired VTOP session exists.")
    detail: str = Field(..., description="Short human-readable explanation.")


__all__ = [
    "AttendanceRow",
    "AttendanceRows",
    "SessionStatus",
    "CGPA",
    "CGPAComposite",
    "CourseList",
    "AssignmentList",
    "EventList",
    "FeedbackList",
    "MarksInfo",
    "ProctorMessage",
]