"""Typed data models produced by the VTOP parsers.

Field names mirror the actual structure of sanitized VTOP responses captured
from the live site (see ``tests/fixtures/*.html``). No fields are invented:
only values observed in real responses are represented.
"""

from .assignment import Assignment, AssignmentList
from .attendance import Attendance
from .cgpa import AttendanceSummary, CGPA, CGPAComposite
from .course import Course, CourseList
from .event import Event, EventDay, EventList
from .feedback import Feedback, FeedbackList
from .marks import MarksInfo
from .proctor import ProctorMessage
from .student import StudentIdentity

__all__ = [
    "Assignment",
    "AssignmentList",
    "Attendance",
    "AttendanceSummary",
    "CGPA",
    "CGPAComposite",
    "Course",
    "CourseList",
    "Event",
    "EventDay",
    "EventList",
    "Feedback",
    "FeedbackList",
    "MarksInfo",
    "ProctorMessage",
    "StudentIdentity",
]