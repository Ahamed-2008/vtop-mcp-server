"""Secret redaction helpers.

Guards against accidentally leaking secrets into logs or exceptions. A single
:class:`Redactor` instance holds the values that must never appear in output;
a :class:`logging.Filter` applies it to every log record.

Redacted things:
* CSRF tokens (UUID-form and any ``_csrf``-labelled value)
* session cookie values (``Cookie:``/``Set-Cookie`` header values)
* the authenticated session's ``authorizedID`` and login username
* the VTOP password whenever it is passed around internally
* any ``Authorization`` header
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_CSRF_VALUE_RE = re.compile(r"(?i)(_csrf[\"']?\s*[:=]\s*[\"'])([^\"'\s,}]+)")
_AUTH_HEADER_RE = re.compile(r"(?i)(\b(?:Authorization|Cookie)\s*[:=][^,\n]*)")
_TSV_VALUE_RE = re.compile(r"(?i)(captcha(?:str)?[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)")


@dataclass
class Redactor:
    """Value-based secret redactor. Construct once per process."""

    secrets: set[str] = field(default_factory=set)
    placeholder: str = "[REDACTED]"

    def register(self, *values: Optional[str]) -> None:
        for v in values:
            if v:
                self.secrets.add(str(v))

    def redact(self, text: str) -> str:
        """Remove registered secrets and known sensitive patterns from `text`."""
        if not text:
            return text
        out = text
        for secret in self.secrets:
            if secret and secret in out:
                out = out.replace(secret, self.placeholder)
        out = _UUID_RE.sub(self.placeholder, out)
        out = _AUTH_HEADER_RE.sub(self.placeholder, out)
        out = _TSV_VALUE_RE.sub(r"\g<1>" + self.placeholder, out)

        def _csrf(match: re.Match[str]) -> str:
            return match.group(1) + self.placeholder

        out = _CSRF_VALUE_RE.sub(_csrf, out)
        return out

    def redact_many(self, texts: Iterable[str]) -> list[str]:
        return [self.redact(t) for t in texts]


class RedactingFilter:
    """logging.Filter that redacts every emitted message."""

    def __init__(self, redactor: Redactor) -> None:
        self.redactor = redactor

    def filter(self, record) -> bool:
        try:
            record.msg = self.redactor.redact(str(record.msg))
            record.args = tuple(self.redactor.redact(str(a)) if a is not None else a for a in record.args)
        except Exception:  # pragma: no cover - never let filtering break logging
            pass
        return True