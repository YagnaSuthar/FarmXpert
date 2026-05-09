# ── MARKET INTELLIGENCE — SCHEMAS ─────────────────────────
# Pydantic models used across the entire agent.
# AI_Backend never imports ORM models — uses these DTOs only.

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
        None,
        max_length=100,
        description="Farmer's state — improves transport cost accuracy.",
        examples=["Gujarat"],
    )
    district: Optional[str] = Field(
        None,
        max_length=100,
        description="Farmer's district — used for same-district transport tier.",
        examples=["Ahmedabad"],
    )
    local_market: Optional[str] = Field(
        None,
        max_length=100,
        description="Farmer's nearest mandi — used to detect SELL_IN_OTHER_MANDI.",
        examples=["Ahmedabad"],
    )

    @field_validator("commodity", "state", "district", "local_market", mode="before")
    @classmethod
    def normalise_string(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = v.strip()
            # Remove control characters
            cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
            return cleaned or None
        return v


# ─────────────────────────────────────────────────────────────
# INTERNAL DTO  (mirrors Backend DB row — no ORM dependency)
# ─────────────────────────────────────────────────────────────

class PriceRecord(BaseModel):
    """
    Lightweight DTO passed from the Backend API to AI decision logic.
    One row ≈ one mandi report for a single commodity on a given date.
    """

    commodity: str
    market: str
    state: Optional[str] = None
    district: Optional[str] = None

    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    modal_price: Optional[float] = Field(None, ge=0)

    arrival_date: Optional[str] = None   # ISO date string "YYYY-MM-DD"
    variety: Optional[str] = None
    grade: Optional[str] = None

    @field_validator("modal_price", "min_price", "max_price", mode="before")
    @classmethod
    def coerce_price(cls, v: object) -> Optional[float]:
        """Accept numeric strings, reject zero/negative/null."""
        if v is None:
            return None
        try:
            f = float(v)
            return round(f, 2) if f > 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("commodity", "market", "state", "district",
                     "variety", "grade", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def enforce_price_ordering(self) -> "PriceRecord":
        """Ensure min_price ≤ modal_price ≤ max_price when all present."""
        mn, md, mx = self.min_price, self.modal_price, self.max_price
        if mn and mx and mn > mx:
            # swap silently — data entry error
            self.min_price, self.max_price = mx, mn
        return self


# ─────────────────────────────────────────────────────────────
# SUB-MODELS
# ─────────────────────────────────────────────────────────────

class RankedMarket(BaseModel):
    """A single entry in the top-N market ranking."""

    rank: int = Field(..., ge=1, description="1 = best profit.", examples=[1])
    market: str = Field(..., examples=["Surat"])
    state: Optional[str] = Field(None, examples=["Gujarat"])
    district: Optional[str] = Field(None, examples=["Surat"])
    price: float = Field(..., ge=0, description="Modal price (₹/quintal).", examples=[2450.0])
    profit: float = Field(..., description="Net profit after transport (₹/quintal).", examples=[2300.0])
    transport_cost: float = Field(..., ge=0, description="Estimated transport cost (₹/quintal).", examples=[150.0])


class PriceTrendPrediction(BaseModel):
    """Output produced by the LSTM / fallback forecaster."""

    predicted_price: float = Field(..., ge=0, description="Forecasted modal price (₹/quintal).")
    predicted_trend: str = Field(
        ...,
        description="Direction: 'increasing' | 'decreasing' | 'stable'.",
    )
    model_used: str = Field(
        default="fallback",
        description="'lstm' | 'moving_average' | 'fallback'.",
    )


# ─────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────

class MarketRecommendation(BaseModel):
    """
    Final decision produced by the Market Intelligence Agent.
    Consumed by the router and returned to the client.
    """

    # Core identification
    commodity: str = Field(..., examples=["Wheat"])

    # Best market result
    best_market: str = Field(..., examples=["Surat"])
    best_price: float = Field(..., ge=0, description="Modal price at best market (₹/quintal).", examples=[2450.0])
    best_profit: float = Field(..., description="Net profit at best market after transport (₹/quintal).", examples=[2300.0])
    transport_cost: float = Field(..., ge=0, description="Transport cost to best market (₹/quintal).", examples=[150.0])

    # Decision
    recommended_action: str = Field(
        ...,
        description="SELL_NOW | SELL_IN_OTHER_MANDI | HOLD",
        examples=["SELL_IN_OTHER_MANDI"],
    )

    # Supporting data
    top_markets: List[RankedMarket] = Field(
        default_factory=list,
        description="Top 3 markets ranked by net profit.",
    )

    # Explanation
    reason: str = Field(
        ...,
        examples=["Surat mandi offers ₹200 higher profit than Ahmedabad after ₹150 transport cost."],
    )

    # Quality signal
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Multi-factor confidence score (0 = no data, 1 = very reliable).",
        examples=[0.82],
    )

    # Trend signals
    trend: Optional[str] = Field(
        None,
        description="Historical price trend (linear regression): 'increasing' | 'decreasing' | 'stable'.",
        examples=["stable"],
    )
    predicted_price: Optional[float] = Field(
        None,
        ge=0,
        description="LSTM / WMA forecasted price for next period (₹/quintal).",
        examples=[2500.0],
    )
    predicted_trend: Optional[str] = Field(
        None,
        description="Forecast direction: 'increasing' | 'decreasing' | 'stable'.",
        examples=["increasing"],
    )

    # Diagnostics
    data_points_used: int = Field(
        default=0,
        ge=0,
        description="Number of mandi price records used in this recommendation.",
        examples=[87],
    )


# ── API response wrapper (used by FastAPI router) ──────────

class MarketRecommendationResponse(MarketRecommendation):
    """
    HTTP response model — inherits all fields from MarketRecommendation.
    Kept separate so the router can evolve API shape independently.
    """

    class Config:
        from_attributes = True