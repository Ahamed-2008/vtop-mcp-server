"""VTOP service layer.

Combines the VTOP HTTP client, response parsers, and caching into clean
methods used by the MCP tool layer. No MCP concepts live here. All read
methods gate on an authenticated session and return typed pydantic models.
"""

from __future__ import annotations

from ..config import Settings
from ..models import (
    Assignment,
    AssignmentList,
    AttendanceSummary,
    CGPA,
    CGPAComposite,
    Course,
    CourseList,
    EventList,
    FeedbackList,
    MarksInfo,
    ProctorMessage,
)
from ..logging_setup import get_logger
from ..metrics import Metrics
from ..redaction import Redactor
from ..vtop.auth import AuthManager
from ..vtop.cache import TTLCache
from ..vtop.client import VTOPClient
from ..vtop.parsers import AssignmentParser, CGPAParser, CourseParser, EventParser, FeedbackParser, ProctorParser

log = get_logger("services.academic")


class AcademicService:
    def __init__(self, auth: AuthManager, settings: Settings, metrics: Metrics, redactor: Redactor) -> None:
        self._auth = auth
        self._client = auth._client  # noqa: SLF001  (client is private to auth; service is a peer layer)
        self._metrics = metrics
        self._settings = settings
        self._cache: TTLCache = TTLCache(settings.cache_ttl)

    @property
    def client(self) -> VTOPClient:
        return self._client

    def _key(self, name: str) -> str:
        session = self._client.session
        cid = session.authorized_id if session else "anon"
        return f"{cid}:{name}"

    # ------------------------------------------------------------------ CGPA
    async def get_cgpa(self, *, use_cache: bool = True) -> CGPA:
        await self._auth.ensure_session()
        key = self._key("cgpa")
        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        raw = await self._client.get_cgpa()
        result = CGPAParser(raw).parse()
        if use_cache:
            self._cache.set(key, result)
        return result

    # -------------------------------------------------------------- courses
    async def get_courses(self, *, use_cache: bool = True) -> CourseList:
        await self._auth.ensure_session()
        key = self._key("courses")

        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        raw = await self._client.get_course_details()
        result = CourseParser(raw).parse()
        if use_cache:
            self._cache.set(key, result)
        return result

    async def get_attendance(self) -> list[dict]:
        """Attendance rows derived from the (cached) course-details response.

        One VTOP request is made at most: a cached CourseList is reused.
        """
        courses = await self.get_courses()
        rows = []
        for c in courses.courses:
            rows.append(
                {
                    "course_code": c.course_code,
                    "course_name": c.course_name,
                    "course_type": c.course_type,
                    "percentage": c.attendance.percentage if c.attendance else None,
                    "remark": c.attendance.remark if c.attendance else None,
                }
            )
        return rows

    async def get_marks(self) -> MarksInfo:
        """Marks availability report derived from the course-details response."""
        await self.get_courses()  # fetch (and cache) the same underlying data
        return MarksInfo()  # no marks columns in the captured response

    async def get_course_summary(self) -> AttendanceSummary:
        courses = await self.get_courses()
        flagged = [
            c.course_code
            for c in courses.courses
            if c.attendance and c.attendance.remark and any(k in (c.attendance.remark or "").lower() for k in ("caution", "risk", "danger"))
        ]
        return AttendanceSummary(
            course_count=len(courses.courses),
            courses_with_attendance=sum(1 for c in courses.courses if c.attendance and c.attendance.percentage is not None),
            flagged_courses=[f for f in flagged if f],
        )

    # ------------------------------------------------------------- overview
    async def get_academic_summary(self) -> CGPAComposite:
        """Concise academic overview: CGPA/credits + current courses."""
        cgpa = await self.get_cgpa()
        courses = await self.get_courses()
        summary = await self.get_course_summary()
        return CGPAComposite(
            cgpa=cgpa.current_cgpa,
            earned_credits=cgpa.earned_credits,
            total_credits_required=cgpa.total_credits_required,
            courses=courses.courses,
            semester=courses.semester,
            summary=summary,
        )

    # ------------------------------------------------------- other read data
    async def get_assignments(self) -> AssignmentList:
        await self._auth.ensure_session()
        key = self._key("assignments")
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = await self._client.get_assignments()
        result = AssignmentParser(raw).parse()
        self._cache.set(key, result)
        return result

    async def get_events(self) -> EventList:
        await self._auth.ensure_session()
        key = self._key("events")
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = await self._client.get_events()
        result = EventParser(raw).parse()
        self._cache.set(key, result)
        return result

    async def get_feedback(self) -> FeedbackList:
        await self._auth.ensure_session()
        key = self._key("feedback")
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = await self._client.get_feedback()
        result = FeedbackParser(raw).parse()
        self._cache.set(key, result)
        return result

    async def get_proctor_message(self) -> ProctorMessage:
        await self._auth.ensure_session()
        raw = await self._client.get_proctor_message()
        return ProctorParser(raw).parse()


__all__ = ["AcademicService"]