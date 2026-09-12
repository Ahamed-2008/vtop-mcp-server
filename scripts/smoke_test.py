"""Smoke test for the new tools MCP server (mcp_server.py).

Spawns ``python -m mcp_server`` over stdio, verifies the tool list, calls
every read-only tool against the live persisted VTOP session, and asserts
each response has the expected shape. ``submit_leave`` is only invoked
without ``confirm=True`` to check it is refused (it never writes).

Requires a valid session file (default ``.vtop-session/session.json``), so
run ``vtop-mcp login`` (host) or ``docker exec -it vtop-mcp vtop-mcp login``
first. The optional ``semester_sub_id`` for grade checks defaults to
``VL20252601`` (a past semester that has published grades).

Usage (from the repository root):

    .venv/bin/python scripts/smoke_test.py                # run all checks
    .venv/bin/python scripts/smoke_test.py --tool get_cgpa_credits

Exit code: 0 = all passed, 1 = a check failed, 2 = no usable session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"

EXPECTED_TOOLS = {
    "get_attendance",
    "get_cgpa_credits",
    "get_digital_assignments",
    "get_employee_profile",
    "get_exam_schedule",
    "get_grades",
    "get_hod_dean_details",
    "get_leave_status",
    "get_marks",
    "get_timetable",
    "search_employee",
    "submit_leave",
}

GRADES_SEMESTER = "VL20252601"
CALL_TIMEOUT = 45.0

PASSED: list[str] = []
FAILED: list[str] = []


def _text(result) -> str:
    return "; ".join(c.text for c in result.content if getattr(c, "type", "") == "text")


def _check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  | ' + detail if detail else ''}", flush=True)


async def _call(session, name: str, args: dict):
    return await asyncio.wait_for(session.call_tool(name, args), timeout=CALL_TIMEOUT)


async def run(only: tuple[str, ...] | None) -> int:
    server = StdioServerParameters(
        command=str(PYTHON),
        args=["-m", "mcp_server"],
        cwd=str(ROOT),
        env=None,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = {t.name for t in (await session.list_tools()).tools}
            missing = sorted(EXPECTED_TOOLS - tools)
            _check("tool-list-complete", not missing, f"missing={missing}")

            if only:
                targets = [n for n in only if n in EXPECTED_TOOLS]
            else:
                targets = sorted(EXPECTED_TOOLS - {"submit_leave"})

            for name in targets:
                try:
                    await _route(session, name)
                except Exception as exc:  # noqa: BLE001 - report loudly, keep going
                    _check(name, False, f"{type(exc).__name__}: {str(exc)[:200]}")

            # submit_leave must be refused without explicit confirmation
            if only is None or "submit_leave" in only:
                result = await _call(
                    session,
                    "submit_leave",
                    {
                        "leave_code": "L1",
                        "visiting_place": "Home",
                        "from_date": "2026-09-20",
                        "from_time": "18:00",
                        "to_date": "2026-09-21",
                        "to_time": "20:00",
                        "reason": "smoke test",
                        "confirm": False,
                    },
                )
                _check("submit_leave-refused-without-confirm", result.is_error)

    return 1 if FAILED else 0


async def _route(session, name: str) -> None:
    if name == "get_cgpa_credits":
        res = await _call(session, name, {})
        data = _loads(res, name)[0]
        detail = f"keys={sorted(data) if isinstance(data, dict) else type(data).__name__}"
        _check(name, isinstance(data, dict) and "cgpa" in data, detail)
    elif name == "get_attendance":
        data = _loads(await _call(session, name, {}), name)
        ok = isinstance(data, list) and (not data or "Course Detail" in data[0])
        _check(name, ok, f"rows={len(data) if isinstance(data, list) else '?'}")
    elif name == "get_timetable":
        data = _loads(await _call(session, name, {}), name)[0]
        ok = isinstance(data, dict) and "courses" in data and "grid" in data
        _check(name, ok, f"courses={len(data['courses']) if isinstance(data, dict) else '?'}")
    elif name == "get_exam_schedule":
        data = _loads(await _call(session, name, {}), name)
        _check(name, isinstance(data, list), f"rows={len(data)}")
    elif name == "get_digital_assignments":
        data = _loads(await _call(session, name, {}), name)
        _check(name, isinstance(data, list), f"rows={len(data)}")
    elif name == "get_marks":
        data = _loads(await _call(session, name, {}), name)
        ok = isinstance(data, list) and (not data or "course_code" in data[0])
        _check(name, ok, f"courses={len(data) if isinstance(data, list) else '?'}")
    elif name == "get_grades":
        data = _loads(await _call(session, name, {"semester_sub_id": GRADES_SEMESTER}), name)
        ok = isinstance(data, list) and (not data or "Course Code" in data[0])
        _check(name, ok, f"courses={len(data) if isinstance(data, list) else '?'}")
    elif name == "search_employee":
        res = await _call(session, name, {"search_term": "BOOMINATHAN"})
        data = _loads(res, name)
        ok = isinstance(data, list) and bool(data) and "emp_id" in data[0]
        _check(name, ok, f"hits={len(data) if isinstance(data, list) else '?'}")
    elif name == "get_employee_profile":
        res = await _call(session, name, {"emp_id": "12392"})
        data = _loads(res, name)[0]
        ok = isinstance(data, dict) and data.get("email")
        _check(name, ok, f"email={data.get('email') if isinstance(data, dict) else '?'}")
    elif name == "get_hod_dean_details":
        data = _loads(await _call(session, name, {}), name)[0]
        ok = isinstance(data, dict) and set(data) >= {"dean", "hod"}
        _check(name, ok, f"keys={sorted(data) if isinstance(data, dict) else '?'}")
    elif name == "get_leave_status":
        res = await _call(session, name, {})
        _check(name, not res.is_error, _text(res)[:120])
    else:
        _check(name, False, "no route")  # pragma: no cover


def _loads(result, name: str):
    if result.is_error:
        raise AssertionError(_text(result)[:300])
    items = [json.loads(c.text) for c in result.content if getattr(c, "type", "") == "text"]
    if not items:
        raise AssertionError("no text content in result")
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the vtop tools MCP server.")
    parser.add_argument(
        "--tool",
        nargs="+",
        default=None,
        help="Only run specific tools (default: all read-only tools + refusal check).",
    )
    args = parser.parse_args()
    only = tuple(args.tool) if args.tool else None
    try:
        code = asyncio.run(run(only))
    except Exception as exc:  # transport-level failure (bad session, port, etc.)
        print(f"smoke test aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return code


if __name__ == "__main__":
    raise SystemExit(main())