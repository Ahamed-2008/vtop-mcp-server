"""
parsers.py

Turn the raw HTML returned by ``vtop_tools.py`` into plain Python data.

VTOP has no JSON API, so every tool returns HTML. These functions are pure
(no network, no shared state) and are keyed to the real DOM shapes confirmed
against a live VIT Vellore session (2026-09). They are deliberately tolerant
of column reordering by locating columns through their header text rather
than by index, and of VTOP's occasional empty-state pages.

Each function returns builtins (dict / list / str / int / float) so the
result can be handed straight to an MCP ``@mcp.tool()`` wrapper.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

__all__ = [
    "parse_cgpa_credits",
    "parse_attendance",
    "parse_timetable",
    "parse_exam_schedule",
    "parse_digital_assignments",
    "parse_grades",
    "parse_marks",
    "parse_employee_search",
    "parse_employee_detail",
    "parse_hod_dean",
    # new
    "parse_dashboard_courses",
    "parse_upcoming_assignments",
    "parse_last_feedbacks",
    "parse_scheduled_events",
    "parse_generic_table",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _num(value: str):
    """Coerce a VTOP cell to int/float when it is fully numeric."""
    text = _norm(value).replace("%", "").replace(",", "")
    if text in ("", "-", "--"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return _norm(value)


def _cells(row, recursive: bool = False) -> list[str]:
    found = row.find_all(["th", "td"], recursive=recursive)
    return [_norm(c.get_text(" ", strip=True)) for c in found]


def _find_table(soup: BeautifulSoup, *needles: str):
    """Return the first <table> whose header text contains every needle."""
    for table in soup.find_all("table"):
        text = _norm(table.get_text(" ", strip=True))
        if all(n.lower() in text.lower() for n in needles):
            return table
    return None


def _header_row(table):
    """First row that clearly looks like a header (has a <th> or many cells)."""
    for row in table.find_all("tr"):
        if row.find("th") or len(row.find_all(["td"], recursive=False)) >= 3:
            return row
    return table.find("tr")


def _table_to_dicts(table) -> list[dict]:
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = _cells(_header_row(table))
    out = []
    for row in rows:
        if row is _header_row(table):
            continue
        cells = _cells(row)
        if not cells or cells == headers:
            continue
        if len(cells) != len(headers):
            continue
        out.append(dict(zip(headers, cells, strict=True)))
    return out


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

def parse_cgpa_credits(html: str) -> dict:
    """Dashboard CGPA widget -> {total_credits_required, earned_credits, cgpa}."""
    soup = _soup(html)
    raw: dict[str, str] = {}
    for item in soup.select("li.list-group-item"):
        spans = item.find_all("span")
        if len(spans) < 2:
            continue
        label = _norm(spans[0].get_text(" ", strip=True)).rstrip(" :")
        value = _norm(spans[-1].get_text(" ", strip=True))
        raw[label] = value

    def pick(*names):
        for name in names:
            for key, value in raw.items():
                if key.lower().startswith(name.lower()):
                    return _num(value)
        return None

    return {
        "total_credits_required": pick("Total Credits Required"),
        "earned_credits": pick("Earned Credits"),
        "cgpa": pick("Current CGPA"),
    }


# ---------------------------------------------------------------------------
# academics
# ---------------------------------------------------------------------------

def parse_attendance(html: str) -> list[dict]:
    """Attendance page -> one dict per registered course."""
    soup = _soup(html)
    table = soup.find("table", id="AttendanceDetailDataTable") or _find_table(
        soup, "Attendance Percentage"
    )
    if table is None:
        return []
    rows = _table_to_dicts(table)
    for row in rows:
        row["attendance_percentage"] = _num(row.get("Attendance Percentage", ""))
        row["attended_classes"] = _num(row.get("Attended Classes/Days", ""))
        row["total_classes"] = _num(row.get("Total Classes", ""))
    return rows


def parse_timetable(html: str) -> dict:
    """Timetable page -> {courses, dropped, grid}.

    ``courses`` is the reliable registered-course list; ``grid`` is a
    best-effort decode of the weekly day x period table.
    """
    soup = _soup(html)
    courses = []
    dropped = []
    course_table = _find_table(soup, "Slot/", "Course") or _find_table(soup, "L T P J C")
    if course_table is not None:
        courses = _table_to_dicts(course_table)
    dropped_table = _find_table(soup, "Dropped")
    if dropped_table is not None:
        dropped = _table_to_dicts(dropped_table)

    return {"courses": courses, "dropped": dropped, "grid": _parse_timetable_grid(soup)}


def _parse_timetable_grid(soup: BeautifulSoup) -> list[dict]:
    grid_table = soup.find("table", id="timeTableStyle")
    if grid_table is None:
        return []
    rows = grid_table.find_all("tr")
    if len(rows) < 5:
        return []

    theory_starts = _cells(rows[0])[2:]
    theory_ends = _cells(rows[1])[1:]
    lab_starts = _cells(rows[2])[2:]
    lab_ends = _cells(rows[3])[1:]

    grid: list[dict] = []
    index = 4
    while index < len(rows):
        day_row = rows[index]
        day_cells = day_row.find_all(["td"], recursive=False)
        if not day_cells or day_row.find("td", rowspan="2") is None:
            index += 1
            continue
        day = _norm(day_cells[0].get_text(" ", strip=True))

        def collect(
            kind: str, labels: list[str], starts: list[str], ends: list[str], day_name: str = day
        ):
            for pos, cell in enumerate(labels):
                value = _norm(cell).strip()
                if value in ("", "-", "Lunch"):
                    continue
                grid.append(
                    {
                        "day": day_name,
                        "type": kind,
                        "period": pos + 1,
                        "start": starts[pos] if pos < len(starts) else None,
                        "end": ends[pos] if pos < len(ends) else None,
                        "slot": value,
                    }
                )

        collect("THEORY", _cells(day_row)[2:], theory_starts, theory_ends)
        if index + 1 < len(rows):
            collect("LAB", _cells(rows[index + 1])[1:], lab_starts, lab_ends)
        index += 2
    return grid


# ---------------------------------------------------------------------------
# examinations
# ---------------------------------------------------------------------------

def parse_exam_schedule(html: str) -> list[dict]:
    """Exam schedule -> one dict per exam, tagged with its category (e.g. FAT)."""
    soup = _soup(html)
    table = _find_table(soup, "Course Code", "Exam Date")
    if table is None:
        return []

    headers: list[str] = []
    out: list[dict] = []
    category = None
    for row in table.find_all("tr"):
        cells = _cells(row)
        if not cells:
            continue
        if "Course Code" in cells:
            headers = cells
            continue
        if len(cells) == 1:
            category = cells[0]
            continue
        if headers and len(cells) >= len(headers):
            record = dict(zip(headers, cells, strict=False))
            record["category"] = category
            out.append(record)
    return out


def parse_digital_assignments(html: str) -> list[dict]:
    """Digital assignment page -> one dict per course."""
    soup = _soup(html)
    table = _find_table(soup, "Class Nbr", "Course Code") or _find_table(
        soup, "Course Title", "Faculty"
    )
    if table is None:
        return []
    return _table_to_dicts(table)


_GRADE_SUBHEADERS = ["L", "P", "J", "C"]


def parse_grades(html: str) -> list[dict]:
    """Grade view -> one dict per course for the chosen semester.

    Returns [] when the semester has no published grades (VTOP then echoes
    its semester picker instead of a grade table).
    """
    soup = _soup(html)
    table = _find_table(soup, "Grand Total", "Grade")
    if table is None:
        return []

    rows = table.find_all("tr")
    headers = _cells(rows[0])
    subheaders = _cells(rows[1]) if len(rows) > 1 else []
    if "Credits" in headers and subheaders == _GRADE_SUBHEADERS:
        idx = headers.index("Credits")
        headers = headers[:idx] + _GRADE_SUBHEADERS + headers[idx + 1:]

    out = []
    for row in rows[2:]:
        cells = _cells(row)
        if not cells or "GPA" in " ".join(cells):
            continue
        if len(cells) == len(headers):
            out.append(dict(zip(headers, cells, strict=True)))
    for record in out:
        record["Grand Total"] = _num(record.get("Grand Total", ""))
    return out


def parse_marks(html: str) -> list[dict]:
    """Marks page -> courses, each with its nested per-assessment ``marks``."""
    soup = _soup(html)
    master = _find_table(soup, "ClassNbr", "Course Code")
    if master is None:
        return []

    courses: list[dict] = []
    current: dict | None = None
    for row in master.find_all("tr", recursive=False):
        direct = row.find_all("td", recursive=False)
        if len(direct) == 1 and row.find("table") is not None:
            if current is not None:
                current["marks"] = _table_to_dicts(row.find("table"))
            continue
        cells = _cells(row)
        if not cells or "ClassNbr" in cells or "Course Code" in cells:
            continue
        if len(cells) == 9:
            current = {
                "sl_no": _num(cells[0]),
                "class_nbr": cells[1],
                "course_code": cells[2],
                "course_title": cells[3],
                "course_type": cells[4],
                "course_system": cells[5],
                "faculty": cells[6],
                "slot": cells[7],
                "course_mode": cells[8],
                "marks": [],
            }
            courses.append(current)
    return courses


# ---------------------------------------------------------------------------
# hrms directory
# ---------------------------------------------------------------------------

def parse_employee_search(html: str) -> list[dict]:
    """Faculty search results -> [{name, designation, school, emp_id}]."""
    soup = _soup(html)
    if "No records found" in _norm(soup.get_text(" ", strip=True)):
        return []

    table = _find_table(soup, "Name of the Faculty", "Designation")
    if table is None:
        return []

    out = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 4 or "Name of the Faculty" in _norm(cells[0].get_text(" ", strip=True)):
            continue
        button = cells[-1].find("button")
        onclick = button.get("onclick", "") if button else ""
        match = re.search(r"getEmployeeIdNo\([^0-9]*(\d+)", onclick)
        out.append(
            {
                "name": _norm(cells[0].get_text(" ", strip=True)),
                "designation": _norm(cells[1].get_text(" ", strip=True)),
                "school": _norm(cells[2].get_text(" ", strip=True)),
                "emp_id": match.group(1) if match else (button.get("id") if button else None),
            }
        )
    return out


_EMP_DETAIL_LABELS = [
    "Name of the Faculty",
    "Designation",
    "Name of Department",
    "School / Centre Name",
    "E-Mail Id",
    "Cabin Number",
]


def _labelled_fields(text: str, labels: list[str], stop: str | None = None) -> dict:
    stops = "|".join(re.escape(label) for label in labels if label in text)
    out = {}
    for label in labels:
        tail = f"{stops}|{re.escape(stop)}" if stop else stops
        if tail:
            pattern = rf"{re.escape(label)}\s*(.*?)(?=\s*(?:{tail})\b|$)"
        else:
            pattern = rf"{re.escape(label)}\s*(.*)$"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            out[label] = _norm(match.group(1))
    return out


def parse_employee_detail(html: str) -> dict:
    """Faculty profile -> labelled fields + office_hours list."""
    soup = _soup(html)
    text = _norm(soup.get_text(" ", strip=True))
    fields = _labelled_fields(text, _EMP_DETAIL_LABELS, stop="OPEN HOURS")

    office_hours = []
    table = _find_table(soup, "Week Day", "Timings")
    if table is not None:
        for row in table.find_all("tr"):
            cells = _cells(row)
            if len(cells) >= 2 and "Week Day" not in cells:
                office_hours.append({"week_day": cells[0], "timings": cells[1]})

    return {
        "name": fields.get("Name of the Faculty"),
        "designation": fields.get("Designation"),
        "department": fields.get("Name of Department"),
        "school": fields.get("School / Centre Name"),
        "email": fields.get("E-Mail Id"),
        "cabin": fields.get("Cabin Number"),
        "office_hours": office_hours,
    }


_HOD_FIELDS = ["Name of the Faculty", "Designation", "Cabin Number", "Email ID"]


def parse_hod_dean(html: str) -> dict:
    """HoD/Dean page -> {"dean": {...}, "hod": {...}}."""
    soup = _soup(html)
    text = _norm(soup.get_text(" ", strip=True))
    text = text.split("Enable JavaScript")[0].strip()
    parts = re.split(r"Head of the Department \(HoD\)", text, maxsplit=1)
    dean_text = parts[0]
    hod_text = parts[1] if len(parts) > 1 else ""
    return {
        "dean": _labelled_fields(dean_text, _HOD_FIELDS),
        "hod": _labelled_fields(hod_text, _HOD_FIELDS),
    }


# ---------------------------------------------------------------------------
# generic / new tools
# ---------------------------------------------------------------------------

def parse_generic_table(html: str) -> list[dict]:
    """Best-effort conversion of the most content-rich table in *html* to a
    list of row dicts.  Used for endpoints whose exact DOM shape hasn't been
    hand-tuned yet (curriculum categories, biometric log, calendar, class
    messages, etc.).  Falls back to an empty list when no table is found.
    """
    soup = _soup(html)
    best_table = None
    best_rows = 0
    for table in soup.find_all("table"):
        row_count = len(table.find_all("tr"))
        if row_count > best_rows:
            best_rows = row_count
            best_table = table
    if best_table is None or best_rows < 2:
        return []
    return _table_to_dicts(best_table)


def parse_dashboard_courses(html: str) -> list[dict]:
    """Dashboard current-semester course widget -> one dict per course row."""
    soup = _soup(html)
    table = (
        _find_table(soup, "Course", "Attendance")
        or _find_table(soup, "Course", "Remarks")
        or _find_table(soup, "Code")
    )
    if table is None:
        return parse_generic_table(html)
    return _table_to_dicts(table)


def parse_upcoming_assignments(html: str) -> list[dict]:
    """Dashboard upcoming digital assignments widget -> one dict per assignment."""
    soup = _soup(html)
    table = (
        _find_table(soup, "Course Name", "Title")
        or _find_table(soup, "Last Date")
    )
    if table is None:
        return parse_generic_table(html)
    return _table_to_dicts(table)


def parse_last_feedbacks(html: str) -> list[dict]:
    """Dashboard last-five feedbacks widget -> one dict per feedback entry."""
    soup = _soup(html)
    table = _find_table(soup, "Feedback", "Status") or _find_table(soup, "Category")
    if table is None:
        return parse_generic_table(html)
    return _table_to_dicts(table)


def parse_scheduled_events(html: str) -> list[dict]:
    """Dashboard scheduled events widget -> one dict per event."""
    soup = _soup(html)
    table = _find_table(soup, "Event") or _find_table(soup, "Date")
    if table is None:
        # Fallback: extract list items or paragraphs
        items = []
        for el in soup.find_all(["li", "p"]):
            text = _norm(el.get_text(" ", strip=True))
            if text and len(text) > 5:
                items.append({"text": text})
        return items[:50]
    return _table_to_dicts(table)

