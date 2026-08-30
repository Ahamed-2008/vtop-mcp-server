"""Proctor parser — maps the dashboard proctor message response.

The captured live response contains only whitespace, meaning VTOP had no
proctor message to show. An empty response is a valid outcome, not an error.
"""

from __future__ import annotations

from ...models import ProctorMessage
from .base import BaseParser


class ProctorParser(BaseParser[ProctorMessage]):
    model = ProctorMessage

    def _parse(self) -> ProctorMessage:
        text = self._clean(self.soup.get_text(" ", strip=True))
        if not text:
            return ProctorMessage(message=None)
        return ProctorMessage(message=text)