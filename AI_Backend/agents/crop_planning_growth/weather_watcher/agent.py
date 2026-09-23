"""
WeatherAgent — current conditions, 14-day forecast and alerts for one farm.

Accepts any of:
  • {"lat": .., "lon": ..}                            (router)
  • {"location": {"lat": .., "lon": ..}}              (LangGraph state)
  • {"farm": {"location": {"lat": .., "lon": ..}}}    (scheduler-style state)
  • an object exposing .lat / .lon

Output keys consumed elsewhere are unchanged: `current_weather`,
`forecast_short_term` (read by irrigation), `forecast_long_term` (read by crop
prediction), `alerts` (read by the scheduler adapter), `warnings`. Everything
else - `status`, `sources`, `timezone`, `cached`, `data_age_seconds`, per-day
`source` - is additive.

`status` tells a caller how far to trust the answer:
  ok          every provider answered
  partial     something is missing or came from cache after an outage;
              `warnings` says what
  unavailable no weather data at all - do not act on this response
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from AI_Backend.agents.base.base_agent import BaseAgent
from AI_Backend.agents.crop_planning_growth.weather_watcher.config import (
    AGENT_ID,
    AGENT_VERSION,
    OPENWEATHER_BASE_URL,
)
from AI_Backend.agents.crop_planning_growth.weather_watcher.service import (
    WeatherService,
    cache_stats,
)

load_dotenv()


class WeatherAgent(BaseAgent):
    AGENT_ID = AGENT_ID
    AGENT_VERSION = AGENT_VERSION

    def __init__(
        self,
        name: str = "WeatherWatcher",
        api_key: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        super().__init__(name)
        self.api_key = api_key if api_key is not None else os.getenv("OPENWEATHER_API_KEY")
        if not self.api_key:
            self.logger.warning(
                "OPENWEATHER_API_KEY not set - running on Open-Meteo only.")
        self.base_url = OPENWEATHER_BASE_URL
        self.service = WeatherService(
            api_key=self.api_key,
            base_url=self.base_url,
            logger=self.logger,
            transport=transport,
        )

    async def run(self, input_data: Any) -> dict:
        """Fetch weather for the location in `input_data`. Never raises."""
        location, problem = self._normalise_location(input_data)
        if location is None:
            self.logger.error("WeatherAgent.run: %s", problem)
            return self._error_payload(problem)

        result = await self.service.fetch(location["lat"], location["lon"])
        result["agent_id"] = self.AGENT_ID
        result["agent_version"] = self.AGENT_VERSION

        self.logger.info(
            "WeatherAgent v%s | lat=%.4f lon=%.4f status=%s cached=%s days=%d alerts=%d",
            self.AGENT_VERSION, location["lat"], location["lon"], result["status"],
            result["cached"],
            len(result["forecast_short_term"]) + len(result["forecast_long_term"]),
            len(result["alerts"]),
        )
        return self.postprocess(result)

    async def get_weather_data(self, location: dict) -> dict:
        """Kept for existing callers: the four core blocks only."""
        result = await self.service.fetch(float(location["lat"]), float(location["lon"]))
        return {
            "current_weather": result["current_weather"] or {},
            "forecast_short_term": result["forecast_short_term"],
            "forecast_long_term": result["forecast_long_term"],
            "alerts": result["alerts"],
        }

    def health(self) -> dict:
        return {
            "agent_id": self.AGENT_ID,
            "agent_version": self.AGENT_VERSION,
            # Whether a key is set - never the key.
            "openweather_configured": bool(self.api_key),
            "fallback_provider": "open-meteo",
            "cache": cache_stats(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Input normalisation
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_location(input_data: Any) -> tuple[Optional[dict], str]:
        """Return ({lat, lon}, "") or (None, reason)."""
        lat = lon = None
        if input_data is None:
            pass
        elif hasattr(input_data, "lat") and hasattr(input_data, "lon"):
            lat, lon = input_data.lat, input_data.lon
        elif isinstance(input_data, dict):
            for candidate in (
                input_data,
                input_data.get("location"),
                (input_data.get("farm") or {}).get("location")
                if isinstance(input_data.get("farm"), dict) else None,
            ):
                if isinstance(candidate, dict) and "lat" in candidate and "lon" in candidate:
                    lat, lon = candidate["lat"], candidate["lon"]
                    break

        if lat is None or lon is None:
            return None, "Missing 'lat'/'lon' in input."
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return None, "'lat'/'lon' must be numbers."
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return None, "'lat'/'lon' must be finite numbers."
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None, "'lat' must be within -90..90 and 'lon' within -180..180."
        return {"lat": lat, "lon": lon}, ""

    def _error_payload(self, msg: str) -> dict:
        return self.postprocess({
            "agent_id": self.AGENT_ID,
            "agent_version": self.AGENT_VERSION,
            "status": "unavailable",
            "location": None,
            "timezone": None,
            "current_weather": None,
            "forecast_short_term": [],
            "forecast_long_term": [],
            "alerts": [],
            "sources": {},
            "warnings": [msg],
            "fetched_at": None,
            "cached": False,
            "data_age_seconds": 0,
        })
