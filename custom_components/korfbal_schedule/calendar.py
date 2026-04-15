"""Calendar platform for Korfbal Schedule."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .coordinator import KorfbalMatch, KorfbalScheduleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Korfbal calendar."""
    coordinator: KorfbalScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KorfbalCalendar(coordinator, entry)], True)


class KorfbalCalendar(CoordinatorEntity[KorfbalScheduleCoordinator], CalendarEntity):
    """Calendar entity for a korfball team's schedule."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KorfbalScheduleCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_name = f"{coordinator.team_name} Wedstrijden"
        self._attr_icon = "mdi:calendar-star"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming match as the current event."""
        now = datetime.now(tz=self.coordinator.data[0].start.tzinfo if self.coordinator.data else None)
        upcoming = [
            m for m in (self.coordinator.data or [])
            if m.end > now and m.status != "cancelled"
        ]
        if not upcoming:
            return None
        upcoming.sort(key=lambda m: m.start)
        return self._match_to_event(upcoming[0])

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return all events within the given date range."""
        events: list[CalendarEvent] = []
        for match in (self.coordinator.data or []):
            if match.start < end_date and match.end > start_date:
                events.append(self._match_to_event(match))
        return events

    @staticmethod
    def _match_to_event(match: KorfbalMatch) -> CalendarEvent:
        """Convert a KorfbalMatch to a CalendarEvent."""
        return CalendarEvent(
            start=match.start,
            end=match.end,
            summary=match.summary,
            description=match.description,
            location=match.location,
        )
