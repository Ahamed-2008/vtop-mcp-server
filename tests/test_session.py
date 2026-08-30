"""Session serialization, persistence, and expiry tests."""

from __future__ import annotations

import json
import os
import time

import pytest

from vtop_mcp.errors import InvalidConfigurationError, SessionExpiredError
from vtop_mcp.redaction import Redactor
from vtop_mcp.vtop.session import Session

_CSRF = "11111111-2222-3333-4444-555555555555"
_ID = "25BCE0001"


def _session(**kw) -> Session:
    base = dict(csrf_token=_CSRF, authorized_id=_ID)
    base.update(kw)
    return Session(**base)


def test_roundtrip(tmp_path):
    path = tmp_path / "session.json"
    s = _session(username="student", cookies=[{"name": "VTOP_SESSION", "value": "abc", "domain": "x", "path": "/"}])
    s.save(path)
    loaded = Session.load(path)
    assert loaded.csrf_token == _CSRF
    assert loaded.authorized_id == _ID
    assert loaded.username == "student"
    assert loaded.cookies[0]["value"] == "abc"


def test_file_permissions_0600(tmp_path):
    path = tmp_path / "session.json"
    _session().save(path)
    assert (path.stat().st_mode & 0o777) == 0o600


def test_load_missing_returns_none(tmp_path):
    assert Session.load(tmp_path / "nope.json") is None


def test_load_corrupt_raises(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidConfigurationError):
        Session.load(path)


def test_load_wrong_version_raises(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(InvalidConfigurationError):
        Session.load(path)


def test_load_missing_fields_raises(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(InvalidConfigurationError):
        Session.load(path)


def test_to_dict_masks_with_redactor():
    masked = _session().to_dict(Redactor())
    assert masked["csrf_token"] == "[REDACTED]"
    assert masked["authorized_id"] == "[REDACTED]"
    for cookie in masked["cookies"]:
        assert cookie["value"] == "[REDACTED]"


def test_fresh_and_expired():
    s = _session()
    assert s.is_fresh(3600)
    s.mark_expired()
    assert not s.is_fresh(3600)


def test_hard_max_age():
    s = _session(established_at=time.time() - (6 * 3600 + 1))
    with pytest.raises(SessionExpiredError):
        s.enforce_hard_max_age()


def test_enforce_hard_max_age_passes_when_new():
    _session().enforce_hard_max_age()


def test_refresh_csrf():
    s = _session()
    s.refresh_csrf("22222222-3333-4444-5555-666666666666")
    assert s.csrf_token == "22222222-3333-4444-5555-666666666666"


def test_set_authorized_id():
    s = _session()
    s.set_authorized_id("99BCE9999")
    assert s.authorized_id == "99BCE9999"


def test_save_is_atomic_replaces_tmp(tmp_path):
    path = tmp_path / "session.json"
    s = _session()
    s.save(path)
    # after save there is no leftover tmp file and the real file is present
    assert path.exists()
    assert not (tmp_path / "session.json.tmp").exists()