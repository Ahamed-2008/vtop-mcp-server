"""Configuration loading tests (env-driven, no network)."""

from __future__ import annotations

import pytest

from vtop_mcp.config import Settings, RetrySettings
from vtop_mcp.errors import InvalidConfigurationError


def test_settings_defaults():
    s = Settings()
    assert s.base_url == "https://vtop.vit.ac.in"
    assert s.initial_url == "/vtop/open/page"
    assert s.enable_login is True
    assert s.timeout.connect == 10.0
    assert s.retry.attempts == 2


def test_session_path_default(monkeypatch, tmp_path):
    s = Settings()
    path = s.resolved_session_path
    assert path.name == "session.json"


def test_session_path_explicit(monkeypatch):
    s = Settings(session_path=None)
    monkeypatch.setenv("VTOP_SESSION_PATH", "~/custom/session.json")
    loaded = Settings.from_env()
    assert str(loaded.session_path).endswith("custom/session.json")
    assert loaded.resolved_session_path.is_absolute()


def test_from_env_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("VTOP_BASE_URL", "https://vtop.example.com/")
    monkeypatch.setenv("VTOP_ENABLE_LOGIN", "false")
    monkeypatch.setenv("VTOP_CACHE_TTL", "5.5")
    monkeypatch.setenv("VTOP_LOG_LEVEL", "debug")
    s = Settings.from_env()
    assert s.base_url == "https://vtop.example.com"
    assert s.enable_login is False
    assert s.cache_ttl == 5.5
    assert s.log_level == "DEBUG"


def test_from_env_bad_numeric(tmp_path, monkeypatch):
    monkeypatch.setenv("VTOP_CACHE_TTL", "abc")
    with pytest.raises(InvalidConfigurationError):
        Settings.from_env()


def test_from_env_bad_log_level(tmp_path, monkeypatch):
    monkeypatch.setenv("VTOP_LOG_LEVEL", "LOUD")
    with pytest.raises(InvalidConfigurationError):
        Settings.from_env()


def test_retry_backoff():
    r = RetrySettings(attempts=3, backoff_base=0.5)
    assert r.delay_for(0) == 0.5
    assert r.delay_for(1) == 1.0
    assert r.delay_for(2) == 2.0
    assert r.delay_for(10) == 10.0  # capped


def test_timeout_property():
    t = Settings().timeout
    assert t.connect == 10.0
    assert t.read == 30.0