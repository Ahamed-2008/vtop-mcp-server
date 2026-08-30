"""Assignments parser — maps the upcoming digital assignments response.

VTOP's markup here is malformed (a stray ``<<td`` opens the date cell), so the
parser ignores the exact column layout and instead identifies the assignment
date by its DD-MM-YYYY shape within each row's text. Tests run against the
real sanitized fixture (``tests/fixtures/assignments.html``).
"""

from __future__ import annotations

import re

from ...models import Assignment, AssignmentList
from .base import BaseParser

_DATE_RE = re.compile(r"(\d{2}-\d{2}-\d{4})")


class AssignmentParser(BaseParser[AssignmentList]):
    model = AssignmentList

    def _parse(self) -> AssignmentList:
        assignments: list[Assignment] = []
        table = self.soup.find("table")
        if table is None:
            return AssignmentList(assignments=[])  # "no assignments" renders empty

        body = table.find("tbody")
        if body is None:
            return AssignmentList(assignments=[])

        for row in body.find_all("tr", recursive=False):
            cells = row.find_all(["th", "td"], recursive=False)
            if not cells:
                continue

            # Course name + title are the first two data cells after the # cell.
            texts = [self._cell_text(c) for c in cells]
            course = texts[1] if len(texts) > 1 else None
            title = texts[2] if len(texts) > 2 else None
            if not (course or title):
                continue

            # Find any date-shaped cell text; treat the rest as upload/extra.
            date: str | None = None
            uploaded: str | None = None
            for t in texts[3:]:
                m = _DATE_RE.search(t)
                if m:
                    date = m.group(1)
                elif t and not t.startswith("#"):
                    uploaded = t

            assignments.append(
                Assignment(
                    course_name=course or None,
                    title=title or None,
                    last_date=date,
                    uploaded=uploaded,
                )
            )

        return AssignmentList(assignments=assignments)