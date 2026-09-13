"""
mcp_server.py

High-level MCP tool layer (mcp SDK 2.x ``MCPServer``, formerly FastMCP)
exposing the ``vtop_tools.py`` request layer + ``parsers.py`` as typed,
read-mostly tools.

This is the second-generation tool surface, built from the captured HAR
session, and is independent of the legacy ``src/vtop_mcp/server/mcp_server.py``
service layer. The old server still runs under ``vtop-mcp serve``; run this
one with:

    python -m mcp_server          # MCP over stdio

All tools are read-only except ``submit_leave``, which requires
``confirm=True`` before it will write a hostel leave application to VTOP.

Session: the persisted login-module session file
(``.vtop-session/session.json``, or ``$VTOP_SESSION_PATH``) is loaded once
and reused; run ``vtop-mcp login`` (or ``docker exec -it vtop-mcp vtop-mcp
login``) to (re)authenticate.
"""

from __future__ import annotations

import os
from pathlib import Path

from bs4 import BeautifulSoup
from mcp.server.mcpserver import MCPServer

import parsers
import vtop_tools

__all__ = ["mcp", "main"]

mcp = MCPServer("vtop-mcp-tools", title="VTOP Tools", version="0.1.0")


def _session_path() -> Path:
    override = os.environ.get("VTOP_SESSION_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / ".vtop-session" / "session.json"


_SESSION: vtop_tools.VtopSession | None = None


def _vtop() -> vtop_tools.VtopSession:
    global _SESSION
    if _SESSION is None:
        _SESSION = vtop_tools.VtopSession.from_stored(_session_path())
    return _SESSION


def _run(body):
    try:
        return body()
    except (FileNotFoundError, ValueError) as exc:
        message = str(exc)
        if "expired" in message.lower() or "hard max age" in message.lower():
            raise ValueError(
                "The saved VTOP session has expired. Re-run `vtop-mcp login` to authenticate."
            ) from None
        if "No stored VTOP session" in message:
            raise ValueError(
                "No saved VTOP session. Log in first: `docker exec -it vtop-mcp vtop-mcp login`."
            ) from None
        raise ValueError(f"VTOP request failed: {message}") from None


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

@mcp.tool()
def get_cgpa_credits() -> dict:
    """Current CGPA, earned credits and total credits required (read-only)."""
    def body():
        html = vtop_tools.DashboardTools(_vtop()).get_cgpa_credits()
        return parsers.parse_cgpa_credits(html)

    return _run(body)


@mcp.tool()
def get_proctor_message() -> str:
    """Latest message from the student's assigned proctor (read-only)."""
    def body():
        html = vtop_tools.DashboardTools(_vtop()).get_proctor_message()
        return " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())[:3000]

    return _run(body)


@mcp.tool()
def get_current_semester_courses() -> list:
    """Enrolled courses for the active semester shown on the dashboard (read-only)."""
    def body():
        html = vtop_tools.DashboardTools(_vtop()).get_current_semester_courses()
        return parsers.parse_dashboard_courses(html)

    return _run(body)


@mcp.tool()
def get_upcoming_assignments() -> list:
    """Upcoming digital assignments (title, course, due date) shown on the dashboard (read-only)."""
    def body():
        html = vtop_tools.DashboardTools(_vtop()).get_upcoming_digital_assignments()
        return parsers.parse_upcoming_assignments(html)

    return _run(body)


@mcp.tool()
def get_last_feedbacks() -> list:
    """Last five feedback entries shown on the dashboard (read-only)."""
    def body():
        html = vtop_tools.DashboardTools(_vtop()).get_last_five_feedbacks()
        return parsers.parse_last_feedbacks(html)

    return _run(body)


@mcp.tool()
def get_scheduled_events() -> list:
    """Upcoming campus events shown on the dashboard (read-only)."""
    def body():
        html = vtop_tools.DashboardTools(_vtop()).get_scheduled_events()
        return parsers.parse_scheduled_events(html)

    return _run(body)



# ---------------------------------------------------------------------------
# academics
# ---------------------------------------------------------------------------

@mcp.tool()
def get_timetable(semester_sub_id: str | None = None) -> dict:
    """Registered courses and the weekly class grid for a semester.

    Omit semester_sub_id to use the current semester automatically.
    Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_timetable(semester_sub_id)
        return parsers.parse_timetable(html)

    return _run(body)


@mcp.tool()
def get_attendance(semester_sub_id: str | None = None) -> list:
    """Per-course attendance for a semester.

    Omit semester_sub_id to use the current semester automatically.
    Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_attendance(semester_sub_id)
        return parsers.parse_attendance(html)

    return _run(body)


@mcp.tool()
def get_curriculum() -> str:
    """Curriculum overview for the student's programme. Returns raw structured text.
    Use the returned category links to call get_curriculum_category. Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_curriculum()
        return " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())[:5000]

    return _run(body)


@mcp.tool()
def get_curriculum_category(category_id: str) -> list:
    """Course list for a single curriculum category (e.g. 'NC', 'PC').

    category_id comes from the links in get_curriculum(). Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_curriculum_category(category_id)
        return parsers.parse_generic_table(html)

    return _run(body)


@mcp.tool()
def get_course_page() -> list:
    """Consolidated course page — list of enrolled courses with outcome/learning objectives.
    Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_course_page()
        return parsers.parse_generic_table(html)

    return _run(body)


@mcp.tool()
def get_course_detail(semester: str, course_id: str, course_type: str) -> dict:
    """Outcome descriptions and module-level topic breakdown for one course.

    semester, course_id (e.g. 'VL_BACSE102_00100') and course_type (e.g. 'LO')
    come from the rows of get_course_page(). Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_course_detail(semester, course_id, course_type)
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        return {
            "outcomes": parsers.parse_generic_table(str(tables[0])) if len(tables) > 0 else [],
            "modules": parsers.parse_generic_table(str(tables[1])) if len(tables) > 1 else [],
        }

    return _run(body)


@mcp.tool()
def get_academic_calendar(sem_sub_id: str, cal_date: str, class_group_id: str = "COMB") -> list:
    """Monthly academic calendar grid for a given date in a semester.

    cal_date format: 'DD-MON-YYYY' (e.g. '01-JUL-2026').
    class_group_id defaults to 'COMB' (combined). Omit to use the default.
    Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_calendar_for_date(
            cal_date, sem_sub_id, class_group_id
        )
        return parsers.parse_generic_table(html)

    return _run(body)


@mcp.tool()
def get_semester_date_range(sem_sub_id: str) -> dict:
    """Start and end dates for a given semesterSubId. Read-only."""
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_semester_date_range(
            "getDateForSemesterPreview", sem_sub_id
        )
        text = " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())
        return {"raw": text[:1000]}

    return _run(body)


@mcp.tool()
def get_biometric_info() -> str:
    """Biometric attendance module landing page text. Read-only."""
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_biometric_info()
        return " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())[:3000]

    return _run(body)


@mcp.tool()
def get_biometric_log(from_date: str) -> list:
    """Biometric attendance log entries from a given date.

    from_date format: 'DD-Mon-YYYY' (e.g. '30-Sep-2026'). Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_biometric_log(from_date)
        return parsers.parse_generic_table(html)

    return _run(body)


@mcp.tool()
def get_class_messages() -> list:
    """Class-level announcements from faculty for enrolled courses. Read-only."""
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_class_messages()
        return parsers.parse_generic_table(html)

    return _run(body)


@mcp.tool()
def get_additional_learning() -> list:
    """Additional learning credits and activities recorded for the student. Read-only."""
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_additional_learning()
        return parsers.parse_generic_table(html)

    return _run(body)


@mcp.tool()
def get_council_regulations() -> str:
    """Council regulation documents (large response). Returns plain text summary.
    Read-only.
    """
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_council_regulation()
        return " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())[:5000]

    return _run(body)


@mcp.tool()
def get_qcm_session(sem_sub_id: str) -> str:
    """Quality Circle Meeting session data for a semester. Read-only."""
    def body():
        html = vtop_tools.AcademicsTools(_vtop()).get_qcm_login("getStudentLoginForQcm", sem_sub_id)
        return " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())[:3000]

    return _run(body)



# ---------------------------------------------------------------------------
# examinations
# ---------------------------------------------------------------------------

_EXAM_MENUS = {
    "get_exam_schedule": "/vtop/examinations/StudExamSchedule",
    "get_digital_assignments": "/vtop/examinations/StudentDA",
    "get_grades": "/vtop/examinations/examGradeView/StudentGradeView",
    "get_marks": "/vtop/examinations/StudentMarkView",
}


def _semester(exam, menu_path, requested):
    if requested:
        return requested
    return vtop_tools._first_option(exam._open_menu(menu_path))


@mcp.tool()
def get_exam_schedule(semester_sub_id: str | None = None) -> list:
    """Exam schedule (dates, sessions, venue, seat) for a semester.

    Omit semester_sub_id for the current semester. Read-only.
    """
    def body():
        exam = vtop_tools.ExaminationTools(_vtop())
        sem = _semester(exam, _EXAM_MENUS["get_exam_schedule"], semester_sub_id)
        return parsers.parse_exam_schedule(exam.get_exam_schedule(sem))

    return _run(body)


@mcp.tool()
def get_digital_assignments(semester_sub_id: str | None = None) -> list:
    """Digital assignments for a semester. Read-only."""
    def body():
        exam = vtop_tools.ExaminationTools(_vtop())
        sem = _semester(exam, _EXAM_MENUS["get_digital_assignments"], semester_sub_id)
        return parsers.parse_digital_assignments(exam.get_digital_assignments(sem))

    return _run(body)


@mcp.tool()
def get_grades(semester_sub_id: str | None = None) -> list:
    """Published grades (per course) for a semester.

    The current semester usually has no grades yet, so pass an earlier
    semester_sub_id (e.g. VL20252601) or expect an empty list. Read-only.
    """
    def body():
        exam = vtop_tools.ExaminationTools(_vtop())
        sem = _semester(exam, _EXAM_MENUS["get_grades"], semester_sub_id)
        return parsers.parse_grades(exam.get_grades(sem))

    return _run(body)


@mcp.tool()
def get_marks(semester_sub_id: str | None = None) -> list:
    """Per-course marks with per-assessment breakdowns for a semester.

    Omit semester_sub_id for the current semester. Read-only.
    """
    def body():
        exam = vtop_tools.ExaminationTools(_vtop())
        sem = _semester(exam, _EXAM_MENUS["get_marks"], semester_sub_id)
        return parsers.parse_marks(exam.get_marks(sem))

    return _run(body)


# ---------------------------------------------------------------------------
# hrms directory
# ---------------------------------------------------------------------------

@mcp.tool()
def search_employee(search_term: str) -> list:
    """Search faculty by name (at least 3 characters). Returns matching
    faculty with their numeric employee id for get_employee_profile.
    Read-only.
    """
    def body():
        html = vtop_tools.DirectoryTools(_vtop()).search_employee(search_term)
        return parsers.parse_employee_search(html)

    return _run(body)


@mcp.tool()
def get_employee_profile(emp_id: str) -> dict:
    """Full faculty profile (department, school, email, cabin, office hours)
    for a numeric employee id from search_employee. Read-only.
    """
    def body():
        html = vtop_tools.DirectoryTools(_vtop()).search_employee_detail(emp_id)
        return parsers.parse_employee_detail(html)

    return _run(body)


@mcp.tool()
def get_hod_dean_details() -> dict:
    """Dean and HoD names, cabins and email addresses for the student's
    school/centre. Read-only.
    """
    def body():
        html = vtop_tools.DirectoryTools(_vtop()).get_hod_dean_details()
        return parsers.parse_hod_dean(html)

    return _run(body)


# ---------------------------------------------------------------------------
# hostel leave
# ---------------------------------------------------------------------------

@mcp.tool()
def get_leave_status() -> str:
    """Current hostel leave applications and status (read-only)."""
    def body():
        html = vtop_tools.HostelTools(_vtop()).get_leave_status()
        text = " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())
        return text[:2000]

    return _run(body)


@mcp.tool()
def submit_leave(
    leave_code: str,
    visiting_place: str,
    from_date: str,
    from_time: str,
    to_date: str,
    to_time: str,
    reason: str,
    confirm: bool = False,
) -> str:
    """Submit a hostel leave application to VTOP.

    WRITES REAL DATA — the tool refuses to run unless ``confirm=True`` is
    passed explicitly. Leave codes and allowed date/time formats come from
    the leave form (see get_leave_status / get_leave_form in the tool layer).
    Returns VTOP's raw response text.
    """
    if confirm is not True:
        raise ValueError(
            "submit_leave writes a real leave application to VTOP. "
            "Re-call with confirm=True to proceed."
        )

    def body():
        html = vtop_tools.HostelTools(_vtop()).submit_leave(
            leave_code,
            visiting_place,
            from_date,
            from_time,
            to_date,
            to_time,
            reason,
        )
        text = " ".join(BeautifulSoup(html, "lxml").get_text(" ", strip=True).split())
        return text[:2000]

    return _run(body)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()