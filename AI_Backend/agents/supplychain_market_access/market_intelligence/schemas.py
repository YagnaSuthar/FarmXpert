# ── INPUT / OUTPUT SCHEMAS ─────────────────────────────────
# Decision-layer schemas for the Market Intelligence Agent.

from pydantic import BaseModel, Field
from typing import Optional, List


# ── Input ─────────────────────────────────────────────────
class MarketQueryInput(BaseModel):
    """What the agent receives as a request."""
    commodity: str = Field(..., example="Wheat")
    state: Optional[str] = Field(None, example="Gujarat")
    district: Optional[str] = Field(None, example="Ahmedabad")
    local_market: Optional[str] = Field(None, example="Ahmedabad")


# ── Internal DTO (mirrors Backend DB row, no ORM dep) ─────
class PriceRecord(BaseModel):
    """Lightweight DTO passed from Backend query service to AI logic."""
    commodity: str
    market: str
    state: Optional[str] = None
    district: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    modal_price: Optional[float] = None
    arrival_date: Optional[str] = None
    variety: Optional[str] = None
    grade: Optional[str] = None


# ── Sub-models ────────────────────────────────────────────
class RankedMarket(BaseModel):
    """A single market entry in the top-N ranking."""
    rank: int = Field(..., ge=1, example=1)
    market: str = Field(..., example="Surat")
    state: Optional[str] = Field(None, example="Gujarat")
    district: Optional[str] = Field(None, example="Surat")
    price: float = Field(..., ge=0, example=2450.0)
    profit: float = Field(..., example=2350.0)
    transport_cost: float = Field(..., ge=0, example=100.0)


# ── Output ────────────────────────────────────────────────
class MarketRecommendation(BaseModel):
    """Final decision output from the Market Intelligence Agent."""
    commodity: str = Field(..., example="Wheat")
    best_market: str = Field(..., example="Surat")
    best_price: float = Field(..., ge=0, example=2450.0)
    best_profit: float = Field(..., example=2350.0)
    recommended_action: str = Field(
        ...,
        example="SELL_NOW",
        description="SELL_NOW | SELL_IN_OTHER_MANDI | HOLD",
    )
    top_markets: List[RankedMarket] = Field(
        default_factory=list,
        description="Top 3 markets ranked by profit",
    )
    reason: str = Field(
        ...,
        example="Surat mandi offers ₹200 higher profit than Ahmedabad after transport cost",
    )
    confidence: float = Field(default=0.0, ge=0, le=1, example=0.82)


class MarketRecommendationResponse(BaseModel):
    """API response wrapper (mirrors MarketRecommendation for endpoint)."""
    commodity: str
    best_market: str
    best_price: float
    best_profit: float
    recommended_action: str
    top_markets: List[RankedMarket]
    reason: str
    confidence: float = Field(..., ge=0, le=1)

    class Config:
        from_attributes = True
