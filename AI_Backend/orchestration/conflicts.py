"""
Conflict detection and resolution
==================================
Two agents can be individually right and jointly contradictory: the irrigation
planner says water today, the weather agent says 40 mm of rain is coming.

Each detector below is a small, explicit function - a farmer, an agronomist or
an auditor can read one and say whether it is correct. There is no scoring
model deciding which agent to believe.

Resolution order, applied in this sequence:

  1. Safety      an option that cannot hurt the crop, the person, or whoever
                 eats the produce wins outright.
  2. Authority   the agent that owns the decision wins inside its own domain.
  3. Evidence    measurement beats forecast; forecast beats extrapolation.
  4. Freshness   newer data wins when authority is equal.
  5. Surface it  if none of the above settles it, the conflict is returned
                 with both positions. Inventing certainty is the one outcome
                 that is never acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from AI_Backend.orchestration.contracts import ExecutionContext


class Resolution(str, Enum):
    SAFETY     = "safety"
    AUTHORITY  = "authority"
    EVIDENCE   = "evidence"
    FRESHNESS  = "freshness"
    UNRESOLVED = "unresolved"


@dataclass
class Conflict:
    """A disagreement between agents, and what was done about it."""
    topic: str
    description: str
    positions: Dict[str, str]                 # agent name -> what it says
    resolution: Resolution
    chosen: Optional[str] = None              # the agent that prevails
    rationale: str = ""
    farmer_note: str = ""                     # what the farmer should be told
    agents: List[str] = field(default_factory=list)


Detector = Callable[[ExecutionContext], Optional[Conflict]]


# ── detectors ───────────────────────────────────────────────────────────────

def _irrigation_versus_rain(context: ExecutionContext) -> Optional[Conflict]:
    """Irrigating into forecast rain.

    The irrigation agent works from soil water balance; it may not have seen
    the forecast the weather agent has. Rain is only a real conflict when
    there is enough of it, and when the forecast is confident enough.
    """
    advice = context.output("irrigation_planner")
    weather = context.output("weather_watcher")
    if not isinstance(advice, dict) or not isinstance(weather, dict):
        return None

    today = _first_irrigation_day(advice)
    if not today:
        return None
    depth = _number(today.get("water_depth_mm"))
    if depth is None or depth <= 0:
        return None

    rain_mm, probability = _rain_tomorrow(weather)
    if rain_mm is None or rain_mm < depth * 0.8 or (probability or 0) < 50:
        return None

    return Conflict(
        topic="irrigation_vs_rainfall",
        description=(f"The irrigation plan asks for {depth:.0f} mm, while the forecast "
                     f"expects about {rain_mm:.0f} mm of rain within a day."),
        positions={"irrigation_planner": f"apply {depth:.0f} mm",
                   "weather_watcher": f"about {rain_mm:.0f} mm of rain expected"},
        # Safety: over-watering drowns roots and wastes water that cannot be
        # taken back, while waiting a day is reversible.
        resolution=Resolution.SAFETY,
        chosen="weather_watcher",
        rationale=("Waiting is reversible; water already applied is not. Rain of this "
                   "size covers the planned depth."),
        farmer_note=("Hold the irrigation - rain is expected to do the job. Check the "
                     "field after the rain and water only if it falls short."),
        agents=["irrigation_planner", "weather_watcher"])


def _spray_versus_weather(context: ExecutionContext) -> Optional[Conflict]:
    """A spray scheduled into weather that would waste or misdirect it."""
    plan = context.output("task_scheduler")
    weather = context.output("weather_watcher")
    if not isinstance(plan, dict) or not isinstance(weather, dict):
        return None

    sprays = [t for t in plan.get("all_tasks", [])
              if t.get("category") == "pest_control" and t.get("status") == "scheduled"]
    if not sprays:
        return None

    rain_mm, probability = _rain_tomorrow(weather)
    if rain_mm is None or rain_mm < 2.0 or (probability or 0) < 50:
        return None

    spray = sprays[0]
    if spray.get("scheduled_date") and not _same_day(spray["scheduled_date"], weather):
        return None

    return Conflict(
        topic="spray_vs_rainfall",
        description=(f"A spray is scheduled while about {rain_mm:.0f} mm of rain is "
                     "expected, which would wash it off before it works."),
        positions={"task_scheduler": f"spray: {spray.get('title', 'pest control')}",
                   "weather_watcher": f"about {rain_mm:.0f} mm of rain expected"},
        resolution=Resolution.EVIDENCE,
        chosen="weather_watcher",
        rationale=("The forecast is the more direct evidence about the sprayability of "
                   "the day, and a washed-off spray is money spent for no effect."),
        farmer_note="Move the spray to the next dry window; rain would wash it off.",
        agents=["task_scheduler", "weather_watcher"])


def _crop_versus_water(context: ExecutionContext) -> Optional[Conflict]:
    """A recommended crop the farm may not be able to water."""
    crop = context.output("crop_predictor")
    if not isinstance(crop, dict):
        return None
    result = crop.get("result") or {}
    top = (result.get("recommendations") or [None])[0]
    if not isinstance(top, dict):
        return None

    security = top.get("water_security") or {}
    category = str(security.get("category", "")).lower()
    if "essential" not in category:
        return None
    if (context.resources or {}).get("irrigation_available", True):
        return None

    return Conflict(
        topic="crop_vs_water_availability",
        description=(f"{top.get('crop', 'The top crop')} needs irrigation in most years, "
                     "but this farm reported none available."),
        positions={"crop_predictor": f"recommends {top.get('crop')}",
                   "farm_context": "no irrigation available"},
        # No agent can resolve this: it is a fact about the farm, not a
        # disagreement about agronomy. Say so rather than picking a side.
        resolution=Resolution.UNRESOLVED,
        rationale="Whether irrigation can be arranged is the farmer's decision, not the model's.",
        farmer_note=("This crop scores best but needs watering in most years. If you "
                     "cannot irrigate, choose the next rainfed-suitable option instead."),
        agents=["crop_predictor"])


DETECTORS: List[Detector] = [
    _irrigation_versus_rain,
    _spray_versus_weather,
    _crop_versus_water,
]


def detect(context: ExecutionContext) -> List[Conflict]:
    """Run every detector. A broken detector must not break the response."""
    found: List[Conflict] = []
    for detector in DETECTORS:
        try:
            conflict = detector(context)
        except Exception:  # noqa: BLE001 - a detector is never worth a 500
            import logging
            logging.getLogger("farmxpert.orchestration").warning(
                "Conflict detector %s failed", getattr(detector, "__name__", "?"),
                exc_info=True)
            continue
        if conflict:
            found.append(conflict)
    return found


# ── small readers, tolerant of shape ────────────────────────────────────────

def _first_irrigation_day(advice: dict) -> Optional[dict]:
    schedule = advice.get("irrigation_schedule") or advice.get("schedule") or []
    for day in schedule:
        if isinstance(day, dict) and (day.get("irrigation_required")
                                      or str(day.get("decision_code", "")).endswith("IRRIGATE")):
            return day
    return None


def _rain_tomorrow(weather: dict):
    """Rain in the next forecast day: (mm, probability). Either may be None."""
    days = (weather.get("forecast_short_term") or weather.get("forecast") or [])
    for day in days[:2]:
        if not isinstance(day, dict):
            continue
        mm = _number(day.get("rainfall_mm") or day.get("rainfall") or day.get("precipitation_mm"))
        probability = _number(day.get("rain_probability_percent") or day.get("rain_probability"))
        if mm is not None:
            return mm, probability
    return None, None


def _same_day(iso_date: str, weather: dict) -> bool:
    days = (weather.get("forecast_short_term") or weather.get("forecast") or [])
    for day in days[:2]:
        if isinstance(day, dict) and str(day.get("date")) == str(iso_date):
            return True
    return False


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
