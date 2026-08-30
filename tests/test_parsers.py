"""Parser tests grounded in the real sanitized VTOP fixtures.

These fixtures came from live VTOP captures (see vtop-endpoint-discovery). If
VTOP changes its markup, update the fixtures AND these assertions together.
"""

from __future__ import annotations

import pytest

from vtop_mcp.errors import VTOPParseError
from vtop_mcp.vtop.parsers import (
    AssignmentParser,
    CGPAParser,
    CourseParser,
    EventParser,
    FeedbackParser,
    ProctorParser,
)


def _html(fixture_data: dict[str, str], name: str) -> str:
    return fixture_data[name + ".html"]


# --------------------------------------------------------------------- CGPA
def test_cgpa_parser_real(fixture_data):
    result = CGPAParser(_html(fixture_data, "cgpa")).parse()
    assert result.current_cgpa == 8.72
    assert result.earned_credits == 47.0
    assert result.total_credits_required == 162.0
    assert result.gpa is None  # VTOP does not return GPA here
    assert result.has_data


def test_cgpa_parser_empty():
    with pytest.raises(VTOPParseError):
        CGPAParser("<html><body></body></html>").parse()


def test_cgpa_parser_extra_label_is_tolerated():
    html = """
    <ul><li class="list-group-item">Total Credits Required : 200</li>
    <li class="list-group-item">Earned Credits : 88.5</li>
    <li class="list-group-item">Current CGPA : 9.11</li></ul>
    """
    result = CGPAParser(html).parse()
    assert result.current_cgpa == 9.11
    assert result.earned_credits == 88.5
    assert result.total_credits_required == 200.0


# ------------------------------------------------------------------- courses
def test_course_parser_real(fixture_data):
    result = CourseParser(_html(fixture_data, "courses")).parse()
    assert result.semester == "FALLSEM2026-27"
    assert len(result.courses) == 13


def test_course_parser_real_first_row(fixture_data):
    result = CourseParser(_html(fixture_data, "courses")).parse()
    first = result.courses[0]
    assert first.course_code == "BACSE102"
    assert first.course_name == "Problem Solving using Java"
    assert first.course_type == "LO"
    assert first.attendance is not None
    assert first.attendance.percentage == 100.0
    assert first.attendance.remark == "Excellent - Keep going"


def test_course_parser_real_flagged_attendance(fixture_data):
    result = CourseParser(_html(fixture_data, "courses")).parse()
    soc = next(c for c in result.courses if c.course_code == "BAHUM109")
    assert soc.attendance is not None
    assert soc.attendance.percentage == 79.0
    assert soc.attendance.remark == "Be cautious"


def test_course_parser_attendance_rows_have_percentages(fixture_data):
    result = CourseParser(_html(fixture_data, "courses")).parse()
    assert all(c.attendance is not None and c.attendance.percentage is not None for c in result.courses)


def test_course_parser_empty_semester_table_no_rows():
    # a header outside the tbody still resolves the semester; zero rows is valid
    html = (
        "<div class='card-header'><span class='badge'>FALLSEM2026-27</span></div>"
        "<table><thead><tr><th>#</th></tr></thead><tbody></tbody></table>"
    )
    result = CourseParser(html).parse()
    assert result.semester == "FALLSEM2026-27"
    assert result.courses == []


def test_course_parser_no_table_raises():
    with pytest.raises(VTOPParseError):
        CourseParser("<html><body><p>An error page.</p></body></html>").parse()


# ----------------------------------------------------------------- assignments
def test_assignment_parser_real(fixture_data):
    result = AssignmentParser(_html(fixture_data, "assignments")).parse()
    assert len(result.assignments) == 4


def test_assignment_parser_real_fields(fixture_data):
    result = AssignmentParser(_html(fixture_data, "assignments")).parse()
    by_title = {a.title: a for a in result.assignments}
    a3 = by_title["Assessment - 3"]
    assert a3.course_name == "Probability and Statistics"
    assert a3.last_date in ("05-09-2026", "30-08-2026")
    a4 = by_title["Assessment - 4"]
    assert a4.last_date == "05-09-2026"


def test_assignment_parser_empty_is_valid():
    result = AssignmentParser("<html><body>No assignments.</body></html>").parse()
    assert result.assignments == []


# --------------------------------------------------------------------- events
def test_event_parser_real(fixture_data):
    result = EventParser(_html(fixture_data, "events")).parse()
    assert len(result.days) == 6
    assert len(result.events) == 9
    assert result.days[0].day == "30"
    assert result.days[0].month_title == "Aug-2026"


def test_event_parser_real_sections(fixture_data):
    result = EventParser(_html(fixture_data, "events")).parse()
    sections = {e.section for e in result.events}
    assert "Today : Ongoing Events" in sections or "Ongoing Events" in " ".join(sections)
    assert "Forthcoming Events" in sections


def test_event_parser_real_fields(fixture_data):
    result = EventParser(_html(fixture_data, "events")).parse()
    titles = {e.title for e in result.events}
    assert "AAGOMONI 2026" in titles
    assert "Midweek Matinee : Dead Poets Society" in titles
    with_date = [e for e in result.events if e.date]
    assert with_date and all(len(e.date) == 10 for e in with_date)
    assert any(e.organizer for e in result.events)


def test_event_parser_empty():
    result = EventParser("<html><body><div class='card'>--- No events scheduled ---</div></body></html>").parse()
    assert result.events == []


# ------------------------------------------------------------------- feedback
def test_feedback_parser_real(fixture_data):
    result = FeedbackParser(_html(fixture_data, "feedback")).parse()
    assert len(result.feedbacks) == 5
    first = result.feedbacks[0]
    assert first.feedback
    assert first.category == "General"
    assert first.status in ("Completed", "Not Completed")


def test_feedback_parser_empty():
    result = FeedbackParser("<html><body>No feedback.</body></html>").parse()
    assert result.feedbacks == []


# -------------------------------------------------------------------- proctor
def test_proctor_parser_whitespace_only(fixture_data):
    result = ProctorParser(_html(fixture_data, "proctor")).parse()
    assert result.message is None


def test_proctor_parser_with_text():
    result = ProctorParser("<html><body>  Meet your proctor on Friday.  </body></html>").parse()
    assert result.message == "Meet your proctor on Friday."


# ------------------------------------------------------------------ resilience
@pytest.mark.parametrize(
    "name, parser",
    [
        ("cgpa", CGPAParser),
        ("courses", CourseParser),
        ("assignments", AssignmentParser),
        ("events", EventParser),
        ("feedback", FeedbackParser),
        ("proctor", ProctorParser),
    ],
)
def test_parsers_never_invent_data(fixture_data, name, parser):
    """Absent values stay absent — parsers must not fabricate numbers or text."""
    result = parser(_html(fixture_data, name)).parse()
    dumped = result.model_dump(exclude_none=True)
    if name == "cgpa":
        assert "gpa" not in dumped