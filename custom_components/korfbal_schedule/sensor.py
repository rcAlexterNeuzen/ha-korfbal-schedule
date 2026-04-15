"""Sensor platform for Korfbal Schedule.

Provides three sensors:
  - sensor.korfbal_<team>_volgende_wedstrijd — datetime of next match + full details
  - sensor.korfbal_<team>_aantal_wedstrijden — number of upcoming matches
  - sensor.korfbal_<team>_laatste_uitslag    — score of the most recent played match
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .coordinator import KorfbalScheduleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Korfbal sensors."""
    coordinator: KorfbalScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            KorfbalNextMatchSensor(coordinator, entry),
            KorfbalMatchCountSensor(coordinator, entry),
            KorfbalLastResultSensor(coordinator, entry),
        ],
        True,
    )


class KorfbalNextMatchSensor(CoordinatorEntity[KorfbalScheduleCoordinator], SensorEntity):
    """Sensor showing the next match date/time."""

    _attr_icon = "mdi:whistle"
    _attr_has_entity_name = True

    def __init__(self, coordinator: KorfbalScheduleCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_match"
        self._attr_name = f"{coordinator.team_name} Volgende Wedstrijd"

    @property
    def _next_match(self):
        now = datetime.now().astimezone()
        upcoming = [
            m for m in (self.coordinator.data or [])
            if m.end > now and m.status != "cancelled"
        ]
        upcoming.sort(key=lambda m: m.start)
        return upcoming[0] if upcoming else None

    @property
    def native_value(self) -> datetime | None:
        """State is the datetime of the next match (required for device_class timestamp)."""
        m = self._next_match
        return m.start if m else None

    @property
    def extra_state_attributes(self) -> dict:
        """Full match details as attributes (useful for automations/lovelace)."""
        m = self._next_match
        if not m:
            return {}
        return {
            "home_team": m.home_team,
            "away_team": m.away_team,
            "start": m.start.isoformat(),
            "end": m.end.isoformat(),
            "location": m.location,
            "competition": m.competition,
            "status": m.status,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "match_id": m.match_id,
        }

    @property
    def device_class(self) -> str:
        return "timestamp"


class KorfbalMatchCountSensor(CoordinatorEntity[KorfbalScheduleCoordinator], SensorEntity):
    """Sensor showing how many upcoming matches are scheduled."""

    _attr_icon = "mdi:counter"
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "wedstrijden"

    def __init__(self, coordinator: KorfbalScheduleCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_match_count"
        self._attr_name = f"{coordinator.team_name} Aantal Wedstrijden"

    @property
    def native_value(self) -> int:
        now = datetime.now().astimezone()
        return sum(
            1 for m in (self.coordinator.data or [])
            if m.end > now and m.status != "cancelled"
        )


class KorfbalLastResultSensor(CoordinatorEntity[KorfbalScheduleCoordinator], SensorEntity):
    """Sensor showing the most recent played match result."""

    _attr_icon = "mdi:scoreboard"
    _attr_has_entity_name = True

    def __init__(self, coordinator: KorfbalScheduleCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_laatste_uitslag"
        self._attr_name = f"{coordinator.team_name} Laatste Uitslag"

    @property
    def _last_match(self):
        played = [
            m for m in (self.coordinator.data or [])
            if m.status == "played" and m.home_score is not None
        ]
        if not played:
            return None
        played.sort(key=lambda m: m.start, reverse=True)
        return played[0]

    @property
    def native_value(self) -> str | None:
        """State is the score string, e.g. '4 - 2'."""
        m = self._last_match
        if not m:
            return None
        return f"{m.home_score} - {m.away_score}"

    @property
    def extra_state_attributes(self) -> dict:
        m = self._last_match
        if not m:
            return {}
        home_score = m.home_score or 0
        away_score = m.away_score or 0
        # m.is_home_game is not available here; use whether home_team contains
        # the tracked team name as a best-effort indicator.
        tracked_is_home = self.coordinator.team_name.lower() in m.home_team.lower()
        tracked_score = home_score if tracked_is_home else away_score
        opponent_score = away_score if tracked_is_home else home_score
        if tracked_score > opponent_score:
            uitslag = "gewonnen"
        elif tracked_score < opponent_score:
            uitslag = "verloren"
        else:
            uitslag = "gelijkspel"
        return {
            "home_team": m.home_team,
            "away_team": m.away_team,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "date": m.start.isoformat(),
            "location": m.location,
            "competition": m.competition,
            "match_id": m.match_id,
            "uitslag": uitslag,
        }
