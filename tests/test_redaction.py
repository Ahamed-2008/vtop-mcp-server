"""Redaction tests: secrets and sensitive patterns must never leak."""

from __future__ import annotations

import logging

from vtop_mcp.redaction import Redactor, RedactingFilter

_CSRF = "11111111-2222-3333-4444-555555555555"
_ID = "25BCE0001"
_PASSWORD = "hunter2-supersecret"


def _redactor() -> Redactor:
    r = Redactor()
    r.register(_CSRF, _ID, _PASSWORD)
    return r


def test_registered_secret_replaced():
    r = _redactor()
    assert r.redact(f"csrf is {_CSRF} ok") == "csrf is [REDACTED] ok"


def test_authorized_id_replaced():
    r = _redactor()
    assert r.redact(_ID) == "[REDACTED]"


def test_uuid_anywhere_replaced():
    r = Redactor()
    uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert r.redact(f"token={uuid}") == "token=[REDACTED]"


def test_csrf_key_value_pattern():
    r = Redactor()
    out = r.redact("_csrf: 99999999-8888-7777-6666-555555555555")
    assert "99999999-8888" not in out


def test_captcha_value_pattern():
    r = Redactor()
    out = r.redact('captchaStr = "K7M2P9"')
    assert "K7M2P9" not in out
    out2 = r.redact("captcha=ABC123")
    assert "ABC123" not in out2


def test_cookie_header_redacted():
    r = Redactor()
    assert r.redact("Cookie: VTOP_SESSION=deadbeef1234; path=/)") == "[REDACTED]"


def test_authorization_header_redacted():
    r = Redactor()
    assert r.redact("Authorization: Bearer tok1234567890") == "[REDACTED]"


def test_redact_many():
    r = _redactor()
    result = r.redact_many([f"a {_PASSWORD}", f"b {_ID}"])
    assert result == ["a [REDACTED]", "b [REDACTED]"]


def test_redact_empty_and_none_safe():
    r = Redactor()
    assert r.redact("") == ""
    assert RedactingFilter(r).filter(record_with_empty_message()) is True


def test_filter_redacts_message_and_args(caplog):
    r = _redactor()
    logging.getLogger("test.redaction").addFilter(RedactingFilter(r))
    with caplog.at_level(logging.INFO, logger="test.redaction"):
        logging.getLogger("test.redaction").info("password is %s", _PASSWORD)
    assert _PASSWORD not in caplog.text
    assert "[REDACTED]" in caplog.text


class _Rec:
    pass


def record_with_empty_message():
    rec = _Rec()
    rec.msg = ""
    rec.args = ()
    return rec