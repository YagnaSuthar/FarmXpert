import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from Backend.app.core.config import Base


# 🔹 1. Raw + Historical Mandi Data
class MandiPriceData(Base):
    """
    Stores historical mandi price data (used for ML + analytics)
    """

    __tablename__ = "mandi_price_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Optional relation to farm (for personalization later)
    farm_id = Column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)

    # Core mandi data
    commodity = Column(String(100), nullable=False, index=True)
    market = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)

    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    modal_price = Column(Float, nullable=True)

    # Extra attributes
    arrival_date = Column(String(50), nullable=True)
    variety = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)

    # Metadata
    recorded_at = Column(DateTime, server_default=func.now(), index=True)
    source = Column(String(50), default="AGMARKNET")

    # Relationships
    farm = relationship("Farm", back_populates="mandi_prices")


# 🔹 2. Market Recommendation (Agent Output)
class MarketRecommendation(Base):
    """
    Stores intelligent selling recommendations for crops
    """

    __tablename__ = "market_recommendations"

    id = Column(Integer, primary_key=True, index=True)

    farm_id = Column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)

    # Input context
    commodity = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)

    # Best market decision
    best_market = Column(String(100), nullable=True)
    best_price = Column(Float, nullable=True)

    # Forecast info
    forecast_trend = Column(String(20), nullable=True)  # increasing / decreasing
    predicted_price = Column(Float, nullable=True)

    # Final decision
    recommendation = Column(String(20), nullable=False)  # SELL / HOLD / WAIT
    confidence = Column(Float, nullable=True)

    # Explainability (very important for AI agent)
    reasoning = Column(JSONB, nullable=True)

    # Metadata
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    farm = relationship("Farm", back_populates="market_recommendations")