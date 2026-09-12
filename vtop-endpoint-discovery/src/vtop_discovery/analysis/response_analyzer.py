from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote

from vtop_discovery.storage.models import Endpoint, ResponseAnalysis

DOMAIN_KEYWORDS = (
    "attendance",
    "cgpa",
    "gpa",
    "credits",
    "marks",
    "grade",
    "grades",
    "timetable",
    "time table",
    "course registration",
    "course details",
    "curriculum",
    "student profile",
    "profile",
    "exam schedule",
    "examinations",
    "hall ticket",
    "digital assignment",
    "assignments",
    "academic history",
    "proctor",
    "faculty",
    "feedback",
    "scheduled events",
    "slot",
    "cat-1",
    "cat-2",
    "fat",
)


class _VtopHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.headings: list[str] = []
        self.table_headers: list[str] = []
        self.table_captions: list[str] = []
        self.form_fields: list[str] = []
        self.labels: list[str] = []
        self.text_tokens: list[str] = []
        self.produced_fields: dict[str, list[str]] = {}

        self._in_title = False
        self._in_heading = False
        self._in_th = False
        self._in_caption = False
        self._in_label = False
        self._curr_text: list[str] = []
        self._current_select_name: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if lowered == "title":
            self._in_title = True
            self._curr_text = []
        elif lowered in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._in_heading = True
            self._curr_text = []
        elif lowered == "th":
            self._in_th = True
            self._curr_text = []
        elif lowered == "caption":
            self._in_caption = True
            self._curr_text = []
        elif lowered == "label":
            self._in_label = True
            self._curr_text = []
        elif lowered == "select":
            name = attr_dict.get("name") or attr_dict.get("id")
            if name:
                self._current_select_name = name
                if name not in self.form_fields:
                    self.form_fields.append(name)
                if name not in self.produced_fields:
                    self.produced_fields[name] = []
        elif lowered == "option":
            val = attr_dict.get("value", "").strip()
            if self._current_select_name and val:
                if val not in self.produced_fields[self._current_select_name]:
                    self.produced_fields[self._current_select_name].append(val)
        elif lowered in {"input", "textarea"}:
            name = attr_dict.get("name") or attr_dict.get("id")
            val = attr_dict.get("value", "").strip()
            if name:
                if name not in self.form_fields:
                    self.form_fields.append(name)
                if val:
                    if name not in self.produced_fields:
                        self.produced_fields[name] = []
                    if val not in self.produced_fields[name]:
                        self.produced_fields[name].append(val)
        elif lowered == "button":
            name = attr_dict.get("name") or attr_dict.get("id")
            val = attr_dict.get("value", "").strip()
            if name and val:
                if name not in self.produced_fields:
                    self.produced_fields[name] = []
                if val not in self.produced_fields[name]:
                    self.produced_fields[name].append(val)
        elif lowered == "a":
            href = attr_dict.get("href", "")
            if "?" in href:
                query_part = href.split("?", 1)[1]
                for pair in query_part.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k and v:
                            if k not in self.produced_fields:
                                self.produced_fields[k] = []
                            if v not in self.produced_fields[k]:
                                self.produced_fields[k].append(v)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        text = re.sub(r"\s+", " ", " ".join(self._curr_text)).strip()

        if lowered == "title" and self._in_title:
            self._in_title = False
            if text:
                self.title = text
        elif lowered in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._in_heading:
            self._in_heading = False
            if text and text not in self.headings:
                self.headings.append(text)
        elif lowered == "th" and self._in_th:
            self._in_th = False
            if text and text not in self.table_headers:
                self.table_headers.append(text)
        elif lowered == "caption" and self._in_caption:
            self._in_caption = False
            if text and text not in self.table_captions:
                self.table_captions.append(text)
        elif lowered == "label" and self._in_label:
            self._in_label = False
            if text and text not in self.labels:
                self.labels.append(text)
        elif lowered == "select":
            self._current_select_name = None

        self._curr_text = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if not cleaned:
            return
        if self._in_title or self._in_heading or self._in_th or self._in_caption or self._in_label:
            self._curr_text.append(cleaned)
        self.text_tokens.append(cleaned.lower())


def _clean_and_decode_html(raw_html: str) -> str:
    decoded = raw_html
    if "%3C" in decoded or "%3c" in decoded or "%20" in decoded:
        try:
            decoded = unquote(decoded)
        except Exception:
            pass

    decoded = html.unescape(decoded)
    return decoded


def parse_html_response(html_content: str) -> ResponseAnalysis:
    cleaned_html = _clean_and_decode_html(html_content)
    parser = _VtopHTMLParser()
    try:
        parser.feed(cleaned_html)
    except Exception:
        pass

    combined_text = " ".join(parser.text_tokens)
    matched_keywords: list[str] = []

    for kw in DOMAIN_KEYWORDS:
        if kw in combined_text and kw not in matched_keywords:
            matched_keywords.append(kw)

    all_headings = parser.headings + parser.table_captions

    # Cap values per produced field to 10 to keep summary concise
    produced = {k: v[:10] for k, v in parser.produced_fields.items()}

    return ResponseAnalysis(
        title=parser.title,
        headings=all_headings[:15],
        table_headers=parser.table_headers[:30],
        form_fields=parser.form_fields[:25],
        keywords=matched_keywords,
        data_keys=parser.table_headers[:15],
        produced_fields=produced,
    )


def parse_json_response(json_data: Any) -> ResponseAnalysis:
    keys: list[str] = []
    produced: dict[str, list[str]] = {}
    if isinstance(json_data, dict):
        keys = list(str(k) for k in json_data.keys())
        for k, v in json_data.items():
            if isinstance(v, (str, int, float, bool)):
                produced[str(k)] = [str(v)]
    elif isinstance(json_data, list) and json_data and isinstance(json_data[0], dict):
        keys = list(str(k) for k in json_data[0].keys())

    text_dump = json.dumps(json_data).lower()
    matched_keywords = [
        kw for kw in DOMAIN_KEYWORDS
        if kw in text_dump
    ]

    return ResponseAnalysis(
        title=None,
        headings=[],
        table_headers=[],
        form_fields=[],
        keywords=matched_keywords,
        data_keys=keys[:25],
        produced_fields=produced,
    )


def analyze_response(endpoint: Endpoint) -> None:
    """Analyze response content (HTML or JSON) and populate endpoint.response.analysis."""
    body = endpoint.response.body
    content_type = (endpoint.response.content_type or "").lower()

    if not body:
        return

    if isinstance(body, (dict, list)):
        endpoint.response.analysis = parse_json_response(body)
        return

    if isinstance(body, str):
        if "json" in content_type:
            try:
                parsed = json.loads(body)
                endpoint.response.analysis = parse_json_response(parsed)
                return
            except Exception:
                pass

        # HTML parsing
        if "html" in content_type or ("<" in body and ">" in body):
            endpoint.response.analysis = parse_html_response(body)

