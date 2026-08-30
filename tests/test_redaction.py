"""Redaction tests: secrets and sensitive patterns must never leak."""

from __future__ import annotations

import io
import logging

from vtop_mcp.redaction import RedactingFilter, RedactingFormatter, Redactor

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


def _record(msg: str, args: tuple = ()) -> logging.LogRecord:
    return logging.LogRecord("test.redaction", logging.INFO, __file__, 1, msg, args, None)


def test_filter_preserves_numeric_args():
    """Regression: redaction must never stringify record.args (%d/%f crash)."""
    r = _redactor()
    rec = _record("Loaded persisted VTOP session (age %.0fs). %d tools.", (19.826436042785645, 10))
    assert RedactingFilter(r).filter(rec) is True
    assert rec.getMessage() == "Loaded persisted VTOP session (age 20s). 10 tools."


def test_filter_redacts_literal_secret_in_template():
    r = _redactor()
    rec = _record(f"password is {_PASSWORD}")
    assert RedactingFilter(r).filter(rec) is True
    assert _PASSWORD not in rec.getMessage()
    assert "[REDACTED]" in rec.getMessage()


def test_formatter_redacts_interpolated_message():
    r = _redactor()
    rec = _record("password is %s", (_PASSWORD,))
    out = RedactingFormatter(r, "%(message)s").format(rec)
    assert _PASSWORD not in out
    assert "password is [REDACTED]" in out


def test_formatter_redacts_secret_in_arg():
    r = _redactor()
    rec = _record("token=%s", (_CSRF,))
    out = RedactingFormatter(r, "%(message)s").format(rec)
    assert _CSRF not in out
    assert "token=[REDACTED]" in out


def test_logger_output_redacts_and_formats_numeric(caplog):
    """End-to-end: emitting through a RedactingFormatter must not raise and
    must strip a secret that lives in the args."""
    r = _redactor()
    logger = logging.getLogger("test.redaction.e2e")
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(RedactingFormatter(r, "%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info("password is %s", _PASSWORD)
        logger.info("Loaded persisted VTOP session (age %.0fs).", 19.826436042785645)
        logger.info("vtop-mcp ready (stdio). %d tools registered.", 10)
    finally:
        logger.removeHandler(handler)
    out = buffer.getvalue()
    assert _PASSWORD not in out
    assert "password is [REDACTED]" in out
    assert "age 20s" in out
    assert "10 tools registered" in out


def test_redact_empty_and_none_safe():
    r = Redactor()
    assert r.redact("") == ""
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "", (), None)
    assert RedactingFilter(r).filter(rec) is True


def test_emit_via_real_handler_never_raises():
    """A secret in the format string + numeric args is the crash combo."""
    r = _redactor()
    logger = logging.getLogger("test.redaction.handler")
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(RedactingFormatter(r, "%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info("session %s age %.0fs", _ID, 19.83)
    finally:
        logger.removeHandler(handler)
    assert "session [REDACTED] age 20s" in buffer.getvalue()