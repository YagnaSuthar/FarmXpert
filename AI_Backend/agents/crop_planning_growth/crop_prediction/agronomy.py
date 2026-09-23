"""Agronomic advice attached to each recommended crop.

Nothing here changes a score or the order of the shortlist - the validated
model owns that. This module answers the questions a farmer asks *after*
seeing the list: will the rain be enough, is my soil right for it, is it
wise after what I grew last, and what am I committing to.

Inputs are catalogue facts about the recommended variety (water need,
duration, the soil nutrient range it does well in) and the location's
climate history (`climate.py`).

On soil nutrients: the dataset's N/P/K columns hold the soil available-
nutrient range each crop does well in, on the Indian soil-test scale (kg/ha of
available N, P and K - the scale of the Muhr et al. fertility classes and of
the Soil Health Card). The evidence is in the values:
groundnut's range is N 294-588, P 10.5-25.7, K 102.6-273.9 kg/ha - the
"medium" fertility class (N 280-560, P 10-25, K 108-280 kg/ha) - identical across
every groundnut variety, and 65 rows put K_min exactly on the 108 kg/ha
class boundary. As fertiliser doses these numbers would be impossible
(groundnut is a legume and receives ~20 kg N/ha). So a farmer's soil test is
directly comparable with them.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .climate import Climatology

# ---------------------------------------------------------------------------
# Water security
# ---------------------------------------------------------------------------
# A season is adequate when rain meets >= 90 % of the crop's water need:
# with the FAO-33 yield response factor Ky ~ 1, that is <= ~10 % yield loss.
ADEQUATE_SUPPLY = 0.9
RAINFED_SHARE = 0.8        # adequate in >= 8 of 10 seasons -> rainfed
# Irrigation is essential when rain falls short even in a *typical* year:
# meeting < 70 % of the need is ~30 % yield loss in a normal season.
# Between the two, rain carries most seasons and irrigation protects dry ones.
ESSENTIAL_TYPICAL_SUPPLY = 0.7
# Post-monsoon sowing months: the root zone may hold conserved monsoon water.
_POST_MONSOON_MONTHS = {10, 11, 12, 1, 2}
_HEAVY_SOIL_AWC = 170.0

# Effective rooting depth, m - midpoints of FAO-56 Table 22 ranges.
# Spices are taken at the shallow end of small vegetables.
ROOT_DEPTH_M = {
    "cotton": 1.35, "groundnut": 0.75, "guar": 0.7, "white peas": 0.8,
    "potato": 0.5, "tomato": 1.1, "cabbage": 0.65,
    "ajwain": 0.5, "coriander (leaves)": 0.5,
}
DEFAULT_ROOT_DEPTH_M = 0.8


def root_zone_water_mm(crop: str, soil_awc_mm_per_m: Optional[float]) -> Optional[float]:
    """Total available water in the root zone (FAO-56 TAW = AWC x root depth)."""
    if not soil_awc_mm_per_m:
        return None
    return soil_awc_mm_per_m * ROOT_DEPTH_M.get(crop.lower(), DEFAULT_ROOT_DEPTH_M)


def water_security(climatology: Optional[Climatology], month: int,
                   duration_days: Optional[float], water_need_mm: Optional[float],
                   taw_mm: Optional[float],
                   irrigation_available: Optional[bool]) -> Optional[dict]:
    if climatology is None or not duration_days or not water_need_mm or not taw_mm:
        return None
    ratios = climatology.rainfed_supply_by_year(
        month, int(duration_days), float(water_need_mm), float(taw_mm))
    if len(ratios) < 5:
        return None
    ordered = sorted(ratios)
    met = sum(1 for r in ratios if r >= ADEQUATE_SUPPLY)
    share = met / len(ratios)
    median = ordered[len(ordered) // 2]
    dry = ordered[max(0, int(round(0.2 * (len(ordered) - 1))))]
    typical_gap = max(0, round(water_need_mm * (1 - median)))
    dry_gap = max(0, round(water_need_mm * (1 - dry)))

    if share >= RAINFED_SHARE:
        category = "rainfed"
        message = (f"Rain with stored soil water met this crop's need in {met} of "
                   f"{len(ratios)} recent seasons here - rainfed cultivation is realistic.")
    elif median < ESSENTIAL_TYPICAL_SUPPLY:
        category = "irrigation_essential"
        message = (f"Even in a typical season rain meets only {round(median * 100)}% of this "
                   f"crop's need here - it needs irrigation (about {typical_gap} mm).")
    else:
        category = "supplemental_irrigation"
        message = (f"Rain carries most seasons ({round(median * 100)}% of the need in a "
                   f"typical year) but fell short in {len(ratios) - met} of {len(ratios)} - "
                   f"keep protective irrigation ready: about {dry_gap} mm in a dry year.")

    if irrigation_available is False and category == "irrigation_essential":
        message += " You reported no irrigation: expect heavy losses in most years."
    elif irrigation_available is False and category == "supplemental_irrigation":
        message += " Without irrigation, expect yield loss in dry years."
    if category != "rainfed" and month in _POST_MONSOON_MONTHS and taw_mm >= 0.5 * _HEAVY_SOIL_AWC:
        message += (" This assumes the root zone half full at sowing; on heavy soil after a "
                    "good monsoon, conserved moisture can carry more of the crop.")

    return {
        "category": category,
        "seasons_analysed": len(ratios),
        "seasons_rain_sufficient": met,
        "crop_water_need_mm": round(water_need_mm),
        "rain_met_percent_median": round(median * 100),
        "rain_met_percent_dry_year": round(dry * 100),
        "typical_irrigation_mm": typical_gap,
        "dry_year_irrigation_mm": dry_gap,
        "root_zone_water_mm": round(taw_mm),
        "message": message,
    }


# ---------------------------------------------------------------------------
# Soil nutrients
# ---------------------------------------------------------------------------
_NUTRIENTS = (("N", "n_kg_ha", "N_min", "N_max", "available nitrogen"),
              ("P", "p_kg_ha", "P_min", "P_max", "available phosphorus"),
              ("K", "k_kg_ha", "K_min", "K_max", "available potassium"))


def soil_nutrients(profile: dict, soil: Dict[str, Optional[float]]) -> List[dict]:
    out = []
    for symbol, key, lo_col, hi_col, label in _NUTRIENTS:
        value = soil.get(key)
        lo, hi = profile.get(lo_col), profile.get(hi_col)
        if value is None or lo is None or hi is None or lo != lo or hi != hi:
            continue
        if value < lo:
            status = "low"
            advice = (f"Soil {label} ({value:.0f} kg/ha) is below the {lo:.0f}-{hi:.0f} "
                      f"kg/ha this crop does well in - apply {symbol} fertiliser as your "
                      "soil test recommendation advises.")
        elif value > hi:
            status = "high"
            advice = (f"Soil {label} ({value:.0f} kg/ha) is above this crop's "
                      f"{lo:.0f}-{hi:.0f} kg/ha range - reduce {symbol} fertiliser.")
        else:
            status = "adequate"
            advice = f"Soil {label} ({value:.0f} kg/ha) is within this crop's range."
        out.append({"nutrient": symbol, "soil_kg_ha": round(value, 1),
                    "crop_range_kg_ha": [round(lo, 1), round(hi, 1)],
                    "status": status, "advice": advice})
    return out


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------
FAMILY = {
    # the model's crops
    "ajwain": "Apiaceae", "coriander (leaves)": "Apiaceae", "coriander": "Apiaceae",
    "cotton": "Malvaceae", "groundnut": "Fabaceae", "guar": "Fabaceae",
    "white peas": "Fabaceae", "potato": "Solanaceae", "tomato": "Solanaceae",
    "cabbage": "Brassicaceae", "mango": "Anacardiaceae",
    # common previous crops in Gujarat and India
    "wheat": "Poaceae", "rice": "Poaceae", "paddy": "Poaceae", "maize": "Poaceae",
    "bajra": "Poaceae", "pearl millet": "Poaceae", "jowar": "Poaceae",
    "sorghum": "Poaceae", "sugarcane": "Poaceae",
    "chickpea": "Fabaceae", "gram": "Fabaceae", "moong": "Fabaceae",
    "green gram": "Fabaceae", "urad": "Fabaceae", "black gram": "Fabaceae",
    "tur": "Fabaceae", "pigeon pea": "Fabaceae", "soybean": "Fabaceae",
    "pea": "Fabaceae", "peas": "Fabaceae", "cowpea": "Fabaceae",
    "brinjal": "Solanaceae", "eggplant": "Solanaceae", "chilli": "Solanaceae",
    "chili": "Solanaceae", "capsicum": "Solanaceae",
    "cumin": "Apiaceae", "fennel": "Apiaceae", "carrot": "Apiaceae",
    "mustard": "Brassicaceae", "cauliflower": "Brassicaceae", "radish": "Brassicaceae",
    "okra": "Malvaceae", "bhindi": "Malvaceae",
    "castor": "Euphorbiaceae", "sesame": "Pedaliaceae", "til": "Pedaliaceae",
    "onion": "Amaryllidaceae", "garlic": "Amaryllidaceae",
}

_CARRY_OVER = {
    "Solanaceae": "bacterial wilt, early and late blight and root-knot nematodes carry over",
    "Fabaceae": "collar rot, wilt and nematodes build up",
    "Malvaceae": "pink bollworm and root rot carry over",
    "Apiaceae": "wilt and soil-borne fungi build up",
    "Brassicaceae": "club root and cabbage pests carry over",
    "Poaceae": "shared cereal pests and diseases carry over",
}


def rotation_notes(crop: str, previous_crops: Optional[List[str]]) -> List[str]:
    if not previous_crops:
        return []
    family = FAMILY.get(crop.lower())
    previous = [(p, FAMILY.get(p.strip().lower())) for p in previous_crops if p and p.strip()]
    notes = []
    for name, prev_family in previous:
        if name.strip().lower() == crop.lower():
            notes.append(f"Same crop as last season ({name}) - pests and diseases build up; "
                         "rotate if you can.")
        elif family and prev_family == family:
            notes.append(f"Same family as {name} ({family}) - "
                         f"{_CARRY_OVER.get(family, 'soil-borne problems carry over')}.")
    legumes_before = [n for n, f in previous if f == "Fabaceae"]
    if legumes_before and family != "Fabaceae":
        notes.append(f"Follows a legume ({', '.join(legumes_before)}) - residual nitrogen "
                     "may reduce the N this crop needs; soil test before applying full N.")
    if family == "Fabaceae" and any(f == "Poaceae" for _, f in previous):
        notes.append("Legume after a cereal - a good rotation: breaks cereal pest cycles "
                     "and adds nitrogen for the next crop.")
    return notes


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
PERENNIALS = {"mango"}


def for_crop(crop: str, profile: Optional[dict], month_index: int,
             climatology: Optional[Climatology], soil: Dict[str, Optional[float]],
             previous_crops: Optional[List[str]],
             irrigation_available: Optional[bool],
             soil_awc_mm_per_m: Optional[float] = None) -> dict:
    """Advice for one recommended crop, from its top variety's catalogue entry."""
    perennial = crop.lower() in PERENNIALS
    profile = profile or {}
    notes: List[str] = []

    water = None
    if perennial:
        notes.append("Perennial orchard crop - a 20+ year investment with 4-5 years "
                     "before the first real harvest, not a one-season choice.")
    else:
        water = water_security(climatology, month_index,
                               profile.get("crop_duration_days"), profile.get("water_req_mm"),
                               root_zone_water_mm(crop, soil_awc_mm_per_m),
                               irrigation_available)
        if water:
            notes.append(water["message"])

    nutrients = soil_nutrients(profile, soil)
    notes.extend(n["advice"] for n in nutrients if n["status"] != "adequate")
    rotation = rotation_notes(crop, previous_crops)
    notes.extend(rotation)

    return {"perennial": perennial, "water_security": water,
            "soil_nutrients": nutrients, "rotation": rotation, "notes": notes}
