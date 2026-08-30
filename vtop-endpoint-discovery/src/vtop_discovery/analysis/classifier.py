from __future__ import annotations

import re
from typing import Any
from vtop_discovery.storage.models import CapturedExchange, Endpoint

# Exact known method + path routes
EXACT_METHOD_PATH_ROUTES: dict[tuple[str, str], dict[str, Any]] = {
    ("GET", "/vtop/open/page"): {
        "category": "authentication",
        "purpose": "authentication_entry",
        "confidence": 0.98,
        "evidence": "GET /vtop/open/page is the initial VTOP authentication portal landing page.",
    },
    ("POST", "/vtop/prelogin/setup"): {
        "category": "authentication",
        "purpose": "prelogin_setup",
        "confidence": 0.98,
        "evidence": "POST /vtop/prelogin/setup initializes the CSRF token and authentication environment.",
    },
    ("GET", "/vtop/login"): {
        "category": "authentication",
        "purpose": "login_page",
        "confidence": 0.98,
        "evidence": "GET /vtop/login renders the VTOP credential and captcha login form.",
    },
    ("POST", "/vtop/login"): {
        "category": "authentication",
        "purpose": "login",
        "confidence": 0.98,
        "evidence": "POST /vtop/login submits user credentials and captcha for authentication.",
    },
    ("POST", "/vtop/login/checkusername"): {
        "category": "authentication",
        "purpose": "session_or_username_check",
        "confidence": 0.98,
        "evidence": "POST /vtop/login/checkusername validates active session or student registration ID.",
    },
    ("GET", "/vtop/init/page"): {
        "category": "authentication",
        "purpose": "initialization",
        "confidence": 0.95,
        "evidence": "GET /vtop/init/page performs post-login redirect initialization.",
    },
    ("GET", "/vtop/main/page"): {
        "category": "navigation",
        "purpose": "main_page",
        "confidence": 0.95,
        "evidence": "GET /vtop/main/page loads the main authenticated application frame.",
    },
    ("GET", "/vtop/open"): {
        "category": "navigation",
        "purpose": "open_page",
        "confidence": 0.95,
        "evidence": "GET /vtop/open navigates to the authenticated workspace container.",
    },
    ("GET", "/vtop/content"): {
        "category": "navigation",
        "purpose": "authenticated_content",
        "confidence": 0.95,
        "evidence": "GET /vtop/content loads the core authenticated student dashboard frame and sidebar.",
    },
    ("GET", "/vtop/vtop/mandatory/data/off"): {
        "category": "navigation",
        "purpose": "mandatory_data",
        "confidence": 0.90,
        "evidence": "Path matches the mandatory data off status check route.",
    },
    ("POST", "/vtop/admissions/dogetpassedoutinformationmandatory"): {
        "category": "data",
        "purpose": "passed_out_information",
        "confidence": 0.90,
        "evidence": "Path matches the admissions passed out information check pattern.",
    },
    ("POST", "/vtop/get/dashboard/proctor/message"): {
        "category": "data",
        "purpose": "proctor_message",
        "confidence": 0.95,
        "evidence": "Path contains the dashboard/proctor/message route pattern.",
    },
    ("POST", "/vtop/get/dashboard/current/cgpa/credits"): {
        "category": "data",
        "purpose": "cgpa_credits",
        "confidence": 0.95,
        "evidence": "Path contains the dashboard/current/cgpa/credits route pattern.",
    },
    ("POST", "/vtop/get/dashboard/current/semester/course/details"): {
        "category": "data",
        "purpose": "course_details",
        "confidence": 0.95,
        "evidence": "Path contains the dashboard/current/semester/course/details route pattern.",
    },
    ("POST", "/vtop/get/upcoming/digital/assignments"): {
        "category": "data",
        "purpose": "assignments",
        "confidence": 0.95,
        "evidence": "Path contains the upcoming/digital/assignments route pattern.",
    },
    ("POST", "/vtop/get/last/five/feedbacks"): {
        "category": "data",
        "purpose": "feedback",
        "confidence": 0.95,
        "evidence": "Path contains the last/five/feedbacks route pattern.",
    },
    ("POST", "/vtop/get/scheduled/events"): {
        "category": "data",
        "purpose": "scheduled_events",
        "confidence": 0.95,
        "evidence": "Path contains the scheduled/events route pattern.",
    },
}

