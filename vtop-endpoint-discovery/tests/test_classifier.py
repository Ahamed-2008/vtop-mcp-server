from __future__ import annotations

from datetime import datetime, timezone
from vtop_discovery.analysis.classifier import classify_endpoint
from vtop_discovery.storage.models import (
    Endpoint,
    EndpointRequest,
    EndpointResponse,
    ParameterSchema,
    ResponseAnalysis,
)


def _make_ep(path: str, method: str = "POST", params: dict = None, analysis: ResponseAnalysis = None, guided: str = "unknown") -> Endpoint:
    now = datetime.now(timezone.utc)
    return Endpoint(
        method=method,
        path=path,
        purpose=guided,
        first_seen=now,
        last_seen=now,
        request=EndpointRequest(parameters=params or {}),
        response=EndpointResponse(status=200, analysis=analysis),
    )


def test_classify_known_auth_and_nav_endpoints():
    login_get = _make_ep("/vtop/login", method="GET")
    classify_endpoint(login_get)
    assert login_get.category == "authentication"
    assert login_get.purpose == "login_page"
    assert login_get.confidence >= 0.95

    login_post = _make_ep("/vtop/login", method="POST")
    classify_endpoint(login_post)
    assert login_post.category == "authentication"
    assert login_post.purpose == "login"
    assert login_post.confidence >= 0.95

    open_page_ep = _make_ep("/vtop/open/page", method="GET")
    classify_endpoint(open_page_ep)
    assert open_page_ep.category == "authentication"
    assert open_page_ep.purpose == "authentication_entry"

    content_ep = _make_ep("/vtop/content", method="GET")
    classify_endpoint(content_ep)
    assert content_ep.category == "navigation"
    assert content_ep.purpose == "authenticated_content"


def test_single_evidence_heuristic():
    ep = _make_ep("/vtop/customAttendQuery", method="POST")
    classify_endpoint(ep)

    assert ep.category == "data"
    assert ep.purpose == "attendance"
    assert len(ep.evidence) == 1
    assert ep.confidence <= 0.65


def test_two_independent_evidence_reaches_high_confidence():
    analysis = ResponseAnalysis(
        headings=["ATTENDANCE SUMMARY"],
        table_headers=["Course Code", "Total Classes", "Percentage"],
    )
    ep = _make_ep("/vtop/processAttendance", method="POST", analysis=analysis)
    classify_endpoint(ep)

    assert ep.category == "data"
    assert ep.purpose == "attendance"
    assert len(ep.evidence) >= 2
    assert ep.confidence >= 0.80


def test_three_evidence_signals_gives_highest_confidence():
    analysis = ResponseAnalysis(
        headings=["STUDENT MARKS DETAIL"],
        table_headers=["Course Code", "Max Mark", "Weightage", "Scored"],
    )
    params = {
        "semesterSubId": ParameterSchema(type="semester_id", dynamic=False),
        "courseId": ParameterSchema(type="course_id", dynamic=False),
    }
    ep = _make_ep("/vtop/getMarks", method="POST", params=params, analysis=analysis)
    classify_endpoint(ep)

    assert ep.category == "data"
    assert ep.purpose == "marks"
    assert len(ep.evidence) >= 3
    assert ep.confidence >= 0.90


def test_unknown_endpoint_stays_unknown():
    ep = _make_ep("/vtop/someGenericHandler", method="POST")
    classify_endpoint(ep)

    assert ep.category == "unknown"
    assert ep.purpose == "unknown"
    assert ep.confidence == 0.0
