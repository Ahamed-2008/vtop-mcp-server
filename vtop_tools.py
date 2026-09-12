"""
vtop_tools.py

MCP tool skeleton for the VIT VTOP student portal, derived from a captured
HAR session (82 entries). Endpoints are grouped by resource. Each data
endpoint follows a two-step pattern discovered in the capture:

    1. MENU call  -> loads a page, seeds server-side session state
                     (returns HTML containing a fresh semesterSubId /
                     categoryId embedded in a <select> or <input>)
    2. PROCESS call -> POSTs that id back to get the real data

Prerequisites
-------------
- An authenticated VTOP session (JSESSIONID cookie) obtained via the normal
  login + OTP/captcha flow. This module does not perform login; it assumes
  a valid `requests.Session` is passed in.
- A fresh `_csrf` token. VTOP re-issues this per page load, so it must be
  scraped from the last HTML response, not hardcoded.

Every method returns raw HTML (VTOP does not expose JSON). Parsing that
HTML into structured data is a separate step (see `parsers.py`, not
included here) and should not be conflated with the request layer below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


CSRF_PATTERN = re.compile(r'name="_csrf"\s+value="([^"]+)"')

# Browser-ish headers. VTOP serves HTML to browsers and can hard-fail bare
# python-requests UA strings.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class VtopSession:
    """Holds the authenticated session and rolling CSRF token.

    authorized_id is the student's registration/login ID, taken from the
    HAR capture's `authorizedID` form field. It must be set once after
    login and is reused on every subsequent call.
    """

    session: requests.Session
    base_url: str
    authorized_id: str
    csrf_token: str

    def refresh_csrf(self, html: str) -> None:
        """Update csrf_token from the most recent HTML response.

        Call this after every request. VTOP invalidates the previous
        token once a new page is rendered, so reusing a stale token
        causes the next POST to fail with a session-expired redirect.
        """
        match = CSRF_PATTERN.search(html)
        if match:
            self.csrf_token = match.group(1)

    def post(self, path: str, data: dict) -> str:
        payload = {"authorizedID": self.authorized_id, "_csrf": self.csrf_token, **data}
        resp = self.session.post(f"{self.base_url}{path}", data=payload)
        resp.raise_for_status()
        self.refresh_csrf(resp.text)
        return resp.text

    # -- wiring to the existing login module --------------------------------
    @classmethod
    def from_login_session(cls, session, base_url: str) -> VtopSession:
        """Wrap an authenticated login-module Session into a requests-backed one.

        ``session`` is a ``vtop_mcp.vtop.session.Session`` (from `vtop-mcp
        login`). Its cookie jar, rolling ``_csrf`` and ``authorizedID`` are
        copied verbatim; login itself is never performed here.
        """
        sess = requests.Session()
        sess.headers.update(_BROWSER_HEADERS)
        sess.headers["Origin"] = base_url
        for c in session.cookies or []:
            sess.cookies.set(
                c["name"],
                c["value"],
                domain=c.get("domain"),
                path=c.get("path") or "/",
            )
        return cls(
            session=sess,
            base_url=base_url,
            authorized_id=session.authorized_id,
            csrf_token=session.csrf_token,
        )

    @classmethod
    def from_stored(
        cls, path: Path | str, base_url: str | None = None
    ) -> VtopSession:
        """Load a persisted login-module session file and wrap it."""
        from vtop_mcp.vtop.session import Session

        if base_url is None:
            from vtop_mcp.config import Settings

            base_url = Settings().base_url
        stored = Session.load(Path(path))
        if stored is None:
            raise FileNotFoundError(
                f"No stored VTOP session at {path}; run `vtop-mcp login` first."
            )
        stored.enforce_hard_max_age()
        return cls.from_login_session(stored, base_url)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardTools:
    """Landing-page widgets. All single-step; no menu call required."""

    def __init__(self, vtop: VtopSession):
        self.vtop = vtop

    def get_cgpa_credits(self) -> str:
        """Current CGPA and credit summary."""
        return self.vtop.post("/vtop/get/dashboard/current/cgpa/credits", {"x": _timestamp()})

    def get_current_semester_courses(self) -> str:
        """Enrolled courses for the active semester."""
        return self.vtop.post("/vtop/get/dashboard/current/semester/course/details", {"x": _timestamp()})

    def get_proctor_message(self) -> str:
        """Latest message from the assigned proctor."""
        return self.vtop.post("/vtop/get/dashboard/proctor/message", {"x": _timestamp()})

    def get_upcoming_digital_assignments(self) -> str:
        return self.vtop.post("/vtop/get/upcoming/digital/assignments", {"x": _timestamp()})

    def get_last_five_feedbacks(self) -> str:
        return self.vtop.post("/vtop/get/last/five/feedbacks", {"x": _timestamp()})

    def get_scheduled_events(self) -> str:
        return self.vtop.post("/vtop/get/scheduled/events", {"x": _timestamp()})


# ---------------------------------------------------------------------------
# Academics
# ---------------------------------------------------------------------------

class AcademicsTools:
    """Timetable, attendance, curriculum, course pages, calendar."""

    def __init__(self, vtop: VtopSession):
        self.vtop = vtop

    def _open_menu(self, path: str) -> str:
        """Menu step shared by every page in this class."""
        return self.vtop.post(path, {"verifyMenu": "true", "nocache": _timestamp()})

    def get_timetable(self, semester_sub_id: Optional[str] = None) -> str:
        """Class timetable for one semester.

        If semester_sub_id is omitted, opens the menu page first and
        extracts the current semester's id automatically.
        """
        if semester_sub_id is None:
            menu_html = self._open_menu("/vtop/academics/common/StudentTimeTable")
            semester_sub_id = _first_option(menu_html)
        return self.vtop.post("/vtop/processViewTimeTable", {"semesterSubId": semester_sub_id, "x": _timestamp()})

    def get_attendance(self, semester_sub_id: Optional[str] = None) -> str:
        if semester_sub_id is None:
            menu_html = self._open_menu("/vtop/academics/common/StudentAttendance")
            semester_sub_id = _first_option(menu_html)
        return self.vtop.post("/vtop/processViewStudentAttendance", {"semesterSubId": semester_sub_id, "x": _timestamp()})

    def get_curriculum(self) -> str:
        return self._open_menu("/vtop/academics/common/Curriculum")

    def get_curriculum_category(self, category_id: str) -> str:
        """category_id comes from a link/button in get_curriculum()'s HTML."""
        return self.vtop.post("/vtop/academics/common/curriculumCategoryView", {"categoryId": category_id, "x": _timestamp()})

    def get_course_page(self) -> str:
        return self._open_menu("/vtop/academics/common/CoursePageConsolidated")

    def get_course_detail(self, semester: str, course_id: str, course_type: str) -> str:
        """course_id and course_type come from get_course_page()'s course list."""
        return self.vtop.post(
            "/vtop/academics/CoursePageConsolidated/getCourseDetail",
            {"semester": semester, "CourseId": course_id, "CoursType": course_type, "x": _timestamp()},
        )

    def get_calendar_preview(self) -> str:
        return self._open_menu("/vtop/academics/common/CalendarPreview")

    def get_calendar_for_date(self, cal_date: str, sem_sub_id: str, class_group_id: str) -> str:
        return self.vtop.post(
            "/vtop/processViewCalendar",
            {"calDate": cal_date, "semSubId": sem_sub_id, "classGroupId": class_group_id, "x": _timestamp()},
        )

    def get_semester_date_range(self, param_return_id: str, sem_sub_id: str) -> str:
        return self.vtop.post(
            "/vtop/getDateForSemesterPreview",
            {"paramReturnId": param_return_id, "semSubId": sem_sub_id, "x": _timestamp()},
        )

    def get_additional_learning(self) -> str:
        return self._open_menu("/vtop/academics/additionalLearning/AdditionalLearningStudentView")

    def get_council_regulation(self) -> str:
        return self._open_menu("/vtop/academics/council/CouncilRegulationView/new")

    def get_biometric_info(self) -> str:
        return self._open_menu("/vtop/academics/common/BiometricInfo")

    def get_biometric_log(self, from_date: str) -> str:
        return self.vtop.post("/vtop/getStudViewBioList", {"fromDate": from_date, "x": _timestamp()})

    def get_class_messages(self) -> str:
        return self._open_menu("/vtop/academics/common/StudentClassMessage")

    def get_qcm_login_page(self) -> str:
        return self._open_menu("/vtop/academics/common/QCMStudentLogin")

    def get_qcm_login(self, param_return_id: str, sem_sub_id: str) -> str:
        return self.vtop.post(
            "/vtop/getStudentLoginForQcm",
            {"paramReturnId": param_return_id, "semSubId": sem_sub_id, "x": _timestamp()},
        )

    def open_registration_page(self) -> str:
        """Redirects (302) in the capture — likely blocked outside the registration window."""
        return self.vtop.post("/vtop/academics/exc/studentRegistration/mandatoryPage", {"x": _timestamp()})

    def get_registration_outcome(self) -> str:
        return self._open_menu("/vtop/outcome/set/studentRegistrationPage")


