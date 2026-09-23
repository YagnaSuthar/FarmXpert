"""Configuration for the crop prediction agent.

Every knob here is a serving-layer concern (region, how many crops to show,
caching, timeouts).  The model's own thresholds - the suitability floor and
the ML blend weight - deliberately live in the engine, not here: changing
them changes validated behaviour and must go through the model repo.
"""
import os


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _num(name: str, default, cast=float):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


AGENT_ID = "crop_prediction"
AGENT_NAME = "CropPrediction"
AGENT_VERSION = "1.2.0"

# The deployed configuration is Gujarat; 9 of 10 crops and 66 of 344
# varieties survive the region filter.
DEFAULT_REGION = os.getenv("CROP_PREDICTION_REGION", "Gujarat")

# Regions loaded at startup so the first request for each pays nothing.
WARMUP_REGIONS = [
    r.strip() for r in os.getenv("CROP_PREDICTION_WARMUP_REGIONS", DEFAULT_REGION).split(",")
    if r.strip()
]

# Three, not one.  Top-1 accuracy is 80.6%, top-3 is 99.0% - showing one crop
# is wrong for roughly one field in five, and the farmer knows their water
# access, plot and market better than the model does.
DEFAULT_TOP_N = _num("CROP_PREDICTION_TOP_N", 3, int)
MAX_TOP_N = 5

# A reason scoring below this is an actionable problem worth surfacing first.
PROBLEM_REASON_THRESHOLD = 0.5

# --- scoring cache -------------------------------------------------------
# Scoring is deterministic, so identical fields reuse the answer. The TTL
# keeps an entry from outliving the forecast it was scored against.
CACHE_ENABLED = _flag("CROP_PREDICTION_CACHE", True)
CACHE_SIZE = _num("CROP_PREDICTION_CACHE_SIZE", 512, int)
CACHE_TTL_S = _num("CROP_PREDICTION_CACHE_TTL", 900.0)

# --- limits --------------------------------------------------------------
# Scoring is CPU-bound and runs in a worker thread. Bounding concurrency
# keeps a burst from queueing behind the thread pool with no ceiling; callers
# past the limit wait, then fail fast rather than hanging.
MAX_CONCURRENT_SCORINGS = _num("CROP_PREDICTION_MAX_CONCURRENCY", 8, int)
SCORING_TIMEOUT_S = _num("CROP_PREDICTION_TIMEOUT", 15.0)
# Log any request slower than this so a regression shows up in the logs.
SLOW_REQUEST_MS = _num("CROP_PREDICTION_SLOW_MS", 250.0)

# --- optional enrichment -------------------------------------------------
# Optional LLM narration of the engine's reasons. Never re-ranks, never
# invents a crop - it only puts the reason list into farmer-readable words.
ENABLE_LLM_NARRATION = _flag("CROP_PREDICTION_LLM", False)
LLM_MODEL = os.getenv("CROP_PREDICTION_LLM_MODEL", "llama-3.1-8b-instant")
LLM_TIMEOUT_S = _num("CROP_PREDICTION_LLM_TIMEOUT", 12.0)

# Weather enrichment: pull forecast means from the Weather Watcher agent when
# the caller did not supply them.
ENABLE_WEATHER_ENRICHMENT = _flag("CROP_PREDICTION_WEATHER", True)

# Season climate (ERA5 via Open-Meteo): fills season rain, temperature and
# humidity when a location is given, and drives per-crop water security.
ENABLE_CLIMATE = _flag("CROP_PREDICTION_CLIMATE", True)
CLIMATE_TIMEOUT_S = _num("CROP_PREDICTION_CLIMATE_TIMEOUT", 20.0)
WEATHER_TIMEOUT_S = _num("CROP_PREDICTION_WEATHER_TIMEOUT", 10.0)

# --- provenance ----------------------------------------------------------
# Validated performance of the deployed (Gujarat) configuration. Surfaced on
# every response so no caller can present this as more certain than it is.
MODEL_ACCURACY_TOP1 = 0.806
MODEL_ACCURACY_TOP3 = 0.990

DISCLAIMER = (
    "Shortlisting tool built from a crop suitability reference table, not from "
    "observed outcomes on real fields. Top-1 accuracy is 80.6% and top-3 is 99.0%: "
    "treat the list as candidates to discuss with an agronomist, not as agronomic advice."
)
