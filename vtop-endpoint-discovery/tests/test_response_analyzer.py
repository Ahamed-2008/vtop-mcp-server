from __future__ import annotations

from datetime import datetime, timezone
from vtop_discovery.analysis.response_analyzer import (
    analyze_response,
    parse_html_response,
    parse_json_response,
)
from vtop_discovery.storage.models import Endpoint, EndpointResponse


def test_parse_html_response():
    html = """
    <!DOCTYPE html>
    <html>
      <head><title>VTOP - Student Attendance</title></head>
      <body>
        <h1>ATTENDANCE SUMMARY</h1>
        <h2>Winter Semester 2026</h2>
        <form>
          <input type="hidden" name="_csrf" value="tok" />
          <select name="semesterSubId"><option>WIN2026</option></select>
        </form>
        <table>
          <thead>
            <tr>
              <th>Course Code</th>
              <th>Course Title</th>
              <th>Total Classes</th>
              <th>Attended</th>
              <th>Percentage</th>
            </tr>
          </thead>
        </table>
      </body>
    </html>
    """
    analysis = parse_html_response(html)

    assert analysis.title == "VTOP - Student Attendance"
    assert "ATTENDANCE SUMMARY" in analysis.headings
    assert "Winter Semester 2026" in analysis.headings
    assert "Course Code" in analysis.table_headers
    assert "Percentage" in analysis.table_headers
    assert "_csrf" in analysis.form_fields
    assert "semesterSubId" in analysis.form_fields
    assert "attendance" in analysis.keywords


def test_parse_json_response():
    data = {
        "status": "SUCCESS",
        "attendanceList": [{"course": "CSE1001", "percent": 90}],
    }
    analysis = parse_json_response(data)
    assert "status" in analysis.data_keys
    assert "attendanceList" in analysis.data_keys
    assert "attendance" in analysis.keywords


def test_analyze_response_endpoint():
    now = datetime.now(timezone.utc)
    ep = Endpoint(
        method="POST",
        path="/vtop/processAttendance",
        first_seen=now,
        last_seen=now,
        response=EndpointResponse(
            status=200,
            content_type="text/html",
            body="<html><title>Marks View</title><h1>STUDENT MARKS</h1><th>Cat 1</th></html>",
        ),
    )
    analyze_response(ep)

    assert ep.response.analysis is not None
    assert ep.response.analysis.title == "Marks View"
    assert "STUDENT MARKS" in ep.response.analysis.headings
    assert "Cat 1" in ep.response.analysis.table_headers
    assert "marks" in ep.response.analysis.keywords
