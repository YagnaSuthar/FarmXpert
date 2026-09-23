"""Vendored FarmXpert crop recommender engine (Layer 1 rules + Layer 2 LightGBM).

Copied verbatim from the validated model repo; only the imports and artifact
paths were changed.  Do not re-tune or re-rank its output here — see
`agents/crop_planning_growth/crop_prediction/` for the serving layer.
"""
from .recommend import Recommender, explain, SUITABILITY_FLOOR, ML_WEIGHT
from .rule_scorer import FieldReading
from . import units

__all__ = ["Recommender", "explain", "FieldReading", "units",
           "SUITABILITY_FLOOR", "ML_WEIGHT"]