# ---------------------------------------------------------------------------
# Examinations
# ---------------------------------------------------------------------------

class ExaminationTools:
    """Exam schedule, digital assignments, grades, marks.

    The `do*` endpoints in this group were captured as multipart/form-data,
    but live testing (2026-09) shows VTOP ignores multipart here (request
    hangs) and answers urlencoded instantly — so plain urlencoded POSTs are
    used below, like the rest of VTOP.
    """

    def __init__(self, vtop: VtopSession):
        self.vtop = vtop

    def _open_menu(self, path: str) -> str:
        return self.vtop.post(path, {"verifyMenu": "true", "nocache": _timestamp()})

    def _post_exam(self, path: str, semester_sub_id: str) -> str:
        return self.vtop.post(path, {"semesterSubId": semester_sub_id, "x": _timestamp()})

    def get_exam_schedule(self, semester_sub_id: str) -> str:
        self._open_menu("/vtop/examinations/StudExamSchedule")
        return self._post_exam("/vtop/examinations/doSearchExamScheduleForStudent", semester_sub_id)

    def get_digital_assignments(self, semester_sub_id: str) -> str:
        self._open_menu("/vtop/examinations/StudentDA")
        return self._post_exam("/vtop/examinations/doDigitalAssignment", semester_sub_id)

    def get_grades(self, semester_sub_id: str) -> str:
        self._open_menu("/vtop/examinations/examGradeView/StudentGradeView")
        return self._post_exam("/vtop/examinations/examGradeView/doStudentGradeView", semester_sub_id)

    def get_marks(self, semester_sub_id: str) -> str:
        self._open_menu("/vtop/examinations/StudentMarkView")
        return self._post_exam("/vtop/examinations/doStudentMarkView", semester_sub_id)


