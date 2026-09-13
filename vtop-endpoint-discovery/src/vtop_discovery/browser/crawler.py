"""
Exhaustive VTOP portal crawler.

Key design decisions
--------------------
* **iframe-aware** – VTOP loads every section's content into a child ``<iframe>``.
  All helpers iterate over ``page.frames`` so nothing is missed.
* **dynamic menu expansion** – accordion parents are expanded and the link list is
  re-collected after each expansion, so sub-menus revealed on-the-fly are included.
* **exhaustive inner-page exploration** – after navigating to a section every
  interactive element in every frame is clicked (buttons, tabs, ``<a>`` tags,
  onclick cells).  ``<select>`` elements have *all* options exercised, not just the
  first one, because VTOP uses semester/year dropdowns where each value triggers a
  distinct XHR.
* **one level of recursion** – after clicking a tab/button we re-scan for new
  controls that appeared as a result and click those too.
* **safe-write filter** – unchanged from the original; no state-changing actions
  (payments, registrations, etc.) are executed.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Generator

from vtop_discovery.utils.logging import get_logger

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page
    from vtop_discovery.capture.network import NetworkCapture

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Login detection selectors
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Sidebar / navigation menu selectors (applied to top-level page only)
# ---------------------------------------------------------------------------
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
    # Broader fallback — every anchor in the sidebar wrapper
    "#wrapper a",
    ".left-side a",
)

# Accordion / treeview parents to expand so child links become visible
EXPANDABLE_SELECTORS = (
    ".sidebar li.has-treeview > a",
    ".sidebar .dropdown-toggle",
    ".nav-sidebar .has-treeview > a",
    ".menu-sidebar .has-treeview > a",
    ".sidebar li.treeview > a",
    "[data-toggle='collapse']",
    "[data-bs-toggle='collapse']",
)

# ---------------------------------------------------------------------------
# Content-area interactive element selectors (applied to ALL frames)
# ---------------------------------------------------------------------------
CONTENT_INTERACTIVE_SELECTORS = (
    # Tabs
    ".nav-tabs a",
    ".nav-tabs li a",
    ".nav-pills a",
    "[role='tab']",
    # Buttons
    "button:not([disabled])",
    "button.btn",
    "[role='button']",
    # Input buttons / submits
    "input[type='button']:not([disabled])",
    "input[type='submit']:not([disabled])",
    # Anchors with real hrefs or onclick handlers
    "a[onclick]",
    "a[href]:not([href=''])",
    # VTOP uses onclick on table cells for row-level detail loads
    "td[onclick]",
    "th[onclick]",
    # Clickable rows / cards
    "tr[onclick]",
    "[onclick]",
)

# ---------------------------------------------------------------------------
# Unsafe state-changing keywords — actions matching these are skipped
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_potentially_unsafe_action(text: str, href: str = "", name_or_id: str = "") -> bool:
    """Return True if the element looks like a state-changing write action."""
    haystack = f"{text} {href} {name_or_id}".lower()
    return any(kw in haystack for kw in UNSAFE_WRITE_KEYWORDS)


def is_logged_in(page: Page) -> bool:
    """Heuristic check for successful VTOP login."""
    try:
        for selector in LOGIN_INDICATOR_SELECTORS:
            if page.locator(selector).count() > 0:
                return True
    except Exception:
        pass
    return False


def wait_for_login(page: Page, timeout: float = 300.0) -> bool:
    """Block until login is detected or *timeout* seconds elapse."""
    logger.info("Waiting for user login to complete in browser (timeout: %.0fs)...", timeout)
    start = time.time()
    while time.time() - start < timeout:
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
    """Map a menu-item label to a short snake_case purpose string."""
    lowered = text.lower().strip()
    mapping = {
        "attend": "attendance",
        "mark": "marks",
        "grade": "marks",
        "timetable": "timetable",
        "time table": "timetable",
        "course": "courses",
        "regis": "courses",
        "profile": "profile",
        "student": "profile",
        "exam": "examinations",
        "hostel": "hostel",
        "library": "library",
        "faculty": "faculty",
        "pay": "payments",
        "fee": "payments",
        "transport": "transport",
        "scholar": "scholarships",
        "placement": "placements",
        "club": "clubs",
        "event": "events",
        "grievance": "grievances",
        "feedback": "feedback",
        "history": "academic_history",
        "result": "results",
        "alumni": "alumni",
    }
    for kw, purpose in mapping.items():
        if kw in lowered:
            return purpose
    return lowered.replace(" ", "_")[:24] or "unknown"


def _all_frames(page: Page) -> Generator[Frame, None, None]:
    """Yield the top-level page and every nested frame (handles VTOP's iframe layout)."""
    yield page  # type: ignore[misc]  # Page is also a Frame-like object
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        yield frame  # type: ignore[misc]


def _wait_for_network(page: Page, timeout_ms: int = 4000) -> None:
    """Wait for network to go idle, falling back to a fixed pause."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        page.wait_for_timeout(1500)


# ---------------------------------------------------------------------------
# Core crawl logic
# ---------------------------------------------------------------------------

def _exhaust_selects(frame: Frame, page: Page, timeout_ms: int = 4000) -> int:
    """
    For every ``<select>`` in *frame*, try **all** non-empty option values.
    Returns the number of option changes made.
    """
    changes = 0
    try:
        selects = frame.query_selector_all("select")
        for sel in selects:
            try:
                options = sel.query_selector_all("option")
                for opt in options:
                    val = opt.get_attribute("value")
                    if not val or not val.strip():
                        continue
                    try:
                        sel.select_option(value=val)
                        changes += 1
                        _wait_for_network(page, timeout_ms)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
    return changes


def _collect_interactive(frame: Frame) -> list[tuple[str, str, str, object]]:
    """
    Return a list of (text, href_or_empty, identifier, element_handle) tuples
    for every interactive element found in *frame*.
    """
    seen_keys: set[str] = set()
    results: list[tuple[str, str, str, object]] = []

    for selector in CONTENT_INTERACTIVE_SELECTORS:
        try:
            elements = frame.query_selector_all(selector)
            for el in elements:
                try:
                    text = (el.text_content() or el.get_attribute("value") or "").strip()
                    href = el.get_attribute("href") or ""
                    el_id = el.get_attribute("id") or ""
                    el_name = el.get_attribute("name") or ""
                    onclick = el.get_attribute("onclick") or ""

                    # Skip empty, logout, and unsafe items
                    label = text or href or el_id or onclick[:30]
                    if not label:
                        continue
                    if "logout" in label.lower():
                        continue
                    if is_potentially_unsafe_action(text, href=href, name_or_id=f"{el_id} {el_name}"):
                        continue

                    # Dedup key
                    key = f"{text}|{href}|{el_id}|{onclick[:40]}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    results.append((text, href, f"{el_id} {el_name}", el))
                except Exception:
                    pass
        except Exception:
            pass

    return results


def _crawl_frame_interactive(
    frame: Frame,
    page: Page,
    capture: NetworkCapture,
    stats: dict[str, int],
    visited_inner: set[str],
    timeout_ms: int = 4000,
    depth: int = 0,
) -> None:
    """
    Click every safe interactive element in *frame*, then recurse once to catch
    controls that only appear after a click.
    """
    if depth > 1:
        # Only recurse one level to avoid infinite loops
        return

    # 1. Exhaust selects first (semester/year dropdowns trigger important XHRs)
    _exhaust_selects(frame, page, timeout_ms)

    # 2. Collect and click all interactive elements
    items = _collect_interactive(frame)
    logger.debug("[frame %s] Found %d interactive elements at depth %d", frame.url[:60], len(items), depth)

    for text, href, ident, el in items:
        if stats["actions_performed"] >= stats["_max_actions"]:
            return

        key = f"{text}|{href}|{ident}"
        if key in visited_inner:
            continue
        visited_inner.add(key)

        label = text or href or ident.strip() or "?"
        if is_potentially_unsafe_action(text, href=href, name_or_id=ident):
            stats["unsafe_actions_skipped"] += 1
            continue

        try:
            # Re-locate by fresh query to avoid stale handle issues
            tag = el.get_property("tagName").json_value().lower()  # type: ignore[union-attr]
            el_id = el.get_attribute("id") or ""
            el_name = el.get_attribute("name") or ""

            if el_id:
                fresh = frame.query_selector(f"#{el_id}")
            elif el_name:
                fresh = frame.query_selector(f"[name='{el_name}']")
            elif text and tag in ("button", "a", "input"):
                fresh = frame.locator(f"text='{text}'").first.element_handle(timeout=1000)
            else:
                fresh = el  # type: ignore[assignment]

            if fresh is None:
                continue
            if not fresh.is_visible():
                continue

            logger.debug("  [CLICK] depth=%d '%s'", depth, label[:60])
            fresh.click(timeout=timeout_ms)
            stats["actions_performed"] += 1
            _wait_for_network(page, timeout_ms)

            # Recurse to discover controls revealed by this click
            if depth == 0:
                for sub_frame in _all_frames(page):
                    _crawl_frame_interactive(
                        sub_frame, page, capture, stats, visited_inner,
                        timeout_ms=timeout_ms, depth=depth + 1,
                    )

        except Exception as exc:
            logger.debug("  [SKIP] Could not click '%s': %s", label[:60], exc)


def _expand_menus(page: Page, timeout_ms: int = 4000) -> None:
    """Expand all accordion/treeview sidebar entries so child links are visible."""
    for selector in EXPANDABLE_SELECTORS:
        try:
            expandables = page.query_selector_all(selector)
            for btn in expandables:
                try:
                    txt = (btn.text_content() or "").strip()
                    if is_potentially_unsafe_action(txt):
                        continue
                    if btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(400)
                except Exception:
                    pass
        except Exception:
            pass


def _collect_menu_links(page: Page) -> list[tuple[str, str]]:
    """
    Return all unique (text, href) pairs from the sidebar navigation.
    Called after every menu expansion so dynamically-revealed items are included.
    """
    seen: set[str] = set()
    links: list[tuple[str, str]] = []

    for selector in MENU_SELECTORS:
        try:
            elements = page.query_selector_all(selector)
            for el in elements:
                try:
                    text = (el.text_content() or "").strip()
                    href = el.get_attribute("href") or ""
                    if not text:
                        continue
                    if "logout" in text.lower():
                        continue
                    if is_potentially_unsafe_action(text, href=href):
                        continue
                    key = f"{text}|{href}"
                    if key not in seen:
                        seen.add(key)
                        links.append((text, href))
                except Exception:
                    pass
        except Exception:
            pass

    return links


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def auto_crawl_vtop(
    page: Page,
    capture: NetworkCapture,
    max_pages: int = 500,
    max_actions: int = 2000,
    max_depth: int = 500,
    request_timeout: float = 5.0,
) -> dict[str, int]:
    """
    Exhaustively explore VTOP by:

    1. Expanding every sidebar accordion so all menu items are visible.
    2. Clicking every menu item (re-collecting after each expansion pass).
    3. For each loaded section: iterating ALL frames, exhausting ALL selects,
       and clicking every visible safe interactive element (tabs, buttons, links,
       onclick cells) — then recursing one level to catch dynamically-revealed
       controls.

    State-changing write operations are always skipped.
    """
    timeout_ms = int(request_timeout * 1000)

    stats: dict[str, int] = {
        "pages_visited": 0,
        "actions_performed": 0,
        "unsafe_actions_skipped": 0,
        "_max_actions": max_actions,  # internal sentinel consumed by helpers
    }

    # Wait for initial page to settle
    _wait_for_network(page, timeout_ms)

    # -----------------------------------------------------------------------
    # Phase 1: Expand all sidebar menus then collect every link
    # -----------------------------------------------------------------------
    logger.info("Phase 1: Expanding navigation menus...")
    _expand_menus(page, timeout_ms)

    menu_links = _collect_menu_links(page)
    logger.info("Discovered %d navigation menu links to explore.", len(menu_links))

    # Visited set for top-level menu navigation
    visited_menu: set[str] = set()

    # -----------------------------------------------------------------------
    # Phase 2: Navigate each menu section and do deep inner-page exploration
    # -----------------------------------------------------------------------
    logger.info("Phase 2: Visiting each section and crawling all frames...")

    for text, href in menu_links[:max_depth]:
        if stats["pages_visited"] >= max_pages or stats["actions_performed"] >= max_actions:
            logger.info(
                "Crawl limits reached (pages: %d/%d, actions: %d/%d).",
                stats["pages_visited"], max_pages,
                stats["actions_performed"], max_actions,
            )
            break

        menu_key = f"{text}|{href}"
        if menu_key in visited_menu:
            continue
        visited_menu.add(menu_key)

        purpose = _purpose_from_label(text)
        print(f"[PAGE] {text}  ({purpose})")
        logger.info("[PAGE] Navigating to section '%s' [%s]...", text, purpose)

        capture.start_phase(purpose)
        try:
            # Re-locate the element fresh to avoid stale handle errors
            clicked = False
            if href and href not in ("#", "javascript:void(0)", ""):
                try:
                    page.goto(
                        href if href.startswith("http") else f"https://vtop.vit.ac.in{href}",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                try:
                    locator = page.locator(f"text='{text}'").first
                    if locator.count() > 0 and locator.is_visible():
                        locator.click(timeout=timeout_ms)
                        clicked = True
                except Exception:
                    pass

            if not clicked:
                logger.debug("[SKIP] Could not activate menu item '%s'", text)
                continue

            stats["pages_visited"] += 1
            stats["actions_performed"] += 1
            _wait_for_network(page, timeout_ms)

            # After a menu section loads, re-expand in case new sub-items appeared
            _expand_menus(page, timeout_ms)

            # Visit every frame in the now-loaded page
            visited_inner: set[str] = set()
            for frame in _all_frames(page):
                frame_url = frame.url if hasattr(frame, "url") else "?"
                logger.debug("  [FRAME] Crawling frame: %s", frame_url[:80])
                _crawl_frame_interactive(
                    frame, page, capture, stats, visited_inner,
                    timeout_ms=timeout_ms, depth=0,
                )

            logger.info(
                "  Done with '%s' — total actions so far: %d", text, stats["actions_performed"]
            )

        except Exception as exc:
            logger.warning("Error crawling menu item '%s': %s", text, exc)
        finally:
            capture.stop_phase()

    stats.pop("_max_actions", None)  # clean up internal sentinel
    logger.info(
        "Crawl complete. Pages visited: %d, actions: %d, unsafe skipped: %d.",
        stats["pages_visited"], stats["actions_performed"], stats["unsafe_actions_skipped"],
    )
    return stats
