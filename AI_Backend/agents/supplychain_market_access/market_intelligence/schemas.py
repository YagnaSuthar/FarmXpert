# ── MARKET INTELLIGENCE — SCHEMAS (insights-only, v3.0) ───────
# Pydantic models for the Market Intelligence Agent.
#
# What this agent emits:
#   • Commodity price snapshot (per-market + aggregated)
#   • Historical price trend (OLS over fetched window)
#   • Forecast prediction (LSTM / WMA / fallback)
#   • Confidence + data-quality signals
#
# What this agent does NOT emit (removed in v3.0):
#   • No SELL_NOW / SELL_IN_OTHER_MANDI / HOLD action
#   • No transport-cost estimation
#   • No profit ranking
#   • No storage / logistics suggestion
#
# The orchestrator turns these structured insights into farmer-facing
# prose; this layer never speaks language directly.

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────
# INPUT
# ─────────────────────────────────────────────────────────────

class MarketQueryInput(BaseModel):
    """Request payload received by the Market Intelligence Agent."""

    commodity: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Crop / commodity name (e.g. 'Wheat', 'Tomato').",
        examples=["Wheat"],
    )
    state: Optional[str] = Field(
        None, max_length=100,
        description="Optional regional filter — scopes Backend fetch to a state.",
        examples=["Gujarat"],
    )
    district: Optional[str] = Field(
        None, max_length=100,
        description="Optional — annotates per-market rows with locality.",
        examples=["Ahmedabad"],
    )
    forecast_horizon_days: int = Field(
        7, ge=1, le=30,
        description="Days ahead the forecast targets (informational; LSTM step is fixed).",
    )

    @field_validator("commodity", "state", "district", mode="before")
    @classmethod
    def _normalise_string(cls, v):
        if isinstance(v, str):
            cleaned = re.sub(r"[\x00-\x1f\x7f]", "", v.strip())
            return cleaned or None
        return v


# ─────────────────────────────────────────────────────────────
# INTERNAL DTO  (mirrors Backend DB row — no ORM dependency)
# ─────────────────────────────────────────────────────────────

