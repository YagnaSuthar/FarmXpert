# ── MARKET INTELLIGENCE — ORCHESTRATION SERVICE ───────────
# Coordinates: data fetching → trend analysis → ML forecast → decision logic.
# AI_Backend NEVER touches the DB directly — all data via Backend API.
#
# Architecture contract:
#   • HTTP calls live here (and only here)
#   • Logic functions are called here (never in agent.py)
#   • model_loader is called here (never in logic.py)
#   • No business logic beyond orchestration order lives in this file

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import httpx

from agents.supplychain_market_access.market_intelligence import model_loader
from agents.supplychain_market_access.market_intelligence.config import (
    BACKEND_BASE_URL,
    DEFAULT_FETCH_LIMIT,
    FORECAST_DECREASE_THRESHOLD,
    FORECAST_INCREASE_THRESHOLD,
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF,
    HTTP_TIMEOUT_SECONDS,
    LSTM_SCALER_PATH,
    LSTM_MODEL_PATH,
    LSTM_SEQUENCE_LENGTH,
    MANDI_PRICES_ENDPOINT,
    MIN_RECORDS_FOR_RECOMMENDATION,
)
from agents.supplychain_market_access.market_intelligence.logic import (
    calculate_confidence,
    calculate_profit,
    calculate_trend,
    determine_action,
    estimate_transport_cost,
    find_best_market,
    generate_reason,
    rank_markets,
)
from agents.supplychain_market_access.market_intelligence.schemas import (
    MarketRecommendation,
    PriceRecord,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# MODEL LIFECYCLE  (called once per process startup)
# ═════════════════════════════════════════════════════════════

_model_init_attempted: bool = False


def _ensure_model_loaded() -> None:
    """
    Initialise the ML model exactly once.

    Called lazily on first request so the service starts even if the model
    file is unavailable — the agent degrades gracefully to WMA forecasting.
    """
    global _model_init_attempted
    if not _model_init_attempted:
        _model_init_attempted = True
        loaded = model_loader.load_model(LSTM_MODEL_PATH, LSTM_SCALER_PATH)
        if loaded:
            logger.info("ML model initialised successfully.")
        else:
            logger.warning(
                "ML model unavailable — forecasting will use weighted moving average."
            )


# ═════════════════════════════════════════════════════════════
# DATA FETCHING  (Backend API with retry)
# ═════════════════════════════════════════════════════════════

async def _http_get_with_retry(
    url: str,
    params: dict,
    max_retries: int = HTTP_MAX_RETRIES,
    backoff: float = HTTP_RETRY_BACKOFF,
) -> Optional[list]:
    """
    GET request with exponential-backoff retry.

    Retries on: connection errors, timeouts.
    Does NOT retry on: 4xx client errors (bad request, not found).

    Returns:
        Parsed JSON list, or None on final failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, list):
                    # Backend may wrap in {"data": [...]} — handle both shapes
                    if isinstance(data, dict):
                        data = (
                            data.get("data")
                            or data.get("results")
                            or data.get("records")
                            or []
                        )

                return data  # type: ignore[return-value]

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error(
                "Backend returned HTTP %d for %s (attempt %d/%d).",
                status, url, attempt, max_retries,
            )
            if status in (400, 404, 422):
                # Client error — retrying won't help
                return None

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning(
                "Request to %s failed on attempt %d/%d: %s",
                url, attempt, max_retries, exc,
            )

        except Exception:
            logger.exception(
                "Unexpected error fetching %s on attempt %d/%d.", url, attempt
            )

        if attempt < max_retries:
            sleep_secs = backoff * attempt
            logger.debug("Retrying in %.1fs …", sleep_secs)
            await asyncio.sleep(sleep_secs)

    logger.error("All %d fetch attempts failed for %s.", max_retries, url)
    return None


async def fetch_prices_from_backend(
    commodity: str,
    state: Optional[str] = None,
    limit: int = DEFAULT_FETCH_LIMIT,
) -> List[PriceRecord]:
    """
    Retrieve the latest mandi price records for a commodity from the Backend.

    Args:
        commodity: Crop name (e.g. "Wheat").
        state:     Optional state filter — narrows results to a region.
        limit:     Maximum number of records to request.

    Returns:
        List of validated PriceRecord DTOs.
        Empty list on any error (service handles gracefully downstream).
    """
    url    = f"{BACKEND_BASE_URL}{MANDI_PRICES_ENDPOINT}"
    params: dict = {"commodity": commodity, "limit": limit}
    if state:
        params["state"] = state

    logger.info(
        "Fetching prices: commodity='%s' | state=%s | limit=%d | url=%s",
        commodity, state or "ALL", limit, url,
    )

    raw = await _http_get_with_retry(url, params)

    if raw is None:
        logger.error("Price fetch failed for commodity '%s'.", commodity)
        return []

    records: List[PriceRecord] = []
    parse_errors = 0

    for item in raw:
        try:
            records.append(PriceRecord(**item))
        except Exception:
            parse_errors += 1
            logger.debug("Skipped malformed record: %s", item)

    if parse_errors:
        logger.warning(
            "Skipped %d malformed records for '%s' (%d valid).",
            parse_errors, commodity, len(records),
        )

    logger.info(
        "Fetched %d valid PriceRecords for '%s'.",
        len(records), commodity,
    )
    return records


# ═════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═════════════════════════════════════════════════════════════

async def generate_recommendation(
    commodity: str,
    local_market: Optional[str] = None,
    local_district: Optional[str] = None,
    local_state: Optional[str] = None,
) -> Optional[MarketRecommendation]:
    """
    End-to-end Market Intelligence pipeline.

    ┌────────────────────────────────────────────────────────┐
    │ Step │ What                                            │
    ├────────────────────────────────────────────────────────┤
    │  1   │ Ensure LSTM model is loaded (once per process)  │
    │  2   │ Fetch mandi prices from Backend API             │
    │  3   │ Validate data sufficiency                       │
    │  4   │ Calculate historical price trend (OLS slope)    │
    │  5   │ Run LSTM / WMA price forecast                   │
    │  6   │ Find best market by net profit                  │
    │  7   │ Rank top 3 markets                              │
    │  8   │ Calculate multi-factor confidence score         │
    │  9   │ Determine action (multi-signal decision engine) │
    │ 10   │ Generate farmer-friendly reason string          │
    │ 11   │ Assemble and return MarketRecommendation        │
    └────────────────────────────────────────────────────────┘

    Args:
        commodity:      Crop name (required).
        local_market:   Farmer's nearest mandi (optional).
        local_district: Farmer's district (optional — for transport tiers).
        local_state:    Farmer's state (optional — for transport tiers).

    Returns:
        MarketRecommendation DTO, or None if data is insufficient.
    """

    # ── Step 1: Model init ───────────────────────────────────
    _ensure_model_loaded()

    # ── Step 2: Fetch data ───────────────────────────────────
    records = await fetch_prices_from_backend(
        commodity=commodity,
        state=local_state,   # scope to farmer's state for faster response
        limit=DEFAULT_FETCH_LIMIT,
    )

    # ── Step 3: Data sufficiency check ──────────────────────
    if len(records) < MIN_RECORDS_FOR_RECOMMENDATION:
        logger.warning(
            "Insufficient data for '%s': %d records (minimum %d).",
            commodity, len(records), MIN_RECORDS_FOR_RECOMMENDATION,
        )
        return None

    # ── Step 4: Historical trend ─────────────────────────────
    historical_trend = calculate_trend(records)
    logger.info("Historical trend for '%s': %s", commodity, historical_trend)

    # ── Step 5: ML price forecast ────────────────────────────
    forecast = model_loader.predict_price_trend(
        records=records,
        sequence_length=LSTM_SEQUENCE_LENGTH,
        current_price=records[-1].modal_price if records else None,
        increase_threshold=FORECAST_INCREASE_THRESHOLD,
        decrease_threshold=FORECAST_DECREASE_THRESHOLD,
    )
    predicted_price: Optional[float] = forecast.get("predicted_price")
    predicted_trend: Optional[str]   = forecast.get("predicted_trend")
    model_used: str                  = forecast.get("model_used", "fallback")

    logger.info(
        "Forecast [%s] for '%s': ₹%.2f | trend=%s",
        model_used, commodity,
        predicted_price or 0.0,
        predicted_trend or "N/A",
    )

    # ── Step 6: Find best market ─────────────────────────────
    best = find_best_market(records, local_market, local_district, local_state)
    if best is None:
        logger.warning("No valid market found for '%s'.", commodity)
        return None

    # ── Step 7: Rank markets ─────────────────────────────────
    ranked = rank_markets(records, local_market, local_district, local_state, top_n=3)

    # ── Step 8: Confidence ───────────────────────────────────
    confidence = calculate_confidence(
        records, ranked,
        historical_trend=historical_trend,
        predicted_trend=predicted_trend,
    )

    # ── Step 9: Action ───────────────────────────────────────
    action = determine_action(
        best=best,
        ranked=ranked,
        local_market=local_market,
        local_district=local_district,
        local_state=local_state,
        historical_trend=historical_trend,
        predicted_trend=predicted_trend,
        confidence=confidence,
    )

    # ── Step 10: Reason ──────────────────────────────────────
    reason = generate_reason(
        best=best,
        ranked=ranked,
        action=action,
        local_market=local_market,
        local_district=local_district,
        local_state=local_state,
        historical_trend=historical_trend,
        predicted_trend=predicted_trend,
        predicted_price=predicted_price,
    )

    # ── Step 11: Assemble output ─────────────────────────────
    best_profit   = calculate_profit(best, local_market, local_district, local_state)
    transport_cost = estimate_transport_cost(best, local_market, local_district, local_state)

    recommendation = MarketRecommendation(
        commodity=best.commodity,
        best_market=best.market,
        best_price=best.modal_price,         # type: ignore[arg-type]
        best_profit=best_profit,
        transport_cost=transport_cost,
        recommended_action=action,
        top_markets=ranked,
        reason=reason,
        confidence=confidence,
        trend=historical_trend,
        predicted_price=predicted_price,
        predicted_trend=predicted_trend,
        data_points_used=len(records),
    )

    logger.info(
        "✅ [%s] action=%s | market='%s' | price=₹%.2f | profit=₹%.2f | "
        "transport=₹%.2f | confidence=%.0f%% | hist=%s | forecast=%s [%s] | records=%d",
        commodity,
        action,
        best.market,
        best.modal_price,
        best_profit,
        transport_cost,
        confidence * 100,
        historical_trend,
        predicted_trend or "N/A",
        model_used,
        len(records),
    )

    return recommendation