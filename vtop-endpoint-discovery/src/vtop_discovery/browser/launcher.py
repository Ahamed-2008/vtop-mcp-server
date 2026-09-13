import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from vtop_discovery.utils.logging import get_logger

DEFAULT_URL = "https://vtop.vit.ac.in/vtop/open/page"
DEFAULT_AUTHENTICATED_URL = "https://vtop.vit.ac.in/vtop/content"
logger = get_logger(__name__)


def _find_session_file(explicit_path: Path | None = None) -> Path | None:
    if explicit_path and explicit_path.exists():
        return explicit_path
    candidates = [
        Path(".vtop-session/session.json"),
        Path("../.vtop-session/session.json"),
        Path.home() / ".vtop-session" / "session.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def restore_session_cookies(context: BrowserContext, session_path: Path | None = None) -> bool:
    """Load cookies from a stored session file and apply them to the Playwright context."""
    sess_file = _find_session_file(session_path)
    if not sess_file:
        return False
    try:
        data = json.loads(sess_file.read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        if not cookies:
            return False
        pw_cookies = []
        for c in cookies:
            cookie_dict = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain") or "vtop.vit.ac.in",
                "path": c.get("path") or "/",
            }
            pw_cookies.append(cookie_dict)
        context.add_cookies(pw_cookies)
        logger.info("Restored %d session cookies from %s", len(pw_cookies), sess_file)
        return True
    except Exception as exc:
        logger.warning("Could not restore session from %s: %s", sess_file, exc)
        return False


import os

# Skip Debian/Ubuntu-only host requirement checks on Fedora / RHEL
if "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS" not in os.environ:
    os.environ["PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS"] = "1"


def _launch_chromium(playwright: Playwright, headless: bool = False) -> Browser:
    """Launch Chromium, attempting default bundled binary first and falling back to system channels if needed."""
    try:
        return playwright.chromium.launch(headless=headless)
    except Exception as exc:
        logger.warning("Default Playwright Chromium launch failed (%s). Attempting system Google Chrome...", exc)
        for channel in ("chrome", "chromium", "msedge"):
            try:
                browser = playwright.chromium.launch(headless=headless, channel=channel)
                logger.info("Successfully launched system browser using channel=%s", channel)
                return browser
            except Exception:
                continue
        raise exc


@contextmanager
def launch_browser(
    url: str = DEFAULT_URL,
    headless: bool = False,
    session_path: Path | None = None,
    on_context: Callable[[BrowserContext], None] | None = None,
) -> Iterator[tuple[Playwright, Browser, BrowserContext, Page]]:
    """Launch Chromium, restore session if available, attach listeners, and yield.

    If session is restored or valid, attempts opening the portal directly.
    Otherwise, waits for manual user login.
    """
    playwright = sync_playwright().start()
    browser = _launch_chromium(playwright, headless=headless)
    context = browser.new_context()


    has_session = restore_session_cookies(context, session_path=session_path)

    if on_context is not None:
        on_context(context)

    page = context.new_page()
    target_url = DEFAULT_AUTHENTICATED_URL if has_session and url == DEFAULT_URL else url
    logger.info("Opening %s (session restored: %s)", target_url, has_session)
    if not has_session:
        logger.info("Complete login in the browser if prompted (including CAPTCHA).")
    try:
        page.goto(target_url, wait_until="domcontentloaded")
    except Exception as exc:
        logger.warning("Initial navigation failed (%s); window remains open.", exc)
    try:
        yield playwright, browser, context, page
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        playwright.stop()
        logger.info("Browser closed")

