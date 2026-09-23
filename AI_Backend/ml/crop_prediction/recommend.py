"""Layer 1 + Layer 2 combined crop recommender.

The rule scorer runs first and owns the veto: if no variety clears the
suitability floor the recommender says so instead of naming a crop.  The
classifier only re-ranks what survives, which keeps the ML from asserting a
confident answer on a field where nothing should be planted.
"""
import math
import os
import threading
from functools import lru_cache

import numpy as np
import pandas as pd
import joblib

from .rule_scorer import FieldReading, score_all, prepare_profiles
from .region import filter_prepared, filter_profiles, known_regions
from .features import (add_engineered, ENGINEERED_NUM, MONTH_NUM, SOIL_AWC,
                       SOIL_ORDER)

HERE = os.path.dirname(os.path.abspath(__file__))
# Artifacts live under AI_Backend/ml/models/crop_prediction/.
MODEL_DIR = os.path.normpath(os.path.join(HERE, "..", "models", "crop_prediction"))
MODEL_PATH = os.path.join(MODEL_DIR, "crop_classifier.joblib")
PROFILE_PATH = os.path.join(MODEL_DIR, "crop_profiles.pkl")

# Below this Layer 1 score no variety is worth recommending.
SUITABILITY_FLOOR = 55.0
# Blend weight: how much the ML ranking counts against the agronomic score.
ML_WEIGHT = 0.35
# Median organic carbon across the dataset, used when the sensor omits it.
DEFAULT_OC_PERCENT = 0.55


# The artifacts are read-only after load and the model's predict path does
# not mutate state, so one copy is shared by every Recommender in the
# process.  Loading per instance meant a 3.4 MB joblib read for each region.
_load_lock = threading.Lock()


@lru_cache(maxsize=1)
def _load_bundle():
    return joblib.load(MODEL_PATH)


@lru_cache(maxsize=1)
def _load_profile_frame():
    return pd.read_pickle(PROFILE_PATH)


@lru_cache(maxsize=1)
def _load_prepared():
    return prepare_profiles(_load_profile_frame())


# Bounded: a region arrives from the caller, so an unbounded cache keyed on
# it is a memory leak with a public entry point.
@lru_cache(maxsize=32)
def _prepared_for_region(user_region):
    return filter_prepared(_load_prepared(), user_region)


def available_regions():
    """States named in the variety table. Used to reject unknown regions."""
    return known_regions(_load_profile_frame())


class Recommender:
    def __init__(self, user_region=None):
        """`user_region` restricts varieties to those grown in that state.

        The classifier itself is still trained on all-India data: a
        Gujarat-only model scored 79.0% against 84.6% because 66 varieties
        is too few groups to learn from.  Region belongs in the filter.
        """
        self.user_region = user_region
        with _load_lock:
            bundle = _load_bundle()
            self.all_profiles = _load_profile_frame()
            self._prepared = _prepared_for_region(user_region)
        self.model = bundle["model"]
        self.classes = bundle["classes"]
        self.features = bundle["features"]

    @property
    def profiles(self):
        """The region-filtered variety table, as a DataFrame.

        Kept for callers and tests that inspect it; scoring uses the prepared
        list instead, which costs nothing per request.
        """
        return (filter_profiles(self.all_profiles, self.user_region)
                if self.user_region else self.all_profiles)

    def _ml_probabilities(self, reading):
        # The classifier sees six numbers and nothing about the region or the
        # varieties, so identical readings - a dashboard refresh, a retry -
        # reuse the result instead of re-entering the sklearn pipeline.
        # dict() per call: the cache holds an immutable tuple so a caller
        # cannot mutate the shared entry.
        return dict(_ml_probabilities_cached(
            reading.pH,
            reading.EC_dSm,
            (reading.OC_percent if reading.OC_percent is not None
             else DEFAULT_OC_PERCENT),
            reading.moisture_percent,
            reading.soil_type,
            reading.month,
        ))

    def recommend(self, reading, top_n=5):
        region = reading.region or self.user_region
        profiles = (self._prepared if region == self.user_region
                    else _prepared_for_region(region))
        scored = score_all(reading, profiles)
        viable = [s for s in scored if s["score"] >= SUITABILITY_FLOOR]

        if not viable:
            best = scored[0]
            return {
                "status": "no_suitable_crop",
                "message": (
                    "No crop in the database is suitable for this field. "
                    f"The closest is {best['crop']} at {best['score']:.0f}/100."),
                "closest": best,
                "recommendations": [],
            }

        ml = self._ml_probabilities(reading)
        ml_max = max(ml.values()) or 1.0

        by_crop = {}
        for v in viable:
            by_crop.setdefault(v["crop"], []).append(v)

        results = []
        for crop, varieties in by_crop.items():
            varieties.sort(key=lambda v: (-v["score"], -v["yield_tha"]))
            agro = varieties[0]["score"] / 100.0
            ml_p = ml.get(crop, 0.0) / ml_max
            results.append({
                "crop": crop,
                "confidence": (1 - ML_WEIGHT) * agro + ML_WEIGHT * ml_p,
                "suitability_score": varieties[0]["score"],
                "ml_probability": ml.get(crop, 0.0),
                "top_varieties": [
                    {"variety": v["variety"], "score": round(v["score"], 1),
                     "expected_yield_tha": round(float(v["yield_tha"]), 2)}
                    for v in varieties[:3]],
                "reasons": varieties[0]["checks"],
            })

        results.sort(key=lambda r: -r["confidence"])
        return {"status": "ok", "recommendations": results[:top_n]}


