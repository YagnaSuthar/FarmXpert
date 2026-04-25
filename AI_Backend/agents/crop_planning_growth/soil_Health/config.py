# config.py — app/soil_health/config.py
"""All constants, thresholds, and mappings for Soil Health Agent."""

# ── Input Validation Ranges ──────────────────────────────
VALID_RANGES = {
    "soil_moisture":            (0, 100),
    "soil_temperature":         (0, 60),
    "soil_ph":                  (3.0, 10.0),
    "nitrogen":                 (0, 300),
    "phosphorus":               (0, 200),
    "potassium":                (0, 300),
    "electrical_conductivity":  (0, 5.0),
    "air_temperature":          (0, 60),
    "air_humidity":             (0, 100),
    "rainfall":                 (0, 5000),
    "irrigation_amount":        (0, 100),
    "fertilizer_amount":        (0, 500),
}

# ── Optimal Ranges (Analysis) ────────────────────────────
OPTIMAL_RANGES = {
    "soil_ph":                  (6.0, 7.5),
    "nitrogen":                 (50, 150),
    "phosphorus":               (30, 60),
    "potassium":                (40, 80),
    "soil_moisture":            (40, 70),
    "electrical_conductivity":  (0.2, 1.0),
}

# ── Critical Thresholds → HIGH severity ──────────────────
CRITICAL_THRESHOLDS = {
    "soil_ph":                  {"low": 5.5, "high": 8.0},
    "nitrogen":                 {"low": 40},
    "electrical_conductivity":  {"high": 1.5},
}

LOW_DEVIATION_THRESHOLD = 0.15

# ── Alert Definitions ────────────────────────────────────
ALERT_DEFS = {
    "ACIDIC":        {"type": "ACIDIC",        "message": "Soil is Acidic",          "param": "soil_ph",                 "base_severity": "medium"},
    "ALKALINE":      {"type": "ALKALINE",      "message": "Soil is Alkaline",        "param": "soil_ph",                 "base_severity": "medium"},
    "LOW_N":         {"type": "LOW_N",         "message": "Low Nitrogen",            "param": "nitrogen",                "base_severity": "medium"},
    "HIGH_N":        {"type": "HIGH_N",        "message": "Excess Nitrogen",         "param": "nitrogen",                "base_severity": "medium"},
    "LOW_P":         {"type": "LOW_P",         "message": "Low Phosphorus",          "param": "phosphorus",              "base_severity": "medium"},
    "HIGH_P":        {"type": "HIGH_P",        "message": "Excess Phosphorus",       "param": "phosphorus",              "base_severity": "medium"},
    "LOW_K":         {"type": "LOW_K",         "message": "Low Potassium",           "param": "potassium",               "base_severity": "medium"},
    "HIGH_K":        {"type": "HIGH_K",        "message": "Excess Potassium",        "param": "potassium",               "base_severity": "medium"},
    "LOW_MOISTURE":  {"type": "LOW_MOISTURE",  "message": "Low Soil Moisture",       "param": "soil_moisture",           "base_severity": "medium"},
    "HIGH_MOISTURE": {"type": "HIGH_MOISTURE", "message": "Excess Soil Moisture",    "param": "soil_moisture",           "base_severity": "medium"},
    "HIGH_EC":       {"type": "HIGH_EC",       "message": "High Soil Salinity (EC)", "param": "electrical_conductivity", "base_severity": "medium"},
}

ALERT_MESSAGES = {k: v["message"] for k, v in ALERT_DEFS.items()}

# ── Fertilizer Recommendations ───────────────────────────
FERTILIZER_MAP = {
    "Low Nitrogen":            {"name": "Urea",                    "advice": "Apply 40-50 kg/acre in split doses during early growth stages"},
    "Low Phosphorus":          {"name": "DAP / SSP",               "advice": "Apply 25-30 kg/acre before sowing for root development"},
    "Low Potassium":           {"name": "MOP (Muriate of Potash)", "advice": "Apply 20-30 kg/acre to improve disease resistance"},
    "Soil is Acidic":          {"name": "Lime (CaCO₃)",            "advice": "Apply 1-2 tonnes/acre to raise soil pH gradually"},
    "Soil is Alkaline":        {"name": "Gypsum (CaSO₄)",          "advice": "Apply 500-800 kg/acre to lower soil pH over time"},
    "High Soil Salinity (EC)": {"name": "Soil Flushing",           "advice": "Use good quality irrigation water to flush salts; add organic matter"},
}

# ── Suggestions (keyed by alert type) ────────────────────
SUGGESTION_MAP = {
    "LOW_MOISTURE":  "Increase irrigation frequency or switch to drip irrigation for better water retention",
    "HIGH_MOISTURE": "Reduce watering schedule and improve field drainage to prevent root rot",
    "HIGH_EC":       "Flush soil with fresh water and add organic compost to reduce salinity",
    "LOW_N":         "Apply nitrogen-rich organic manure or green manure cover crops between seasons",
    "HIGH_N":        "Reduce nitrogen fertilizer application; consider planting nitrogen-scavenging cover crops",
    "LOW_P":         "Incorporate bone meal or rock phosphate into the soil before next planting cycle",
    "HIGH_P":        "Stop phosphorus fertilizer application until levels normalize",
    "LOW_K":         "Add wood ash or potash-rich compost to improve potassium availability",
    "HIGH_K":        "Reduce potassium-based fertilizers and monitor soil nutrient balance",
    "ACIDIC":        "Apply agricultural lime and avoid excessive use of ammonium-based fertilizers",
    "ALKALINE":      "Apply gypsum and use sulfur-based soil amendments to lower pH",
}

DEFAULT_SUGGESTION = "Continue monitoring soil health periodically and maintain balanced fertilization practices"

# ── Conflict Detection ───────────────────────────────────
# Maps fertilizer keywords → alert types they should fix
CONFLICT_MAP = {
    "urea":     ["LOW_N"],
    "dap":      ["LOW_N", "LOW_P"],
    "ssp":      ["LOW_P"],
    "npk":      ["LOW_N", "LOW_P", "LOW_K"],
    "mop":      ["LOW_K"],
    "potash":   ["LOW_K"],
    "lime":     ["ACIDIC"],
    "gypsum":   ["ALKALINE"],
}

# ── Optional Fields (for data quality) ───────────────────
OPTIONAL_FIELDS = [
    "soil_type", "crop_type", "rainfall",
    "irrigation_type", "irrigation_amount",
    "fertilizer_type", "fertilizer_amount",
]

# ── Score Weights ────────────────────────────────────────
SCORE_WEIGHTS = {
    "soil_ph": 20,
    "nitrogen": 20,
    "phosphorus": 15,
    "potassium": 15,
    "soil_moisture": 15,
    "electrical_conductivity": 15,
}

SCORE_CATEGORIES = {
    "EXCELLENT": (85, 100),
    "GOOD":      (70, 84),
    "ALERT":     (50, 69),
    "CRITICAL":  (0, 49),
}

# ── Summary Fragments ───────────────────────────────────
SUMMARY_FRAGMENTS = {
    "LOW_N":         "nitrogen deficiency",
    "HIGH_N":        "nitrogen excess",
    "LOW_P":         "phosphorus deficiency",
    "HIGH_P":        "phosphorus excess",
    "LOW_K":         "potassium deficiency",
    "HIGH_K":        "potassium excess",
    "ACIDIC":        "soil acidity",
    "ALKALINE":      "soil alkalinity",
    "LOW_MOISTURE":  "low moisture levels",
    "HIGH_MOISTURE": "excess moisture",
    "HIGH_EC":       "high salinity",
}