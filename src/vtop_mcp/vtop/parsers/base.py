"""Response parser infrastructure.

Parsers convert raw VTOP HTML into typed pydantic models. They must (a) be
resilient to VTOP's occasionally malformed markup and cosmetic class churn,
and (b) never invent data — fields absent from a response stay empty/None.
"""

from __future__ import annotations

import re
from typing import Generic, Optional, TypeVar

from bs4 import BeautifulSoup

from ...errors import VTOPParseError
from ...logging_setup import get_logger

log = get_logger("vtop.parsers")

T = TypeVar("T")


class BaseParser(Generic[T]):
    """Base class: parse HTML docs (possibly fragments) into models."""

    model: type[T]  # set by subclasses

    def __init__(self, html: str) -> None:
        self.html = html or ""
        self.soup = BeautifulSoup(self.html, "lxml")

    def parse(self) -> T:
        try:
            result = self._parse()
        except VTOPParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VTOPParseError(
                f"The {type(self).__name__} could not interpret the VTOP response."
            ) from exc
        return result

    def _parse(self) -> T:  # pragma: no cover - abstract
        raise NotImplementedError

    # helpers ---------------------------------------------------------------
    @staticmethod
    def _norm(value: str | None) -> str | None:
        """Normalise a scraped string (whitespace collapse, strip)."""
        if value is None:
            return None
        text = " ".join(value.split())
        return text or None

    @staticmethod
    def _clean(text: str | None) -> str:
        return " ".join((text or "").split())

    @staticmethod
    def _float(value: str | None) -> Optional[float]:
        if value is None:
            return None
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None

    @staticmethod
    def _cell_text(cell) -> str:
        return " ".join(cell.get_text(" ", strip=True).split())

    def _has_data_table(self) -> bool:
        return bool(self.soup.find("table"))


def require_table(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    if not soup.find("table"):
        # A data-less response is valid (e.g. "no assignments"), raise only for
        # structurally impossible responses.
        raise VTOPParseError("The VTOP response contained no data table.")
    return soup