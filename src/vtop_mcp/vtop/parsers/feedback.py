"""Feedback parser — maps the last-five-feedbacks response.

Real structure (``tests/fixtures/feedback.html``): a table with columns
[#, Feedback, Category, Status].
"""

from __future__ import annotations

from ...models import Feedback, FeedbackList
from .base import BaseParser


class FeedbackParser(BaseParser[FeedbackList]):
    model = FeedbackList

    def _parse(self) -> FeedbackList:
        feedbacks: list[Feedback] = []
        table = self.soup.find("table")
        if table is None:
            return FeedbackList(feedbacks=[])

        body = table.find("tbody")
        if body is None:
            return FeedbackList(feedbacks=[])

        for row in body.find_all("tr", recursive=False):
            cells = row.find_all(["th", "td"], recursive=False)
            texts = [self._cell_text(c) for c in cells]
            if len(texts) < 4:
                continue
            feedbacks.append(
                Feedback(
                    feedback=texts[1] or None,
                    category=texts[2] or None,
                    status=texts[3] or None,
                )
            )
        return FeedbackList(feedbacks=feedbacks)