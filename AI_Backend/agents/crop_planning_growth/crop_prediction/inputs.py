"""Turn whatever a caller sends into one strict `CropPredictionRequest`.

Three shapes reach this agent and all of them are legitimate:

  * the native flat request (`ph`, `ec_us_cm`, `soil_type`, `month`, ...);
  * the legacy crop-selector shape, readings nested under `soil_data`
    (`ph`, `ec`, `moisture`, `npk`, ...) plus `season` and `location`;
  * orchestrator state - `lat`/`lon` at the root, raw sensor readings under
    `soil_data` in the Soil Health agent's vocabulary (`soil_ph`,
    `electrical_conductivity`, `air_temperature`, ...) and optionally the
    Weather Watcher's output under `weather_data`.

The schema stays strict; this module does the adapting, and every value it
had to infer - a month from a season, a soil class from a synonym - is
reported back as a note so the caller sees it in `warnings`. Anything it
cannot map without guessing is left for validation to reject, because a
guessed soil class or season scores a different field than the farmer has.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional, Tuple


# Unambiguous synonyms only. "Peaty" has no equivalent among the ten classes
# the model was built on, so it is deliberately absent: it reaches the
# schema unchanged and is rejected there, instead of being scored as
# something it is not.
_SOIL_SYNONYMS = {
    "loam": "Loam", "loamy": "Loam",
    "sand": "Sandy", "sandy": "Sandy",
    "clay": "Clay", "clayey": "Clay",
    "silt": "Silty Loam", "silty": "Silty Loam", "silty loam": "Silty Loam",
    "sandy loam": "Sandy Loam",
    "clay loam": "Clay Loam",
    "alluvial": "Alluvial",
    "black": "Black Cotton", "black soil": "Black Cotton",
    "black cotton": "Black Cotton", "regur": "Black Cotton",
    "red": "Red Laterite", "red soil": "Red Laterite",
    "laterite": "Red Laterite", "red laterite": "Red Laterite",
    "saline": "Saline-Alkaline", "alkaline": "Saline-Alkaline",
    "saline-alkaline": "Saline-Alkaline", "saline alkaline": "Saline-Alkaline",
}

# Opening sowing month of each season, from the same season table the
# engine uses (recommend._SEASON_BY_MONTH): Kharif starts in June, Rabi in
# October, Zaid in March. The Soil Health agent's vocabulary maps onto them.
_SEASON_OPENING_MONTH = {
    "kharif": "June", "monsoon": "June",
    "rabi": "October", "winter": "October",
    "zaid": "March", "summer": "March",
}

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]

# Keys of the native request. If any is present at the root the payload is
# treated as native and passed through untouched.
_NATIVE_KEYS = {"ph", "ec_ds_m", "ec_us_cm", "moisture_percent"}


def normalize(raw: Any, today: Optional[date] = None) -> Tuple[dict, list[str]]:
    """Return (native request dict, notes about anything inferred)."""
    data = dict(raw or {})
    notes: list[str] = []

    # Nested readings are flattened whenever present. A value already at the
    # root wins, so a caller mixing both shapes gets what they put on top.
    if isinstance(data.get("soil_data"), dict):
        data = _from_nested(data, notes)

    _resolve_location(data)
    _resolve_soil_type(data, notes)
    _resolve_month(data, notes, today or date.today())
    return data, notes


def has_soil_readings(data: dict) -> bool:
    """True when the payload carries readings, natively or nested."""
    if _NATIVE_KEYS & data.keys():
        return True
    soil = data.get("soil_data")
    if not isinstance(soil, dict):
        return False
    return any(soil.get(k) is not None for k in (
        "ph", "soil_ph", "ec", "electrical_conductivity",
        "moisture", "soil_moisture"))


# ---------------------------------------------------------------------------
# shape conversion
# ---------------------------------------------------------------------------
def _from_nested(data: dict, notes: list[str]) -> dict:
    """Flatten legacy / orchestrator payloads onto the native field names."""
    soil = data.get("soil_data") if isinstance(data.get("soil_data"), dict) else {}
    out = {k: v for k, v in data.items() if k != "soil_data"}

    def first(*keys):
        for key in keys:
            value = soil.get(key)
            if value is not None:
                return value
        return None

    _set(out, "ph", first("ph", "soil_ph"))
    _set(out, "moisture_percent", first("moisture", "soil_moisture"))
    _set(out, "soil_type", first("soil_type", "texture"))
    _set(out, "organic_carbon_percent", first("organic_carbon", "organic_carbon_percent"))

    # Both source schemas document EC in dS/m (the Soil Health input caps it
    # at 16). The request's range check still rejects a uS/cm value sent
    # here by mistake, so naming the unit is safe rather than a guess.
    _set(out, "ec_ds_m", first("ec", "electrical_conductivity"))

    # Air readings only. `temperature` in the legacy shape was ambiguous -
    # soil or air - and soil temperature fed into the air-temperature veto
    # would disqualify or admit crops on the wrong number, so it is ignored.
    _set(out, "air_temp_c", first("air_temperature"))
    _set(out, "air_humidity_percent", first("air_humidity", "humidity"))

    # N/P/K in sensor payloads come from a 7-in-1 probe, which calculates them
    # from conductivity rather than measuring them - comparing them with crop
    # needs would present an EC artefact as a fertilizer finding. Only lab
    # values sent as n_kg_ha / p_kg_ha / k_kg_ha feed the nutrient check.
    if any(soil.get(k) is not None for k in ("nitrogen", "phosphorus", "potassium")):
        notes.append(
            "Sensor N/P/K were not compared with crop needs: 7-in-1 soil sensors estimate "
            "them from conductivity. Send n_kg_ha / p_kg_ha / k_kg_ha from a soil-test "
            "report (Soil Health Card) for a nutrient check.")
    if soil.get("npk") is not None:
        notes.append(
            "Soil NPK in `soil_data.npk` has no stated unit, so it was not compared with "
            "crop needs. Send n_kg_ha / p_kg_ha / k_kg_ha (soil-test kg/ha) for a "
            "nutrient check.")

    if soil.get("temperature") is not None and out.get("air_temp_c") is None:
        notes.append(
            "soil_data.temperature was ignored: it may be soil temperature, and "
            "the temperature check needs air or forecast temperature.")

    season = data.get("season") or soil.get("season")
    if season and not out.get("month"):
        out["season"] = season

    return out


def _resolve_location(data: dict) -> None:
    if data.get("location") is None and data.get("lat") is not None \
            and data.get("lon") is not None:
        data["location"] = {"lat": data["lat"], "lon": data["lon"]}


def _resolve_soil_type(data: dict, notes: list[str]) -> None:
    value = data.get("soil_type")
    if not isinstance(value, str):
        return
    key = " ".join(value.replace("_", " ").split()).lower()
    mapped = _SOIL_SYNONYMS.get(key)
    if mapped and mapped.lower() != key:
        notes.append(f"Soil type '{value}' was read as '{mapped}'.")
    if mapped:
        data["soil_type"] = mapped


def _resolve_month(data: dict, notes: list[str], today: date) -> None:
    if data.get("month"):
        return
    season = data.pop("season", None)
    if isinstance(season, str) and season.strip().lower() in _SEASON_OPENING_MONTH:
        month = _SEASON_OPENING_MONTH[season.strip().lower()]
        data["month"] = month
        notes.append(
            f"No sowing month given; season '{season}' was scored as its opening "
            f"sowing month, {month}. Send `month` to score a different one.")
        return
    month = _MONTHS[today.month - 1]
    data["month"] = month
    notes.append(
        f"No sowing month or season given; scored for the current month, {month}.")


def _set(out: dict, key: str, value) -> None:
    if value is not None and out.get(key) is None:
        out[key] = value
