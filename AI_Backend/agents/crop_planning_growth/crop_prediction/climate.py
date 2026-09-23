"""Season climate for a farm, from ten years of ERA5 reanalysis.

The model scores a field against conditions over the *growing season*: rain
totalled over it, temperature and humidity averaged over it. A caller cannot
know those for a season that has not happened, and a 14-day forecast is not a
stand-in for four months. What agronomy uses instead is climatology - what
this exact location has actually had in this season, year after year.

Source: Open-Meteo Historical Weather API (ECMWF ERA5 reanalysis, ~25 km),
no API key. Ten complete years are fetched once per ~11 km cell and cached
for 30 days in memory and on disk - climate normals do not move within a
month, and a farm's history should be fetched once, not once per restart.

Caveat carried into every output: ERA5 rain is modelled, not gauged, and has
a known wet bias over parts of the Indian monsoon. The dry-year (20th
percentile) figure is reported alongside the median for that reason.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import pathlib
import statistics
import threading
import time
import weakref
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
YEARS = 10
TIMEOUT_S = 12.0
CACHE_TTL_S = 30 * 24 * 3600.0
CACHE_MAX = 512
# ERA5 is a ~25 km grid; one decimal (~11 km) is one cell for caching.
COORD_DECIMALS = 1
# The model takes one season window for all crops. The median duration of
# the Gujarat varieties is 106 days; four months covers it.
SEASON_DAYS = 120

# Disk cache shared by every worker and kept across restarts. Set the env
# var to "" to disable. Default: AI_Backend/.cache/climate (git-ignored).
CACHE_DIR = os.getenv(
    "CROP_PREDICTION_CLIMATE_CACHE_DIR",
    str(pathlib.Path(__file__).resolve().parents[3] / ".cache" / "climate"))

SOURCE_NOTE = ("ERA5 reanalysis via Open-Meteo, last 10 complete years. Modelled, "
               "not gauged: treat as an estimate of this location's normal season.")

_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_cache_lock = threading.Lock()

logger = logging.getLogger(__name__)


class ClimateUnavailable(RuntimeError):
    """Climatology could not be obtained; callers fall back without it."""


class Climatology:
    """Daily ERA5 series for one location, with season arithmetic on top."""

    def __init__(self, days: Dict[date, dict], lat: float, lon: float):
        self.days = days
        self.lat, self.lon = lat, lon
        self.years = sorted({d.year for d in days})

    # -- season windows -----------------------------------------------------
    def _window(self, year: int, month: int, length_days: int) -> Optional[List[dict]]:
        start = date(year, month, 1)
        values = []
        for offset in range(length_days):
            day = self.days.get(start + timedelta(days=offset))
            if day is None:
                return None          # window runs past the record: skip the year
            values.append(day)
        return values

    def season(self, month: int, length_days: int = SEASON_DAYS) -> Optional[dict]:
        """Median season rain, dry-year rain, mean temperature and humidity."""
        rains, temps, hums, by_year = [], [], [], {}
        for year in self.years:
            window = self._window(year, month, length_days)
            if not window:
                continue
            rain = sum(d["rain"] for d in window)
            rains.append(rain)
            by_year[year] = round(rain)
            temps.extend(d["temp"] for d in window if d["temp"] is not None)
            hums.extend(d["rh"] for d in window if d["rh"] is not None)
        if len(rains) < 5:
            return None
        return {
            "years": len(rains),
            "window_days": length_days,
            "rain_median_mm": round(statistics.median(rains), 1),
            "rain_dry_year_mm": round(_percentile(rains, 20), 1),
            "rain_by_year_mm": by_year,
            "temp_mean_c": round(statistics.fmean(temps), 1) if temps else None,
            "humidity_mean_percent": round(statistics.fmean(hums), 1) if hums else None,
        }

    def rainfed_supply_by_year(self, month: int, length_days: int,
                               water_need_mm: float, taw_mm: float) -> List[float]:
        """Share of the crop's water need that rain met, per past season.

        Daily soil water balance after FAO-56 (Allen et al., 1998, ch. 8):
          • the root zone is a bucket holding `taw_mm` of plant-available
            water; rain fills it, and what does not fit drains below the
            roots and is lost;
          • daily crop demand follows the FAO-56 crop-coefficient curve
            (see `crop_demand_curve`) and sums to `water_need_mm`;
          • below the readily-available fraction (p = 0.5) the crop cannot
            draw at full rate: uptake falls linearly with the water left
            (the FAO-56 Ks stress coefficient, eq. 84).
        The season starts with the root zone half full, a neutral assumption
        for a field sown after the first rains.

        Why a water balance and not seasonal "effective rainfall": monsoon
        rain falls in a few weeks while the crop drinks for months. On a
        heavy soil much of that rain is stored and used later; on sand it
        drains away. Only a day-by-day balance sees either.
        """
        weights = crop_demand_curve(length_days)
        readily_available = 0.5 * taw_mm
        out = []
        for year in self.years:
            window = self._window(year, month, length_days)
            if not window:
                continue
            storage = 0.5 * taw_mm
            supplied = 0.0
            for day, weight in zip(window, weights):
                storage = min(taw_mm, storage + day["rain"])
                demand = weight * water_need_mm
                if storage >= taw_mm - readily_available:
                    uptake = demand
                else:
                    uptake = demand * storage / (taw_mm - readily_available)
                uptake = min(uptake, storage)
                storage -= uptake
                supplied += uptake
            out.append(supplied / water_need_mm if water_need_mm else 1.0)
        return out


def crop_demand_curve(length_days: int) -> List[float]:
    """Daily share of seasonal crop water use, shaped like the FAO-56 Kc curve.

    Generic stage split (FAO-56 Table 11 typical proportions): initial 15 %,
    development 25 %, mid-season 40 %, late 20 % of the season, with Kc
    rising from 0.4 to 1.0, holding, then falling to 0.6. Normalised to sum
    to 1, so multiplying by the crop's seasonal need gives daily demand.
    A crop uses little water as a seedling and most at flowering - a flat
    split would overstate early stress and understate the critical middle.
    """
    n = max(1, int(length_days))
    ini, dev, mid = int(0.15 * n), int(0.25 * n), int(0.40 * n)
    kc = []
    for i in range(n):
        if i < ini:
            kc.append(0.4)
        elif i < ini + dev:
            kc.append(0.4 + 0.6 * (i - ini + 1) / max(1, dev))
        elif i < ini + dev + mid:
            kc.append(1.0)
        else:
            late = n - (ini + dev + mid)
            kc.append(1.0 - 0.4 * (i - ini - dev - mid + 1) / max(1, late))
    total = sum(kc)
    return [k / total for k in kc]


def _percentile(values: List[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def get_climatology(lat: float, lon: float,
                          transport: Optional[httpx.AsyncBaseTransport] = None) -> Climatology:
    """Climate record for a location. Raises ClimateUnavailable.

    Three levels, fastest first: memory (microseconds), disk (a few ms -
    survives restarts and is shared by every worker process), then the ERA5
    archive (~2 s). A farm's climate history does not change, so after the
    first request it should never be fetched again within the TTL.
    Concurrent requests for the same cell share one fetch.
    """
    key = (round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS))
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL_S:
            _cache.move_to_end(key)
            return hit[1]

    payload = await asyncio.to_thread(_read_disk, key)
    if payload is None:
        payload = await _single_flight(key, lat, lon, transport)
    days = _parse(payload)
    if len(days) < 365 * 5:
        raise ClimateUnavailable("Climate history was incomplete.")
    climatology = Climatology(days, lat, lon)
    _remember(key, climatology)
    return climatology


async def prefetch(lat: float, lon: float) -> bool:
    """Warm the cache for a farm ahead of its first question. Never raises.

    Call it when a farm is registered or its app is opened, so the farmer's
    first crop question does not wait ~2 s for the climate archive.
    """
    try:
        await get_climatology(lat, lon)
        return True
    except Exception:  # noqa: BLE001
        return False


def _remember(key: tuple, climatology: "Climatology") -> None:
    with _cache_lock:
        _cache[key] = (time.time(), climatology)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)


_inflight: "weakref.WeakKeyDictionary[Any, Dict[tuple, asyncio.Task]]" = weakref.WeakKeyDictionary()


async def _single_flight(key, lat, lon, transport) -> dict:
    loop = asyncio.get_running_loop()
    with _cache_lock:
        tasks = _inflight.setdefault(loop, {})
        task = tasks.get(key)
        if task is None:
            task = loop.create_task(_fetch(key, lat, lon, transport))
            tasks[key] = task
            task.add_done_callback(lambda _t, k=key, d=tasks: d.pop(k, None))
    return await asyncio.shield(task)


async def _fetch(key, lat, lon, transport) -> dict:
    last_year = date.today().year - 1
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": f"{last_year - YEARS + 1}-01-01",
        "end_date": f"{last_year}-12-31",
        "daily": "precipitation_sum,temperature_2m_mean,relative_humidity_2m_mean",
        "timezone": "auto",
    }
    payload, reason = None, "no response"
    async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
        for attempt in range(2):
            try:
                response = await client.get(ARCHIVE_URL, params=params)
                if response.status_code == 200:
                    payload = response.json()
                    break
                reason = f"HTTP {response.status_code}"
            except (httpx.TransportError, ValueError) as exc:
                reason = type(exc).__name__
            if attempt == 0:
                await asyncio.sleep(0.5)
    if not isinstance(payload, dict):
        logger.warning("Climatology unavailable for %s: %s", key, reason)
        raise ClimateUnavailable("Climate history could not be retrieved.")
    if len(_parse(payload)) >= 365 * 5:
        await asyncio.to_thread(_write_disk, key, payload)
    return payload


# ── disk cache ────────────────────────────────────────────────────────────
# One gzipped JSON file per ~11 km cell (~25 KB). Written atomically, so a
# crash mid-write never leaves a half file for the next process to read.

def _disk_path(key: tuple) -> Optional[pathlib.Path]:
    if not CACHE_DIR:
        return None
    return pathlib.Path(CACHE_DIR) / f"era5_{key[0]:+.1f}_{key[1]:+.1f}_{YEARS}y.json.gz"


def _read_disk(key: tuple) -> Optional[dict]:
    path = _disk_path(key)
    try:
        if path is None or time.time() - path.stat().st_mtime > CACHE_TTL_S:
            return None
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_disk(key: tuple, payload: dict) -> None:
    path = _disk_path(key)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump({"daily": payload.get("daily")}, fh)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Could not write climate cache %s: %s", path, exc)


def _parse(payload: dict) -> Dict[date, dict]:
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    times = daily.get("time")
    rain = daily.get("precipitation_sum")
    temp = daily.get("temperature_2m_mean")
    rh = daily.get("relative_humidity_2m_mean")
    if not all(isinstance(x, list) for x in (times, rain)) or len(times) != len(rain):
        return {}
    n = len(times)
    temp = temp if isinstance(temp, list) and len(temp) == n else [None] * n
    rh = rh if isinstance(rh, list) and len(rh) == n else [None] * n
    days: Dict[date, dict] = {}
    for i in range(n):
        try:
            p = float(rain[i])
            if not 0.0 <= p <= 1000.0:
                continue
            days[date.fromisoformat(str(times[i]))] = {
                "rain": p,
                "temp": float(temp[i]) if temp[i] is not None and -60 <= float(temp[i]) <= 60 else None,
                "rh": float(rh[i]) if rh[i] is not None and 0 <= float(rh[i]) <= 100 else None,
            }
        except (TypeError, ValueError):
            continue
    return days


def clear_cache(disk: bool = True) -> None:
    """Forget cached climatologies (memory, and the disk cache unless disk=False)."""
    with _cache_lock:
        _cache.clear()
    if disk and CACHE_DIR and pathlib.Path(CACHE_DIR).is_dir():
        for path in pathlib.Path(CACHE_DIR).glob("era5_*.json.gz"):
            try:
                path.unlink()
            except OSError:
                pass
