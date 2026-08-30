"""Proctor message model.

The captured proctor-message response is empty whitespace
(``tests/fixtures/proctor.html``), so the model allows an absent message.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProctorMessage(BaseModel):
    message: Optional[str] = Field(
        None, description="Proctor message text. None/empty when VTOP has not published one."
    )