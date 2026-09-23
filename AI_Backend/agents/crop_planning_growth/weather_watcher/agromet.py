"""
Agrometeorology — turning a forecast into farm decisions.

Pure functions over the merged daily forecast and Open-Meteo's hourly data.
No I/O, no state: everything here is checked against published reference
values in `test_agent.py`.

Methods
  • Reference ET0 ........ FAO-56 Penman–Monteith, as computed by Open-Meteo
                            from radiation, humidity, wind and temperature.
  • Wet-bulb temperature . Stull (2011), J. Appl. Meteor. Climatol. 50:2267.
                            ±0.3 °C for RH 5–99 %, T −20…50 °C.
  • Delta-T .............. dry bulb − wet bulb; spraying guidance per GRDC.
  • Heat index ........... NOAA/NWS Rothfusz regression with its low- and
                            high-humidity adjustments.
  • Leaf wetness ......... hours with RH ≥ 90 % (NHRH proxy).
  • Late blight .......... Hutton criteria (AHDB, 2017).
  • Growing degree days .. simple average method.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from AI_Backend.agents.crop_planning_growth.weather_watcher.config import AGROMET

_A = AGROMET


# ═════════════════════════════════════════════════════════════════════════════
# Physics
# ═════════════════════════════════════════════════════════════════════════════

def wet_bulb_c(temp_c: float, rh: float) -> float:
    """Wet-bulb temperature, Stull (2011). Reference: 20 °C, 50 % → 13.7 °C."""
    rh = min(max(rh, 5.0), 99.0)   # the fit's validity range
    return (temp_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
            + math.atan(temp_c + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
            - 4.686035)


def delta_t_c(temp_c: float, rh: float) -> float:
    return temp_c - wet_bulb_c(temp_c, rh)


def heat_index_c(temp_c: float, rh: float) -> float:
    """NOAA heat index. Reference: 90 °F, 70 % RH → 106 °F (NWS table)."""
    t = temp_c * 9.0 / 5.0 + 32.0
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2.0 < 80.0:
        hi = simple
    else:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh
              - 0.22475541 * t * rh - 0.00683783 * t * t
              - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
              + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
        if rh < 13.0 and 80.0 <= t <= 112.0:
            hi -= ((13.0 - rh) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
        elif rh > 85.0 and 80.0 <= t <= 87.0:
            hi += ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return (hi - 32.0) * 5.0 / 9.0


def heat_index_category(hi_c: float) -> str:
    if hi_c >= _A["heat_index_extreme_danger_c"]:
        return "extreme_danger"
    if hi_c >= _A["heat_index_danger_c"]:
        return "danger"
    if hi_c >= _A["heat_index_extreme_caution_c"]:
        return "extreme_caution"
    if hi_c >= _A["heat_index_caution_c"]:
        return "caution"
    return "none"


def growing_degree_days(temp_min: float, temp_max: float) -> float:
    return max(0.0, (temp_min + temp_max) / 2.0 - _A["gdd_base_c"])


def forecast_confidence(day_index: int) -> str:
    if day_index < _A["confidence_high_days"]:
        return "high"
    if day_index < _A["confidence_medium_days"]:
        return "medium"
    return "low"


# ═════════════════════════════════════════════════════════════════════════════
# Hourly → daily indicators
# ═════════════════════════════════════════════════════════════════════════════

def daily_hourly_stats(hourly: List[dict]) -> Dict[str, dict]:
    """Per local date: leaf-wetness hours, Hutton humid hours, Tmin, heat index."""
    by_day: Dict[str, List[dict]] = defaultdict(list)
    for h in hourly:
        by_day[h["time"].date().isoformat()].append(h)

    stats: Dict[str, dict] = {}
    for day, hours in by_day.items():
        wet = [h for h in hours if h["rh"] >= _A["leaf_wet_rh"] or h["precip"] > 0.0]
        favourable = [h for h in wet
                      if _A["fungal_temp_min_c"] <= h["temp"] <= _A["fungal_temp_max_c"]]
        max_hi = max(heat_index_c(h["temp"], h["rh"]) for h in hours)
        stats[day] = {
            "hours": len(hours),
            "leaf_wetness_hours": len(wet),
            "favourable_wet_hours": len(favourable),
            "humid_hours": sum(1 for h in hours if h["rh"] >= _A["hutton_rh"]),
            "tmin_hourly": min(h["temp"] for h in hours),
            "max_heat_index_c": round(max_hi, 1),
        }
    return stats


def fungal_risk(favourable_wet_hours: int) -> str:
    if favourable_wet_hours >= _A["fungal_high_hours"]:
        return "high"
    if favourable_wet_hours >= _A["fungal_moderate_hours"]:
        return "moderate"
    return "low"


def hutton_dates(stats: Dict[str, dict]) -> List[str]:
    """Dates completing a Hutton period (this day and the one before both qualify).

    A day counts only when its hourly record is complete; a partial day
    cannot show 6 humid hours it never observed.
    """
    def qualifies(s: Optional[dict]) -> bool:
        return (s is not None and s["hours"] >= 20
                and s["tmin_hourly"] >= _A["hutton_tmin_c"]
                and s["humid_hours"] >= _A["hutton_humid_hours"])

    out = []
    for day in sorted(stats):
        previous = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        if qualifies(stats[day]) and qualifies(stats.get(previous)):
            out.append(day)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Spray windows
# ═════════════════════════════════════════════════════════════════════════════

_REASON_TEXT = {
    "rain": "rain in the hour or within the rain-free period after it",
    "wind_high": f"wind above {_A['spray_wind_max_kmh']:.0f} km/h (drift)",
    "wind_low": f"wind below {_A['spray_wind_min_kmh']:.0f} km/h (inversion risk)",
    "delta_t_high": f"Delta-T above {_A['spray_delta_t_max_c']:.0f} °C (droplets evaporate)",
    "delta_t_low": f"Delta-T below {_A['spray_delta_t_min_c']:.0f} °C (inversion / slow drying)",
    "too_hot": f"temperature above {_A['spray_temp_max_c']:.0f} °C",
    "too_cold": f"temperature below {_A['spray_temp_min_c']:.0f} °C (poor uptake, frost risk)",
}


def _spray_blocker(hourly: List[dict], i: int) -> Optional[str]:
    """Why hour i is unsuitable for spraying, or None when it is suitable."""
    h = hourly[i]
    if h["precip"] > 0.0 or (h["pop"] or 0.0) >= _A["spray_rain_prob_max"]:
        return "rain"
    after = hourly[i + 1:i + 1 + _A["spray_rain_free_hours"]]
    if len(after) < _A["spray_rain_free_hours"]:
        return "rain"   # cannot confirm the rain-free period: not safe to say yes
    if any(x["precip"] >= 0.2 or (x["pop"] or 0.0) >= 50.0 for x in after):
        return "rain"
    if h["wind"] > _A["spray_wind_max_kmh"]:
        return "wind_high"
    if h["wind"] < _A["spray_wind_min_kmh"]:
        return "wind_low"
    dt = delta_t_c(h["temp"], h["rh"])
    if dt > _A["spray_delta_t_max_c"]:
        return "delta_t_high"
    if dt < _A["spray_delta_t_min_c"]:
        return "delta_t_low"
    if h["temp"] > _A["spray_temp_max_c"]:
        return "too_hot"
    if h["temp"] < _A["spray_temp_min_c"]:
        return "too_cold"
    return None


def spray_windows(hourly: List[dict], now: datetime) -> Tuple[List[dict], Optional[str]]:
    """Daylight windows of >= 2 consecutive suitable hours in the next 72 h.

    Returns (windows, limiting_factor) where limiting_factor names the most
    common reason daylight hours failed - what the farmer is up against.
    """
    horizon = now + timedelta(hours=_A["spray_horizon_hours"])
    # The hour in progress counts if at least half of it remains.
    start_from = now - timedelta(minutes=30)

    windows: List[dict] = []
    reasons: Counter = Counter()
    run: List[dict] = []

    def close_run():
        if len(run) >= _A["spray_min_window_hours"]:
            end = run[-1]["time"] + timedelta(hours=1)
            windows.append({
                "date": run[0]["time"].date().isoformat(),
                "start": run[0]["time"].isoformat(timespec="minutes"),
                "end": end.isoformat(timespec="minutes"),
                "hours": len(run),
                "mean_wind_kmh": round(sum(x["wind"] for x in run) / len(run), 1),
                "mean_delta_t_c": round(sum(delta_t_c(x["temp"], x["rh"]) for x in run) / len(run), 1),
                "max_temp_c": round(max(x["temp"] for x in run), 1),
            })
        run.clear()

    for i, h in enumerate(hourly):
        if h["time"] < start_from or h["time"] >= horizon:
            continue
        if not h["is_day"]:
            close_run()
            continue
        blocker = _spray_blocker(hourly, i)
        if blocker is None:
            run.append(h)
        else:
            reasons[blocker] += 1
            close_run()
    close_run()

    limiting = _REASON_TEXT[reasons.most_common(1)[0][0]] if reasons else None
    return windows, limiting


# ═════════════════════════════════════════════════════════════════════════════
# Daily-level advisories
# ═════════════════════════════════════════════════════════════════════════════

def water_balance(days: List[dict]) -> Optional[dict]:
    """Rain against FAO-56 reference ET0 over the given days."""
    with_et0 = [d for d in days if d.get("et0_mm") is not None]
    if not with_et0:
        return None
    rain = round(sum(d["rainfall_mm"] for d in with_et0), 1)
    et0 = round(sum(d["et0_mm"] for d in with_et0), 1)
    ratio = rain / et0 if et0 > 0 else None
    if ratio is None or ratio >= _A["water_covered_ratio"]:
        status = "rain_covers_demand"
    elif ratio >= _A["water_partial_ratio"]:
        status = "partly_covered"
    else:
        status = "irrigation_likely_needed"
    return {
        "days": len(with_et0),
        "rainfall_mm": rain,
        "reference_et0_mm": et0,
        "balance_mm": round(rain - et0, 1),
        "rain_covers_percent": round(ratio * 100.0) if ratio is not None else None,
        "status": status,
        "note": "ET0 is for a reference grass surface; the crop's own demand is "
                "ET0 × its crop coefficient (Kc) for the growth stage.",
    }


def dry_spells(days: List[dict]) -> List[dict]:
    """Runs of dry days, for harvest, fertilizer and field work."""
    spells, run = [], []

    def close():
        if len(run) >= _A["dry_spell_min_days"]:
            spells.append({"start": run[0]["date"], "end": run[-1]["date"], "days": len(run)})
        run.clear()

    for d in days:
        if (d["rainfall_mm"] < _A["dry_day_rain_mm"]
                and d["rain_probability_percent"] < _A["dry_day_rain_prob"]):
            run.append(d)
        else:
            close()
    close()
    return spells


# ═════════════════════════════════════════════════════════════════════════════
# Assembly
# ═════════════════════════════════════════════════════════════════════════════

def build(days: List[dict], hourly: List[dict], et0_by_date: Dict[str, float],
          now: Optional[datetime]) -> Tuple[dict, List[dict]]:
    """Enrich `days` in place and return (agro_advisory, extra_alerts)."""
    stats = daily_hourly_stats(hourly) if hourly else {}
    blight = set(hutton_dates(stats)) if stats else set()

    for index, d in enumerate(days):
        d["forecast_confidence"] = forecast_confidence(index)
        d["gdd_base10"] = round(growing_degree_days(d["temp_min"], d["temp_max"]), 1)
        d["et0_mm"] = et0_by_date.get(d["date"])
        s = stats.get(d["date"])
        if s:
            d["leaf_wetness_hours"] = s["leaf_wetness_hours"]
            d["fungal_risk"] = fungal_risk(s["favourable_wet_hours"])
            d["late_blight_risk"] = d["date"] in blight
            d["max_heat_index_c"] = s["max_heat_index_c"]
            d["heat_index_category"] = heat_index_category(s["max_heat_index_c"])

    short = days[:7]
    windows, limiting = spray_windows(hourly, now) if hourly and now else ([], None)
    balance = water_balance(short)
    spells = dry_spells(days)

    advisory = {
        "water_balance_7d": balance,
        "gdd_base10": {
            "next_7_days": round(sum(d["gdd_base10"] for d in short), 1),
            "next_14_days": round(sum(d["gdd_base10"] for d in days), 1),
        },
        "spray_windows": windows,
        "spray_limiting_factor": limiting if not windows else None,
        "dry_spells": spells,
        "hourly_available": bool(hourly),
        "summary": _summary(balance, windows, limiting, days, spells, bool(hourly)),
    }
    return advisory, _alerts(days)


def _summary(balance, windows, limiting, days, spells, hourly_ok) -> List[str]:
    lines: List[str] = []
    if days and all(d["temp_max"] <= _A["frozen_ground_tmax_c"] for d in days[:7]):
        lines.append("Ground is likely frozen all week - do not irrigate or spray until it thaws; "
                     "protect nurseries and livestock from the cold.")
        balance = None
    if balance:
        pct = balance["rain_covers_percent"]
        if balance["status"] == "irrigation_likely_needed":
            lines.append(f"Next {balance['days']} days: rain covers only {pct}% of water "
                         f"demand ({balance['rainfall_mm']} mm rain vs "
                         f"{balance['reference_et0_mm']} mm ET0) - plan irrigation.")
        elif balance["status"] == "partly_covered":
            lines.append(f"Next {balance['days']} days: rain covers about {pct}% of water "
                         "demand - top up with irrigation as the crop needs.")
        else:
            lines.append(f"Next {balance['days']} days: rain is expected to meet water "
                         "demand - hold irrigation and watch for waterlogging.")
    if hourly_ok:
        if windows:
            w = windows[0]
            lines.append(f"Best spray window: {w['start'][:16].replace('T', ' ')} to "
                         f"{w['end'][11:16]} ({w['hours']} h).")
        elif limiting:
            lines.append(f"No good spray window in the next 72 h - mainly {limiting}.")
    fungal = [d["date"] for d in days[:7] if d.get("fungal_risk") == "high"]
    if fungal:
        lines.append(f"High fungal disease risk on {', '.join(fungal)} - scout crops and "
                     "protect before these days.")
    blight = [d["date"] for d in days if d.get("late_blight_risk")]
    if blight:
        lines.append(f"Late blight weather (Hutton criteria) on {', '.join(blight)} - "
                     "potato and tomato need protection.")
    if spells:
        s = spells[0]
        lines.append(f"Dry spell {s['start']} to {s['end']} ({s['days']} days) - "
                     "suitable for harvest, fertilizer and field work.")
    low_conf = [d for d in days if d.get("forecast_confidence") == "low"]
    if low_conf:
        lines.append(f"Forecasts from {low_conf[0]['date']} onward are low-confidence; "
                     "re-check before acting on them.")
    return lines


def _alerts(days: List[dict]) -> List[dict]:
    alerts: List[dict] = []
    for d in days:
        if d.get("late_blight_risk"):
            alerts.append({
                "type": "late_blight_risk", "severity": "high", "date": d["date"],
                "source": "forecast",
                "message": f"Late blight weather on {d['date']} (Hutton criteria met) "
                           "- potato and tomato at risk.",
                "recommendations": [
                    "Apply a protectant fungicide before the risk period, as your local "
                    "extension service recommends - check the label",
                    "Scout lower leaves for water-soaked lesions",
                    "Avoid overhead irrigation",
                ]})
        if d.get("fungal_risk") == "high" and d.get("forecast_confidence") != "low":
            alerts.append({
                "type": "fungal_disease_risk", "severity": "medium", "date": d["date"],
                "source": "forecast",
                "message": f"Leaves stay wet ~{d['leaf_wetness_hours']} h on {d['date']} "
                           "at temperatures that favour fungal infection.",
                "recommendations": [
                    "Scout for leaf spots, blight and mildew",
                    "Water early in the day so foliage dries",
                    "Improve airflow: weed control, avoid dense canopies",
                ]})
        category = d.get("heat_index_category")
        if category in ("danger", "extreme_danger"):
            alerts.append({
                "type": "heat_safety",
                "severity": "critical" if category == "extreme_danger" else "high",
                "date": d["date"], "source": "forecast",
                "message": f"Feels-like temperature up to {d['max_heat_index_c']:.0f}°C on "
                           f"{d['date']} - dangerous for field workers and livestock.",
                "recommendations": [
                    "Do heavy field work before 10:00 and after 16:00",
                    "Water, shade and rest breaks every hour",
                    "Give livestock shade and extra drinking water",
                ]})
    return alerts
