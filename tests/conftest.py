"""Shared test fixtures.

The mock VTOP HTTP server is thread-based, so it is created and torn down with
a plain (non-async) fixture. Clients/services built on top get function-scoped
fixtures so tests never share sessions or caches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mock_vtop import MockVTOPServer
from vtop_mcp.config import Settings
from vtop_mcp.metrics import Metrics
from vtop_mcp.redaction import Redactor
from vtop_mcp.services import AcademicService
from vtop_mcp.vtop.auth import AuthManager
from vtop_mcp.vtop.client import VTOPClient

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def fixture_data() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in FIXTURE_DIR.glob("*.html")}


@pytest.fixture
def mock_server() -> MockVTOPServer:
    with MockVTOPServer(fixture_dir=FIXTURE_DIR) as server:
        yield server


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(base_url="http://mock.invalid", session_path=tmp_path / "nonexistent.json")


@pytest.fixture
def session_settings(mock_server) -> Settings:
    return Settings(base_url=mock_server.base_url, session_path=None)


@pytest.fixture
def redactor() -> Redactor:
    return Redactor()


@pytest.fixture
def metrics() -> Metrics:
    return Metrics()


@pytest.fixture
async def client(session_settings, metrics, redactor) -> VTOPClient:
    c = VTOPClient(session_settings, metrics, redactor)
    yield c
    await c.close()


@pytest.fixture
def auth_persist_path(tmp_path) -> Path:
    """Per-test temp dir so tests never touch the real .vtop-session/."""
    return tmp_path / "sessions"


@pytest.fixture
async def auth(client, session_settings, metrics, redactor, auth_persist_path) -> AuthManager:
    return AuthManager(client, session_settings, metrics, redactor, persist_path=auth_persist_path)


@pytest.fixture
async def service(auth, session_settings, metrics, redactor) -> AcademicService:
    return AcademicService(auth, session_settings, metrics, redactor)