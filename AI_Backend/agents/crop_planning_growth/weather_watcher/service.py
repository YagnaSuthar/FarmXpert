"""
WeatherService — fetches, validates and merges weather data for one farm.

Sources
  • OpenWeather  - current conditions and a 5-day / 3-hour forecast
                   (needs OPENWEATHER_API_KEY).
  • Open-Meteo   - current conditions and 14 days of daily aggregates in the
                   farm's own timezone (no key).

Guarantees a farmer can rely on
  • Every forecast day is a full-day aggregate for that local calendar date.
    3-hourly OpenWeather data is grouped by local date and used only when it
    covers the day; otherwise Open-Meteo's daily values are used, and each
    day says which source it came from.
  • One provider failing never fails the request. Without an OpenWeather key
    the agent runs on Open-Meteo alone. If every provider is down, the last
    good forecast (up to 6 h old) is served with a warning saying how old.
  • Corrupt provider values are dropped with a warning, never passed on.
  • Error messages are fixed strings. Provider errors carry the request URL,
    which includes the API key, so exception text is never logged or
    returned.
  • Alerts follow published thresholds (see config.ALERT_THRESHOLDS).

Performance
  • The three provider calls run concurrently over one pooled HTTP client.
  • Results are cached per ~1 km cell for 15 minutes, and concurrent
    requests for the same cell share a single fetch.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import math
import random
import threading
import time
import weakref
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from AI_Backend.agents.crop_planning_growth.weather_watcher import agromet
from AI_Backend.agents.crop_planning_growth.weather_watcher.config import (
    ALERT_THRESHOLDS,
    CACHE_COORD_DECIMALS,
    CACHE_MAX_ENTRIES,
    CACHE_STALE_MAX_SECONDS,
    CACHE_TTL_SECONDS,
    HTTP_BACKOFF_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT_SECONDS,
    LONG_RANGE_DAYS,
    MIN_SLOTS_FOR_FULL_DAY,
    MS_TO_KMH,
    OPENMETEO_BASE_URL,
    SHORT_TERM_DAYS,
    VALID_RAIN_MM,
    VALID_TEMP_C,
    VALID_WIND_KMH,
)

_TH = ALERT_THRESHOLDS

SOURCE_OPENWEATHER = "openweather"
SOURCE_OPENMETEO = "open-meteo"

# Open-Meteo reports WMO weather codes; map them onto OpenWeather's "main"
# vocabulary so `conditions` means the same thing whichever source won.
_WMO_CONDITIONS = {
    0: "Clear", 1: "Clouds", 2: "Clouds", 3: "Clouds", 45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Drizzle", 57: "Drizzle",
    61: "Rain", 63: "Rain", 65: "Rain", 66: "Rain", 67: "Rain",
    71: "Snow", 73: "Snow", 75: "Snow", 77: "Snow",
    80: "Rain", 81: "Rain", 82: "Rain", 85: "Snow", 86: "Snow",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# ═════════════════════════════════════════════════════════════════════════════
# Process-wide state: HTTP clients, cache, in-flight fetches
# ═════════════════════════════════════════════════════════════════════════════
#
# httpx.AsyncClient and asyncio tasks belong to one event loop, so both are
# kept per loop (a server has one; tests and workers may run several).

_clients: "weakref.WeakKeyDictionary[Any, httpx.AsyncClient]" = weakref.WeakKeyDictionary()
_inflight: "weakref.WeakKeyDictionary[Any, Dict[tuple, asyncio.Task]]" = weakref.WeakKeyDictionary()
_state_lock = threading.Lock()


def _shared_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        with _state_lock:
            client = _clients.get(loop)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT_SECONDS,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
                _clients[loop] = client
    return client


async def aclose_http_clients() -> None:
    """Close this loop's pooled client. Call from the app's shutdown hook."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    client = _clients.pop(loop, None)
    if client is not None and not client.is_closed:
        await client.aclose()


class _ForecastCache:
    """Bounded cache of assembled results, keyed by a ~1 km cell."""

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._data: "OrderedDict[tuple, Tuple[float, dict]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = self.stale_served = 0

    def get(self, key: tuple) -> Optional[Tuple[float, dict]]:
        with self._lock:
            entry = self._data.get(key)
            if entry is not None:
                self._data.move_to_end(key)
            return entry

    def set(self, key: tuple, value: dict) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = self.misses = self.stale_served = 0

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._data), "maxsize": self.maxsize,
                "ttl_seconds": CACHE_TTL_SECONDS, "hits": self.hits,
                "misses": self.misses, "stale_served": self.stale_served,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


