"""CSRF extraction and validation tests."""

from __future__ import annotations

import pytest

from vtop_mcp.errors import CSRFError
from vtop_mcp.vtop.csrf import (
    ensure_valid,
    extract_content_tokens,
    extract_csrf_from_html,
)

_SAMPLE = "a1b2c3d4-e5f6-a7b8-c9d0-e1f2a3b4c5d6"


def test_csrf_from_hidden_input():
    html = f'<form><input type="hidden" name="_csrf" value="{_SAMPLE}"/></form>'
    assert extract_csrf_from_html(html) == _SAMPLE


def test_csrf_from_js_variable():
    html = f"<script>var csrfValue = \"{_SAMPLE}\";</script>"
    assert extract_csrf_from_html(html) == _SAMPLE


def test_csrf_prefers_hidden_input_over_js():
    js = f"<script>var csrfValue = \"js-token-123456789\";</script>"
    hidden = f'<input type="hidden" name="_csrf" value="{_SAMPLE}"/>'
    assert extract_csrf_from_html(hidden + js) == _SAMPLE


def test_csrf_missing_raises():
    with pytest.raises(CSRFError):
        extract_csrf_from_html("<html><body>nothing</body></html>")


def test_csrf_implausible_raises():
    with pytest.raises(CSRFError):
        extract_csrf_from_html('<input type="hidden" name="_csrf" value="&lt;script&gt;"/>')


def test_csrf_empty_html_raises():
    with pytest.raises(CSRFError):
        extract_csrf_from_html("")


def test_content_tokens_extracted(fixture_data):
    html = (
        '<input type="hidden" name="authorizedID" id="authorizedID" value="25BCE0001"/>'
        f'<script>var csrfValue = "{_SAMPLE}"; var id = "25BCE0001";</script>'
    )
    csrf, authorized_id = extract_content_tokens(html)
    assert csrf == _SAMPLE
    assert authorized_id == "25BCE0001"


def test_content_tokens_authorized_idx_only(fixture_data):
    html = (
        '<input type="hidden" name="authorizedIDX" id="authorizedIDX" value="25BCE0002"/>\n'
        f'<script>var csrfValue = "{_SAMPLE}";</script>'
    )
    csrf, authorized_id = extract_content_tokens(html)
    assert authorized_id == "25BCE0002"


def test_content_tokens_var_id_fallback():
    html = f'<script>var csrfValue = "{_SAMPLE}"; var id = "25BCE0003";</script>'
    _, authorized_id = extract_content_tokens(html)
    assert authorized_id == "25BCE0003"


def test_content_tokens_let_id_fallback():
    html = f'<script>var csrfValue = "{_SAMPLE}"; let id = "25BCE0004";</script>'
    _, authorized_id = extract_content_tokens(html)
    assert authorized_id == "25BCE0004"


def test_content_tokens_live_layout_multiline_attrs():
    """Live /vtop/content uses multi-line attribute layout; robust extraction."""
    html = (
        f'<script>var csrfValue = "{_SAMPLE}";</script>\n'
        '<input type="hidden" name="authorizedID" id="authorizedID"\n'
        '       value="25BCE0005"/>'
    )
    _, authorized_id = extract_content_tokens(html)
    assert authorized_id == "25BCE0005"


def test_content_tokens_missing_identity_raises():
    html = '<!-- no authorizedID anywhere -->'
    with pytest.raises(CSRFError):
        extract_content_tokens(html)


def test_ensure_valid_accepts_plausible():
    assert ensure_valid("abc-def-1234567890") == "abc-def-1234567890"


@pytest.mark.parametrize("bad", ["", " ", "short", "<script>", "a b"])
def test_ensure_valid_rejects_malformed(bad):
    with pytest.raises(CSRFError):
        ensure_valid(bad)