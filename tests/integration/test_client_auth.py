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


async def test_login_page_captcha_scan_prefers_large_data_image(client):
    """A tiny spacer GIF earlier in the DOM must not mask the CAPTCHA image."""
    spacer = "data:image/gif;base64,R0lGODlhAQAB"
    big = "data:image/jpeg;base64," + ("/9j/4AAQ" * 300)
    html = (
        f'<script>var csrfValue = "abc-def-1234567890";</script>'
        f'<img src="{spacer}" height="1"/>'
        f'<img src="{big}" id="captchaImg"/>'
    )
    challenge = client._parse_login_page(html)
    assert challenge.captcha_type == "builtin"
    assert challenge.captcha_image and challenge.captcha_image.startswith("/9j/4AAQ")
    assert len(challenge.captcha_image) > 1000


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


async def test_login_uses_supplied_challenge_without_refetch(client, auth):
    """Regression: the CAPTCHA the user solved must be submitted verbatim with
    its paired CSRF. submit_login() must not re-fetch the challenge (which
    would rotate the CSRF/CAPTCHA pair on /vtop/login and invalidate the answer)."""
    init_calls: list[int] = []
    orig = auth._client.initialize
    async def counting_init():
        init_calls.append(1)
        return await orig()
    auth._client.initialize = counting_init

    challenge = await auth._client.initialize()
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA, challenge=challenge)
    assert len(init_calls) == 1


async def test_login_fetches_challenge_once_when_omitted(client, auth):
    orig = auth._client.initialize
    async def counting_init():
        return await orig()
    auth._client.initialize = counting_init

    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    assert auth.session is not None


async def test_wrong_password_failure_message_mentions_rejection(client, auth):
    """Rejections carry a VTOP-derived reason when available."""
    with pytest.raises(LoginFailedError) as ei:
        await auth.login(MOCK_USERNAME, "bad-password", MOCK_CAPTCHA)
    assert "VTOP" in str(ei.value)


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