# ---------------------------------------------------------------------------
# HRMS (faculty/staff directory, as exposed to students)
# ---------------------------------------------------------------------------

class DirectoryTools:
    """Faculty/HOD/Dean lookup.

    Confirmed live against VIT Vellore (2026-09): the three employee-search
    endpoints are distinct, NOT interchangeable:
      * employeeSearchForStudent      -> renders the search form (menu step)
      * EmployeeSearchForStudent      -> search by NAME term (>=3 chars);
                                         returns a results table; each row's
                                         select button id is the numeric id
      * EmployeeSearch1ForStudent     -> full profile for one numeric id taken
                                         from a search result's button id
      * viewHodDeanDetails            -> separate: Dean/HoD names + emails
    """

    def __init__(self, vtop: VtopSession):
        self.vtop = vtop

    def open_search_page(self) -> str:
        return self.vtop.post("/vtop/hrms/employeeSearchForStudent", {"verifyMenu": "true", "nocache": _timestamp()})

    def search_employee(self, search_term: str) -> str:
        """Search faculty by NAME (>=3 chars). Returns the matching results
        table; each row has a select button whose id is the numeric employee
        id to pass to search_employee_detail(). Numeric terms return no
        records (VTOP only name-searches here).
        """
        search_term = (search_term or "").strip()
        if len(search_term) < 3:
            raise ValueError("search_term must be at least 3 characters.")
        return self.vtop.post("/vtop/hrms/EmployeeSearchForStudent", {"empId": search_term, "x": _timestamp()})

    def search_employee_detail(self, emp_id: str) -> str:
        """Full faculty profile for one numeric employee id (from a search
        result row's select-button id). Includes dept/school, email, cabin,
        and office hours.
        """
        return self.vtop.post("/vtop/hrms/EmployeeSearch1ForStudent", {"empId": emp_id, "x": _timestamp()})

    def get_hod_dean_details(self) -> str:
        return self.vtop.post("/vtop/hrms/viewHodDeanDetails", {"verifyMenu": "true", "nocache": _timestamp()})


# ---------------------------------------------------------------------------
# Hostel leave
# ---------------------------------------------------------------------------

class HostelTools:
    """Three-step leave workflow: view page -> load application form ->
    submit. Submitting writes real data to VTOP — treat get_leave_form
    and submit_leave as state-changing, not safe to retry blindly.
    """

    def __init__(self, vtop: VtopSession):
        self.vtop = vtop

    def get_leave_status(self) -> str:
        return self.vtop.post("/vtop/hostels/student/leave/1", {"verifyMenu": "true", "nocache": _timestamp()})

    def get_leave_form(self) -> str:
        return self.vtop.post("/vtop/hostels/student/leave/2", {"apply": "true", "form": "true", "control": "true", "x": _timestamp()})

    def submit_leave(self, leave_code: str, visiting_place: str, from_date: str, from_time: str, to_date: str, to_time: str, reason: str) -> str:
        """Submits a hostel leave application. State-changing — confirm
        with the user before calling this from an automated agent.
        """
        return self.vtop.post(
            "/vtop/hostels/student/leave/3",
            {
                "leaveCode": leave_code,
                "visitingPlace": visiting_place,
                "leaveFromDate": from_date,
                "fromTime": from_time,
                "leaveToDate": to_date,
                "toTime": to_time,
                "reason": reason,
                "form": "true",
                "control": "true",
                "x": _timestamp(),
            },
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    import email.utils
    import time

    return email.utils.formatdate(time.time(), usegmt=True)


def _first_option(html: str) -> str:
    """Extract the current semesterSubId from a semester dropdown.

    VTOP's academics menu pages render a single
    ``<select name="semesterSubId" id="semesterSubId">`` whose first *non-empty*
    ``<option>`` is the current semester (confirmed live against
    StudentTimeTable and StudentAttendance: VTOP lists semesters newest-first
    and the leading placeholder option has an empty value).
    """
    soup = BeautifulSoup(html, "lxml")
    select = soup.find("select", attrs={"name": "semesterSubId"})
    if select is None:
        raise ValueError(
            "No semesterSubId <select> found in menu HTML; page structure may differ from capture."
        )
    for option in select.find_all("option"):
        value = (option.get("value") or "").strip()
        if value:
            return value
    raise ValueError("The semesterSubId <select> contained no non-empty option.")