_cache = _ForecastCache(CACHE_MAX_ENTRIES)


def cache_stats() -> dict:
    return _cache.stats()


def clear_cache() -> None:
    _cache.clear()


# ═════════════════════════════════════════════════════════════════════════════
# Service
# ═════════════════════════════════════════════════════════════════════════════

class WeatherService:
    def __init__(
        self,
        api_key: Optional[str],
        base_url: str,
        logger: Optional[logging.Logger] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key or None
        self.base_url = base_url.rstrip("/")
        self.logger = logger or logging.getLogger("farmxpert.weather")
        # Tests inject a mock transport; production shares the pooled client.
        self._transport = transport
        self._own_clients: "weakref.WeakKeyDictionary[Any, httpx.AsyncClient]" = (
            weakref.WeakKeyDictionary())

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def fetch(self, lat: float, lon: float, use_cache: bool = True) -> dict:
        """Current conditions, forecasts and alerts for one location.

        Never raises for provider trouble: the result's `status` is `ok`,
        `partial` or `unavailable`, and `warnings` says what went wrong.
        """
        key = (round(lat, CACHE_COORD_DECIMALS), round(lon, CACHE_COORD_DECIMALS),
               bool(self.api_key))

        if use_cache:
            entry = _cache.get(key)
            if entry is not None and time.time() - entry[0] <= CACHE_TTL_SECONDS:
                _cache.hits += 1
                return self._served_from_cache(entry, stale=False)
            _cache.misses += 1

        result = await self._single_flight(key, lat, lon)

        if result["status"] != "unavailable":
            _cache.set(key, result)
            return copy.deepcopy(result)

        # Every provider failed. An older forecast beats none, if it is recent.
        entry = _cache.get(key) if use_cache else None
        if entry is not None and time.time() - entry[0] <= CACHE_STALE_MAX_SECONDS:
            _cache.stale_served += 1
            stale = self._served_from_cache(entry, stale=True)
            stale["warnings"] = result["warnings"] + stale["warnings"]
            return stale
        return copy.deepcopy(result)

    async def _single_flight(self, key: tuple, lat: float, lon: float) -> dict:
        """Concurrent requests for the same cell share one provider round-trip."""
        loop = asyncio.get_running_loop()
        with _state_lock:
            tasks = _inflight.setdefault(loop, {})
            task = tasks.get(key)
            if task is None:
                task = loop.create_task(self._fetch_fresh(lat, lon))
                tasks[key] = task
                task.add_done_callback(lambda _t, k=key, d=tasks: d.pop(k, None))
        # shield: one caller being cancelled must not cancel the shared fetch.
        return await asyncio.shield(task)

    @staticmethod
    def _served_from_cache(entry: Tuple[float, dict], stale: bool) -> dict:
        stored_at, value = entry
        out = copy.deepcopy(value)
        age = int(time.time() - stored_at)
        out["cached"] = True
        out["data_age_seconds"] = age
        _drop_expired_spray_windows(out)
        if stale:
            out["status"] = "partial"
            out["warnings"] = list(out.get("warnings") or []) + [
                f"All weather providers are unreachable; showing the forecast fetched "
                f"{age // 60} minutes ago. Check again before acting on it."]
        return out

    # ─────────────────────────────────────────────────────────────────────────
    # One fresh fetch: concurrent calls, then merge
    # ─────────────────────────────────────────────────────────────────────────

    async def _fetch_fresh(self, lat: float, lon: float) -> dict:
        warnings: List[str] = []
        sources: Dict[str, str] = {}
        location = {"lat": lat, "lon": lon}

        if self.api_key:
            ow_current_raw, ow_forecast_raw, om_raw = await asyncio.gather(
                self._get_json(f"{self.base_url}/weather", self._ow_params(location),
                               "OpenWeather current", warnings),
                self._get_json(f"{self.base_url}/forecast",
                               {**self._ow_params(location), "cnt": 40},
                               "OpenWeather forecast", warnings),
                self._get_json(OPENMETEO_BASE_URL, self._om_params(location),
                               "Open-Meteo", warnings),
            )
        else:
            warnings.append(
                "OpenWeather API key not configured; using Open-Meteo only.")
            sources["openweather_current"] = sources["openweather_forecast"] = "skipped"
            ow_current_raw = ow_forecast_raw = None
            om_raw = await self._get_json(OPENMETEO_BASE_URL, self._om_params(location),
                                          "Open-Meteo", warnings)

        ow_current = self._parse_ow_current(ow_current_raw, warnings)
        ow_days, ow_today = self._parse_ow_forecast(ow_forecast_raw, warnings)
        om_current, om_days, om_today, tz_name = self._parse_openmeteo(om_raw, warnings)
        hourly, et0_by_date, utc_offset = self._parse_openmeteo_hourly(om_raw, warnings)

        # A source is "ok" when it answered with something readable - an empty
        # set of complete days is a valid answer, not a failure.
        if self.api_key:
            sources["openweather_current"] = "ok" if ow_current else "failed"
            sources["openweather_forecast"] = "ok" if ow_today is not None else "failed"
        sources["open_meteo"] = "ok" if om_today is not None else "failed"

        today = om_today or ow_today
        days = self._merge_days(ow_days, om_days, today)
        cutoff = _iso(today + timedelta(days=SHORT_TERM_DAYS)) if today else ""
        short = [d for d in days if d["date"] < cutoff]
        long_ = [d for d in days if d["date"] >= cutoff]

        current = ow_current or om_current
        if current is not None:
            current["rainfall_today"] = self._rainfall_today(days, today, warnings)

        # Where both models cover a date, the displayed day comes from one of
        # them - but a hazard predicted by the other must not vanish. Alerts
        # are raised if either model predicts one, and say so.
        second_opinion = [om_days[d["date"]] for d in days
                          if d["source"] == SOURCE_OPENWEATHER and d["date"] in om_days]
        now_local = ((datetime.now(timezone.utc) + timedelta(seconds=utc_offset))
                     .replace(tzinfo=None) if utc_offset is not None else None)
        advisory, agro_alerts = agromet.build(days, hourly, et0_by_date, now_local)
        if not hourly:
            warnings.append("Hourly forecast unavailable; spray windows and disease "
                            "risk could not be computed.")
        alerts = self.generate_alerts(current or {}, days, today=today,
                                      second_opinion=second_opinion,
                                      extra=agro_alerts,
                                      humidity_fallback=not hourly)

        has_forecast = bool(days)
        if current is None and not has_forecast:
            status = "unavailable"
        elif current is None or not has_forecast or "failed" in sources.values():
            status = "partial"
        else:
            status = "ok"

        return {
            "status": status,
            "location": location,
            "timezone": tz_name,
            "current_weather": current,
            "forecast_short_term": short,
            "forecast_long_term": long_,
            "alerts": alerts,
            "agro_advisory": advisory,
            "utc_offset_seconds": utc_offset,
            "sources": sources,
            "warnings": warnings,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cached": False,
            "data_age_seconds": 0,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # HTTP
    # ─────────────────────────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        if self._transport is None:
            return _shared_client()
        loop = asyncio.get_running_loop()
        client = self._own_clients.get(loop)
        if client is None:
            client = httpx.AsyncClient(transport=self._transport, timeout=HTTP_TIMEOUT_SECONDS)
            self._own_clients[loop] = client
        return client

    async def _get_json(self, url: str, params: dict, source: str,
                        warnings: List[str]) -> Optional[dict]:
        """GET with retries on transient failure. Never raises.

        Only a fixed description of the failure is recorded: httpx error
        messages include the full URL, and the OpenWeather URL carries the
        API key in its query string.
        """
        reason = "failed"
        for attempt in range(HTTP_MAX_RETRIES + 1):
            retryable = False
            try:
                response = await self._client().get(url, params=params)
            except httpx.TimeoutException:
                reason, retryable = "timed out", True
            except httpx.TransportError:
                reason, retryable = "connection failed", True
            except Exception:  # noqa: BLE001
                reason = "request failed"
            else:
                code = response.status_code
                if code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        reason = "returned an unreadable response"
                    else:
                        if isinstance(payload, dict):
                            return payload
                        reason = "returned an unexpected response"
                elif code in (401, 403):
                    reason = f"rejected the API key (HTTP {code})"
                elif code == 429:
                    reason, retryable = "rate limit reached (HTTP 429)", True
                elif code >= 500:
                    reason, retryable = f"is having problems (HTTP {code})", True
                else:
                    reason = f"refused the request (HTTP {code})"

            if retryable and attempt < HTTP_MAX_RETRIES:
                delay = HTTP_BACKOFF_SECONDS * (2 ** attempt)
                await asyncio.sleep(delay + random.uniform(0, delay / 2))
                continue
            break

        self.logger.warning("%s %s", source, reason)
        warnings.append(f"{source} {reason}.")
        return None

    def _ow_params(self, location: dict) -> dict:
        return {"lat": location["lat"], "lon": location["lon"],
                "appid": self.api_key, "units": "metric"}

    @staticmethod
    def _om_params(location: dict) -> dict:
        return {
            "latitude": location["lat"],
            "longitude": location["lon"],
            "daily": ",".join([
                "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                "precipitation_probability_max", "wind_speed_10m_max",
                "relative_humidity_2m_mean", "et0_fao_evapotranspiration",
            ]),
            # Hourly series drive the agromet indicators: spray windows
            # (Delta-T), leaf wetness, late blight and heat index.
            "hourly": ",".join([
                "temperature_2m", "relative_humidity_2m", "precipitation",
                "precipitation_probability", "wind_speed_10m", "is_day",
            ]),
            "current": ",".join([
                "temperature_2m", "relative_humidity_2m", "precipitation",
                "wind_speed_10m", "weather_code",
            ]),
            "wind_speed_unit": "kmh",
            "timezone": "auto",
            "forecast_days": LONG_RANGE_DAYS,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Parsers - each isolated: one bad payload cannot fail the others
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_ow_current(self, data: Optional[dict], warnings: List[str]) -> Optional[dict]:
        if not data:
            return None
        try:
            temp = float(data["main"]["temp"])
            humidity = float(data["main"]["humidity"])
            wind = float(data["wind"]["speed"]) * MS_TO_KMH
            if not (_within(temp, VALID_TEMP_C) and 0 <= humidity <= 100
                    and _within(wind, VALID_WIND_KMH)):
                raise ValueError("out of range")
            return {
                "temperature": round(temp, 1),
                "humidity": round(humidity, 1),
                "wind_speed": round(wind, 1),
                "conditions": (data.get("weather") or [{}])[0].get("main"),
                "rainfall_last_hour_mm": round(float((data.get("rain") or {}).get("1h", 0.0) or 0.0), 2),
                "source": SOURCE_OPENWEATHER,
            }
        except Exception:  # noqa: BLE001
            warnings.append("OpenWeather current conditions were unreadable and were ignored.")
            return None

    def _parse_ow_forecast(self, data: Optional[dict],
                           warnings: List[str]) -> Tuple[Dict[str, dict], Optional[date]]:
        """Group 3-hourly slots by the farm's local date; keep complete days only."""
        if not data:
            return {}, None
        try:
            tz = timezone(timedelta(seconds=int((data.get("city") or {}).get("timezone", 0))))
            today = datetime.now(tz).date()
            buckets: Dict[date, List[dict]] = defaultdict(list)
            for slot in data.get("list") or []:
                buckets[datetime.fromtimestamp(slot["dt"], tz).date()].append(slot)
        except Exception:  # noqa: BLE001
            warnings.append("OpenWeather forecast was unreadable and was ignored.")
            return {}, None

        days: Dict[str, dict] = {}
        dropped = 0
        for day_date, slots in buckets.items():
            if len(slots) < MIN_SLOTS_FOR_FULL_DAY:
                continue  # partial day: Open-Meteo's full-day value is used instead
            try:
                # Per-slot min/max, not the slot mean: 3-hourly samples miss
                # the afternoon peak and pre-dawn low.
                temp_min = min(float(s["main"].get("temp_min", s["main"]["temp"])) for s in slots)
                temp_max = max(float(s["main"].get("temp_max", s["main"]["temp"])) for s in slots)
                day = {
                    "date": _iso(day_date),
                    "temp_min": round(temp_min, 1),
                    "temp_max": round(temp_max, 1),
                    "rainfall_mm": round(sum(float((s.get("rain") or {}).get("3h", 0.0) or 0.0)
                                             for s in slots), 1),
                    "rain_probability_percent": round(
                        max(float(s.get("pop", 0.0) or 0.0) for s in slots) * 100.0, 1),
                    "humidity": round(sum(float(s["main"]["humidity"]) for s in slots)
                                      / len(slots), 1),
                    "wind_speed": round(max(float(s["wind"]["speed"]) for s in slots)
                                        * MS_TO_KMH, 1),
                    "source": SOURCE_OPENWEATHER,
                }
            except Exception:  # noqa: BLE001
                dropped += 1
                continue
            if self._valid_day(day):
                days[day["date"]] = day
            else:
                dropped += 1
        if dropped:
            warnings.append(f"{dropped} OpenWeather forecast day(s) had invalid values and were dropped.")
        return days, today

    def _parse_openmeteo(self, data: Optional[dict], warnings: List[str]
                         ) -> Tuple[Optional[dict], Dict[str, dict], Optional[date], Optional[str]]:
        if not data:
            return None, {}, None, None
        tz_name = data.get("timezone")

        current = None
        try:
            c = data.get("current") or {}
            if c.get("temperature_2m") is not None:
                temp = float(c["temperature_2m"])
                humidity = float(c.get("relative_humidity_2m"))
                wind = float(c.get("wind_speed_10m") or 0.0)
                if _within(temp, VALID_TEMP_C) and 0 <= humidity <= 100 and _within(wind, VALID_WIND_KMH):
                    current = {
                        "temperature": round(temp, 1),
                        "humidity": round(humidity, 1),
                        "wind_speed": round(wind, 1),
                        "conditions": _WMO_CONDITIONS.get(int(c.get("weather_code", -1))),
                        "rainfall_last_hour_mm": round(float(c.get("precipitation") or 0.0), 2),
                        "source": SOURCE_OPENMETEO,
                    }
        except Exception:  # noqa: BLE001
            current = None

        daily = data.get("daily")
        times = daily.get("time") if isinstance(daily, dict) else None
        if not isinstance(times, list):
            warnings.append("Open-Meteo forecast was unreadable and was ignored.")
            return current, {}, None, tz_name
        n = len(times)

        def column(*names):
            for name in names:
                values = daily.get(name)
                if isinstance(values, list) and len(values) == n:
                    return values
            return [None] * n

        tmax, tmin = column("temperature_2m_max"), column("temperature_2m_min")
        rain = column("precipitation_sum")
        pop = column("precipitation_probability_max")
        wind = column("wind_speed_10m_max", "windspeed_10m_max")
        hum = column("relative_humidity_2m_mean")

        days: Dict[str, dict] = {}
        dropped = 0
        for i in range(n):
            try:
                if tmax[i] is None or tmin[i] is None or rain[i] is None:
                    raise ValueError("missing")
                rainfall = float(rain[i])
                estimated = pop[i] is None
                day = {
                    "date": str(times[i]),
                    "temp_min": round(float(tmin[i]), 1),
                    "temp_max": round(float(tmax[i]), 1),
                    "rainfall_mm": round(rainfall, 1),
                    "rain_probability_percent": round(
                        self._estimate_pop_from_rainfall(rainfall) if estimated else float(pop[i]), 1),
                    "humidity": round(float(hum[i]), 1) if hum[i] is not None else None,
                    "wind_speed": round(float(wind[i] or 0.0), 1),
                    "source": SOURCE_OPENMETEO,
                }
                if estimated:
                    day["rain_probability_estimated"] = True
            except Exception:  # noqa: BLE001
                dropped += 1
                continue
            if self._valid_day(day):
                days[day["date"]] = day
            else:
                dropped += 1
        if dropped:
            warnings.append(f"{dropped} Open-Meteo forecast day(s) had missing or invalid values and were dropped.")

        today = None
        if times:
            try:
                today = date.fromisoformat(str(times[0]))
            except ValueError:
                today = None
        return current, days, today, tz_name

    def _parse_openmeteo_hourly(self, data: Optional[dict], warnings: List[str]
                                ) -> Tuple[List[dict], Dict[str, float], Optional[int]]:
        """Hourly series as local, naive datetimes, plus daily ET0 by date."""
        if not data:
            return [], {}, None
        try:
            offset: Optional[int] = int(data.get("utc_offset_seconds", 0))
        except (TypeError, ValueError):
            offset = None

        et0_by_date: Dict[str, float] = {}
        daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
        times, et0 = daily.get("time"), daily.get("et0_fao_evapotranspiration")
        if isinstance(times, list) and isinstance(et0, list) and len(times) == len(et0):
            for day, value in zip(times, et0):
                if value is not None and _within(value, (0.0, 20.0)):
                    et0_by_date[str(day)] = round(float(value), 2)

        hourly_raw = data.get("hourly") if isinstance(data.get("hourly"), dict) else {}
        h_times = hourly_raw.get("time")
        if not isinstance(h_times, list):
            return [], et0_by_date, offset
        n = len(h_times)

        def column(name):
            values = hourly_raw.get(name)
            return values if isinstance(values, list) and len(values) == n else None

        temp, rh = column("temperature_2m"), column("relative_humidity_2m")
        rain, pop = column("precipitation"), column("precipitation_probability")
        wind, is_day = column("wind_speed_10m"), column("is_day")
        if temp is None or rh is None or rain is None or wind is None:
            warnings.append("Open-Meteo hourly data was incomplete and was ignored.")
            return [], et0_by_date, offset

        hourly: List[dict] = []
        bad = 0
        for i in range(n):
            try:
                stamp = datetime.fromisoformat(str(h_times[i]))
                hour = {
                    "time": stamp,
                    "temp": float(temp[i]), "rh": float(rh[i]),
                    "precip": float(rain[i]), "wind": float(wind[i]),
                    "pop": float(pop[i]) if pop and pop[i] is not None else None,
                    # Without the provider's flag, 06:00-19:00 local is daylight.
                    "is_day": (bool(is_day[i]) if is_day and is_day[i] is not None
                               else 6 <= stamp.hour < 19),
                }
            except (TypeError, ValueError):
                bad += 1
                continue
            if (_within(hour["temp"], VALID_TEMP_C) and 0 <= hour["rh"] <= 100
                    and _within(hour["precip"], VALID_RAIN_MM)
                    and _within(hour["wind"], VALID_WIND_KMH)):
                hourly.append(hour)
            else:
                bad += 1
        if bad:
            warnings.append(f"{bad} hourly value(s) were missing or invalid and were ignored.")
        return hourly, et0_by_date, offset

    # ─────────────────────────────────────────────────────────────────────────
    # Merge + derived values
    # ─────────────────────────────────────────────────────────────────────────

    def _merge_days(self, ow_days: Dict[str, dict], om_days: Dict[str, dict],
                    today: Optional[date]) -> List[dict]:
        """One entry per local date from today on. A complete OpenWeather day
        wins (the precedence the agent always had); Open-Meteo fills the rest."""
        merged: Dict[str, dict] = dict(om_days)
        merged.update(ow_days)
        start = _iso(today) if today else None
        out = []
        for key in sorted(merged):
            if start and key < start:
                continue
            day = dict(merged[key])
            if day.get("humidity") is None and key in om_days:
                day["humidity"] = om_days[key].get("humidity")
            self._apply_risk_flags(day)
            # Flags drive what the scheduler lets happen that day (spraying,
            # field work). If the other model sees a risk, keep the flag up.
            if key in ow_days and key in om_days:
                other = dict(om_days[key])
                self._apply_risk_flags(other)
                for flag in ("frost_risk", "storm_warning", "heat_stress_risk", "spray_unsafe"):
                    day[flag] = day[flag] or other[flag]
            out.append(day)
        return out

    @staticmethod
    def _rainfall_today(days: List[dict], today: Optional[date],
                        warnings: List[str]) -> Optional[float]:
        """Full-day rain total for today (observed so far plus forecast)."""
        if today is not None:
            for day in days:
                if day["date"] == _iso(today):
                    return day["rainfall_mm"]
        warnings.append("Today's rainfall total is unavailable.")
        return None

    @staticmethod
    def _valid_day(day: dict) -> bool:
        return (_within(day["temp_min"], VALID_TEMP_C)
                and _within(day["temp_max"], VALID_TEMP_C)
                and day["temp_min"] <= day["temp_max"]
                and _within(day["rainfall_mm"], VALID_RAIN_MM)
                and _within(day["wind_speed"], VALID_WIND_KMH)
                and 0 <= day["rain_probability_percent"] <= 100
                and (day.get("humidity") is None or 0 <= day["humidity"] <= 100))

    @staticmethod
    def _apply_risk_flags(day: dict) -> None:
        """Day-level flags the scheduler and irrigation planner read."""
        day["frost_risk"] = day["temp_min"] <= _TH["frost_temp_c"]
        day["storm_warning"] = (day["wind_speed"] >= _TH["strong_wind_kmh"]
                                or day["rainfall_mm"] >= _TH["heavy_rainfall_mm"])
        day["heat_stress_risk"] = day["temp_max"] >= _TH["heat_stress_temp_c"]
        day["spray_unsafe"] = day["wind_speed"] > _TH["spray_wind_limit_kmh"]

    @staticmethod
    def _estimate_pop_from_rainfall(rainfall_mm: float) -> float:
        """Rough probability when the provider omits it; flagged as estimated."""
        if rainfall_mm <= 0.1:
            return 5.0
        if rainfall_mm < 2.0:
            return 35.0
        if rainfall_mm < 10.0:
            return 60.0
        if rainfall_mm < 30.0:
            return 80.0
        return 95.0

    # ─────────────────────────────────────────────────────────────────────────
    # Alerts
    # ─────────────────────────────────────────────────────────────────────────

    def generate_alerts(self, current: dict, forecast: List[dict],
                        today: Optional[date] = None,
                        second_opinion: Optional[List[dict]] = None,
                        extra: Optional[List[dict]] = None,
                        humidity_fallback: bool = True) -> List[dict]:
        """Alerts from current conditions and each forecast day.

        `second_opinion` holds the other model's values for dates where the
        displayed day came from one model. A hazard only that model predicts
        still raises an alert, worded as coming from one forecast model.

        One alert per (type, date): the most severe wins, and on a tie the
        primary forecast's wording is kept. Frost supersedes a cold-wave
        alert, and a heat wave supersedes heat stress, on the same day.
        """
        candidates: List[dict] = list(extra or [])
        today_iso = _iso(today) if today else None

        if current:
            temp = current.get("temperature")
            wind = current.get("wind_speed") or 0.0
            if temp is not None:
                candidates += self._heat_alerts(temp, today_iso, "current", "now")
                candidates += self._cold_alerts(temp, today_iso, "current", "now")
            candidates += self._wind_alerts(wind, today_iso, "current", "now", "high_wind")

        days = [(day, f"on {day['date']}") for day in forecast] + [
            (day, f"on {day['date']} (one forecast model)") for day in (second_opinion or [])]
        for day, when in days:
            candidates += self._heat_alerts(day["temp_max"], day["date"], "forecast", when)
            candidates += self._cold_alerts(day["temp_min"], day["date"], "forecast", when)
            candidates += self._wind_alerts(day["wind_speed"], day["date"], "forecast", when, "storm")
            candidates += self._rain_alerts(day["rainfall_mm"], day["date"], when)
            # Daily-mean humidity is a crude disease signal, used only when
            # the hourly leaf-wetness model (agromet) could not run.
            if humidity_fallback and day.get("humidity") is not None \
                    and day["humidity"] >= _TH["high_humidity_percent"]:
                candidates.append(_alert(
                    "high_humidity", "medium",
                    f"High humidity {when} ({day['humidity']:.0f}%): fungal disease risk.",
                    day["date"], "forecast",
                    ["Scout for fungal disease (blight, mildew) over the next days",
                     "Avoid overhead irrigation; water early so leaves dry",
                     "Hold fungicide spray until wind and rain allow"]))

        return _dedupe_alerts(candidates)

    @staticmethod
    def _heat_alerts(temp: float, day: Optional[str], source: str, when: str) -> List[dict]:
        if temp >= _TH["heatwave_temp_c"]:
            severe = temp >= _TH["severe_heatwave_temp_c"]
            return [_alert(
                "heatwave", "critical" if severe else "high",
                f"{'Severe heat wave' if severe else 'Heat wave'} {when}: {temp:.1f}°C.",
                day, source,
                ["Irrigate in early morning or evening, never at midday",
                 "Shade nurseries and young transplants",
                 "Stop field work between 12:00 and 16:00; keep workers hydrated"])]
        if temp >= _TH["heat_stress_temp_c"]:
            return [_alert(
                "heat_stress", "medium",
                f"Very hot {when}: {temp:.1f}°C. Crops may suffer heat stress.",
                day, source,
                ["Irrigate early morning or evening",
                 "Avoid spraying in the heat of the day"])]
        return []

    @staticmethod
    def _cold_alerts(temp: float, day: Optional[str], source: str, when: str) -> List[dict]:
        if temp <= _TH["frost_temp_c"]:
            hard = temp <= _TH["hard_frost_temp_c"]
            return [_alert(
                "frost", "critical" if hard else "high",
                f"Frost risk {when}: {temp:.1f}°C.",
                day, source,
                ["Irrigate lightly the evening before - moist soil holds heat",
                 "Cover nurseries and sensitive crops overnight",
                 "Smoke or windbreaks on the upwind side reduce ground frost"])]
        if temp <= _TH["cold_wave_temp_c"]:
            return [_alert(
                "cold_wave", "medium",
                f"Cold wave {when}: {temp:.1f}°C.",
                day, source,
                ["Protect nurseries and young seedlings overnight",
                 "Postpone transplanting until nights warm up"])]
        return []

    @staticmethod
    def _wind_alerts(wind: float, day: Optional[str], source: str, when: str,
                     alert_type: str) -> List[dict]:
        if wind >= _TH["strong_wind_kmh"]:
            gale = wind >= _TH["gale_wind_kmh"]
            return [_alert(
                alert_type, "critical" if gale else "high",
                f"{'Gale-force' if gale else 'Strong'} wind {when} ({wind:.0f} km/h).",
                day, source,
                ["Do not spray pesticide or fertilizer",
                 "Secure equipment, nets and polyhouse covers",
                 "Stake tall crops if possible"])]
        return []

    @staticmethod
    def _rain_alerts(rain: float, day: str, when: str) -> List[dict]:
        if rain >= _TH["extreme_rainfall_mm"]:
            label, severity = "Extremely heavy rain", "critical"
        elif rain >= _TH["very_heavy_rainfall_mm"]:
            label, severity = "Very heavy rain", "critical"
        elif rain >= _TH["heavy_rainfall_mm"]:
            label, severity = "Heavy rain", "high"
        else:
            return []
        return [_alert(
            "heavy_rainfall", severity,
            f"{label} expected {when} ({rain:.0f} mm).",
            day, "forecast",
            ["Clear field drains and channels now",
             "Postpone fertilizer and pesticide application",
             "Harvest mature produce before the rain if you can"])]

    # ─────────────────────────────────────────────────────────────────────────
    # Backwards-compatible surface
    # ─────────────────────────────────────────────────────────────────────────

    async def fetch_current_weather(self, location: dict) -> dict:
        result = await self.fetch(float(location["lat"]), float(location["lon"]))
        return result.get("current_weather") or {}

    async def fetch_openweather_forecast(self, location: dict) -> List[dict]:
        result = await self.fetch(float(location["lat"]), float(location["lon"]))
        return result.get("forecast_short_term") or []

    async def fetch_openmeteo_forecast(self, location: dict) -> List[dict]:
        result = await self.fetch(float(location["lat"]), float(location["lon"]))
        return result.get("forecast_long_term") or []


# ═════════════════════════════════════════════════════════════════════════════
# helpers
# ═════════════════════════════════════════════════════════════════════════════

def _drop_expired_spray_windows(result: dict) -> None:
    """A cached forecast can outlive its first spray windows; remove them."""
    advisory = result.get("agro_advisory") or {}
    offset = result.get("utc_offset_seconds")
    if not advisory.get("spray_windows") or offset is None:
        return
    now_local = (datetime.now(timezone.utc) + timedelta(seconds=offset)).replace(tzinfo=None)
    advisory["spray_windows"] = [
        w for w in advisory["spray_windows"]
        if datetime.fromisoformat(w["end"]) > now_local]


def _iso(d: date) -> str:
    return d.isoformat()


def _within(value: Any, bounds: tuple) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and bounds[0] <= v <= bounds[1]


def _alert(alert_type: str, severity: str, message: str, day: Optional[str],
           source: str, recommendations: List[str]) -> dict:
    return {"type": alert_type, "severity": severity, "message": message,
            "date": day, "source": source, "recommendations": recommendations}


def _dedupe_alerts(candidates: List[dict]) -> List[dict]:
    superseded_by = {"cold_wave": "frost", "heat_stress": "heatwave"}
    best: Dict[tuple, dict] = {}
    for alert in candidates:
        key = (alert["type"], alert["date"])
        kept = best.get(key)
        if kept is None or _SEVERITY_RANK[alert["severity"]] > _SEVERITY_RANK[kept["severity"]]:
            best[key] = alert
    out = [a for a in best.values()
           if not (a["type"] in superseded_by
                   and (superseded_by[a["type"]], a["date"]) in best)]
    return sorted(out, key=lambda a: (a["date"] or "", -_SEVERITY_RANK[a["severity"]], a["type"]))
