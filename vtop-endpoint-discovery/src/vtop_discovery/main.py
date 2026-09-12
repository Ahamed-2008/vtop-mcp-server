from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

from vtop_discovery.analysis.classifier import classify_endpoint
from vtop_discovery.analysis.deduplicator import deduplicate
from vtop_discovery.analysis.diff import diff_catalogs, format_diff, load_catalog
from vtop_discovery.analysis.filter import is_interesting
from vtop_discovery.analysis.request_analyzer import analyze_request_parameters
from vtop_discovery.analysis.response_analyzer import analyze_response
from vtop_discovery.analysis.workflow_detector import detect_workflows
from vtop_discovery.browser.crawler import auto_crawl_vtop, wait_for_login
from vtop_discovery.browser.launcher import DEFAULT_URL, launch_browser
from vtop_discovery.capture.network import NetworkCapture
from vtop_discovery.storage.models import CapturedExchange, Endpoint, Workflow
from vtop_discovery.storage.writer import DEFAULT_BASE_URL, write_inventory, write_raw_captures
from vtop_discovery.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)

# Configurable Guided Discovery Targets
GUIDED_TARGETS: tuple[tuple[str, str], ...] = (
    ("Attendance", "attendance"),
    ("Marks", "marks"),
    ("Timetable", "timetable"),
    ("Courses & Registration", "courses"),
    ("Student Profile", "profile"),
    ("Examinations", "exam_schedule"),
    ("Academic History", "academic_history"),
)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vtop-discover",
        description="Automated VTOP browser network capture, endpoint discovery, and workflow dependency analyzer.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output/endpoint_inventory.json"),
        help="Path to write the clean endpoint inventory JSON (default: output/endpoint_inventory.json)",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory to store raw debugging captures (default: captures/)",
    )
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Path to stored VTOP session JSON file (default: .vtop-session/session.json if found)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"Initial URL to open in the browser (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        default=True,
        help="Run browser in visible headed mode (default: enabled)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless background mode",
    )
    parser.add_argument(
        "-a",
        "--auto",
        action="store_true",
        default=True,
        help="Enable automated safe crawler mode after login (default: enabled)",
    )
    parser.add_argument(
        "-g",
        "--guided",
        action="store_true",
        help="Run guided step-by-step discovery mode with interactive section prompts",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum navigation pages/sections to visit (default: 50)",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=100,
        help="Maximum click/select actions to perform during crawl (default: 100)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=50,
        help="Maximum menu discovery depth (default: 50)",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=4.0,
        help="Timeout in seconds when waiting for page/network actions (default: 4.0)",
    )
    parser.add_argument(
        "-d",
        "--diff",
        type=Path,
        default=None,
        metavar="OLD_CATALOG",
        help="Compare an existing catalog/inventory JSON against --output without running browser discovery",
    )
    parser.add_argument(
        "-v",
        "--debug",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args(args)


def run_guided_discovery(page, capture: NetworkCapture) -> dict[str, int]:
    print("\n" + "=" * 60)
    print("  VTOP GUIDED ENDPOINT DISCOVERY ACTIVE")
    print("=" * 60)
    print("Step 1: Complete login (including CAPTCHA) in the browser window if not already authenticated.")
    wait_for_login(page, timeout=300.0)

    total_steps = len(GUIDED_TARGETS)
    for idx, (label, purpose) in enumerate(GUIDED_TARGETS, start=1):
        print("\n" + "-" * 60)
        print(f"[{idx}/{total_steps}] Action: Open your '{label}' page in VTOP.")
        print("-" * 60)
        capture.start_phase(purpose)
        try:
            input(f"Press [Enter] when done browsing '{label}': ")
        finally:
            capture.stop_phase()

    print("\n" + "=" * 60)
    print("Guided discovery completed. Finalizing inventory...")
    print("=" * 60 + "\n")
    return {"pages_visited": total_steps, "actions_performed": total_steps, "unsafe_actions_skipped": 0}


def run_auto_crawler(
    page,
    capture: NetworkCapture,
    max_pages: int = 50,
    max_actions: int = 100,
    max_depth: int = 50,
    request_timeout: float = 4.0,
) -> dict[str, int]:
    print("\n" + "=" * 60)
    print("  VTOP AUTOMATED SAFE CRAWLER ACTIVE")
    print("=" * 60)
    print("1. Complete login (with CAPTCHA) if not using a restored session.")
    print("2. The crawler will automatically explore safe read-only menus and tabs.")
    print("3. State-changing write actions will be automatically skipped.")
    print("=" * 60 + "\n")

    if wait_for_login(page, timeout=300.0):
        return auto_crawl_vtop(
            page,
            capture,
            max_pages=max_pages,
            max_actions=max_actions,
            max_depth=max_depth,
            request_timeout=request_timeout,
        )
    else:
        logger.warning("Automated crawler finished without detecting active login.")
        return {"pages_visited": 0, "actions_performed": 0, "unsafe_actions_skipped": 0}


def process_pipeline(
    exchanges: list[CapturedExchange],
    base_url: str = DEFAULT_BASE_URL,
) -> tuple[list[Endpoint], list[Workflow]]:
    """Execute analysis pipeline: filter -> deduplicate -> request analysis -> response analysis -> classification -> workflow detection."""
    # 1. Filter out static/tracker noise
    filtered = [ex for ex in exchanges if is_interesting(ex)]
    logger.info("Retained %d relevant application exchanges after filtering", len(filtered))

    # 2. Deduplicate into endpoints
    endpoints = deduplicate(filtered)
    logger.info("[DISCOVERY] %d unique VTOP endpoint signatures identified", len(endpoints))

    # 3. Request schema analysis
    for ep in endpoints:
        analyze_request_parameters(ep)
        for p_name, p_schema in ep.request.parameters.items():
            logger.debug("[PARAMETER] %s (location: %s, type: %s)", p_name, p_schema.location, p_schema.type)

    # 4. Response analysis
    for ep in endpoints:
        analyze_response(ep)

    # 5. Endpoint classification
    for ep in endpoints:
        classify_endpoint(ep)
        logger.info("[NEW ENDPOINT] %s %s -> %s (%s, conf: %.2f)", ep.method, ep.path, ep.purpose, ep.classification, ep.confidence)

    # 6. Workflow & dependency detection
    workflows = detect_workflows(filtered)
    logger.info("Detected %d multi-step workflows with producer-consumer dependencies", len(workflows))

    return endpoints, workflows


def run_discovery(
    output_path: Path,
    captures_dir: Path,
    session_path: Path | None = None,
    url: str = DEFAULT_URL,
    headless: bool = False,
    guided: bool = False,
    auto: bool = True,
    max_pages: int = 50,
    max_actions: int = 100,
    max_depth: int = 50,
    request_timeout: float = 4.0,
) -> None:
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else DEFAULT_BASE_URL

    logger.info("Starting VTOP endpoint discovery session...")
    capture: NetworkCapture | None = None

    def _init_capture(context):
        nonlocal capture
        capture = NetworkCapture(context)
        capture.attach()

    crawl_stats = {"pages_visited": 0, "actions_performed": 0, "unsafe_actions_skipped": 0}

    with launch_browser(
        url=url,
        headless=headless,
        session_path=session_path,
        on_context=_init_capture,
    ) as (_playwright, _browser, _context, page):
        assert capture is not None

        try:
            if guided:
                crawl_stats = run_guided_discovery(page, capture)
            elif auto:
                crawl_stats = run_auto_crawler(
                    page,
                    capture,
                    max_pages=max_pages,
                    max_actions=max_actions,
                    max_depth=max_depth,
                    request_timeout=request_timeout,
                )
            else:
                print("\n" + "=" * 60)
                print("  VTOP ENDPOINT DISCOVERY ACTIVE (Manual Browsing)")
                print("=" * 60)
                print("1. Complete login (with CAPTCHA) if not using a restored session.")
                print("2. Navigate through sections (Attendance, Marks, Timetable, etc.).")
                print("3. When finished, press ENTER here or close the browser.")
                print("=" * 60 + "\n")
                input("Press [Enter] when you have finished browsing to save the catalog: ")
        except (KeyboardInterrupt, EOFError):
            print("\nFinalizing capture...")
        finally:
            capture.detach()

    total_captured = len(capture.exchanges)
    logger.info("Captured %d raw HTTP exchanges", total_captured)

    # Save raw captures for debugging
    raw_path = write_raw_captures(capture.exchanges, captures_dir=captures_dir)

    # Run analysis pipeline
    endpoints, workflows = process_pipeline(capture.exchanges, base_url=base_url)

    # Save clean analyzed inventory JSON
    write_inventory(endpoints, output_path, workflows=workflows, base_url=base_url)

    # Count skipped unsafe write endpoints
    unsafe_skipped = crawl_stats.get("unsafe_actions_skipped", 0) + sum(
        1 for ep in endpoints if ep.classification == "UNKNOWN_WRITE_OR_UNSAFE"
    )

    # Display session summary
    print("\n" + "=" * 60)
    print("  DISCOVERY COMPLETE")
    print("=" * 60)
    print(f"Pages visited:                    {crawl_stats.get('pages_visited', 0)}")
    print(f"Requests captured:                {total_captured}")
    print(f"Unique VTOP endpoints:            {len(endpoints)}")
    print(f"Potential write endpoints skipped:{unsafe_skipped}")
    print(f"Workflows detected:               {len(workflows)}")
    print(f"Clean inventory output:           {output_path.resolve()}")
    print(f"Raw capture debugging record:     {raw_path.resolve()}")
    print("\nDiscovered Endpoints Summary:")
    print("-" * 60)
    for ep in endpoints:
        print(f"  • [{ep.classification}] {ep.method} {ep.path}")
        print(f"    Purpose:     {ep.purpose} (confidence: {ep.confidence:.2f})")
        if ep.request.parameters:
            params_str = ", ".join(f"{k} ({v.location})" for k, v in ep.request.parameters.items())
            print(f"    Parameters:  {params_str}")
        if ep.evidence:
            print(f"    Evidence:    {', '.join(ep.evidence[:2])}")
        print()

    if workflows:
        print("Discovered Workflows & Data Dependencies:")
        print("-" * 60)
        for wf in workflows:
            print(f"  • {wf.name}: {' -> '.join(wf.steps)}")
            for dep in wf.dependencies:
                print(f"      ↳ param '{dep.parameter}' produced by {dep.produced_by} -> consumed by {dep.consumed_by}")
        print()

    print("=" * 60 + "\n")


def run_diff(old_path: Path, new_path: Path) -> None:
    if not old_path.exists():
        logger.error("Old catalog file does not exist: %s", old_path)
        sys.exit(1)
    if not new_path.exists():
        logger.error("Target catalog file does not exist: %s", new_path)
        sys.exit(1)

    old_cat = load_catalog(old_path)
    new_cat = load_catalog(new_path)

    diff = diff_catalogs(old_cat, new_cat)
    print(format_diff(diff))


def main() -> None:
    args = parse_args()
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)

    try:
        if args.diff:
            run_diff(old_path=args.diff, new_path=args.output)
        else:
            is_headless = bool(args.headless and not args.headed)
            run_discovery(
                output_path=args.output,
                captures_dir=args.captures_dir,
                session_path=args.session,
                url=args.url,
                headless=is_headless,
                guided=args.guided,
                auto=not args.guided and args.auto,
                max_pages=args.max_pages,
                max_actions=args.max_actions,
                max_depth=args.max_depth,
                request_timeout=args.request_timeout,
            )
    except Exception as exc:
        logger.error("Error during execution: %s", exc, exc_info=args.debug)
        sys.exit(1)


if __name__ == "__main__":
    main()

