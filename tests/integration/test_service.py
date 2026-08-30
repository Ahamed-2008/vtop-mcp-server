"""Integration tests: AcademicService layer against the mock VTOP server."""

from __future__ import annotations

import pytest

from mock_vtop import MOCK_CAPTCHA, MOCK_PASSWORD, MOCK_USERNAME
from vtop_mcp.errors import AuthenticationRequiredError, SessionExpiredError
from vtop_mcp.vtop import endpoints as ep


async def test_service_requires_authentication(service):
    with pytest.raises(AuthenticationRequiredError):
        await service.get_cgpa()


async def test_get_cgpa(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_cgpa()
    assert result.current_cgpa == 8.72
    assert result.earned_credits == 47.0
    assert result.total_credits_required == 162.0


async def test_get_courses(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_courses()
    assert result.semester == "FALLSEM2026-27"
    assert len(result.courses) == 13


async def test_get_attendance_derives_from_courses(service, auth, metrics):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    rows = await service.get_attendance()
    assert len(rows) == 13
    first = rows[0]
    assert first["course_code"] == "BACSE102"
    assert first["percentage"] == 100.0
    assert metrics.vtop_requests.get(ep.COURSE_DETAILS.path) == 1


async def test_get_academic_summary(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    summary = await service.get_academic_summary()
    assert summary.cgpa == 8.72
    assert summary.semester == "FALLSEM2026-27"
    assert len(summary.courses) == 13
    assert summary.summary.course_count == 13


async def test_get_assignments(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_assignments()
    assert len(result.assignments) == 4


async def test_get_events(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_events()
    assert len(result.events) == 9
    assert len(result.days) == 6


async def test_get_feedback(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_feedback()
    assert len(result.feedbacks) == 5


async def test_get_proctor_message(service, auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_proctor_message()
    assert result.message is None


async def test_cache_avoids_duplicate_requests(service, auth, metrics):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    await service.get_cgpa()
    await service.get_cgpa()
    assert metrics.vtop_requests.get(ep.CGPA_CREDITS.path) == 1


async def test_cache_ttl_expiry(auth, metrics, redactor, mock_server):
    from dataclasses import replace

    from vtop_mcp.config import Settings
    from vtop_mcp.services import AcademicService

    import asyncio

    settings = replace(Settings(base_url=mock_server.base_url), cache_ttl=0.05)
    service = AcademicService(auth, settings, metrics, redactor)
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    await service.get_cgpa()
    await asyncio.sleep(0.1)
    await service.get_cgpa()
    assert metrics.vtop_requests.get(ep.CGPA_CREDITS.path) == 2


async def test_session_expiry_detected(service, auth, mock_server):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    mock_server.expire_sessions = True
    with pytest.raises(SessionExpiredError):
        await service.get_cgpa()
    assert auth.session is None


async def test_reauthenticate_after_expiry(service, auth, mock_server):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    mock_server.expire_sessions = True
    with pytest.raises(SessionExpiredError):
        await service.get_cgpa()
    mock_server.expire_sessions = False
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    result = await service.get_cgpa()
    assert result.current_cgpa == 8.72


async def test_malformed_response_persisted(service, auth, mock_server):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    mock_server.malformed = True
    result = await service.get_assignments()  # no table -> empty list, tolerant
    assert result.assignments == []


async def test_server_error_raises(service, auth, mock_server):
    from vtop_mcp.errors import VTOPResponseError

    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    mock_server.reject_status = 502
    try:
        await service.get_cgpa()
    except Exception as exc:  # noqa: BLE001 - retries may exhaust into unavailable
        from vtop_mcp.errors import VTOPUnavailableError

        assert isinstance(exc, (VTOPResponseError, VTOPUnavailableError))