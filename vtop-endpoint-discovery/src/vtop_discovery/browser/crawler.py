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
    "button.btn-info",
    "button.btn-default",
    "input[type='button']",
    "input[type='submit']",
)

# Unsafe state-changing keywords to avoid automatically executing
UNSAFE_WRITE_KEYWORDS = (
    "hostel leave",
    "apply leave",
    "submit leave",
    "student/leave/3",
    "leave application",
    "course registration",
    "add course",
    "drop course",
    "course change",
    "payment",
    "make payment",
    "pay now",
    "proceed to pay",
    "withdraw",
    "confirm submission",
    "final submit",
    "delete",
    "cancel booking",
    "book room",
    "feedback submission",
    "submit feedback",
    "reset password",
    "change password",
)


def is_potentially_unsafe_action(text: str, href: str = "", name_or_id: str = "") -> bool:
    """Detect if an interactive element represents a potentially state-changing write action."""
    haystack = f"{text} {href} {name_or_id}".lower()
    for kw in UNSAFE_WRITE_KEYWORDS:
        if kw in haystack:
            return True
    return False


def is_logged_in(page: Page) -> bool:
    try:
        url = page.url.lower()
        if "open/page" not in url and ("vtop" in url or "content" in url or "main" in url):
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
            print("  Login detected! Starting automated portal exploration...")
            print("=" * 60 + "\n")
            logger.info("Login detected! Starting automated portal exploration...")
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


def auto_crawl_vtop(
    page: Page,
    capture: NetworkCapture,
    max_pages: int = 50,
    max_actions: int = 100,
    max_depth: int = 50,
    request_timeout: float = 4.0,
) -> dict[str, int]:
    """Systematically explore VTOP navigation menus, buttons, and tabs to capture endpoints safely."""
    logger.info("Starting automated VTOP crawler (max_pages=%d, max_actions=%d)...", max_pages, max_actions)

    stats = {
        "pages_visited": 0,
        "actions_performed": 0,
        "unsafe_actions_skipped": 0,
    }

    # Wait briefly for page to settle post-login
    try:
        page.wait_for_load_state("networkidle", timeout=int(request_timeout * 1000))
    except Exception:
        pass

    # 1. Expand all dropdowns / accordion menus in sidebar
    logger.info("Expanding navigation menus...")
    try:
        expandables = page.query_selector_all(".sidebar li.has-treeview > a, .sidebar .dropdown-toggle, .nav-sidebar .has-treeview > a, .menu-sidebar .has-treeview > a")
        for btn in expandables:
            try:
                txt = (btn.text_content() or "").strip()
                if not is_potentially_unsafe_action(txt):
                    btn.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Menu expansion attempt: %s", exc)

    # 2. Collect all clickable menu links
    visited_keys: set[str] = set()
    links_found: list[tuple[str, str, ElementHandle]] = []

    for selector in MENU_SELECTORS:
        try:
            elements = page.query_selector_all(selector)
            for el in elements:
                try:
                    text = (el.text_content() or "").strip()
                    href = el.get_attribute("href") or ""
                    key = f"{text}|{href}"
                    if text and key not in visited_keys and "logout" not in text.lower():
                        visited_keys.add(key)
                        links_found.append((text, href, el))
                except Exception:
                    pass
        except Exception:
            pass

    logger.info("Discovered %d navigation menu items to explore.", len(links_found))

    # 3. Systematically click each discovered link
    for text, href, _ in links_found[:max_depth]:
        if stats["pages_visited"] >= max_pages or stats["actions_performed"] >= max_actions:
            logger.info("Reached configured crawl limits (pages: %d, actions: %d).", stats["pages_visited"], stats["actions_performed"])
            break

        if is_potentially_unsafe_action(text, href=href):
            print(f"  [SKIP] Potential write operation: '{text}'")
            logger.warning("[SKIP] Skipped potentially state-changing menu action: '%s'", text)
            stats["unsafe_actions_skipped"] += 1
            continue

        purpose = _purpose_from_label(text)
        print(f"[PAGE] Crawling section: {text} ({purpose})")
        logger.info("[PAGE] Crawling section [%s] -> '%s'...", purpose, text)
        capture.start_phase(purpose)

        try:
            # Locate element fresh by text to avoid stale element handle errors
            link_locator = page.locator(f"text='{text}'").first
            if link_locator.count() > 0 and link_locator.is_visible():
                link_locator.click(timeout=int(request_timeout * 1000))
                stats["pages_visited"] += 1
                stats["actions_performed"] += 1
                try:
                    page.wait_for_load_state("networkidle", timeout=int(request_timeout * 1000))
                except Exception:
                    page.wait_for_timeout(1500)

                # Look for sub-tabs or inner buttons on the loaded page
                _crawl_inner_tabs(page, capture, stats, max_actions=max_actions, timeout=request_timeout)
        except Exception as exc:
            logger.warning("Error crawling menu item '%s': %s", text, exc)
        finally:
            capture.stop_phase()

    logger.info("Automated crawling complete! Visited %d menu sections, skipped %d unsafe actions.", stats["pages_visited"], stats["unsafe_actions_skipped"])
    return stats


def _crawl_inner_tabs(
    page: Page,
    capture: NetworkCapture,
    stats: dict[str, int],
    max_actions: int = 100,
    timeout: float = 4.0,
) -> None:
    """Click tabs, detail buttons, or read-only query forms rendered inside the current view."""
    # 1. Handle dropdown selects (e.g. semester selection)
    try:
        selects = page.query_selector_all("select")
        for sel in selects[:3]:
            try:
                name = sel.get_attribute("name") or ""
                options = sel.query_selector_all("option")
                for opt in options[:3]:
                    val = opt.get_attribute("value")
                    if val and val.strip():
                        sel.select_option(value=val)
                        page.wait_for_timeout(500)
                        break
            except Exception:
                pass
    except Exception:
        pass

    # 2. Handle tabs and view buttons
    for selector in TAB_SELECTORS:
        if stats["actions_performed"] >= max_actions:
            break
        try:
            tabs = page.query_selector_all(selector)
            for tab in tabs[:5]:  # limit to first 5 inner controls per view
                try:
                    txt = (tab.text_content() or tab.get_attribute("value") or "").strip()
                    btn_id = tab.get_attribute("id") or ""
                    btn_name = tab.get_attribute("name") or ""

                    if not txt or "logout" in txt.lower():
                        continue

                    if is_potentially_unsafe_action(txt, name_or_id=f"{btn_id} {btn_name}"):
                        print(f"  [SKIP] Potential write operation: '{txt}'")
                        logger.warning("[SKIP] Skipped potentially state-changing button: '%s'", txt)
                        stats["unsafe_actions_skipped"] += 1
                        continue

                    if tab.is_visible():
                        logger.debug("Clicking inner read-only control: '%s'", txt)
                        tab.click(timeout=int(timeout * 1000))
                        stats["actions_performed"] += 1
                        try:
                            page.wait_for_load_state("networkidle", timeout=int(timeout * 1000))
                        except Exception:
                            page.wait_for_timeout(1000)
                except Exception:
                    pass
        except Exception:
            pass

