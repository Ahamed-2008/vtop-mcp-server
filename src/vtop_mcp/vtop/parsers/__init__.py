"""VTOP response parsers: raw HTML → typed models."""

from .assignments import AssignmentParser
from .cgpa import CGPAParser
from .courses import CourseParser
from .events import EventParser
from .feedback import FeedbackParser
from .proctor import ProctorParser

__all__ = [
    "CGPAParser",
    "CourseParser",
    "AssignmentParser",
    "EventParser",
    "FeedbackParser",
    "ProctorParser",
]