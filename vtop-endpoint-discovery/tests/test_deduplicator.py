from __future__ import annotations

from datetime import datetime, timezone, timedelta
from vtop_discovery.analysis.deduplicator import compute_endpoint_signature, deduplicate
from vtop_discovery.storage.models import CapturedExchange, CapturedRequest, CapturedResponse


def test_signature_ignores_dynamic_param_values():
    t0 = datetime.now(timezone.utc)
    ex1 = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/processAttendance",
            path="/vtop/processAttendance/",
            query={"_csrf": "token_abc_123", "x": "1710000000"},
            body={"authorizedID": "21BCE0001", "semesterSubId": "WIN2026"},
            timestamp=t0,
        )
    )
    ex2 = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/processAttendance",
            path="/vtop/processAttendance",
            query={"_csrf": "token_xyz_999", "x": "1719999999"},
            body={"authorizedID": "21BCE0002", "semesterSubId": "WIN2026"},
            timestamp=t0,
        )
    )
    sig1 = compute_endpoint_signature(ex1)
    sig2 = compute_endpoint_signature(ex2)
    assert sig1 == sig2


def test_deduplicate_merges_repeated_requests_and_increments_count():
    t0 = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=10)
    t2 = t0 + timedelta(seconds=20)

    ex1 = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/processAttendance",
            path="/vtop/processAttendance",
            query={"sem": "WIN2026", "_csrf": "token_1"},
            timestamp=t0,
        ),
        response=CapturedResponse(status=200, content_type="text/html", body="old_data"),
        purpose="unknown",
    )

    ex2 = CapturedExchange(
        request=CapturedRequest(
            method="POST",
            url="https://vtop.vit.ac.in/vtop/processAttendance",
            path="/vtop/processAttendance",
            query={"sem": "WIN2026", "_csrf": "token_2"},
            timestamp=t1,
        ),
        response=CapturedResponse(status=200, content_type="text/html", body="new_data"),
        purpose="attendance",
    )

    ex3 = CapturedExchange(
        request=CapturedRequest(
            method="GET",
            url="https://vtop.vit.ac.in/vtop/getMarks",
            path="/vtop/getMarks",
            timestamp=t2,
        ),
        response=CapturedResponse(status=200, content_type="application/json"),
        purpose="marks",
    )

    endpoints = deduplicate([ex1, ex2, ex3])
    assert len(endpoints) == 2

    att_ep = next(ep for ep in endpoints if ep.path == "/vtop/processattendance")
    assert att_ep.hit_count == 2
    assert att_ep.first_seen == t0
    assert att_ep.last_seen == t1
    assert att_ep.purpose == "attendance"
    assert att_ep.response.body == "new_data"

    marks_ep = next(ep for ep in endpoints if ep.path == "/vtop/getmarks")
    assert marks_ep.hit_count == 1
    assert marks_ep.purpose == "marks"
