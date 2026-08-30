"""Student identity bound to the authenticated session.

Never exposed to MCP clients or logs; used only internally to link a session
to the correct ``authorizedID`` and to detect unauthorized IDs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StudentIdentity(BaseModel):
    authorized_id: str = Field(description="The authenticated student's authorizedID (registration number).")
    username: str | None = Field(default=None, description="Login username, if known and needed.")

    def matches(self, candidate: str) -> bool:
        """True when a supplied authorizedID belongs to this identity."""
        if not candidate:
            return False
        return candidate.strip() == self.authorized_id