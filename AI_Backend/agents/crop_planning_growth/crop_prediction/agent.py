"""Crop prediction agent - the one crop agent in FarmXpert.

Wraps the validated two-layer recommender (agronomic rule scorer + LightGBM
re-ranker) behind the standard agent interface, so the orchestrator and the
router call the same code path.

It replaces the earlier crop selector, which ran a generic 22-crop model
(coffee, coconut, jute...) on soil NPK and one day's rainfall and then let an
LLM re-rank the result and invent yields and profits. What that agent did
well - accept a farm_id, nested soil readings or orchestrator state, and feed
the task scheduler - lives on here: see `inputs.py`, `repository.py` and
`orchestrator/adapters/crop_prediction_to_scheduler.py`.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from AI_Backend.agents.base.base_agent import BaseAgent

from . import config
from .model_loader import (
    UnknownRegionError,
    get_metrics,
    is_ready,
    known_regions,
    loaded_regions,
    warmup,
)
from .inputs import normalize
from .schemas import CropPredictionRequest, CropPredictionResponse
from .service import CropPredictionService, cache_stats


class CropPredictionAgent(BaseAgent):
    def __init__(self, logger=None):
        super().__init__(config.AGENT_NAME)
        if logger is not None:
            self.logger = logger
        self.service = CropPredictionService(logger=self.logger)

    # ------------------------------------------------------------------
    # orchestrator entry point
    # ------------------------------------------------------------------
    async def run(self, state: dict) -> dict:
        """Score a field for the orchestrator.

        Writes to `crop_recommendation`, the key `FarmState` declares.
        LangGraph silently discards any key a node returns that is not in the
        state schema, so writing anywhere else would lose the result without
        an error.

        The block is always a dict with `agent_status` - success,
        invalid_input, timeout or error - and, on success, `result`. A
        successful run whose `result.status` is `no_suitable_crop` found
        nothing plantable: that is an answer, and it must reach the farmer
        as one.
        """
        try:
            response = await self.predict(state or {})
            block = {"agent_status": "success", "result": response.model_dump(mode="json")}
        except ValidationError as exc:
            self.logger.warning("Invalid crop prediction input: %s", exc)
            block = self._failure("invalid_input", self.format_validation_error(exc))
        except UnknownRegionError as exc:
            self.logger.warning("Crop prediction input unusable: %s", exc)
            block = self._failure("invalid_input", str(exc))
        except TimeoutError as exc:
            self.logger.error("Crop prediction timed out: %s", exc)
            block = self._failure("timeout", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Crop prediction failed: %s", exc, exc_info=True)
            block = self._failure("error", str(exc))
        return {"crop_recommendation": block}

    @staticmethod
    def _failure(agent_status: str, error: str) -> dict:
        return {"agent_status": agent_status, "result": None, "error": error}

    # ------------------------------------------------------------------
    # direct entry point
    # ------------------------------------------------------------------
    async def predict(self, input_data: Any) -> CropPredictionResponse:
        """Score a field.

        Accepts an already-built `CropPredictionRequest` (the router), or a
        dict in any of the shapes `inputs.normalize` understands: the native
        request, the legacy crop-selector payload, or orchestrator state.
        Readings must be supplied. Looking up a farm's stored readings is the
        Node backend's job - it owns the database and sends them in the
        request - so this agent never touches the database.

        Raises `ValidationError` on a bad or missing reading,
        `UnknownRegionError` on a region nobody grows anything in, and
        `TimeoutError` if scoring exceeds its budget.
        """
        notes: list[str] = []
        weather = None

        if isinstance(input_data, CropPredictionRequest):
            request = input_data
        else:
            raw = self.preprocess(dict(input_data))
            if isinstance(raw.get("weather_data"), dict):
                weather = raw["weather_data"]
            payload, adapted = normalize(raw)
            notes.extend(adapted)
            request = CropPredictionRequest.model_validate(payload)

        response = await self.service.predict(request, notes=notes, weather=weather)
        response.processed_at = self.postprocess({})["processed_at"]
        return response

    # ------------------------------------------------------------------
    # operational helpers
    # ------------------------------------------------------------------
    def warmup(self, regions: Optional[list[str]] = None) -> bool:
        """Load the model before serving traffic. Safe to call at startup."""
        return warmup(regions if regions is not None else config.WARMUP_REGIONS)

    def health(self) -> dict:
        """Readiness, provenance and live cache counters for monitoring."""
        region = config.DEFAULT_REGION
        ready = is_ready(region)
        return {
            "status": "ready" if ready else "loading",
            "agent_id": config.AGENT_ID,
            "agent_version": config.AGENT_VERSION,
            "region": region,
            "model_loaded": ready,
            "loaded_regions": loaded_regions(),
            "known_regions": known_regions(),
            "metrics": get_metrics(),
            "cache": cache_stats(),
            "limits": {
                "max_concurrent_scorings": config.MAX_CONCURRENT_SCORINGS,
                "scoring_timeout_s": config.SCORING_TIMEOUT_S,
                "max_top_n": config.MAX_TOP_N,
            },
            "disclaimer": config.DISCLAIMER,
        }

    @staticmethod
    def format_validation_error(exc: ValidationError) -> str:
        """Flatten pydantic's errors into one line a caller can show."""
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "request"
            parts.append(f"{loc}: {err.get('msg', 'invalid')}")
        return "; ".join(parts)
