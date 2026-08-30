"""Course-details parser — produces course + attendance models.

Real response shape (``tests/fixtures/courses.html``):
* header carries the semester badge, e.g. "FALLSEM2026-27"
* one table with rows: [Code - Course Name, Type, Attendance %, Remarks]
* Attendance % and Remark are colored spans whose text carries the value.

The same parsed object feeds ``get_current_courses``, ``get_attendance`` and
``get_marks`` (marks are absent from this response).
"""

from __future__ import annotations

from typing import Optional

from ...models import Attendance, Course, CourseList
from ...errors import VTOPParseError
from .base import BaseParser


class CourseParser(BaseParser[CourseList]):
    model = CourseList

    def _parse(self) -> CourseList:
        header = self.soup.find("div", class_="card-header")
        semester: Optional[str] = None
        if header:
            # Pin to the semester badge span (e.g. FALLSEM2026-27), not the
            # "CURRENT SEMESTER COURSE REGISTRATION DETAILS" caption.
            for span in header.find_all("span"):
                classes = " ".join(span.get("class", []))
                _text = self._norm(span.get_text(" ", strip=True))
                if _text and ("bg-warning" in classes or "badge" in classes or "text-danger" in classes):
                    semester = _text
                    break
            if not semester:
                last = header.find_all("span")
                if last:
                    semester = self._norm(last[-1].get_text(" ", strip=True)) or self._norm(
                        self._cell_text(header)
                    )
                else:
                    semester = self._norm(self._cell_text(header))

        table = self.soup.find("table")
        if table is None:
            raise VTOPParseError(
                "Course-details response contained no table; VTOP may have changed "
                "layout or returned an error page."
            )

        courses: list[Course] = []
        body = table.find("tbody")
        if body is None:
            # No tbody means no rows — valid for an empty semester.
            return CourseList(semester=semester, courses=[])

        for row in body.find_all("tr", recursive=False):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) < 4:
                continue
            code_name = self._cell_text(cells[1])
            course_code, course_name = self._split_code_name(code_name)
            course_type = self._norm(self._cell_text(cells[2]))
            attendance = self._parse_attendance(cells[3], cells[4] if len(cells) > 4 else None)

            # Skip decorative/header rows embedded in tbody.
            if not course_code and not course_name and not attendance.percentage and not attendance.remark:
                continue

            courses.append(
                Course(
                    course_code=course_code,
                    course_name=course_name,
                    course_type=course_type,
                    attendance=attendance if (attendance.percentage is not None or attendance.remark) else None,
                )
            )

        return CourseList(semester=semester, courses=courses)

    @staticmethod
    def _split_code_name(text: str) -> tuple[Optional[str], Optional[str]]:
        """Split 'BACSE102 - Problem Solving using Java' into code/name."""
        if not text:
            return None, None
        if " - " in text:
            code, _, name = text.partition(" - ")
            return code.strip() or None, name.strip() or None
        return text, None

    def _parse_attendance(self, cell, remark_cell: Optional) -> Attendance:
        percentage = self._float(self._cell_text(cell))
        remark = self._norm(self._cell_text(remark_cell)) if remark_cell is not None else None
        # If the remark column is empty, try a link/title on the percentage cell.
        if percentage is None:
            p_cell = self._cell_text(cell)
            percentage = self._float(p_cell)
        return Attendance(percentage=percentage, remark=remark)