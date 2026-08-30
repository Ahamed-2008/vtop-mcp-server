from __future__ import annotations

from datetime import datetime, timezone
from vtop_discovery.analysis.filter import is_interesting, looks_like_captcha
from vtop_discovery.storage.models import CapturedExchange, CapturedRequest


def _make_exchange(url: str, resource_type: str = "document", method: str = "GET") -> CapturedExchange:
    return CapturedExchange(
        request=CapturedRequest(
            method=method,
            url=url,
            path=url.split("?")[0].replace("https://vtop.vit.ac.in", ""),
            resource_type=resource_type,
            timestamp=datetime.now(timezone.utc),
        )
    )


def test_looks_like_captcha():
    assert looks_like_captcha("https://vtop.vit.ac.in/vtop/captcha")
    assert looks_like_captcha("https://vtop.vit.ac.in/vtop/loadCaptcha?x=123")
    assert looks_like_captcha("https://vtop.vit.ac.in/vtop/login?hasCaptcha=true")
    assert not looks_like_captcha("https://vtop.vit.ac.in/vtop/processAttendance")


def test_is_interesting_valid_vtop_endpoints():
    ex = _make_exchange("https://vtop.vit.ac.in/vtop/processAttendance", resource_type="xhr", method="POST")
    assert is_interesting(ex)

    ex_doc = _make_exchange("https://vtop.vit.ac.in/vtop/open/page", resource_type="document")
    assert is_interesting(ex_doc)


def test_is_interesting_captcha_always_kept():
    ex = _make_exchange("https://vtop.vit.ac.in/vtop/captcha.png", resource_type="image")
    assert is_interesting(ex)


def test_is_interesting_drop_static_assets():
    ex_css = _make_exchange("https://vtop.vit.ac.in/vtop/assets/style.css", resource_type="stylesheet")
    assert not is_interesting(ex_css)

    ex_js = _make_exchange("https://vtop.vit.ac.in/vtop/assets/app.js", resource_type="script")
    assert not is_interesting(ex_js)

    ex_img = _make_exchange("https://vtop.vit.ac.in/vtop/assets/logo.png", resource_type="image")
    assert not is_interesting(ex_img)

    ex_font = _make_exchange("https://vtop.vit.ac.in/vtop/assets/font.woff2", resource_type="font")
    assert not is_interesting(ex_font)


def test_is_interesting_drop_external_hosts_and_trackers():
    ex_ext = _make_exchange("https://example.com/api/data", resource_type="xhr")
    assert not is_interesting(ex_ext)

    ex_ga = _make_exchange("https://google-analytics.com/collect", resource_type="xhr")
    assert not is_interesting(ex_ga)