# Static Resource Pattern Rules
STATIC_RESOURCE_PATTERNS: list[tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"^/vtop/get/jq/js/"),
        "static_resource",
        "jquery_script",
        "Path matches the static jQuery resource pattern '/vtop/get/jq/js/*'.",
    ),
    (
        re.compile(r"^/vtop/get/bs/js/"),
        "static_resource",
        "bootstrap_script",
        "Path matches the static Bootstrap resource pattern '/vtop/get/bs/js/*'.",
    ),
    (
        re.compile(r"^/vtop/get/ms/js/"),
        "static_resource",
        "microsoft_script",
        "Path matches the static Microsoft script resource pattern '/vtop/get/ms/js/*'.",
    ),
]


def tokenize_path(path: str) -> list[str]:
    """Extract clean lowercase tokens from URL path."""
    cleaned = path.strip().lower()
    raw_segments = re.split(r"[/._\-]+", cleaned)
    tokens = [s for s in raw_segments if s and not s.isdigit() and s not in {"vtop"}]
    return tokens


# Specific rule taxonomy with priorities for dynamic endpoints
PURPOSE_RULES: list[dict[str, Any]] = [
    {
        "purpose": "cgpa_credits",
        "category": "data",
        "priority": 100,
        "token_combinations": [{"cgpa", "credits"}, {"cgpa"}, {"gpa", "credits"}, {"gpa"}],
        "single_tokens": ["cgpa", "gpa"],
        "content_terms": ["cgpa", "credits earned", "credits registered", "grade point"],
        "table_terms": ["cgpa", "gpa", "credits", "credits earned"],
    },
    {
        "purpose": "course_details",
        "category": "data",
        "priority": 95,
        "token_combinations": [
            {"course", "details"},
            {"course", "detail"},
            {"coursedetail"},
            {"coursedetails"},
            {"registration", "details"},
            {"registrationdetail"},
            {"semester", "course", "details"},
        ],
        "single_tokens": ["coursedetail", "coursedetails", "registrationdetail"],
        "content_terms": ["course registration details", "course details", "semester course registration", "course registration detail"],
        "table_terms": ["course code", "course title", "course type", "credits", "slot", "faculty"],
    },
    {
        "purpose": "assignments",
        "category": "data",
        "priority": 92,
        "token_combinations": [
            {"assignments"},
            {"assignment"},
            {"digital", "assignments"},
            {"digital", "assignment"},
            {"digitalpad"},
        ],
        "single_tokens": ["assignments", "assignment", "digitalpad"],
        "content_terms": ["digital assignment", "assignments", "assignment title", "upload assignment", "due date"],
        "table_terms": ["assignment", "due date", "max marks", "submission date", "status"],
    },
    {
        "purpose": "scheduled_events",
        "category": "data",
        "priority": 90,
        "token_combinations": [
            {"scheduled", "events"},
            {"scheduledevents"},
            {"calendar", "events"},
        ],
        "single_tokens": ["scheduledevents"],
        "content_terms": ["scheduled events", "academic calendar", "events", "holiday list"],
        "table_terms": ["event date", "event description", "day", "event"],
    },
    {
        "purpose": "attendance",
        "category": "data",
        "priority": 85,
        "token_combinations": [{"attendance"}, {"attend"}, {"processattendance"}, {"getattendance"}],
        "single_tokens": ["attendance", "attend", "processattendance", "getattendance"],
        "content_terms": ["attendance", "attended", "classes attended", "attendance summary", "attendance percentage"],
        "table_terms": ["attendance", "attended", "percentage", "total classes", "course code", "course title"],
    },
    {
        "purpose": "marks",
        "category": "data",
        "priority": 85,
        "token_combinations": [{"marks"}, {"mark"}, {"getmarks"}, {"processmarks"}, {"cat"}, {"fat"}],
        "single_tokens": ["marks", "mark", "getmarks", "processmarks"],
        "content_terms": ["marks", "student marks", "cat-1", "cat-2", "fat", "quiz", "scored marks", "assessment"],
        "table_terms": ["marks", "max mark", "weightage", "scored", "course title"],
    },
    {
        "purpose": "grades",
        "category": "data",
        "priority": 82,
        "token_combinations": [{"grades"}, {"grade"}, {"gradehistory"}],
        "single_tokens": ["grades", "grade"],
        "content_terms": ["grades", "grade obtained", "letter grade"],
        "table_terms": ["grade", "letter grade", "credits"],
    },
    {
        "purpose": "exam_schedule",
        "category": "data",
        "priority": 80,
        "token_combinations": [
            {"exam", "schedule"},
            {"examschedule"},
            {"examination", "schedule"},
            {"hallticket"},
            {"hall", "ticket"},
        ],
        "single_tokens": ["examschedule", "hallticket"],
        "content_terms": ["examination schedule", "exam schedule", "hall ticket", "exam date", "exam session"],
        "table_terms": ["exam date", "session", "slot", "course code", "venue", "seat"],
    },
    {
        "purpose": "examinations",
        "category": "data",
        "priority": 75,
        "token_combinations": [{"examinations"}, {"examination"}, {"exam"}],
        "single_tokens": ["examinations", "examination"],
        "content_terms": ["examinations", "examination", "exam"],
        "table_terms": ["exam", "session", "venue"],
    },
    {
        "purpose": "timetable",
        "category": "data",
        "priority": 75,
        "token_combinations": [{"timetable"}, {"time", "table"}, {"classschedule"}],
        "single_tokens": ["timetable"],
        "content_terms": ["timetable", "time table", "class schedule", "weekly schedule"],
        "table_terms": ["theory", "lab", "slot", "start time", "end time", "monday", "tuesday", "wednesday"],
    },
    {
        "purpose": "profile",
        "category": "data",
        "priority": 72,
        "token_combinations": [{"profile"}, {"studentprofile"}, {"student_profile"}, {"studentinfo"}, {"student", "info"}],
        "single_tokens": ["profile", "studentprofile", "studentinfo"],
        "content_terms": ["student profile", "personal information", "proctor", "program", "department"],
        "table_terms": ["registration no", "student name", "date of birth", "program", "branch"],
    },
    {
        "purpose": "academic_history",
        "category": "data",
        "priority": 70,
        "token_combinations": [{"academic", "history"}, {"academichistory"}, {"transcript"}],
        "single_tokens": ["academichistory", "transcript"],
        "content_terms": ["academic history", "cumulative gpa", "grades obtained", "credits earned history"],
        "table_terms": ["semester", "gpa", "cgpa", "credits earned", "credits registered", "grade"],
    },
    {
        "purpose": "feedback",
        "category": "data",
        "priority": 68,
        "token_combinations": [{"feedback"}, {"feedbacks"}, {"facultyevaluation"}, {"faculty", "feedback"}],
        "single_tokens": ["feedback", "feedbacks", "facultyevaluation"],
        "content_terms": ["student feedback", "faculty feedback", "evaluation", "questionnaire"],
        "table_terms": ["question", "rating", "faculty name"],
    },
    {
        "purpose": "faculty",
        "category": "data",
        "priority": 65,
        "token_combinations": [{"faculty"}, {"proctor"}, {"proctormessage"}, {"proctor", "message"}],
        "single_tokens": ["faculty", "proctor"],
        "content_terms": ["faculty details", "proctor message", "proctor name", "faculty advisor"],
        "table_terms": ["faculty name", "cabin", "department", "email"],
    },
    {
        "purpose": "courses",
        "category": "data",
        "priority": 60,
        "token_combinations": [{"courses"}, {"course"}, {"curriculum"}, {"syllabus"}],
        "single_tokens": ["courses", "curriculum", "syllabus"],
        "content_terms": ["courses", "registered courses", "curriculum", "credits registered"],
        "table_terms": ["course code", "course title", "credits", "course type"],
    },
    {
        "purpose": "dashboard",
        "category": "dashboard",
        "priority": 10,
        "token_combinations": [{"dashboard"}],
        "single_tokens": ["dashboard"],
        "content_terms": ["student dashboard", "welcome to vtop"],
        "table_terms": [],
    },
]


