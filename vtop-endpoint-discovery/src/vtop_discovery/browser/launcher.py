from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from vtop_discovery.utils.logging import get_logger

DEFAULT_URL = "https://vtop.vit.ac.in/vtop/open/page"
logger = get_logger(__name__)


@contextmanager
def launch_browser(
    url: str = DEFAULT_URL,
    on_context: Callable[[BrowserContext], None] | None = None,
) -> Iterator[tuple[Playwright, Browser, BrowserContext, Page]]:
    """Launch headed Chromium, attach listeners immediately, open VTOP, and yield.

    Login is interactive: VTOP uses a captcha that this tool does not solve.
    """
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()

    if on_context is not None:
        on_context(context)

    page = context.new_page()
    logger.info("Opening %s", url)
    logger.info("Complete login in the browser, including the captcha. This tool will not solve it.")
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as exc:
        logger.warning("Initial navigation failed (%s); the window is still open.", exc)
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
