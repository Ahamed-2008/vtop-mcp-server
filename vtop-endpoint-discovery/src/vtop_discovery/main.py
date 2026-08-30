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
from vtop_discovery.browser.crawler import auto_crawl_vtop, wait_for_login
from vtop_discovery.browser.launcher import DEFAULT_URL, launch_browser
from vtop_discovery.capture.network import NetworkCapture
from vtop_discovery.storage.models import CapturedExchange, Endpoint
from vtop_discovery.storage.writer import DEFAULT_BASE_URL, write_catalog, write_raw_captures
from vtop_discovery.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)

# Configurable Guided Discovery Targets (§7)
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
        description="Record authenticated VTOP browser traffic and export an analyzed, redacted endpoint catalog.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output/endpoints.json"),
        help="Path to write the clean analyzed endpoint catalog (default: output/endpoints.json)",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory to store raw captures for debugging (default: captures/)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"Initial URL to open in the browser (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "-a",
        "--auto",
        action="store_true",
        default=True,
        help="Enable automated crawler mode: after login, automatically click menus and record endpoints (default: enabled)",
    )
    parser.add_argument(
        "-g",
        "--guided",
        action="store_true",
        help="Run guided step-by-step discovery mode with explicit section prompts",
    )
    parser.add_argument(
        "-d",
        "--diff",
        type=Path,
        default=None,
        metavar="OLD_CATALOG",
        help="Compare an existing catalog JSON against --output without running browser discovery",
    )
    parser.add_argument(
        "-v",
        "--debug",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args(args)


def run_guided_discovery(page, capture: NetworkCapture) -> None:
    print("\n" + "=" * 60)
    print("  VTOP GUIDED ENDPOINT DISCOVERY ACTIVE")
    print("=" * 60)
    print("Step 1: Complete login (including captcha) in the browser window.")
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
    print("Guided discovery completed. Finalizing catalog...")
    print("=" * 60 + "\n")


def run_auto_crawler(page, capture: NetworkCapture) -> None:
    print("\n" + "=" * 60)
    print("  VTOP AUTOMATED CRAWLER MODE ACTIVE")
    print("=" * 60)
    print("1. Complete login (with captcha) in the opened browser window.")
    print("2. Once logged in, the tool will automatically crawl VTOP menus")
    print("   and record endpoints.")
    print("=" * 60 + "\n")

    if wait_for_login(page, timeout=300.0):
        auto_crawl_vtop(page, capture)
    else:
        logger.warning("Automated crawler finished without detecting login.")


def process_pipeline(exchanges: list[CapturedExchange], base_url: str = DEFAULT_BASE_URL) -> list[Endpoint]:
    """Execute analysis pipeline: filter -> deduplicate -> request analysis -> response analysis -> classification."""
    # 1. Filter out static/tracker noise
    filtered = [ex for ex in exchanges if is_interesting(ex)]
    logger.info("Retained %d relevant application exchanges after filtering", len(filtered))

    # 2. Deduplicate into endpoints
    endpoints = deduplicate(filtered)
    logger.info("Generated %d unique endpoint signatures", len(endpoints))

    # 3. Request schema analysis
    for ep in endpoints:
        analyze_request_parameters(ep)

    # 4. Response analysis
    for ep in endpoints:
        analyze_response(ep)

    # 5. Endpoint classification
    for ep in endpoints:
        classify_endpoint(ep)

    return endpoints


def run_discovery(
    output_path: Path,
    captures_dir: Path,
    url: str = DEFAULT_URL,
    guided: bool = False,
    auto: bool = True,
) -> None:
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else DEFAULT_BASE_URL

    logger.info("Starting VTOP endpoint discovery session...")
    capture: NetworkCapture | None = None

    def _init_capture(context):
        nonlocal capture
        capture = NetworkCapture(context)
        capture.attach()

    with launch_browser(url=url, on_context=_init_capture) as (_playwright, _browser, _context, page):
        assert capture is not None

        try:
            if guided:
                run_guided_discovery(page, capture)
            elif auto:
                run_auto_crawler(page, capture)
            else:
                print("\n" + "=" * 60)
                print("  VTOP ENDPOINT DISCOVERY ACTIVE")
                print("=" * 60)
                print("1. Complete login (with captcha) in the browser window.")
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

    # Save raw captures for debugging (§9)
    raw_path = write_raw_captures(capture.exchanges, captures_dir=captures_dir)

    # Run analysis pipeline (§1)
    endpoints = process_pipeline(capture.exchanges, base_url=base_url)

    # Save clean analyzed catalog (§8)
    write_catalog(endpoints, output_path, base_url=base_url)

    # Display session summary (§12)
    print("\n" + "=" * 60)
    print("  DISCOVERY & ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Total raw requests captured:      {total_captured}")
    print(f"Discovered unique endpoints:     {len(endpoints)}")
    print(f"Clean catalog output:            {output_path.resolve()}")
    print(f"Raw capture debugging record:    {raw_path.resolve()}")
    print("\nDiscovered Endpoints Summary:")
    print("-" * 60)
    for ep in endpoints:
        print(f"  • {ep.method} {ep.path}")
        print(f"    Category:   {ep.category}")
        print(f"    Purpose:    {ep.purpose} (confidence: {ep.confidence:.2f})")
        if ep.evidence:
            print(f"    Evidence:   {', '.join(ep.evidence)}")
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
            run_discovery(
                output_path=args.output,
                captures_dir=args.captures_dir,
                url=args.url,
                guided=args.guided,
                auto=not args.guided and args.auto,
            )
    except Exception as exc:
        logger.error("Error during execution: %s", exc, exc_info=args.debug)
        sys.exit(1)


if __name__ == "__main__":
    main()
