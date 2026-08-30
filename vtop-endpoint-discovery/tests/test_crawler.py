from __future__ import annotations

from unittest.mock import MagicMock
from vtop_discovery.browser.crawler import _purpose_from_label, is_logged_in


def test_purpose_from_label():
    assert _purpose_from_label("Student Attendance Detail") == "attendance"
    assert _purpose_from_label("Exam Marks & Grades") == "marks"
    assert _purpose_from_label("Class Timetable View") == "timetable"
    assert _purpose_from_label("Course Registration 2026") == "courses"
    assert _purpose_from_label("Student Profile") == "profile"
    assert _purpose_from_label("Examination Schedule") == "examinations"
    assert _purpose_from_label("General Info Page") == "general_info_page"


def test_is_logged_in():
    page_logged_out = MagicMock()
    page_logged_out.url = "https://vtop.vit.ac.in/vtop/open/page"
    page_logged_out.locator.return_value.count.return_value = 0
    assert not is_logged_in(page_logged_out)

    page_logged_in = MagicMock()
    page_logged_in.url = "https://vtop.vit.ac.in/vtop/content/main"
    locator_mock = MagicMock()
    locator_mock.count.return_value = 1
    page_logged_in.locator.return_value = locator_mock
    assert is_logged_in(page_logged_in)
