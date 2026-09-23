"""Serving layer for the crop recommender.

The one rule that governs this file: the engine's output is fact.  This
module maps it into the API contract, adds warnings about the input and can
ask an LLM to retell the reasons in plainer words - it never recomputes a
score, never re-orders the list and never substitutes a crop.  An agent that
argues its way to a different crop has replaced a validated system with
guesswork.

Everything else here is operational: validate the region before it reaches a
cache, keep the CPU-bound sweep off the event loop, bound how many run at
once, and reuse the answer for a field that was just scored.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
import weakref
from typing import Any, List, Optional, Tuple

from AI_Backend.ml.crop_prediction import FieldReading, explain
from AI_Backend.ml.crop_prediction.features import SOIL_AWC
from AI_Backend.ml.crop_prediction.recommend import (
    ML_WEIGHT,
    SUITABILITY_FLOOR,
    _load_prepared,
)

from . import agronomy, climate, config
from .cache import TTLCache
from .model_loader import get_recommender, normalize_region
from .schemas import (
    CropAgronomy,
    CropCandidate,
    CropPredictionRequest,
    CropPredictionResponse,
    ModelInfo,
    PredictionStatus,
    PH_SUPPORTED,
    ReasonItem,
    SeasonClimate,
    VarietyItem,
)

# Shared across requests: these guard process-wide resources, not one call.
_score_cache = TTLCache(maxsize=config.CACHE_SIZE, ttl_seconds=config.CACHE_TTL_S)

# One semaphore per event loop. An asyncio.Semaphore binds to the loop that
# first blocks on it and raises on any other, which under a server is fine -
# there is one loop - and breaks the moment something runs a second one: a
# test, a script, a worker. Keyed weakly so a finished loop is collected.
_slots_by_loop: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary())
_slots_guard = threading.Lock()


def _scoring_slots() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    slots = _slots_by_loop.get(loop)
    if slots is None:
        with _slots_guard:
            slots = _slots_by_loop.get(loop)
            if slots is None:
                slots = asyncio.Semaphore(config.MAX_CONCURRENT_SCORINGS)
                _slots_by_loop[loop] = slots
    return slots


class CropPredictionService:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    async def predict(
        self,
        request: CropPredictionRequest,
        notes: Optional[List[str]] = None,
        weather: Optional[dict] = None,
    ) -> CropPredictionResponse:
        """Score one field.

        `notes` are warnings produced while adapting the caller's payload
        (an inferred month, a mapped soil class). `weather` is Weather
        Watcher output the orchestrator already has; passing it avoids a
        second call to the same API for the same coordinates.
        """
        started = time.perf_counter()
        request_id = request.request_id or uuid.uuid4().hex[:12]

        # Raises UnknownRegionError, which the agent maps to a 422: a region
        # nobody grows anything in must not be answered with "nothing is
        # suitable here", which is what the filter would otherwise produce.
        region = normalize_region(request.region or config.DEFAULT_REGION)

        warnings: List[str] = list(notes or [])

        # Season climate for this location: what the rain, temperature and
        # humidity of the growing season normally are here. Caller-supplied
        # values always win; climate fills only what is missing.
        climatology, season = await self._season_climate(request, warnings)
        request = self._fill_from_climate(request, season, warnings)

        for warning in self._input_warnings(request):
            if warning not in warnings:
                warnings.append(warning)

        temp_mean, humidity_mean, weather_warnings = await self._resolve_forecast(
            request, weather)
        warnings.extend(weather_warnings)

        reading = self._to_field_reading(request, region, temp_mean, humidity_mean)
        cache_key = self._cache_key(reading, request.top_n)

        result = _score_cache.get(cache_key) if config.CACHE_ENABLED else None
        cached = result is not None
        if not cached:
            result = await self._score(reading, request.top_n, request_id)
            if config.CACHE_ENABLED:
                _score_cache.set(cache_key, result)

        response = self._to_response(request, region, result, warnings)
        self._attach_agronomy(response, request, climatology, season)
        response.request_id = request_id
        response.cached = cached

        if config.ENABLE_LLM_NARRATION:
            response.narration = await self._narrate(response)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        response.latency_ms = round(elapsed_ms, 1)
        self._log_completion(request_id, response, region, cached, elapsed_ms)
        return response

    async def _score(self, reading: FieldReading, top_n: int, request_id: str) -> dict:
        """Run the engine off the event loop, bounded and time-limited."""
        recommender = get_recommender(reading.region)
        try:
            async with _scoring_slots():
                return await asyncio.wait_for(
                    asyncio.to_thread(recommender.recommend, reading, top_n),
                    timeout=config.SCORING_TIMEOUT_S,
                )
        except asyncio.TimeoutError:
            self.logger.error(
                "[%s] Scoring exceeded %ss", request_id, config.SCORING_TIMEOUT_S)
            raise TimeoutError(
                "Crop scoring took too long. Please retry.") from None

    def _log_completion(self, request_id, response, region, cached, elapsed_ms) -> None:
        line = (f"[{request_id}] status={response.status.value} region={region} "
                f"crops={[c.crop for c in response.recommendations]} "
                f"cached={cached} {elapsed_ms:.0f}ms")
        if elapsed_ms > config.SLOW_REQUEST_MS and not cached:
            self.logger.warning("%s  (slower than %sms)", line, config.SLOW_REQUEST_MS)
        else:
            self.logger.info(line)

    @staticmethod
    def _cache_key(reading: FieldReading, top_n: int) -> tuple:
        """Everything the engine actually reads, and nothing else.

        `farm_id` and `request_id` are deliberately absent: two farms with
        the same readings are the same field as far as scoring is concerned.
        """
        return (
            reading.pH, reading.EC_dSm, reading.moisture_percent,
            reading.soil_type, reading.month,
            reading.air_temp_C, reading.air_humidity, reading.OC_percent,
            reading.forecast_rain_mm, reading.forecast_temp_mean_C,
            reading.forecast_humidity_mean, reading.region, top_n,
        )

    # ------------------------------------------------------------------
    # input handling
    # ------------------------------------------------------------------
    def _input_warnings(self, request: CropPredictionRequest) -> List[str]:
        warnings: List[str] = []

        lo, hi = PH_SUPPORTED
        if not lo <= request.ph <= hi:
            warnings.append(
                f"pH {request.ph} lies outside the {lo}-{hi} range the model was built "
                "from. The reading is scored, but treat the result with extra caution.")

        if request.forecast_temp_mean_c is None and request.air_temp_c is None:
            warnings.append(
                "No temperature supplied. Temperature is one of the three hard vetoes, "
                "so the suitability score is weaker without it.")

        if request.forecast_rain_mm is None:
            warnings.append(
                "No growing-window rainfall supplied; the water-requirement check was "
                "skipped.")

        if any(v is not None for v in (request.n_kg_ha, request.p_kg_ha, request.k_kg_ha)):
            warnings.append(
                "Soil NPK is not part of the suitability score (the validated model does not "
                "take it); it is compared with each recommended crop's soil nutrient "
                "range under `agronomy.soil_nutrients`.")
            warnings.append(
                "NPK from an in-field sensor is indicative only; confirm with a lab soil "
                "test (Soil Health Card) before changing fertiliser rates.")

        if request.organic_carbon_percent is None:
            warnings.append(
                "Organic carbon not supplied; the dataset median (0.55%) was used.")

        return warnings

    async def _resolve_forecast(
        self, request: CropPredictionRequest, weather: Optional[dict] = None
    ) -> Tuple[Optional[float], Optional[float], List[str]]:
        """Fill missing forecast means from the Weather Watcher agent.

        Only the means are borrowed.  Rainfall is deliberately never taken
        from the forecast: the engine wants a total over the whole growing
        window, and a 14-day total would understate a season by an order of
        magnitude while looking perfectly reasonable.
        """
        temp = request.forecast_temp_mean_c
        humidity = request.forecast_humidity_mean_percent
        warnings: List[str] = []

        have_both = temp is not None and humidity is not None
        if have_both or not config.ENABLE_WEATHER_ENRICHMENT:
            return temp, humidity, warnings

        if not weather:
            if request.location is None:
                return temp, humidity, warnings
            try:
                weather = await asyncio.wait_for(
                    self._fetch_weather(request.location.lat, request.location.lon),
                    timeout=config.WEATHER_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                warnings.append("Weather lookup timed out; scored without a forecast.")
                return temp, humidity, warnings
            except Exception as exc:  # noqa: BLE001 - enrichment must never fail a prediction
                self.logger.warning("Weather enrichment failed: %s", exc)
                warnings.append("Weather lookup failed; scored without a forecast.")
                return temp, humidity, warnings

        # Short term is today..day 6 and long term the days after; the mean
        # is taken over the whole horizon the weather agent returned.
        days = list(weather.get("forecast_short_term") or []) + \
            list(weather.get("forecast_long_term") or [])
        if not days:
            warnings.append("Weather agent returned no forecast; scored without one.")
            return temp, humidity, warnings

        if temp is None:
            means = [
                (self._num(d, "temp_min") + self._num(d, "temp_max")) / 2.0
                for d in days
                if self._num(d, "temp_min") is not None and self._num(d, "temp_max") is not None
            ]
            if means:
                temp = round(sum(means) / len(means), 2)
                warnings.append(
                    f"Temperature taken from the {len(means)}-day forecast mean "
                    f"({temp} C), not from a full growing-window forecast.")

        if humidity is None:
            hums = [h for h in (self._num(d, "humidity") for d in days) if h is not None]
            if hums:
                humidity = round(sum(hums) / len(hums), 2)
                warnings.append(
                    f"Humidity taken from the {len(hums)}-day forecast mean "
                    f"({humidity}%).")

        return temp, humidity, warnings

    # ------------------------------------------------------------------
    # season climate
    # ------------------------------------------------------------------
    climate_transport = None   # tests inject a mock transport here

    async def _season_climate(self, request: CropPredictionRequest, warnings: List[str]):
        """ERA5 climatology for the location and the season window. Never raises."""
        if request.location is None or not config.ENABLE_CLIMATE:
            return None, None
        try:
            climatology = await asyncio.wait_for(
                climate.get_climatology(request.location.lat, request.location.lon,
                                        transport=self.climate_transport),
                timeout=config.CLIMATE_TIMEOUT_S)
        except (asyncio.TimeoutError, climate.ClimateUnavailable):
            warnings.append("Climate history for this location is unavailable; season "
                            "rainfall could not be estimated.")
            return None, None
        except Exception as exc:  # noqa: BLE001 - enrichment must never fail a prediction
            self.logger.warning("Climatology failed: %s", exc)
            warnings.append("Climate history for this location is unavailable.")
            return None, None
        season = climatology.season(_MONTH_INDEX[request.month.value])
        return climatology, season

    @staticmethod
    def _fill_from_climate(request: CropPredictionRequest, season: Optional[dict],
                           warnings: List[str]) -> CropPredictionRequest:
        if not season:
            return request
        update = {}
        filled = []
        if request.forecast_rain_mm is None:
            update["forecast_rain_mm"] = season["rain_median_mm"]
            filled.append(f"rain {season['rain_median_mm']:.0f} mm "
                          f"(dry year {season['rain_dry_year_mm']:.0f} mm)")
        if request.forecast_temp_mean_c is None and season.get("temp_mean_c") is not None:
            update["forecast_temp_mean_c"] = season["temp_mean_c"]
            filled.append(f"mean temperature {season['temp_mean_c']} C")
        if (request.forecast_humidity_mean_percent is None
                and season.get("humidity_mean_percent") is not None):
            update["forecast_humidity_mean_percent"] = season["humidity_mean_percent"]
            filled.append(f"mean humidity {season['humidity_mean_percent']}%")
        if not update:
            return request
        warnings.append(
            f"Season conditions from this location's {season['years']}-year climate "
            f"record for the {season['window_days']} days from sowing: "
            f"{', '.join(filled)}.")
        return request.model_copy(update=update)

    # ------------------------------------------------------------------
    # agronomy
    # ------------------------------------------------------------------
    def _attach_agronomy(self, response: CropPredictionResponse,
                         request: CropPredictionRequest, climatology, season) -> None:
        month = _MONTH_INDEX[request.month.value]
        soil = {"n_kg_ha": request.n_kg_ha, "p_kg_ha": request.p_kg_ha,
                "k_kg_ha": request.k_kg_ha}
        for candidate in response.recommendations:
            top = candidate.top_varieties[0].variety if candidate.top_varieties else None
            advice = agronomy.for_crop(
                candidate.crop, _profile(candidate.crop, top), month, climatology, soil,
                request.previous_crops, request.irrigation_available,
                soil_awc_mm_per_m=SOIL_AWC.get(request.soil_type.value))
            candidate.agronomy = CropAgronomy.model_validate(advice)

        if season:
            response.climate = SeasonClimate(
                **{k: season[k] for k in ("years", "window_days", "rain_median_mm",
                                          "rain_dry_year_mm", "temp_mean_c",
                                          "humidity_mean_percent")},
                source=climate.SOURCE_NOTE)

        first = response.recommendations[0] if response.recommendations else None
        water = first.agronomy.water_security if first and first.agronomy else None
        if (request.irrigation_available is False and water
                and water.category == "irrigation_essential"):
            response.warnings.append(
                f"The top-ranked crop, {first.crop}, needs irrigation at this location and "
                "you reported none - look at the rainfed options in the shortlist.")

    async def _fetch_weather(self, lat: float, lon: float) -> dict:
        # Imported lazily so a weather-agent import error cannot take down
        # crop prediction, which works perfectly well without it.
        from AI_Backend.agents.crop_planning_growth.weather_watcher.agent import WeatherAgent

        agent = WeatherAgent(name="WeatherWatcher")
        return await agent.run({"lat": lat, "lon": lon})

    @staticmethod
    def _num(day: Any, key: str) -> Optional[float]:
        value = day.get(key) if isinstance(day, dict) else getattr(day, key, None)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _to_field_reading(
        self,
        request: CropPredictionRequest,
        region: Optional[str],
        temp_mean: Optional[float],
        humidity_mean: Optional[float],
    ) -> FieldReading:
        return FieldReading(
            pH=float(request.ph),
            EC_dSm=request.resolved_ec_ds_m,
            moisture_percent=float(request.moisture_percent),
            soil_type=request.soil_type.value,
            month=request.month.value,
            air_temp_C=request.air_temp_c,
            air_humidity=request.air_humidity_percent,
            OC_percent=request.organic_carbon_percent,
            N_kg_ha=request.n_kg_ha,
            P_kg_ha=request.p_kg_ha,
            K_kg_ha=request.k_kg_ha,
            forecast_rain_mm=request.forecast_rain_mm,
            forecast_temp_mean_C=temp_mean,
            forecast_humidity_mean=humidity_mean,
            region=region,
        )

    # ------------------------------------------------------------------
    # output mapping
    # ------------------------------------------------------------------
    def _to_response(
        self,
        request: CropPredictionRequest,
        region: Optional[str],
        result: dict,
        warnings: List[str],
    ) -> CropPredictionResponse:
        model_info = ModelInfo(
            agent_id=config.AGENT_ID,
            agent_version=config.AGENT_VERSION,
            region=region,
            top1_accuracy=config.MODEL_ACCURACY_TOP1,
            top3_accuracy=config.MODEL_ACCURACY_TOP3,
            suitability_floor=SUITABILITY_FLOOR,
            ml_weight=ML_WEIGHT,
        )

        if result.get("status") == "no_suitable_crop":
            # `closest` is carried for diagnosis only. It scored below the
            # floor: the classifier cannot refuse - it was trained solely on
            # crops that succeeded - so this veto is the one real safety
            # property here, and promoting `closest` would remove it.
            return CropPredictionResponse(
                status=PredictionStatus.NO_SUITABLE_CROP,
                message=result.get("message"),
                farm_id=request.farm_id,
                recommendations=[],
                closest=self._to_candidate(result.get("closest"), rank=0, closest=True),
                summary=result.get("message"),
                warnings=warnings,
                model_info=model_info,
                disclaimer=config.DISCLAIMER,
            )

        raw = result.get("recommendations", [])
        candidates = [
            self._to_candidate(item, rank=i) for i, item in enumerate(raw, start=1)
        ]

        if len(candidates) == 1:
            warnings.append(
                "Only one crop cleared the suitability floor on this field.")

        return CropPredictionResponse(
            status=PredictionStatus.OK,
            farm_id=request.farm_id,
            recommendations=[c for c in candidates if c is not None],
            summary=explain(result),
            warnings=warnings,
            model_info=model_info,
            disclaimer=config.DISCLAIMER,
        )

    def _to_candidate(
        self, item: Optional[dict], rank: int, closest: bool = False
    ) -> Optional[CropCandidate]:
        if not item:
            return None

        # A `closest` entry comes from the rule scorer alone and carries a
        # different shape: one variety, no ML probability.
        if closest:
            reasons = self._to_reasons(item.get("checks", []))
            return CropCandidate(
                rank=0,
                crop=item.get("crop", "Unknown"),
                suitability_score=round(float(item.get("score", 0.0)), 1),
                ml_probability=0.0,
                confidence=0.0,
                top_varieties=[VarietyItem(
                    variety=item.get("variety", "Unknown"),
                    score=round(float(item.get("score", 0.0)), 1),
                    expected_yield_tha=round(float(item.get("yield_tha", 0.0) or 0.0), 2),
                    **_variety_facts(item.get("crop"), item.get("variety")),
                )],
                reasons=reasons,
                problems=[r.detail for r in reasons if r.is_problem],
            )

        reasons = self._to_reasons(item.get("reasons", []))
        return CropCandidate(
            rank=rank,
            crop=item.get("crop", "Unknown"),
            suitability_score=round(float(item.get("suitability_score", 0.0)), 1),
            ml_probability=round(float(item.get("ml_probability", 0.0)), 4),
            confidence=round(float(item.get("confidence", 0.0)), 4),
            top_varieties=[
                VarietyItem(
                    variety=v.get("variety", "Unknown"),
                    score=float(v.get("score", 0.0)),
                    expected_yield_tha=float(v.get("expected_yield_tha", 0.0)),
                    **_variety_facts(item.get("crop"), v.get("variety")),
                )
                for v in item.get("top_varieties", [])
            ],
            reasons=reasons,
            problems=[r.detail for r in reasons if r.is_problem],
        )

    @staticmethod
    def _to_reasons(checks: List[dict]) -> List[ReasonItem]:
        reasons = []
        # Worst first: the failing checks are the actionable part of the answer.
        for check in sorted(checks, key=lambda c: float(c.get("score", 0.0))):
            detail = str(check.get("detail", ""))
            score = float(check.get("score", 0.0))
            reasons.append(ReasonItem(
                check=str(check.get("check", "")),
                score=max(0.0, min(1.0, score)),
                weight=int(check.get("weight", 0) or 0),
                detail=detail,
                is_problem=score < config.PROBLEM_REASON_THRESHOLD,
                is_disqualifying=detail.rstrip().endswith("[DISQUALIFYING]"),
            ))
        return reasons

    # ------------------------------------------------------------------
    # optional narration
    # ------------------------------------------------------------------
    async def _narrate(self, response: CropPredictionResponse) -> Optional[str]:
        """Retell the engine's reasons in plainer words. Additive only.

        Failure here returns None: `summary` already carries the same
        information, so narration is never allowed to fail a prediction.
        """
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_groq import ChatGroq
        except ImportError:
            self.logger.warning("LLM narration enabled but langchain_groq is not installed.")
            return None

        import os

        api_key = os.getenv("Groq_API")
        if not api_key:
            self.logger.warning("LLM narration enabled but Groq_API is not set.")
            return None

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are explaining a crop shortlist to a farmer in Gujarat.\n"
             "The analysis below is final and was produced by a validated model.\n"
             "RULES, no exceptions:\n"
             "- Do NOT change the ranking, add a crop, or drop a crop.\n"
             "- Do NOT invent numbers. Use only the scores and reasons given.\n"
             "- If the status is no_suitable_crop, say plainly that nothing in the "
             "database suits this field and explain what is wrong with it. Do not "
             "suggest the closest crop as an option.\n"
             "- Lead with the checks that failed, since those are actionable.\n"
             "- Say clearly that these are candidates to consider, not advice.\n"
             "Write 4-8 short sentences in plain language."),
            ("user", "{analysis}"),
        ])

        llm = ChatGroq(
            model=config.LLM_MODEL,
            temperature=0.2,
            groq_api_key=api_key,
            max_tokens=700,
        )

        analysis = response.model_dump_json(
            include={"status", "message", "recommendations", "warnings"})

        try:
            chain = prompt | llm
            result = await asyncio.wait_for(
                chain.ainvoke({"analysis": analysis}), timeout=config.LLM_TIMEOUT_S)
            return getattr(result, "content", None)
        except asyncio.TimeoutError:
            self.logger.warning("LLM narration timed out after %ss", config.LLM_TIMEOUT_S)
            return None
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("LLM narration failed: %s", exc)
            return None


_MONTH_INDEX = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}

_PROFILES: Optional[dict] = None


def _profile(crop: Optional[str], variety: Optional[str]) -> Optional[dict]:
    """Catalogue entry for a variety, indexed once."""
    global _PROFILES
    if _PROFILES is None:
        _PROFILES = {(p.get("crop"), p.get("variety")): p for p in _load_prepared()}
    return _PROFILES.get((crop, variety))


_VARIETY_FACTS: Optional[dict] = None


def _variety_facts(crop: Optional[str], variety: Optional[str]) -> dict:
    """Sowing window and duration for a variety, read from the reference table.

    These are catalogue facts about the variety, not model output, and they
    are what a farmer - or the task scheduler - needs next: when to sow and
    how long the field will be occupied. Built once, looked up per variety.
    """
    global _VARIETY_FACTS
    if _VARIETY_FACTS is None:
        facts = {}
        for profile in _load_prepared():
            duration = profile.get("crop_duration_days")
            facts[(profile.get("crop"), profile.get("variety"))] = {
                "duration_days": int(duration) if duration == duration and duration else None,
                "sowing_window": profile.get("sowing_month") or None,
            }
        _VARIETY_FACTS = facts
    return _VARIETY_FACTS.get((crop, variety), {"duration_days": None, "sowing_window": None})


def cache_stats() -> dict:
    return _score_cache.stats()


def clear_cache() -> None:
    _score_cache.clear()