class PriceRecord(BaseModel):
    """
    Lightweight DTO carrying one mandi row.
    Provided by the Backend API; never written back.
    """
    commodity: str
    market:    str
    state:     Optional[str] = None
    district:  Optional[str] = None

    min_price:   Optional[float] = Field(None, ge=0)
    max_price:   Optional[float] = Field(None, ge=0)
    modal_price: Optional[float] = Field(None, ge=0)

    arrival_date: Optional[str] = None
    variety:      Optional[str] = None
    grade:        Optional[str] = None

    @field_validator("modal_price", "min_price", "max_price", mode="before")
    @classmethod
    def _coerce_price(cls, v):
        if v is None: return None
        try:
            f = float(v)
            return round(f, 2) if f > 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("commodity", "market", "state", "district",
                     "variety", "grade", mode="before")
    @classmethod
    def _strip_str(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _enforce_price_ordering(self) -> "PriceRecord":
        if self.min_price and self.max_price and self.min_price > self.max_price:
            self.min_price, self.max_price = self.max_price, self.min_price
        return self


# ─────────────────────────────────────────────────────────────
# OUTPUT SUB-MODELS
# ─────────────────────────────────────────────────────────────

class MarketPrice(BaseModel):
    """One row in the per-market price table."""
    market:        str
    state:         Optional[str] = None
    district:      Optional[str] = None
    modal_price:   float = Field(..., ge=0)
    min_price:     Optional[float] = Field(None, ge=0)
    max_price:     Optional[float] = Field(None, ge=0)
    arrival_date:  Optional[str] = None
    variety:       Optional[str] = None
    grade:         Optional[str] = None


class PriceSummary(BaseModel):
    """Aggregated statistics across all sampled markets."""
    modal_price_avg:  float
    modal_price_min:  float
    modal_price_max:  float
    modal_price_median: float
    min_price_avg:    Optional[float] = None
    max_price_avg:    Optional[float] = None
    spread_pct:       float = Field(..., description="(max - min) / avg × 100")
    price_unit:       str = "INR/quintal"
    sampled_markets:  int = Field(..., ge=0)
    sampled_records:  int = Field(..., ge=0)


class PriceTrend(BaseModel):
    """OLS slope over the fetched window."""
    direction:         str = Field(..., description="increasing | decreasing | stable")
    slope_normalised:  float = Field(..., description="slope / mean — scale independent")
    window_records:    int = Field(..., ge=0)


class PriceForecast(BaseModel):
    """Next-step price prediction. No action — just an expected number."""
    predicted_price:      float = Field(..., ge=0, description="Forecasted modal price (INR/quintal).")
    predicted_trend:      str = Field(..., description="increasing | decreasing | stable")
    expected_change_pct:  float = Field(..., description="(pred - current) / current × 100")
    model_used:           str = Field(..., description="lstm | moving_average | fallback")
    horizon_days:         int = Field(..., ge=1, description="Days ahead the forecast targets")


class DataQuality(BaseModel):
    """Honest signal of how much to trust the snapshot."""
    records_used:               int = Field(..., ge=0)
    unique_markets:             int = Field(..., ge=0)
    coefficient_of_variation:   float = Field(..., ge=0, description="std / mean of modal prices")
    fresh_records_pct:          Optional[float] = Field(None, ge=0, le=100,
                                                         description="% of records within 7 days")


# ─────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────

class MarketInsights(BaseModel):
    """
    Final output of the Market Intelligence Agent — purely informational.

    No SELL / HOLD action, no transport calculations, no storage tips.
    The orchestrator composes farmer-facing prose from this JSON.
    """

    # Provenance
    agent_id:      str = "market_intelligence_agent"
    agent_version: str = "3.0.0"
    processed_at:  str

    # What was queried
    commodity:  str
    query_state: Optional[str] = None
    query_district: Optional[str] = None

    # Snapshot — per market + aggregated
    market_prices:  List[MarketPrice] = Field(default_factory=list)
    price_summary:  PriceSummary

    # Trend (historical) + forecast (predicted)
    price_trend:    PriceTrend
    forecast:       PriceForecast

    # Honest signals
    confidence:     float = Field(..., ge=0.0, le=1.0)
    data_quality:   DataQuality
    warnings:       List[str] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "market_intelligence_agent",
                "agent_version": "3.0.0",
                "processed_at": "2026-06-21T08:00:00Z",
                "commodity": "Wheat",
                "query_state": "Gujarat",
                "market_prices": [
                    {"market": "Surat", "state": "Gujarat", "district": "Surat",
                     "modal_price": 2450.0, "min_price": 2200.0,
                     "max_price": 2600.0, "arrival_date": "2026-06-20"},
                    {"market": "Ahmedabad", "state": "Gujarat",
                     "district": "Ahmedabad", "modal_price": 2200.0,
                     "min_price": 2050.0, "max_price": 2350.0,
                     "arrival_date": "2026-06-20"},
                ],
                "price_summary": {
                    "modal_price_avg": 2325.0,
                    "modal_price_min": 2200.0,
                    "modal_price_max": 2450.0,
                    "modal_price_median": 2325.0,
                    "min_price_avg": 2125.0,
                    "max_price_avg": 2475.0,
                    "spread_pct": 10.8,
                    "price_unit": "INR/quintal",
                    "sampled_markets": 2,
                    "sampled_records": 2,
                },
                "price_trend": {
                    "direction": "stable",
                    "slope_normalised": 0.01,
                    "window_records": 87,
                },
                "forecast": {
                    "predicted_price": 2510.0,
                    "predicted_trend": "increasing",
                    "expected_change_pct": 7.9,
                    "model_used": "lstm",
                    "horizon_days": 7,
                },
                "confidence": 0.78,
                "data_quality": {
                    "records_used": 87, "unique_markets": 12,
                    "coefficient_of_variation": 0.07,
                    "fresh_records_pct": 88.5,
                },
                "warnings": [],
            }
        }
    )


# Back-compat re-export — the router file still imports this name.
class MarketInsightsResponse(MarketInsights):
    """HTTP response wrapper; identical surface to MarketInsights."""
    class Config:
        from_attributes = True
