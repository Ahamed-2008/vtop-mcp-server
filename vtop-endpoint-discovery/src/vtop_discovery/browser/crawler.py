from __future__ import annotations

import time
from typing import TYPE_CHECKING

from vtop_discovery.utils.logging import get_logger

if TYPE_CHECKING:
    from playwright.sync_api import ElementHandle, Page
    from vtop_discovery.capture.network import NetworkCapture

logger = get_logger(__name__)

LOGIN_INDICATOR_SELECTORS = (
    'a[href*="logout"]',
    'button:has-text("Logout")',
    'a:has-text("Logout")',
    "#logoutBtn",
    ".logout",
    ".sidebar",
    ".nav-sidebar",
    "#menu-sidebar",
    ".page-wrapper",
    ".main-header",
    "#viewMenu",
)

MENU_SELECTORS = (
    ".sidebar a",
    ".nav-sidebar a",
    "#menu-sidebar a",
    "nav a.nav-link",
    "ul.nav a",
    ".sidebar-menu a",
    "[role='menuitem']",
    "a.menu-link",
    ".dropdown-menu a",
)

TAB_SELECTORS = (
    ".nav-tabs a",
    "ul.nav-tabs li a",
    ".tab-content button",
    "button.btn-primary",
    "input[type='button']",
)


def is_logged_in(page: Page) -> bool:
    try:
        url = page.url.lower()
        if "open/page" not in url and ("vtop" in url or "content" in url or "main" in url):
            # Checking URL signals or element signals
            pass
        for selector in LOGIN_INDICATOR_SELECTORS:
            if page.locator(selector).count() > 0:
                return True
    except Exception:
        pass
    return False


def wait_for_login(page: Page, timeout: float = 300.0) -> bool:
    logger.info("Waiting for user login to complete in browser (timeout: %.0fs)...", timeout)
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_logged_in(page):
            print("\n" + "=" * 60)
            print("  Login Complete. Crawling the website")
            print("=" * 60 + "\n")
            logger.info("Login Complete. Crawling the website")
            return True
        time.sleep(1.0)
    logger.warning("Timed out waiting for login.")
    return False


def _purpose_from_label(text: str) -> str:
    lowered = text.lower().strip()
    if "attend" in lowered:
        return "attendance"
    if "mark" in lowered or "grade" in lowered:
        return "marks"
    if "time" in lowered and "table" in lowered:
        return "timetable"
    if "course" in lowered or "regis" in lowered:
        return "courses"
    if "profile" in lowered or "student" in lowered:
        return "profile"
    if "exam" in lowered:
        return "examinations"
    return lowered.replace(" ", "_")[:20] or "unknown"


def auto_crawl_vtop(page: Page, capture: NetworkCapture, max_depth: int = 50) -> int:
    """Systematically explore VTOP navigation menus, buttons, and tabs to capture endpoints."""
    logger.info("Starting automated VTOP crawler...")

    # Wait briefly for page to settle post-login
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    # 1. Expand all dropdowns / accordion menus in sidebar
    logger.info("Expanding navigation menus...")
    try:
        expandables = page.query_selector_all(".sidebar li.has-treeview > a, .sidebar .dropdown-toggle, .nav-sidebar .has-treeview > a")
        for btn in expandables:
            try:
                btn.click()
                page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Menu expansion attempt: %s", exc)

    # 2. Collect all clickable menu links
    visited_urls_or_texts: set[str] = set()
    links_found: list[tuple[str, str, ElementHandle]] = []

    for selector in MENU_SELECTORS:
        try:
            elements = page.query_selector_all(selector)
            for el in elements:
                try:
                    text = (el.text_content() or "").strip()
                    href = el.get_attribute("href") or ""
                    key = f"{text}|{href}"
                    if text and key not in visited_urls_or_texts and "logout" not in text.lower():
                        visited_urls_or_texts.add(key)
                        links_found.append((text, href, el))
                except Exception:
                    pass
        except Exception:
            pass

    logger.info("Discovered %d navigation menu items to explore.", len(links_found))

    crawled_count = 0
    # 3. Systematically click each discovered link
    for text, href, _ in links_found[:max_depth]:
        purpose = _purpose_from_label(text)
        print(f"  [+] Crawling section: {text} ({purpose})")
        logger.info("Crawling section [%s] -> '%s'...", purpose, text)
        capture.start_phase(purpose)

        try:
            # Locate element fresh by text to avoid stale element handle errors
            link_locator = page.locator(f"text='{text}'").first
            if link_locator.count() > 0 and link_locator.is_visible():
                link_locator.click(timeout=4000)
                crawled_count += 1
                try:
                    page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    page.wait_for_timeout(1500)

                # Look for sub-tabs or inner buttons on the loaded page
                _crawl_inner_tabs(page, capture)
        except Exception as exc:
            logger.warning("Error crawling menu item '%s': %s", text, exc)
        finally:
            capture.stop_phase()

    logger.info("Automated crawling complete! Visited %d menu sections.", crawled_count)
    return crawled_count


def _crawl_inner_tabs(page: Page, capture: NetworkCapture) -> None:
    """Click tabs, detail buttons, or query forms rendered inside the current view."""
    for selector in TAB_SELECTORS:
        try:
            tabs = page.query_selector_all(selector)
            for tab in tabs[:5]:  # limit to first 5 inner controls per view
                try:
                    txt = (tab.text_content() or tab.get_attribute("value") or "").strip()
                    if txt and "logout" not in txt.lower() and tab.is_visible():
                        logger.debug("Clicking inner tab/button: '%s'", txt)
                        tab.click(timeout=3000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            page.wait_for_timeout(1000)
                except Exception:
                    pass
        except Exception:
            pass
