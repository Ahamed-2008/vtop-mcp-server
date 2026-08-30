"""Events parser — maps the scheduled events response.

Real structure (``tests/fixtures/events.html``): each ``div.card`` is one day;
it carries a small day/month header (e.g. day "30", month "Aug-2026") and an
optional section label ("Today : Ongoing Events", "Forthcoming Events"). Event
card-bodies inside hold title, category, ISO date, and organizer.
"""

from __future__ import annotations

from typing import Optional

from ...models import Event, EventDay, EventList
from .base import BaseParser


class EventParser(BaseParser[EventList]):
    model = EventList

    def _parse(self) -> EventList:
        days: list[EventDay] = []
        for card in self.soup.find_all("div", class_="card"):
            day_number, month_title = self._day_header(card)
            section = self._section_label(card)

            events: list[Event] = []
            for body in card.find_all("div", class_="card-body"):
                if "No events scheduled" in self._cell_text(body):
                    continue
                event = self._event_from_body(body, section)
                if event.title or event.date:
                    events.append(event)

            if day_number is not None or events:
                days.append(EventDay(day=day_number, month_title=month_title, events=events))

        flattened = [e for d in days for e in d.events]
        return EventList(days=days, events=flattened)

    def _day_header(self, card) -> tuple[Optional[str], Optional[str]]:
        day: Optional[str] = None
        month: Optional[str] = None
        h5 = card.find("div", class_="h5")
        if h5:
            day = self._norm(h5.get_text(" ", strip=True))
        sub = card.find("div", class_="subtitle")
        if sub:
            month = self._norm(sub.get_text(" ", strip=True))
        return day, month

    def _section_label(self, card) -> Optional[str]:
        """The per-day heading text like 'Today : Ongoing Events' / 'Forthcoming Events'.

        Section labels are ``div.card-title`` elements (event titles are
        ``span.card-title``), so restricting to divs avoids false matches.
        """
        for el in card.find_all("div", class_="card-title"):
            text = self._norm(el.get_text(" ", strip=True))
            if text:
                return text
        return None

    def _event_from_body(self, body, section: Optional[str]) -> Event:
        # title + category are siblings inside the first <div>.
        title: Optional[str] = None
        category: Optional[str] = None
        date: Optional[str] = None
        organizer: Optional[str] = None

        first_div = body.find("div")
        if first_div:
            title_span = first_div.find("span", class_="card-title")
            if title_span:
                title = self._norm(title_span.get_text(" ", strip=True))
            cat = first_div.find("span", class_="fst-italic")
            if cat:
                category = self._norm(cat.get_text(" ", strip=True))

        date_span = body.find("span", class_=["mx-3", "text-secondary"])
        if date_span is None:
            date_span = body.find("span", class_="text-secondary")
        if date_span:
            date = self._norm(date_span.get_text(" ", strip=True))

        small = body.find("small", class_="text-dark")
        if small:
            organizer = self._norm(small.get_text(" ", strip=True))

        return Event(title=title, category=category, date=date, organizer=organizer, section=section)