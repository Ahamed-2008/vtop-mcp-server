"""Event models derived from the scheduled events response.

Real response shape (``tests/fixtures/events.html``):
* day cards: day number + month title (e.g. "30" / "Aug-2026") and an optional
  section label ("Today : Ongoing Events", "Forthcoming Events").
* each card-body contains events with: title, category (italic parenthetical),
  an ISO date (YYYY-MM-DD), and an organizer.
* empty days show "--- No events scheduled ---".
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Event(BaseModel):
    """One scheduled event."""

    title: Optional[str] = Field(None, description="Event title.")
    category: Optional[str] = Field(None, description="Category label, e.g. Art, Career Guidance.")
    date: Optional[str] = Field(None, description="Event date as printed by VTOP (YYYY-MM-DD).")
    organizer: Optional[str] = Field(None, description="Organizer / club name if shown.")
    section: Optional[str] = Field(None, description="Grouping label, e.g. 'Today : Ongoing Events'.")


class EventDay(BaseModel):
    """All events belonging to one displayed day."""

    day: Optional[str] = Field(None, description="Day number, e.g. '30'.")
    month_title: Optional[str] = Field(None, description="Month label, e.g. 'Aug-2026'.")
    events: list[Event] = Field(default_factory=list)


class EventList(BaseModel):
    days: list[EventDay] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list, description="Flattened events for convenience.")