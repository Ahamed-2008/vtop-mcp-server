from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from vtop_discovery.analysis.workflow_detector import detect_workflows
from vtop_discovery.browser.crawler import is_potentially_unsafe_action
from vtop_discovery.browser.launcher import restore_session_cookies
from vtop_discovery.storage.models import CapturedExchange, CapturedRequest, CapturedResponse


def test_workflow_dependency_detection():
    t0 = datetime.now(timezone.utc)

    # Step 1: Menu request returning select options for semesterSubId
    html_menu = """
    <html>
        <body>
            <select name="semesterSubId" id="semesterSubId">
                <option value="">Select Semester</option>
                <option value="WIN2026">Winter 2026</option>
                <option value="FALL2025">Fall 2025</option>
            </select>
        </body>
    </html>
    """
    ex_menu = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/academics/common/StudentAttendance",
            path="/vtop/academics/common/StudentAttendance",
            body="verifyMenu=true",
            timestamp=t0,
        ),
        response=CapturedResponse(
            status=200,
            content_type="text/html",
            body=html_menu,
        ),
    )

    # Step 2: Process request consuming semesterSubId
    ex_process = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/processViewStudentAttendance",
            path="/vtop/processViewStudentAttendance",
            body="semesterSubId=WIN2026&authorizedID=21BCE1234",
            timestamp=t0,
        ),
        response=CapturedResponse(
            status=200,
            content_type="text/html",
            body="<html><body>Attendance Records Table</body></html>",
        ),
    )

    workflows = detect_workflows([ex_menu, ex_process])
    assert len(workflows) == 1
    wf = workflows[0]
    assert len(wf.steps) == 2
    assert "POST_vtop_academics_common_studentattendance" in wf.steps[0]
    assert "POST_vtop_processviewstudentattendance" in wf.steps[1]
    assert len(wf.dependencies) == 1
    dep = wf.dependencies[0]
    assert dep.parameter == "semesterSubId"
    assert dep.produced_by == "POST_vtop_academics_common_studentattendance"
    assert dep.consumed_by == "POST_vtop_processviewstudentattendance"



def test_safe_write_avoidance():
    assert is_potentially_unsafe_action("Hostel Leave Application") is True
    assert is_potentially_unsafe_action("Apply Leave") is True
    assert is_potentially_unsafe_action("Submit Leave Form", href="/vtop/hostels/student/leave/3") is True
    assert is_potentially_unsafe_action("Make Fee Payment") is True
    assert is_potentially_unsafe_action("Course Registration Submit") is True
    assert is_potentially_unsafe_action("Delete Course Selection") is True

    # Read-only actions must NOT be flagged as unsafe
    assert is_potentially_unsafe_action("View Attendance") is False
    assert is_potentially_unsafe_action("Student Marks") is False
    assert is_potentially_unsafe_action("Timetable View") is False
    assert is_potentially_unsafe_action("Faculty Search") is False
    assert is_potentially_unsafe_action("Download Grade History") is False


def test_restore_session_cookies(tmp_path: Path):
    class MockContext:
        def __init__(self):
            self.cookies = []

        def add_cookies(self, cookies):
            self.cookies.extend(cookies)

    session_file = tmp_path / "session.json"
    session_data = {
        "version": 1,
        "csrf_token": "test_csrf",
        "authorized_id": "21BCE0001",
        "cookies": [
            {"name": "JSESSIONID", "value": "TEST123456", "domain": "vtop.vit.ac.in", "path": "/vtop"},
            {"name": "SERVERID", "value": "s1", "domain": "vtop.vit.ac.in", "path": "/"},
        ],
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    ctx = MockContext()
    res = restore_session_cookies(ctx, session_path=session_file)
    assert res is True
    assert len(ctx.cookies) == 2
    assert ctx.cookies[0]["name"] == "JSESSIONID"
    assert ctx.cookies[0]["value"] == "TEST123456"
