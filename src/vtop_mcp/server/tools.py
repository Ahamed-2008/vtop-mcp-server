"""Tool registrations: high-level, read-only MCP tools.

Each tool is narrow, idempotent and typed. The tool → endpoint → parser
mapping lives in ``docs/vtop-endpoints.md``; the MCP layer never constructs
VTOP requests directly — it calls the service layer only.
"""

from __future__ import annotations

import json
from typing import Awaitable, Callable, Optional

from mcp.types import TextContent, Tool
from pydantic import BaseModel

from ..errors import VTopError
from ..logging_setup import get_logger, new_correlation_id, set_correlation_id
from ..metrics import Metrics
from ..services import AcademicService
from ..vtop.auth import AuthManager
from .schemas import (
    AttendanceRows,
    AssignmentList,
    CGPA,
    CGPAComposite,
    CourseList,
    EventList,
    FeedbackList,
    MarksInfo,
    ProctorMessage,
    SessionStatus,
)

log = get_logger("server.tools")

NO_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class ToolSpec:
    """Name, description, schema, and async call-time handler for one tool."""

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable[[], Awaitable[BaseModel]],
        output_model: type[BaseModel],
    ) -> None:
        self.name = name
        self.description = description
        self.handler = handler
        self.output_model = output_model

    def to_mcp_tool(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=NO_ARGS_SCHEMA,
        )


async def _encode(model: BaseModel) -> list[TextContent]:
    return [TextContent(type="text", text=model.model_dump_json(exclude_none=True))]


async def _run_tool(
    name: str,
    status: Metrics,
    fn: Awaitable[BaseModel],
) -> list[TextContent]:
    """Execute one tool call with correlation id + error mapping."""
    set_correlation_id(new_correlation_id())
    try:
        result = await fn
        status.tool_calls[name] += 1
        return await _encode(result)
    except VTopError as exc:
        status.tool_errors[name] += 1
        log.error("tool %s failed", name, extra={"error_code": exc.code})
        raise _to_mcp_error(exc)
    except Exception:  # noqa: BLE001 - never leak internals to the model
        status.tool_errors[name] += 1
        log.exception("tool %s raised an unexpected error", name)
        raise _to_mcp_error(VTopError("An unexpected internal error occurred.", code="INTERNAL_ERROR"))


def _to_mcp_error(exc: VTopError):
    from mcp.shared.exceptions import MCPError

    payload = exc.to_mcp_payload()
    return MCPError(code=-32603, message=payload["message"], data=payload)


_B = Callable[[], Awaitable[BaseModel]]


def build_tools(service: AcademicService, auth: AuthManager, metrics: Metrics) -> list[ToolSpec]:
    specs = [
        ToolSpec(
            "get_academic_summary",
            "Return a concise academic overview: current CGPA, earned/required credits, the current semester "
            "label, and a compact list of courses with attendance percentages and remarks. Requires an "
            "authenticated VTOP session. Errors: AUTHENTICATION_REQUIRED, SESSION_EXPIRED, VTOP_UNAVAILABLE, "
            "VTOP_PARSE_ERROR.",
            lambda: _run_tool("get_academic_summary", metrics, service.get_academic_summary()),
            CGPAComposite,
        ),
        ToolSpec(
            "get_cgpa",
            "Return the authenticated student's current CGPA, earned credits, and total credits required as "
            "reported by VTOP. (VTOP's current-credits endpoint does not supply a GPA field, so it is "
            "omitted.) Requires authentication. Errors: AUTHENTICATION_REQUIRED, SESSION_EXPIRED, "
            "VTOP_UNAVAILABLE, VTOP_PARSE_ERROR.",
            lambda: _run_tool("get_cgpa", metrics, service.get_cgpa()),
            CGPA,
        ),
        ToolSpec(
            "get_current_courses",
            "Return the current semester course registration details from VTOP: course code, name, type, and "
            "attendance percentage/remark per course. Requires authentication. Errors: "
            "AUTHENTICATION_REQUIRED, SESSION_EXPIRED, VTOP_UNAVAILABLE, VTOP_PARSE_ERROR.",
            lambda: _run_tool("get_current_courses", metrics, service.get_courses()),
            CourseList,
        ),
        ToolSpec(
            "get_attendance",
            "Return attendance percentages and remarks per course for the current semester exactly as VTOP "
            "reports them. Derived from the same VTOP response as get_current_courses and shared with the "
            "cache — no duplicate VTOP request. Requires authentication. Errors: AUTHENTICATION_REQUIRED, "
            "SESSION_EXPIRED, VTOP_UNAVAILABLE.",
            lambda: _run_tool("get_attendance", metrics, _attendance(service)),
            AttendanceRows,
        ),
        ToolSpec(
            "get_marks",
            "Report the marks information currently available through VTOP's course-details endpoint. The "
            "captured VTOP response exposes attendance/remarks only, so this tool does not fabricate marks or "
            "assessment components; availability is reported explicitly. Requires authentication.",
            lambda: _run_tool("get_marks", metrics, service.get_marks()),
            MarksInfo,
        ),
        ToolSpec(
            "get_assignments",
            "Return upcoming digital assignments (course, title, last date) as listed by VTOP. Requires "
            "authentication. Errors: AUTHENTICATION_REQUIRED, SESSION_EXPIRED, VTOP_UNAVAILABLE.",
            lambda: _run_tool("get_assignments", metrics, service.get_assignments()),
            AssignmentList,
        ),
        ToolSpec(
            "get_events",
            "Return scheduled events grouped by day (title, category, date, organizer) as listed by VTOP. "
            "Requires authentication. Errors: AUTHENTICATION_REQUIRED, SESSION_EXPIRED, VTOP_UNAVAILABLE.",
            lambda: _run_tool("get_events", metrics, service.get_events()),
            EventList,
        ),
        ToolSpec(
            "get_feedback",
            "Return the last five feedback entries (feedback, category, status) as listed by VTOP. Requires "
            "authentication. Errors: AUTHENTICATION_REQUIRED, SESSION_EXPIRED, VTOP_UNAVAILABLE.",
            lambda: _run_tool("get_feedback", metrics, service.get_feedback()),
            FeedbackList,
        ),
        ToolSpec(
            "get_proctor_message",
            "Return the dashboard proctor message published for the authenticated student, if any. Requires "
            "authentication.",
            lambda: _run_tool("get_proctor_message", metrics, service.get_proctor_message()),
            ProctorMessage,
        ),
        ToolSpec(
            "get_session_status",
            "Report whether an authenticated, non-expired VTOP session is available. Performs a lightweight "
            "session validity probe against VTOP and returns only {'authenticated': bool, 'detail': str} — "
            "never cookies or tokens.",
            lambda: _run_tool("get_session_status", metrics, _session_status(auth)),
            SessionStatus,
        ),
    ]
    return specs


async def _attendance(service: AcademicService) -> AttendanceRows:
    rows = await service.get_attendance()
    return AttendanceRows(attendance=rows)  # type: ignore[arg-type]


async def _session_status(auth: AuthManager) -> SessionStatus:
    alive = await auth.probe()
    if alive:
        return SessionStatus(authenticated=True, detail="Authenticated VTOP session is valid.")
    return SessionStatus(
        authenticated=False,
        detail="No valid VTOP session. Run `vtop-mcp login` to authenticate (CAPTCHA is manual).",
    )


def tool_specs_to_mcp(specs: list[ToolSpec]) -> list[Tool]:
    return [s.to_mcp_tool() for s in specs]


__all__ = ["ToolSpec", "build_tools", "tool_specs_to_mcp"]