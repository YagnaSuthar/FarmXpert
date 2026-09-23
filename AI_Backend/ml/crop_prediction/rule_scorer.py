"""Layer 1: agronomic suitability scoring against the crop constraint table.

This layer contains no machine learning.  Each of the 344 varieties carries
explicit tolerance ranges in the dataset, so a field can be checked against
them one constraint at a time.  Two properties matter and neither is offered
by the classifier:

  * it can return "nothing here is suitable" when no variety scores well;
  * every score decomposes into named reasons a farmer can act on.
"""
from dataclasses import dataclass, field as dc_field

from .calendar_feat import window_to_months

# Weight per constraint; they need not sum to 100, the score is normalised.
WEIGHTS = {
    "pH": 20, "EC": 15, "moisture": 10, "soil_type": 15,
    "temperature": 20, "humidity": 10, "water": 10, "season": 10,
}

# Constraints that cannot be averaged away.  A weighted mean lets a field
# with many acceptable properties outvote one lethal property: 58 C air
# temperature scored 67/100 for Cabbage because pH, EC and soil all passed.
# If any of these bottoms out the variety is disqualified outright, since no
# amount of good soil compensates for heat that kills the plant.
VETO_CHECKS = ("temperature", "pH", "EC")


@dataclass
class FieldReading:
    """Everything known at prediction time."""
    pH: float
    EC_dSm: float
    moisture_percent: float
    soil_type: str
    month: str
    air_temp_C: float = None
    air_humidity: float = None
    OC_percent: float = None
    N_kg_ha: float = None
    P_kg_ha: float = None
    K_kg_ha: float = None
    forecast_rain_mm: float = None
    forecast_temp_mean_C: float = None
    forecast_humidity_mean: float = None
    region: str = None


def _band(value, lo, hi, tol_frac=0.15):
    """1.0 inside [lo, hi], decaying to 0.0 a tolerance band outside it."""
    if value is None:
        return None
    if lo <= value <= hi:
        return 1.0
    span = max(hi - lo, 1e-6)
    slack = span * tol_frac
    dist = (lo - value) if value < lo else (value - hi)
    return max(0.0, 1.0 - dist / slack)


def _ceiling(value, max_allowed, tol_frac=0.25):
    """1.0 at or below the ceiling, decaying above it."""
    if value is None:
        return None
    if value <= max_allowed:
        return 1.0
    slack = max(max_allowed * tol_frac, 1e-6)
    return max(0.0, 1.0 - (value - max_allowed) / slack)


def score_variety(reading, profile):
    """Score one variety. Returns (score_0_100, list of reason dicts)."""
    checks = []

    def add(name, ok_frac, detail):
        if ok_frac is not None:
            checks.append({"check": name, "score": ok_frac,
                           "weight": WEIGHTS[name] if name in WEIGHTS else 0,
                           "detail": detail})

    add("pH", _band(reading.pH, profile["pH_min"], profile["pH_max"]),
        f"pH {reading.pH} vs tolerated {profile['pH_min']}-{profile['pH_max']}")

    add("EC", _ceiling(reading.EC_dSm, profile["EC_tolerance_max"]),
        f"EC {reading.EC_dSm} dS/m vs max {profile['EC_tolerance_max']}")

    add("moisture", _band(reading.moisture_percent,
                          profile["moisture_min"], profile["moisture_max"]),
        f"moisture {reading.moisture_percent}% vs typical "
        f"{profile['moisture_min']:.0f}-{profile['moisture_max']:.0f}%")

    soils = profile["soil_types"]
    add("soil_type", 1.0 if reading.soil_type in soils else 0.0,
        f"{reading.soil_type} " +
        ("is suitable" if reading.soil_type in soils
         else f"not among {', '.join(soils)}"))

    temp = (reading.forecast_temp_mean_C if reading.forecast_temp_mean_C
            is not None else reading.air_temp_C)
    if temp is not None:
        add("temperature", _band(temp, profile["temp_min_C"],
                                 profile["temp_max_C"]),
            f"temp {temp} C vs tolerated {profile['temp_min_C']}-"
            f"{profile['temp_max_C']} C")

    hum = (reading.forecast_humidity_mean if reading.forecast_humidity_mean
           is not None else reading.air_humidity)
    if hum is not None:
        add("humidity", _band(hum, profile["humidity_percent_min"],
                              profile["humidity_percent_max"]),
            f"humidity {hum}% vs tolerated "
            f"{profile['humidity_percent_min']}-"
            f"{profile['humidity_percent_max']}%")

    if reading.forecast_rain_mm is not None:
        need = profile["water_req_mm"]
        ratio = min(1.0, reading.forecast_rain_mm / need) if need else 1.0
        # Shortfall is recoverable by irrigation, so never score it to zero.
        add("water", 0.4 + 0.6 * ratio,
            f"forecast rain {reading.forecast_rain_mm}mm vs requirement "
            f"{need}mm" + ("" if ratio >= 1 else " - irrigation needed"))

    months = profile.get("_sowing_months")
    if months is None:                      # un-prepared profile (DataFrame row)
        months = window_to_months(profile["sowing_month"])
    add("season", 1.0 if reading.month in months else 0.0,
        f"{reading.month} " + ("is in" if reading.month in months
                               else "is outside") +
        f" sowing window {profile['sowing_month']}")

    vetoed = [c for c in checks
              if c["check"] in VETO_CHECKS and c["score"] <= 0.0]
    total_w = sum(c["weight"] for c in checks)
    score = sum(c["score"] * c["weight"] for c in checks) / total_w * 100
    if vetoed:
        # Cap hard so a vetoed variety can never clear the suitability floor.
        score = min(score, 20.0)
        for c in vetoed:
            c["detail"] += "  [DISQUALIFYING]"
    return score, checks


def prepare_profiles(profiles):
    """Turn the variety DataFrame into plain dicts, once, at load time.

    `iterrows` builds a fresh Series per variety on every request, and the
    sowing window is re-parsed per variety per request.  Neither depends on
    the field being scored, so both belong here rather than in the hot path.
    Scoring itself is untouched: `score_variety` reads the same keys.
    """
    prepared = []
    for record in profiles.to_dict("records"):
        record["_sowing_months"] = window_to_months(record["sowing_month"])
        prepared.append(record)
    return prepared


def score_all(reading, profiles):
    """Score every variety, best first.

    Accepts either the prepared list from `prepare_profiles` or the raw
    DataFrame, so existing callers keep working.
    """
    rows = profiles if isinstance(profiles, list) else (
        prof for _, prof in profiles.iterrows())
    out = []
    for prof in rows:
        s, checks = score_variety(reading, prof)
        out.append({"crop": prof["crop"], "variety": prof["variety"],
                    "variety_uid": prof["variety_uid"], "score": s,
                    "yield_tha": prof["yield_potential_tha"],
                    "checks": checks})
    return sorted(out, key=lambda r: -r["score"])
