"""Prove this vendored engine still scores exactly like the model repo.

The copy under `AI_Backend/ml/crop_prediction/` differs from the model repo
only in how it loads and shapes data - artifacts are shared process-wide, the
variety table is prepared once as plain dicts, and the single-row feature
frame is built directly instead of through `add_engineered`. None of that is
allowed to change a score by so much as a rounding step.

This script loads both engines side by side and diffs the full `recommend()`
output - scores, ordering, every reason dict and every string - over a grid
of fields in three regions. Run it after any change to the engine:

    python -m AI_Backend.tests.verify_crop_engine_equivalence

It needs the model repo checked out at MODEL_REPO_SRC below; skip it (with a
clear message) if that path is absent. It takes a few minutes, because the
pristine engine is the slow one.
"""
import importlib
import itertools
import os
import sys

MODEL_REPO_SRC = os.getenv("FARMX_MODEL_SRC", r"D:\CSV\FarmX_data_Zip\src")

GRID = list(itertools.product(
    [5.2, 6.8, 8.0, 8.9],                              # pH
    [0.2, 0.58, 6.0],                                  # EC dS/m
    [5.0, 51.2, 80.0],                                 # moisture
    ["Sandy", "Loam", "Black Cotton", "Saline-Alkaline", "Red Laterite"],
    ["January", "June", "July", "November"],           # month
))

VARIANTS = [
    dict(forecast_temp_mean_C=30.0, forecast_humidity_mean=60.0, forecast_rain_mm=700),
    dict(forecast_temp_mean_C=20.0, forecast_humidity_mean=70.0, forecast_rain_mm=250),
    dict(forecast_temp_mean_C=58.0, forecast_humidity_mean=10.0, forecast_rain_mm=0),
    dict(air_temp_C=28.0, air_humidity=65.0),          # no forecast at all
]

REGIONS = [None, "Gujarat", "Maharashtra"]


def load_pristine():
    """Import the model repo's modules under their own top-level names."""
    sys.path.insert(0, MODEL_REPO_SRC)
    try:
        for name in ("calendar_feat", "features", "region", "rule_scorer", "recommend"):
            sys.modules.pop(name, None)
        return (importlib.import_module("recommend"),
                importlib.import_module("rule_scorer"))
    finally:
        sys.path.remove(MODEL_REPO_SRC)


def compare(region, old_mod, old_rule, new_mod, new_rule):
    old = old_mod.Recommender(user_region=region)
    new = new_mod.Recommender(user_region=region)
    checked = mismatches = 0
    for ph, ec, moisture, soil, month in GRID:
        for extra in VARIANTS:
            kwargs = dict(pH=ph, EC_dSm=ec, moisture_percent=moisture,
                          soil_type=soil, month=month, **extra)
            a = old.recommend(old_rule.FieldReading(**kwargs), top_n=5)
            b = new.recommend(new_rule.FieldReading(**kwargs), top_n=5)
            checked += 1
            if a != b:
                mismatches += 1
                if mismatches <= 3:
                    print(f"  MISMATCH region={region} {kwargs}")
                    print(f"    pristine: {str(a)[:300]}")
                    print(f"    vendored: {str(b)[:300]}")
    return checked, mismatches


def main() -> bool:
    if not os.path.isdir(MODEL_REPO_SRC):
        print(f"Model repo not found at {MODEL_REPO_SRC}; set FARMX_MODEL_SRC.")
        print("Skipping equivalence check - it cannot run without both engines.")
        return True

    old_mod, old_rule = load_pristine()
    new_mod = importlib.import_module("AI_Backend.ml.crop_prediction.recommend")
    new_rule = importlib.import_module("AI_Backend.ml.crop_prediction.rule_scorer")

    total = bad = 0
    for region in REGIONS:
        checked, mismatches = compare(region, old_mod, old_rule, new_mod, new_rule)
        total += checked
        bad += mismatches
        print(f"region={region or 'all-India':<12} {checked} fields, "
              f"{mismatches} mismatches", flush=True)

    print(f"\n{total - bad}/{total} field scorings identical")
    return bad == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
