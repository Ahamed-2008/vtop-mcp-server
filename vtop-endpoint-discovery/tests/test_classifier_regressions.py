from __future__ import annotations

from datetime import datetime, timezone
from vtop_discovery.analysis.classifier import classify_endpoint
from vtop_discovery.analysis.request_analyzer import infer_parameter_schema
from vtop_discovery.analysis.response_analyzer import analyze_response, parse_html_response
from vtop_discovery.storage.models import (
    Endpoint,
    EndpointRequest,
    EndpointResponse,
    ResponseAnalysis,
)
from vtop_discovery.storage.writer import _clean_endpoint_for_export
from vtop_discovery.utils.redaction import redact_payload


def _make_ep(path: str, method: str = "POST", status: int = 200, content_type: str = "text/html;charset=UTF-8", body: str = None, resp_analysis: ResponseAnalysis = None) -> Endpoint:
    now = datetime.now(timezone.utc)
    return Endpoint(
        method=method,
        path=path,
        first_seen=now,
        last_seen=now,
        request=EndpointRequest(
            headers={
                "User-Agent": "Mozilla/5.0",
                "sec-ch-ua": '"Chromium";v="123"',
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            },
            body={
                "_csrf": "[REDACTED]",
                "password": "[REDACTED]",
                "authorizedID": "[REDACTED]",
            }
        ),
        response=EndpointResponse(
            status=status,
            content_type=content_type,
            analysis=resp_analysis,
            body=body,
        ),
    )


def test_get_authentication_page():
    ep = _make_ep("/vtop/open/page", method="GET")
    classify_endpoint(ep)
    assert ep.category == "authentication"
    assert ep.purpose == "authentication_entry"
    assert ep.confidence >= 0.95


def test_post_login():
    ep = _make_ep("/vtop/login", method="POST", status=302)
    classify_endpoint(ep)
    assert ep.category == "authentication"
    assert ep.purpose == "login"
    assert ep.confidence >= 0.95


def test_parameter_detection_csrf_and_studentid_and_credentials():
    csrf_schema = infer_parameter_schema("_csrf", "abc123token")
    assert csrf_schema.type == "csrf_token"
    assert csrf_schema.dynamic is True
    assert csrf_schema.required is True

    student_id_schema = infer_parameter_schema("authorizedID", "22BCE1234")
    assert student_id_schema.type == "student_id"
    assert student_id_schema.dynamic is False
    assert student_id_schema.required is True

    user_schema = infer_parameter_schema("username", "dhanish")
    assert user_schema.type == "username"

    pwd_schema = infer_parameter_schema("password", "secretpass")
    assert pwd_schema.type == "password"

    captcha_schema = infer_parameter_schema("captchaStr", "AB12CD")
    assert captcha_schema.type == "captcha"


def test_javascript_and_css_static_resources_with_302():
    jq_ep = _make_ep("/vtop/get/jq/js/1", method="GET", status=302, content_type="text/javascript;charset=ISO-8859-1")
    classify_endpoint(jq_ep)
    assert jq_ep.category == "static_resource"
    assert jq_ep.purpose == "jquery_script"
    assert jq_ep.confidence >= 0.95
    assert any("jQuery" in ev for ev in jq_ep.evidence)

    bs_css_ep = _make_ep("/vtop/get/bs/js/3", method="GET", status=302, content_type="text/css;charset=ISO-8859-1")
    classify_endpoint(bs_css_ep)
    assert bs_css_ep.category == "static_resource"
    assert bs_css_ep.purpose == "bootstrap_script"
    assert bs_css_ep.confidence >= 0.95

    ms_ep = _make_ep("/vtop/get/ms/js/1", method="GET", status=302, content_type="text/javascript;charset=ISO-8859-1")
    classify_endpoint(ms_ep)
    assert ms_ep.category == "static_resource"
    assert ms_ep.purpose == "microsoft_script"
    assert ms_ep.confidence >= 0.95


def test_dashboard_endpoints():
    cgpa_ep = _make_ep("/vtop/get/dashboard/current/cgpa/credits")
    classify_endpoint(cgpa_ep)
    assert cgpa_ep.category == "data"
    assert cgpa_ep.purpose == "cgpa_credits"
    assert cgpa_ep.confidence >= 0.90

    course_ep = _make_ep("/vtop/get/dashboard/current/semester/course/details")
    classify_endpoint(course_ep)
    assert course_ep.category == "data"
    assert course_ep.purpose == "course_details"
    assert course_ep.confidence >= 0.90

    assign_ep = _make_ep("/vtop/get/upcoming/digital/assignments")
    classify_endpoint(assign_ep)
    assert assign_ep.category == "data"
    assert assign_ep.purpose == "assignments"
    assert assign_ep.confidence >= 0.90

    feedback_ep = _make_ep("/vtop/get/last/five/feedbacks")
    classify_endpoint(feedback_ep)
    assert feedback_ep.category == "data"
    assert feedback_ep.purpose == "feedback"
    assert feedback_ep.confidence >= 0.90

    events_ep = _make_ep("/vtop/get/scheduled/events")
    classify_endpoint(events_ep)
    assert events_ep.category == "data"
    assert events_ep.purpose == "scheduled_events"
    assert events_ep.confidence >= 0.90

    proctor_ep = _make_ep("/vtop/get/dashboard/proctor/message")
    classify_endpoint(proctor_ep)
    assert proctor_ep.category == "data"
    assert proctor_ep.purpose == "proctor_message"
    assert proctor_ep.confidence >= 0.90


def test_missing_or_null_response_body_does_not_break():
    ep = _make_ep("/vtop/get/dashboard/current/cgpa/credits", body=None)
    analyze_response(ep)
    classify_endpoint(ep)
    assert ep.category == "data"
    assert ep.purpose == "cgpa_credits"
    assert ep.confidence >= 0.90


def test_secret_redaction():
    raw_payload = {
        "password": "MySecretPassword123!",
        "captchaStr": "G7KJ9",
        "_csrf": "f83b2a-secret-csrf",
        "normalField": "VTOP"
    }
    redacted = redact_payload(raw_payload)
    assert redacted["password"] == "[REDACTED]"
    assert redacted["captchaStr"] == "[REDACTED]"
    assert redacted["_csrf"] == "[REDACTED]"
    assert redacted["normalField"] == "VTOP"
