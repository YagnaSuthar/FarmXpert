# ── MARKET INTELLIGENCE — INSIGHTS SERVICE (v3.0) ─────────
# Pipeline: fetch → aggregate → trend → forecast → confidence → return.
# v3.0 dropped: action / reason / transport / profit ranking.

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from AI_Backend.agents.supplychain_market_access.market_intelligence import model_loader
from AI_Backend.agents.supplychain_market_access.market_intelligence.config import (
    AGENT_ID,
    AGENT_VERSION,
    BACKEND_BASE_URL,
    DEFAULT_FETCH_LIMIT,
    FORECAST_DECREASE_THRESHOLD,
    FORECAST_INCREASE_THRESHOLD,
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF,
    HTTP_TIMEOUT_SECONDS,
    LSTM_MODEL_PATH,
    LSTM_SCALER_PATH,
    LSTM_SEQUENCE_LENGTH,
    MANDI_PRICES_ENDPOINT,
    MIN_RECORDS_FOR_INSIGHTS,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.logic import (
    build_market_prices,
    build_price_summary,
    calculate_confidence,
    calculate_trend,
    coefficient_of_variation,
    fresh_records_pct,
)
from AI_Backend.agents.supplychain_market_access.market_intelligence.schemas import (
    DataQuality,
    MarketInsights,
    PriceForecast,
    PriceRecord,
    PriceTrend,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# MODEL LIFECYCLE
# ═════════════════════════════════════════════════════════════

_model_init_attempted: bool = False


def _ensure_model_loaded() -> None:
    global _model_init_attempted
    if not _model_init_attempted:
        _model_init_attempted = True
        loaded = model_loader.load_model(LSTM_MODEL_PATH, LSTM_SCALER_PATH)
        logger.info("ML model %s.",
                    "ready" if loaded else "unavailable — WMA fallback active")


# ═════════════════════════════════════════════════════════════
# DATA FETCHING (Backend API with retry)
# ═════════════════════════════════════════════════════════════

async def _http_get_with_retry(
    url: str, params: dict,
    max_retries: int = HTTP_MAX_RETRIES,
    backoff: float = HTTP_RETRY_BACKOFF,
) -> Optional[list]:
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) and isinstance(data, dict):
                    data = (data.get("items") or data.get("data") or data.get("results")
                            or data.get("records") or [])
                return data
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404, 422):
                return None
            logger.warning("HTTP %d on %s (attempt %d/%d)",
                           exc.response.status_code, url, attempt, max_retries)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning("Network error %s on %s (attempt %d/%d)",
                           exc, url, attempt, max_retries)
        except Exception:
            logger.exception("Unexpected error fetching %s", url)
        if attempt < max_retries:
            await asyncio.sleep(backoff * attempt)
    return None


async def fetch_prices_from_backend(
    commodity: str, state: Optional[str] = None,
    limit: int = DEFAULT_FETCH_LIMIT,
) -> List[PriceRecord]:
    url = f"{BACKEND_BASE_URL}{MANDI_PRICES_ENDPOINT}"
    params: dict = {"commodity": commodity, "limit": limit}
    if state:
        params["state"] = state

    raw = await _http_get_with_retry(url, params)
    if raw is None:
        return []

    records: List[PriceRecord] = []
    for item in raw:
        try:
            records.append(PriceRecord(**item))
        except Exception:
            continue
    logger.info("Fetched %d valid PriceRecords for '%s'", len(records), commodity)
    return records


# ═════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═════════════════════════════════════════════════════════════

async def generate_insights(
    commodity: str,
    state: Optional[str] = None,
    district: Optional[str] = None,
    forecast_horizon_days: int = 7,
) -> Optional[MarketInsights]:
    """
    Build a MarketInsights object — purely informational.

    Steps:
        1.  Ensure LSTM model is loaded (lazy, once per process).
        2.  Fetch latest mandi prices.
        3.  Build per-market snapshot + aggregated summary.
        4.  Historical trend (OLS on modal_price).
        5.  Forecast next price (LSTM / WMA / fallback).
        6.  Confidence + data-quality.
        7.  Assemble MarketInsights.

    Returns None if there isn't a single valid price record.
    """
    _ensure_model_loaded()

    records = await fetch_prices_from_backend(
        commodity=commodity, state=state, limit=DEFAULT_FETCH_LIMIT,
    )

    if len(records) < MIN_RECORDS_FOR_INSIGHTS:
        logger.warning("Insufficient price data for '%s': %d records.",
                       commodity, len(records))
        return None

    # Aggregated snapshot
    market_prices = build_market_prices(records)
    price_summary = build_price_summary(records)
    if price_summary is None:
        return None

    # Historical trend
    trend = calculate_trend(records)
    historical_direction = trend["direction"]

    # Forecast
    current_modal = (
        records[-1].modal_price
        if records and records[-1].modal_price else None
    )
    forecast_raw = model_loader.predict_price_trend(
        records=records,
        sequence_length=LSTM_SEQUENCE_LENGTH,
        current_price=current_modal,
        increase_threshold=FORECAST_INCREASE_THRESHOLD,
        decrease_threshold=FORECAST_DECREASE_THRESHOLD,
    )
    predicted_price: float = float(forecast_raw.get("predicted_price") or 0.0)
    predicted_trend: str   = forecast_raw.get("predicted_trend") or "stable"
    model_used:      str   = forecast_raw.get("model_used") or "fallback"

    expected_change = 0.0
    if current_modal and current_modal > 0:
        expected_change = (predicted_price - current_modal) / current_modal * 100.0

    # Confidence + data quality
    confidence = calculate_confidence(
        records, historical_trend=historical_direction,
        predicted_trend=predicted_trend,
    )
    data_quality = DataQuality(
        records_used=len(records),
        unique_markets=price_summary.sampled_markets,
        coefficient_of_variation=coefficient_of_variation(records),
        fresh_records_pct=fresh_records_pct(records),
    )

    insights = MarketInsights(
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        processed_at=datetime.now(timezone.utc).isoformat(),
        commodity=commodity,
        query_state=state,
        query_district=district,
        market_prices=market_prices,
        price_summary=price_summary,
        price_trend=PriceTrend(
            direction=historical_direction,
            slope_normalised=float(trend["slope_normalised"]),
            window_records=int(trend["window_records"]),
        ),
        forecast=PriceForecast(
            predicted_price=round(predicted_price, 2),
            predicted_trend=predicted_trend,
            expected_change_pct=round(expected_change, 2),
            model_used=model_used,
            horizon_days=forecast_horizon_days,
        ),
        confidence=confidence,
        data_quality=data_quality,
        warnings=[],
    )

    logger.info(
        "Insights ready | commodity=%s | markets=%d | hist=%s | pred=%s (%.1f%%) | "
        "model=%s | confidence=%.0f%%",
        commodity, price_summary.sampled_markets, historical_direction,
        predicted_trend, expected_change, model_used, confidence * 100,
    )
    return insights
