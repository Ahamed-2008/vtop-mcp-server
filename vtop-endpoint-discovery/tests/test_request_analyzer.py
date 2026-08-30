from __future__ import annotations

from datetime import datetime, timezone
from vtop_discovery.analysis.request_analyzer import (
    analyze_request_parameters,
    infer_parameter_schema,
)
from vtop_discovery.storage.models import Endpoint, EndpointRequest


def test_infer_parameter_schema_types():
    csrf = infer_parameter_schema("_csrf", "abc123token")
    assert csrf.type == "csrf_token"
    assert csrf.dynamic is True

    ts = infer_parameter_schema("x", "1710000000")
    assert ts.type == "timestamp"
    assert ts.dynamic is True

    student_id = infer_parameter_schema("authorizedID", "21BCE1234")
    assert student_id.type == "student_id"
    assert student_id.dynamic is False

    sem = infer_parameter_schema("semesterSubId", "WIN2026")
    assert sem.type == "semester_id"
    assert sem.dynamic is False

    course = infer_parameter_schema("courseId", "CSE1001")
    assert course.type == "course_id"
    assert course.dynamic is False

    flag = infer_parameter_schema("isActive", "true")
    assert flag.type == "boolean"


def test_analyze_request_parameters_endpoint():
    now = datetime.now(timezone.utc)
    ep = Endpoint(
        method="POST",
        path="/vtop/processAttendance",
        first_seen=now,
        last_seen=now,
        request=EndpointRequest(
            query={"_csrf": "tok123", "x": "1710000000"},
            body={"authorizedID": "21BCE0001", "semesterSubId": "WIN2026"},
        ),
    )
    analyze_request_parameters(ep)

    assert "_csrf" in ep.request.parameters
    assert ep.request.parameters["_csrf"].type == "csrf_token"
    assert ep.request.parameters["_csrf"].dynamic is True

    assert "authorizedID" in ep.request.parameters
    assert ep.request.parameters["authorizedID"].type == "student_id"
    assert ep.request.parameters["authorizedID"].dynamic is False

    assert "semesterSubId" in ep.request.parameters
    assert ep.request.parameters["semesterSubId"].type == "semester_id"
