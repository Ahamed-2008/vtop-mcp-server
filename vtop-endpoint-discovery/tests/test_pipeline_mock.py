from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from vtop_discovery.main import process_pipeline
from vtop_discovery.storage.models import CapturedExchange, CapturedRequest, CapturedResponse
from vtop_discovery.storage.writer import write_catalog, write_raw_captures


def test_end_to_end_pipeline_mock(tmp_path: Path):
    t0 = datetime.now(timezone.utc)

    # 1. Synthetic Auth / Login Exchange
    ex_login = CapturedExchange(
        request=CapturedRequest(
            method="GET",
            url="https://vtop.vit.ac.in/vtop/open/page",
            path="/vtop/open/page",
            headers={"Cookie": "JSESSIONID=secret_session_123"},
            timestamp=t0,
        ),
        response=CapturedResponse(
            status=200,
            content_type="text/html",
            body="<html><title>VTOP Login</title><body>Login Form</body></html>",
        ),
    )

    # 2. Synthetic Navigation Exchange
    ex_nav = CapturedExchange(
        request=CapturedRequest(
            method="GET",
            url="https://vtop.vit.ac.in/vtop/content",
            path="/vtop/content",
            body={"view": "dashboard"},
            timestamp=t0,
        ),
        response=CapturedResponse(
            status=200,
            content_type="text/html",
            body="<html><body>Dashboard Content Area</body></html>",
        ),
    )

    # 3. Synthetic Data Exchange: Attendance with form body & query parameters
    ex_attendance = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/processAttendance",
            path="/vtop/processAttendance",
            query={"_csrf": "csrf_token_secret_999", "x": "1710000000"},
            body="authorizedID=21BCE1234&semesterSubId=WIN2026&password=plaintext_secret_pw",
            headers={"Authorization": "Bearer super_secret_token", "Cookie": "session=xyz"},
            timestamp=t0,
        ),
        response=CapturedResponse(
            status=200,
            content_type="text/html",
            body="""
            <html>
                <head><title>Student Attendance</title></head>
                <body>
                    <h1>ATTENDANCE SUMMARY</h1>
                    <table>
                        <thead>
                            <tr>
                                <th>Course Code</th>
                                <th>Attended</th>
                                <th>Percentage</th>
                            </tr>
                        </thead>
                    </table>
                </body>
            </html>
            """,
        ),
        purpose="attendance",
    )

    # 4. Synthetic Noise / Static Exchange (should be filtered)
    ex_noise = CapturedExchange(
        request=CapturedRequest(
            method="GET",
            url="https://vtop.vit.ac.in/vtop/assets/style.css",
            path="/vtop/assets/style.css",
            resource_type="stylesheet",
            timestamp=t0,
        ),
        response=CapturedResponse(status=200, content_type="text/css"),
    )

    raw_exchanges = [ex_login, ex_nav, ex_attendance, ex_noise]

    # Save raw captures
    raw_file = write_raw_captures(raw_exchanges, captures_dir=tmp_path / "captures")
    assert raw_file.exists()

    # Process pipeline
    endpoints, workflows = process_pipeline(raw_exchanges)

    # Assert noise filtered
    assert len(endpoints) == 3

    # Assert endpoint classifications
    login_ep = next(ep for ep in endpoints if ep.path == "/vtop/open/page")
    assert login_ep.category == "authentication"
    assert login_ep.purpose == "authentication_entry"
    assert login_ep.classification == "AUTH"

    nav_ep = next(ep for ep in endpoints if ep.path == "/vtop/content")
    assert nav_ep.category == "navigation"
    assert nav_ep.purpose == "authenticated_content"
    assert nav_ep.classification == "NAVIGATION"

    att_ep = next(ep for ep in endpoints if ep.path == "/vtop/processattendance")
    assert att_ep.category == "data"
    assert att_ep.purpose == "attendance"
    assert att_ep.classification == "READ"
    assert att_ep.confidence >= 0.70  # Multiple signals (URL + headings + parameters + guided)
    assert len(att_ep.evidence) >= 2

    # Assert parameter schema inference & location
    assert "_csrf" in att_ep.request.parameters
    assert att_ep.request.parameters["_csrf"].type == "csrf_token"
    assert att_ep.request.parameters["_csrf"].dynamic is True
    assert att_ep.request.parameters["_csrf"].location == "query"
    assert att_ep.request.parameters["authorizedID"].type == "student_id"
    assert att_ep.request.parameters["authorizedID"].location == "form"
    assert att_ep.request.parameters["semesterSubId"].type == "semester_id"
    assert att_ep.request.parameters["semesterSubId"].location == "form"

    # Assert response analysis
    assert att_ep.response.analysis is not None
    assert "ATTENDANCE SUMMARY" in att_ep.response.analysis.headings
    assert "Percentage" in att_ep.response.analysis.table_headers

    # Write clean inventory output
    output_path = tmp_path / "output" / "endpoint_inventory.json"
    write_catalog(endpoints, output_path, workflows=workflows)
    assert output_path.exists()

    # Verify inventory structure and redaction
    inventory_data = json.loads(output_path.read_text(encoding="utf-8"))
    assert "generated_at" in inventory_data
    assert "endpoints" in inventory_data
    assert "workflows" in inventory_data

    # Verify no raw secrets or large HTML dumps leaked into clean JSON
    output_text = output_path.read_text(encoding="utf-8")
    assert "plaintext_secret_pw" not in output_text
    assert "super_secret_token" not in output_text
    assert "csrf_token_secret_999" not in output_text
    assert "secret_session_123" not in output_text
    assert "<html>" not in output_text

