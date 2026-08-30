"""Attendance model (re-exported from :mod:`models.course`).

Kept as its own module to match the documented model layout. The course-level
:class:`Attendance` carries only what VTOP reports: percentage + remark.
"""

from .course import Attendance

__all__ = ["Attendance"]