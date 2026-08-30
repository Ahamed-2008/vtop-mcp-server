from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl

from vtop_discovery.storage.models import Endpoint, ParameterSchema

_STUDENT_ID_NAMES = {"authorizedid", "regno", "registrationno", "studentid", "memberid"}
_STUDENT_ID_VAL_RE = re.compile(r"^\d{2}[a-zA-Z]{3}\d{4,5}$")

_CSRF_NAMES = {"_csrf", "csrf", "csrftoken", "x-csrf-token", "_csrftoken", "token"}
_TIMESTAMP_NAMES = {"x", "_", "timestamp", "time", "t", "reqtime"}
_SESSION_NAMES = {"jsessionid", "sessionid", "session", "authsession"}
_SEMESTER_NAMES = {"semestersubid", "semsubid", "semesterid", "sem", "semester"}
_COURSE_NAMES = {"courseid", "classid", "coursecode", "course"}


def infer_parameter_schema(name: str, sample_value: Any) -> ParameterSchema:
    lowered = name.lower().replace("-", "").replace("_", "")
    val_str = str(sample_value).strip() if sample_value is not None else ""

    # 1. CSRF token detection
    if any(k in lowered for k in _CSRF_NAMES) or name in {"_csrf", "csrfToken"}:
        return ParameterSchema(type="csrf_token", dynamic=True, required=True, description="Anti-CSRF validation token")

    # 2. Timestamp / cache-buster detection
    if name in _TIMESTAMP_NAMES or (val_str.isdigit() and len(val_str) in (10, 13)):
        return ParameterSchema(type="timestamp", dynamic=True, required=False, description="Epoch timestamp or cache buster")

    # 3. Student ID detection
    if lowered in _STUDENT_ID_NAMES or _STUDENT_ID_VAL_RE.match(val_str):
        return ParameterSchema(type="student_id", dynamic=False, required=True, description="Student registration identifier")

    # 4. Username detection
    if lowered in {"username", "user", "uname", "loginid"}:
        return ParameterSchema(type="username", dynamic=False, required=True, description="User login handle or registration number")

    # 5. Password detection
    if lowered in {"password", "passwd", "pwd"}:
        return ParameterSchema(type="password", dynamic=False, required=True, description="User authentication password")

    # 6. CAPTCHA string detection
    if "captcha" in lowered:
        return ParameterSchema(type="captcha", dynamic=False, required=True, description="Solved CAPTCHA verification string")

    # 7. Session token detection
    if any(k in lowered for k in _SESSION_NAMES):
        return ParameterSchema(type="session_id", dynamic=True, required=True, description="Active session identifier")

    # 8. Semester ID detection
    if any(k in lowered for k in _SEMESTER_NAMES):
        return ParameterSchema(type="semester_id", dynamic=False, required=True, description="Semester or academic term identifier")

    # 9. Course / Class ID detection
    if any(k in lowered for k in _COURSE_NAMES):
        return ParameterSchema(type="course_id", dynamic=False, required=True, description="Course or class registration code")

    # 10. Boolean detection
    if isinstance(sample_value, bool) or val_str.lower() in {"true", "false"}:
        return ParameterSchema(type="boolean", dynamic=False, required=True, description="Boolean flag")

    # 11. Integer detection
    if isinstance(sample_value, int) or (val_str.isdigit() and not val_str.startswith("0")):
        return ParameterSchema(type="integer", dynamic=False, required=True, description="Integer value")

    # Default string
    return ParameterSchema(type="string", dynamic=False, required=True, description="Query or form parameter")


def _extract_param_dict(data: Any) -> dict[str, Any]:
    if not data:
        return {}
    if isinstance(data, dict):
        return dict(data)
    if isinstance(data, str):
        if "=" in data and "&" in data:
            return dict(parse_qsl(data, keep_blank_values=True))
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def analyze_request_parameters(endpoint: Endpoint) -> None:
    """Analyze query and body parameters, populating endpoint.request.parameters."""
    schemas: dict[str, ParameterSchema] = {}

    # Analyze query parameters
    for name, val in endpoint.request.query.items():
        schemas[name] = infer_parameter_schema(name, val)

    # Analyze body parameters
    body_dict = _extract_param_dict(endpoint.request.body)
    for name, val in body_dict.items():
        schemas[name] = infer_parameter_schema(name, val)

    endpoint.request.parameters = schemas
