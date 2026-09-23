"""Process-wide loader for the crop recommender.

The artifacts are loaded once per process and shared by every request. The
engine itself memoises the joblib bundle and the variety table, so building a
`Recommender` for a second region costs a filtered list, not a 3.4 MB read.

`region` arrives from the caller, so it is validated against the states named
in the variety table before it reaches any cache. Without that check an
unknown region is both a slow memory leak - one cache entry per distinct
string - and a silent wrong answer, since filtering to nothing produces
"no crop is suitable" for a field that may be perfectly plantable.
"""
import json
import os
import threading
from typing import Iterable, Optional

from AI_Backend.ml.crop_prediction import Recommender
from AI_Backend.ml.crop_prediction.recommend import available_regions

_MODEL_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "..", "ml", "models", "crop_prediction")
)
_METRICS_PATH = os.path.join(_MODEL_DIR, "metrics.json")

# "Unfiltered", however the caller spells it. The variety table writes it
# "All-India" while the engine's own fallback looks for "all india", so a
# caller passing the table's spelling would otherwise be filtered down to the
# single row that literally carries that string. All spellings mean the same
# thing: score every variety.
_WILDCARD_REGIONS = {"all india", "all-india", "all_india", "india", "all"}

_lock = threading.Lock()
_recommenders: dict[Optional[str], Recommender] = {}
_metrics: Optional[dict] = None
_regions_lower: Optional[dict[str, str]] = None


class UnknownRegionError(ValueError):
    """Raised for a region no variety in the table is grown in."""


def known_regions() -> list[str]:
    """Every state named in the variety table, sorted.

    The "All-India" marker is left out: it is not a place a caller filters
    to, it is the absence of a filter, and listing it invites someone to send
    it as a region and get one variety back.
    """
    return sorted(name for key, name in _region_index().items()
                  if key not in _WILDCARD_REGIONS)


def _region_index() -> dict[str, str]:
    global _regions_lower
    if _regions_lower is None:
        with _lock:
            if _regions_lower is None:
                _regions_lower = {r.lower(): r for r in available_regions()}
    return _regions_lower


def normalize_region(region: Optional[str]) -> Optional[str]:
    """Canonicalise a caller-supplied region, or raise `UnknownRegionError`.

    Matching is case-insensitive because a region is free text on the way in;
    the canonical spelling is returned so the cache cannot be split across
    "gujarat", "Gujarat" and "GUJARAT".
    """
    if region is None or not str(region).strip():
        return None
    candidate = str(region).strip()
    if candidate.lower() in _WILDCARD_REGIONS:
        return None
    match = _region_index().get(candidate.lower())
    if match is None:
        raise UnknownRegionError(
            f"No variety in the database is grown in '{candidate}'. "
            f"Known regions: {', '.join(known_regions())}.")
    return match


def get_recommender(region: Optional[str]) -> Recommender:
    """Return the shared recommender for `region`, loading it on first use.

    `region` must already be normalised. One instance per region because the
    region filter is applied to the variety table at construction time.
    """
    hit = _recommenders.get(region)
    if hit is not None:
        return hit
    with _lock:
        # Re-check: another thread may have loaded it while we waited.
        hit = _recommenders.get(region)
        if hit is None:
            hit = Recommender(user_region=region)
            _recommenders[region] = hit
        return hit


def get_metrics() -> dict:
    """Validation metrics shipped alongside the model artifacts."""
    global _metrics
    if _metrics is None:
        try:
            with open(_METRICS_PATH, "r", encoding="utf-8") as fh:
                _metrics = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _metrics = {}
    return _metrics


def warmup(regions: Optional[Iterable[Optional[str]]] = None) -> bool:
    """Load the model ahead of the first request. Never raises."""
    try:
        for region in (regions if regions is not None else [None]):
            get_recommender(normalize_region(region))
        get_metrics()
        return True
    except Exception:
        return False


def is_ready(region: Optional[str] = None) -> bool:
    try:
        return normalize_region(region) in _recommenders
    except UnknownRegionError:
        return False


def loaded_regions() -> list[str]:
    return sorted(str(r) for r in _recommenders)
