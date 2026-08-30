"""CGPA parser — maps the live VTOP cgpa/credits response.

The response is a ``<ul>`` of label/value list items:
    "Total Credits Required :"  162
    "Earned Credits :"          47.0
    "Current CGPA :"            8.72
"""

from __future__ import annotations

from ...errors import VTOPParseError
from ...models import CGPA
from .base import BaseParser


class CGPAParser(BaseParser[CGPA]):
    model = CGPA

    def _parse(self) -> CGPA:
        cgpa = CGPA()
        items = self.soup.find_all("li", class_="list-group-item")
        if not items and not self.soup.find("ul"):
            raise VTOPParseError(
                "The CGPA response had no recognizable data rows; "
                "a real sanitized response is required to update this parser."
            )
        for li in items:
            text = self._cell_text(li)
            if not text:
                continue
            label, value = self._split_label_value(text)
            if not value:
                continue
            if "total credits required" in label.lower():
                cgpa.total_credits_required = self._float(value)
            elif "earned credits" in label.lower():
                cgpa.earned_credits = self._float(value)
            elif "current cgpa" in label.lower():
                cgpa.current_cgpa = self._float(value)
        if cgpa.current_cgpa is None and cgpa.earned_credits is None and cgpa.total_credits_required is None:
            raise VTOPParseError("CGPA response parsed, but no numeric values were found.")
        return cgpa

    @staticmethod
    def _split_label_value(text: str) -> tuple[str, str]:
        """Split a 'Label : value' row.

        Prefer the LAST value-bearing segment after the final ':' as the value,
        which tolerates labels that themselves contain colons.
        """
        if ":" not in text:
            return text, ""
        label, _, raw_value = text.rpartition(":")
        return label.strip(), raw_value.strip()