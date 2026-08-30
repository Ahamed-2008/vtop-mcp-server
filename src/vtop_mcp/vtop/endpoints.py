"""Single source of truth for VTOP HTTP endpoints used by the server.

The tool → endpoint → parser mapping documented in ``docs/vtop-endpoints.md``
references these route definitions. Endpoint paths are relative to the
configured ``VTOP_BASE_URL``.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class Method(str, Enum):
    GET = "GET"
    POST = "POST"


class Endpoint(NamedTuple):
    name: str
    method: Method
    path: str
    purpose: str
    requires_auth: bool


# --- Authentication / session establishment ---------------------------------
OPEN_PAGE = Endpoint("open_page", Method.GET, "/vtop/open/page", "Initial VTOP authentication portal.", False)
PRELOGIN_SETUP = Endpoint("prelogin_setup", Method.POST, "/vtop/prelogin/setup", "Initialize auth environment + CSRF state.", False)
INIT_PAGE = Endpoint("init_page", Method.GET, "/vtop/init/page", "Post-login redirect initialization.", False)
LOGIN_GET = Endpoint("login_page", Method.GET, "/vtop/login", "Render username/password/CAPTCHA login form.", False)
LOGIN_POST = Endpoint("login", Method.POST, "/vtop/login", "Authenticate with credentials + manual CAPTCHA.", False)
MAIN_PAGE = Endpoint("main_page", Method.GET, "/vtop/main/page", "Load authenticated application frame.", True)
OPEN = Endpoint("open", Method.GET, "/vtop/open", "Navigates to the authenticated workspace container.", True)
CONTENT = Endpoint("content", Method.GET, "/vtop/content", "Loads authenticated dashboard; exposes authorizedID + csrf tokens.", True)

# --- Authenticated read-only data -------------------------------------------
CGPA_CREDITS = Endpoint(
    "cgpa_credits",
    Method.POST,
    "/vtop/get/dashboard/current/cgpa/credits",
    "Current CGPA / earned credits summary.",
    True,
)
COURSE_DETAILS = Endpoint(
    "course_details",
    Method.POST,
    "/vtop/get/dashboard/current/semester/course/details",
    "Current semester course registration + attendance/remarks.",
    True,
)
ASSIGNMENTS = Endpoint(
    "assignments",
    Method.POST,
    "/vtop/get/upcoming/digital/assignments",
    "Upcoming digital assignments.",
    True,
)
EVENTS = Endpoint("events", Method.POST, "/vtop/get/scheduled/events", "Scheduled events.", True)
FEEDBACKS = Endpoint("feedbacks", Method.POST, "/vtop/get/last/five/feedbacks", "Last five feedback entries.", True)
PROCTOR_MESSAGE = Endpoint(
    "proctor_message",
    Method.POST,
    "/vtop/get/dashboard/proctor/message",
    "Dashboard proctor message.",
    True,
)

# --- Support endpoints -------------------------------------------------------
CHECK_USERNAME = Endpoint(
    "check_username",
    Method.POST,
    "/vtop/login/checkusername",
    "Session/username validation.",
    True,
)
PASSED_OUT_INFO = Endpoint(
    "passed_out_info",
    Method.POST,
    "/vtop/admissions/doGetPassedOutInformationMandatory",
    "Passed-out information/status check.",
    True,
)

DATA_ENDPOINTS: tuple[Endpoint, ...] = (
    CGPA_CREDITS,
    COURSE_DETAILS,
    ASSIGNMENTS,
    EVENTS,
    FEEDBACKS,
    PROCTOR_MESSAGE,
)

AUTH_FLOW: tuple[Endpoint, ...] = (
    OPEN_PAGE,
    PRELOGIN_SETUP,
    INIT_PAGE,
    LOGIN_GET,
    LOGIN_POST,
    MAIN_PAGE,
    OPEN,
    CONTENT,
)

__all__ = [
    "Method",
    "Endpoint",
    "OPEN_PAGE",
    "PRELOGIN_SETUP",
    "INIT_PAGE",
    "LOGIN_GET",
    "LOGIN_POST",
    "MAIN_PAGE",
    "OPEN",
    "CONTENT",
    "CGPA_CREDITS",
    "COURSE_DETAILS",
    "ASSIGNMENTS",
    "EVENTS",
    "FEEDBACKS",
    "PROCTOR_MESSAGE",
    "CHECK_USERNAME",
    "PASSED_OUT_INFO",
    "DATA_ENDPOINTS",
    "AUTH_FLOW",
]