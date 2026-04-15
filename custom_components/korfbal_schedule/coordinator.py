"""Data coordinator for Korfbal Schedule.

Two fetch strategies:
1. Sportlink Club.Dataservice API  — used when `sportlink_client_id` is set.
   Endpoint: https://data.sportlink.com/programma
   Docs: https://sportlinkservices.freshdesk.com/nl/support/solutions/articles/9000062942

2. Mijn Korfbal public page scraper — fallback, no API key required.
   The SPA loads data from an internal JSON endpoint that we reverse-engineer.
   Known pattern: https://mijn.korfbal.nl/api/v1/team/{team_code}/matches
   (observed in browser DevTools network tab)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

TZ_NL = ZoneInfo("Europe/Amsterdam")
SCAN_INTERVAL = timedelta(hours=6)

# Sportlink Club.Dataservice base URL
SPORTLINK_API_BASE = "https://data.sportlink.com"

# Mijn Korfbal internal API (reverse-engineered from SPA network traffic)
MIJN_KORFBAL_API = "https://mijn.korfbal.nl/api/v1"


@dataclass
class KorfbalMatch:
    """Represents a single korfball match."""

    match_id: str
    home_team: str
    away_team: str
    start: datetime
    end: datetime
    location: str
    competition: str
    status: str  # "scheduled", "cancelled", "played"
    home_score: int | None
    away_score: int | None

    @property
    def summary(self) -> str:
        """Calendar event summary."""
        return f"🏐 {self.home_team} – {self.away_team}"

    @property
    def description(self) -> str:
        """Calendar event description."""
        lines = [
            f"Competitie: {self.competition}",
            f"Locatie: {self.location}",
            f"Status: {self.status}",
        ]
        if self.home_score is not None:
            lines.append(f"Uitslag: {self.home_score}–{self.away_score}")
        return "\n".join(lines)


class KorfbalScheduleCoordinator(DataUpdateCoordinator[list[KorfbalMatch]]):
    """Coordinator that fetches match data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Korfbal Schedule",
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.team_code: str = entry.data["team_code"]
        self.club_code: str = entry.data["club_code"]
        self.client_id: str = entry.data.get("sportlink_client_id", "")
        self.team_name: str = entry.data.get("team_name", self.team_code)

    async def _async_update_data(self) -> list[KorfbalMatch]:
        """Fetch data from either Sportlink API or scraper fallback."""
        session = async_get_clientsession(self.hass)
        try:
            if self.client_id:
                return await self._fetch_sportlink_api(session)
            else:
                return await self._fetch_mijn_korfbal(session)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error fetching korfbal schedule: {err}") from err

    # ------------------------------------------------------------------ #
    # Strategy 1: Official Sportlink Club.Dataservice API                 #
    # ------------------------------------------------------------------ #
    async def _fetch_sportlink_api(self, session: aiohttp.ClientSession) -> list[KorfbalMatch]:
        """Fetch schedule via the Sportlink Club.Dataservice API.

        Requires a valid clientId obtained from Sportlink Services.
        The 'programma' endpoint returns upcoming fixtures.
        """
        params = {
            "clientId": self.client_id,
            "teamcode": self.team_code,
            "aantaldagen": 90,          # look ahead 90 days
            "sorteervolgorde": "datum-tijd",
            "eigenwedstrijden": "ja",
            "gebruiklokaleteamnaam": "ja",
        }
        url = f"{SPORTLINK_API_BASE}/programma"
        _LOGGER.debug("Fetching Sportlink API: %s params=%s", url, params)

        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        matches: list[KorfbalMatch] = []
        for item in data if isinstance(data, list) else []:
            match = self._parse_sportlink_match(item)
            if match:
                matches.append(match)
        _LOGGER.info("Fetched %d matches via Sportlink API", len(matches))
        return matches

    def _parse_sportlink_match(self, item: dict[str, Any]) -> KorfbalMatch | None:
        """Parse one Sportlink API match object."""
        try:
            # Sportlink returns datum as "DD-MM-YYYY" and aanvangstijd as "HH:MM"
            raw_date = item.get("datum", "")
            raw_time = item.get("aanvangstijd", "00:00")
            if not raw_date:
                return None

            # Parse Dutch date format
            day, month, year = raw_date.split("-")
            hour, minute = raw_time.split(":")
            start = datetime(
                int(year), int(month), int(day),
                int(hour), int(minute),
                tzinfo=TZ_NL,
            )
            end = start + timedelta(hours=1, minutes=30)

            home_score = item.get("thuisscore")
            away_score = item.get("uitscore")

            return KorfbalMatch(
                match_id=str(item.get("wedstrijdcode", f"{raw_date}-{raw_time}")),
                home_team=item.get("thuisteam", "Thuis"),
                away_team=item.get("uitteam", "Uit"),
                start=start,
                end=end,
                location=item.get("accommodatie", item.get("plaats", "Onbekend")),
                competition=item.get("poule", item.get("competitie", "")),
                status="cancelled" if item.get("status", "").lower() == "afgelast" else "scheduled",
                home_score=int(home_score) if home_score not in (None, "", "-") else None,
                away_score=int(away_score) if away_score not in (None, "", "-") else None,
            )
        except (ValueError, KeyError, TypeError) as err:
            _LOGGER.warning("Could not parse Sportlink match item %s: %s", item, err)
            return None

    # ------------------------------------------------------------------ #
    # Strategy 2: Mijn Korfbal public SPA scraper (no API key needed)    #
    # ------------------------------------------------------------------ #
    async def _fetch_mijn_korfbal(self, session: aiohttp.ClientSession) -> list[KorfbalMatch]:
        """Scrape schedule from the mijn.korfbal.nl SPA internal API.

        The SPA (Vue/React) loads match data from a JSON endpoint.
        This reverse-engineers the network requests the browser makes.
        If the endpoint changes, update MIJN_KORFBAL_API accordingly.

        Observed endpoint from DevTools:
          GET /api/v1/teams/{teamCode}/matches?season=current
        """
        headers = {
            "Accept": "application/json",
            "Referer": f"https://mijn.korfbal.nl/team/details/{self.club_code}/{self.team_code}/programma",
            "X-Requested-With": "XMLHttpRequest",
        }

        # Try the JSON API endpoint first
        url = f"{MIJN_KORFBAL_API}/teams/{self.team_code}/matches"
        _LOGGER.debug("Fetching Mijn Korfbal API: %s", url)

        async with session.get(
            url,
            headers=headers,
            params={"season": "current"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json(content_type=None)
                    matches = self._parse_mijn_korfbal_json(data)
                    _LOGGER.info("Fetched %d matches via Mijn Korfbal JSON API", len(matches))
                    return matches
                except Exception as err:
                    _LOGGER.warning("JSON parse failed (%s), falling back to HTML scraper", err)

        # Fallback: parse the HTML page with regex/BeautifulSoup
        return await self._scrape_html_page(session)

    def _parse_mijn_korfbal_json(self, data: Any) -> list[KorfbalMatch]:
        """Parse JSON response from mijn.korfbal.nl internal API."""
        matches: list[KorfbalMatch] = []
        items = data if isinstance(data, list) else data.get("matches", data.get("data", []))
        for item in items:
            match = self._parse_mijn_korfbal_match(item)
            if match:
                matches.append(match)
        return matches

    def _parse_mijn_korfbal_match(self, item: dict[str, Any]) -> KorfbalMatch | None:
        """Parse a single match from the Mijn Korfbal JSON response."""
        try:
            # Common field names observed in the SPA network traffic
            raw_dt = (
                item.get("startDateTime")
                or item.get("matchDateTime")
                or item.get("date")
                or item.get("datum")
            )
            if not raw_dt:
                return None

            # Try ISO format first, then Dutch format
            try:
                start = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
                start = start.astimezone(TZ_NL)
            except ValueError:
                # Dutch format DD-MM-YYYY HH:MM
                parts = str(raw_dt).split()
                d, m, y = parts[0].split("-")
                h, mn = (parts[1].split(":") if len(parts) > 1 else ["00", "00"])
                start = datetime(int(y), int(m), int(d), int(h), int(mn), tzinfo=TZ_NL)

            end = start + timedelta(hours=1, minutes=30)

            home = item.get("homeTeam") or item.get("thuisteam", {})
            away = item.get("awayTeam") or item.get("uitteam", {})
            home_name = home if isinstance(home, str) else home.get("name", home.get("naam", "Thuis"))
            away_name = away if isinstance(away, str) else away.get("name", away.get("naam", "Uit"))

            location_raw = item.get("location") or item.get("venue") or item.get("accommodatie") or {}
            location = location_raw if isinstance(location_raw, str) else (
                location_raw.get("name") or location_raw.get("naam") or
                location_raw.get("city") or location_raw.get("plaats") or "Onbekend"
            )

            status_raw = str(item.get("status", "")).lower()
            status = "cancelled" if "afgelast" in status_raw or "cancel" in status_raw else "scheduled"

            return KorfbalMatch(
                match_id=str(item.get("id") or item.get("matchId") or item.get("wedstrijdcode") or raw_dt),
                home_team=home_name,
                away_team=away_name,
                start=start,
                end=end,
                location=location,
                competition=str(item.get("competition") or item.get("competitie") or item.get("poule") or ""),
                status=status,
                home_score=item.get("homeScore") or item.get("thuisscore"),
                away_score=item.get("awayScore") or item.get("uitscore"),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as err:
            _LOGGER.warning("Could not parse Mijn Korfbal match %s: %s", item, err)
            return None

    async def _scrape_html_page(self, session: aiohttp.ClientSession) -> list[KorfbalMatch]:
        """Last-resort HTML scraper using regex on the rendered page source.

        NOTE: The mijn.korfbal.nl SPA renders client-side, so this fetches
        the page shell and looks for any JSON data bootstrapped into the HTML.
        For a fully JS-rendered page you would need a headless browser
        (Playwright/Selenium). Consider using the Sportlink API instead.
        """
        import json
        import re

        url = f"https://mijn.korfbal.nl/team/details/{self.club_code}/{self.team_code}/programma"
        _LOGGER.debug("HTML scrape fallback: %s", url)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            html = await resp.text()

        # Look for JSON data bootstrapped into the page
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'window\.__data__\s*=\s*({.*?});',
            r'"programma"\s*:\s*(\[.*?\])',
            r'"matches"\s*:\s*(\[.*?\])',
            r'"wedstrijden"\s*:\s*(\[.*?\])',
        ]
        for pattern in patterns:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                try:
                    raw = json.loads(m.group(1))
                    items = raw if isinstance(raw, list) else (
                        raw.get("matches") or raw.get("wedstrijden") or []
                    )
                    matches = [self._parse_mijn_korfbal_match(i) for i in items]
                    matches = [m for m in matches if m is not None]
                    if matches:
                        _LOGGER.info("Scraped %d matches from HTML", len(matches))
                        return matches
                except json.JSONDecodeError:
                    continue

        _LOGGER.warning(
            "Could not extract schedule from HTML. The SPA may require a headless browser. "
            "Consider providing a Sportlink clientId for the official API."
        )
        return []