def build_feature_row(pH, EC_dSm, OC_percent, moisture_percent, soil_type, month):
    """Build the one-row feature frame the classifier expects.

    `add_engineered` derives ten columns with vectorised pandas operations,
    which is right for training on thousands of rows and wasteful for the
    single row a request carries: each derived column is a separate insert
    into the frame.  Here the same ten formulas are evaluated as scalars and
    the frame is constructed once.

    The arithmetic is copied from `features.add_engineered` and must stay
    identical to it - `AI_Backend/tests/test_crop_prediction.py` asserts the
    two agree column for column, so a change to either side without the
    other fails the suite.
    """
    m = float(MONTH_NUM[month])
    texture_rank = float(SOIL_ORDER[soil_type])
    awc = float(SOIL_AWC[soil_type])
    return pd.DataFrame([{
        "pH": pH,
        "EC_dSm": EC_dSm,
        # Organic carbon is optional; most sensors do not report it.
        "OC_percent": OC_percent,
        "moisture_percent": moisture_percent,
        "soil_type": soil_type,
        "month": month,
        "season": _season_for_month(month),
        # Month is circular: December sits next to January.
        "month_sin": math.sin(2 * math.pi * m / 12),
        "month_cos": math.cos(2 * math.pi * m / 12),
        "soil_texture_rank": texture_rank,
        "soil_awc": awc,
        # Salinity hazard rises sharply once alkaline soils also carry salt.
        "alkalinity_stress": max(pH - 7.5, 0.0) * EC_dSm,
        "acidity_stress": max(6.0 - pH, 0.0),
        # Fertility proxy: organic carbon is the only nutrient signal there is.
        "oc_per_clay": OC_percent / texture_rank,
        # How full the reservoir is relative to what this texture holds.
        "moisture_vs_capacity": moisture_percent / (awc / 10.0),
        "moisture_x_texture": moisture_percent * texture_rank,
        "ph_x_ec": pH * EC_dSm,
    }])


@lru_cache(maxsize=2048)
def _ml_probabilities_cached(pH, EC_dSm, OC_percent, moisture_percent,
                             soil_type, month):
    bundle = _load_bundle()
    row = build_feature_row(pH, EC_dSm, OC_percent, moisture_percent,
                            soil_type, month)[bundle["features"]]
    proba = bundle["model"].predict_proba(row)[0]
    return tuple(zip(bundle["classes"], proba))


_SEASON_BY_MONTH = {
    "June": "Kharif", "July": "Kharif", "August": "Kharif",
    "September": "Kharif", "October": "Rabi", "November": "Rabi",
    "December": "Rabi", "January": "Rabi", "February": "Rabi",
    "March": "Zaid", "April": "Zaid", "May": "Zaid",
}


def _season_for_month(month):
    return _SEASON_BY_MONTH.get(month, "Kharif")


def explain(result, max_reasons=6):
    """Render a recommendation as plain text for a farmer."""
    if result["status"] == "no_suitable_crop":
        return result["message"]
    lines = []
    for i, r in enumerate(result["recommendations"], 1):
        lines.append(f"{i}. {r['crop']}  -  suitability "
                     f"{r['suitability_score']:.0f}/100, "
                     f"model confidence {r['ml_probability']:.0%}")
        for v in r["top_varieties"]:
            lines.append(f"      variety: {v['variety']} "
                         f"({v['expected_yield_tha']} t/ha expected)")
        for c in sorted(r["reasons"], key=lambda c: c["score"])[:max_reasons]:
            mark = "OK " if c["score"] >= 0.99 else (
                   "!! " if c["score"] < 0.5 else "~  ")
            lines.append(f"      {mark}{c['detail']}")
        lines.append("")
    return "\n".join(lines)
