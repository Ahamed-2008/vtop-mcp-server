"""Integration tests: VTOPClient + AuthManager against the mock VTOP server."""

from __future__ import annotations

import pytest

from mock_vtop import MOCK_CAPTCHA, MOCK_PASSWORD, MOCK_USERNAME
from vtop_mcp.errors import LoginFailedError, SessionExpiredError


async def login(client, auth):
    await client.initialize()
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    assert auth.session is not None
    return auth.session


async def test_initialize_returns_builtin_challenge(client):
    challenge = await client.initialize()
    assert challenge.captcha_type == "builtin"
    assert challenge.captcha_image
    assert not challenge.requires_browser


async def test_login_sets_authorized_id(auth):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    assert auth.session.authorized_id == "25BCE0001"


async def test_login_wrong_captcha_fails(auth):
    with pytest.raises(LoginFailedError):
        await auth.login(MOCK_USERNAME, MOCK_PASSWORD, "WRONG0")


async def test_login_wrong_password_fails(auth):
    with pytest.raises(LoginFailedError):
        await auth.login(MOCK_USERNAME, "bad-password", MOCK_CAPTCHA)


async def test_login_rejected_with_200_login_page_fails_clearly(mock_server, client, session_settings, metrics, redactor):
    """Regression: live VTOP re-renders the login form (HTTP 200, with a fresh
    ``var csrfValue``) on a rejected login. That must surface as LoginFailedError,
    not as a CSRFError about a missing authorizedID."""
    from vtop_mcp.vtop.auth import AuthManager

    mock_server.login_reject_200 = True
    auth = AuthManager(client, session_settings, metrics, redactor, persist_path=None)
    with pytest.raises(LoginFailedError):
        await auth.login(MOCK_USERNAME, MOCK_PASSWORD, "WRONG0")


async def test_session_persisted_when_path_set(tmp_path, client, metrics, redactor, mock_server):
    from dataclasses import replace

    from vtop_mcp.config import Settings
    from vtop_mcp.vtop.auth import AuthManager

    path = tmp_path / "session.json"
    settings = replace(
        Settings(session_path=path),  # frozen dataclass -> rebuild, not mutate
        base_url=mock_server.base_url,
    )
    auth = AuthManager(client, settings, metrics, redactor, persist_path=path)
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    assert path.exists()

    import json

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["version"] == 1
    assert stored["authorized_id"] == "25BCE0001"


async def test_bootstrap_loads_persisted_session(tmp_path, client, metrics, redactor, mock_server):
    from dataclasses import replace

    from vtop_mcp.config import Settings
    from vtop_mcp.vtop.auth import AuthManager

    path = tmp_path / "session.json"
    settings = replace(Settings(session_path=path), base_url=mock_server.base_url)
    auth = AuthManager(client, settings, metrics, redactor, persist_path=path)
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    assert auth.session is not None

    from vtop_mcp.vtop.client import VTOPClient

    client2 = VTOPClient(settings, metrics, redactor)
    auth2 = AuthManager(client2, settings, metrics, redactor, persist_path=path)
    await auth2.bootstrap()
    assert auth2.authenticated
    assert auth2.session.authorized_id == "25BCE0001"
    await client2.close()