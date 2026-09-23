"""Engineered features derived only from prediction-time-available inputs.

Every feature here is a transform of the four sensor readings, the soil type
and the calendar month.  Nothing consults a crop attribute, so none of this
can leak the label.
"""
import numpy as np
import pandas as pd

MONTH_NUM = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5,
             "June": 6, "July": 7, "August": 8, "September": 9,
             "October": 10, "November": 11, "December": 12}

# Ordered by water-holding capacity / clay fraction: sand -> clay.
SOIL_ORDER = {"Sandy": 1, "Sandy Loam": 2, "Red Laterite": 3, "Loam": 4,
              "Silty Loam": 5, "Alluvial": 6, "Clay Loam": 7,
              "Black Cotton": 8, "Clay": 9, "Saline-Alkaline": 10}

# Rough plant-available water proxy per soil class (mm per m of depth).
SOIL_AWC = {"Sandy": 60, "Sandy Loam": 110, "Red Laterite": 90, "Loam": 170,
            "Silty Loam": 190, "Alluvial": 175, "Clay Loam": 190,
            "Black Cotton": 200, "Clay": 210, "Saline-Alkaline": 120}


def add_engineered(X):
    """Return a copy of X with derived columns appended."""
    out = X.copy()
    m = out["month"].map(MONTH_NUM).astype(float)

    # Month is circular: December sits next to January, not eleven units away.
    out["month_sin"] = np.sin(2 * np.pi * m / 12)
    out["month_cos"] = np.cos(2 * np.pi * m / 12)

    out["soil_texture_rank"] = out["soil_type"].map(SOIL_ORDER).astype(float)
    out["soil_awc"] = out["soil_type"].map(SOIL_AWC).astype(float)

    # Salinity hazard rises sharply once alkaline soils also carry salt.
    out["alkalinity_stress"] = np.clip(out["pH"] - 7.5, 0, None) * out["EC_dSm"]
    out["acidity_stress"] = np.clip(6.0 - out["pH"], 0, None)

    # Fertility proxy: organic carbon is the only nutrient signal available.
    out["oc_per_clay"] = out["OC_percent"] / out["soil_texture_rank"]

    # How full the soil reservoir is relative to what this texture can hold.
    out["moisture_vs_capacity"] = (out["moisture_percent"] /
                                   (out["soil_awc"] / 10.0))
    out["moisture_x_texture"] = out["moisture_percent"] * out["soil_texture_rank"]
    out["ph_x_ec"] = out["pH"] * out["EC_dSm"]
    return out


ENGINEERED_NUM = ["month_sin", "month_cos", "soil_texture_rank", "soil_awc",
                  "alkalinity_stress", "acidity_stress", "oc_per_clay",
                  "moisture_vs_capacity", "moisture_x_texture", "ph_x_ec"]