def classify_endpoint(endpoint: Endpoint) -> None:
    """Multi-signal deterministic classifier combining method, route table, static resource patterns, and token semantics."""
    method_upper = endpoint.method.upper().strip()
    path_clean = endpoint.path.strip()

    # 1. Check Exact Method + Path Routes Table
    route_key = (method_upper, path_clean)
    if route_key in EXACT_METHOD_PATH_ROUTES:
        match = EXACT_METHOD_PATH_ROUTES[route_key]
        endpoint.category = match["category"]
        endpoint.purpose = match["purpose"]
        endpoint.confidence = match["confidence"]
        evidence_list = [match["evidence"]]
        if endpoint.response.status == 302:
            evidence_list.append("Endpoint returned HTTP 302 redirect")
        if endpoint.response.analysis and endpoint.response.analysis.keywords:
            evidence_list.append(f"Response keywords: {', '.join(endpoint.response.analysis.keywords[:5])}")
        endpoint.evidence = evidence_list
        return

    # 2. Check Static Resource Patterns
    for pattern, cat, purp, ev_text in STATIC_RESOURCE_PATTERNS:
        if pattern.search(path_clean):
            endpoint.category = cat
            endpoint.purpose = purp
            endpoint.confidence = 0.95
            evs = [ev_text]
            if endpoint.response.content_type:
                evs.append(f"Content-Type: '{endpoint.response.content_type}'")
            if endpoint.response.status == 302:
                evs.append("Returned HTTP 302 redirect to static asset")
            endpoint.evidence = evs
            return

    # 3. Dynamic Token-Based Heuristic Evaluation
    tokens = set(tokenize_path(endpoint.path))
    query_params_text = " ".join(endpoint.request.parameters.keys()).lower()
    resp_analysis = endpoint.response.analysis

    title_text = (resp_analysis.title or "").lower() if resp_analysis else ""
    headings_text = " ".join(resp_analysis.headings).lower() if resp_analysis else ""
    table_headers_text = " ".join(resp_analysis.table_headers).lower() if resp_analysis else ""
    keywords_text = " ".join(resp_analysis.keywords).lower() if resp_analysis else ""
    guided_purpose = endpoint.purpose if endpoint.purpose not in {"unknown", ""} else None

    best_rule: dict | None = None
    best_weight = 0.0
    best_evidence: list[str] = []
    highest_priority = -1

    for rule in PURPOSE_RULES:
        purpose = rule["purpose"]
        weight = 0.0
        evidence: list[str] = []
        path_matched = False

        # Check Token Combinations (High Specificity)
        for combo in rule["token_combinations"]:
            if combo.issubset(tokens):
                matched_str = " and ".join(sorted(combo))
                weight += 0.65
                evidence.append(f"URL path tokens contain '{matched_str}'")
                path_matched = True
                break

        # Check single tokens if combination didn't match
        if not path_matched:
            for st in rule["single_tokens"]:
                if st in tokens or any(st in t for t in tokens):
                    weight += 0.50
                    evidence.append(f"URL path contains '{st}'")
                    path_matched = True
                    break

        # Response Title / Headings Match
        for term in rule["content_terms"]:
            if term in title_text:
                weight += 0.35
                evidence.append(f"Page title contains '{term}'")
                break
            elif term in headings_text:
                weight += 0.35
                evidence.append(f"Response headings contain '{term}'")
                break

        # Table Header Match
        for th in rule["table_terms"]:
            if th in table_headers_text:
                weight += 0.30
                evidence.append(f"Table headers contain '{th}'")
                break

        # Request Parameter Match
        if purpose in {"attendance", "marks", "course_details", "timetable", "cgpa_credits"}:
            if "semestersubid" in query_params_text or "courseid" in query_params_text:
                weight += 0.20
                evidence.append("Request parameters contain academic query identifiers (semesterSubId/courseId)")

        # Guided Action Match
        if guided_purpose and (guided_purpose == purpose or (guided_purpose == "courses" and purpose == "course_details")):
            weight += 0.30
            evidence.append(f"Captured during active user guided phase '{guided_purpose}'")

        # Fallback Domain Keyword in Body
        if not any("Response" in ev or "Table" in ev or "title" in ev for ev in evidence):
            for ck in rule["content_terms"]:
                if ck in keywords_text:
                    weight += 0.15
                    evidence.append(f"Response body contains domain keyword '{ck}'")
                    break

        # Check if this rule is superior based on weight and priority
        if weight > 0.40:
            if weight > best_weight or (weight == best_weight and rule["priority"] > highest_priority):
                best_weight = weight
                best_rule = rule
                best_evidence = evidence
                highest_priority = rule["priority"]

    if best_rule is not None and best_weight >= 0.40:
        endpoint.category = best_rule["category"]
        endpoint.purpose = best_rule["purpose"]
        endpoint.evidence = best_evidence
        endpoint.confidence = min(0.98, max(0.45, best_weight))
    else:
        endpoint.category = "unknown"
        endpoint.purpose = "unknown"
        endpoint.confidence = 0.0
        endpoint.evidence = ["No matching classification patterns detected"]


def classify_exchange(exchange: CapturedExchange) -> str:
    """Legacy helper for single exchanges."""
    path = exchange.request.path.lower()
    if "captcha" in path:
        return "captcha"
    if "login" in path:
        return "authentication"
    if "attend" in path:
        return "attendance"
    if "mark" in path:
        return "marks"
    if "time" in path:
        return "timetable"
    return "unknown"
