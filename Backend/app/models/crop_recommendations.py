from sqlalchemy import Column, Integer, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
import uuid

from core.config import Base


class CropRecommendation(Base):
    """
    Stores ML-based crop recommendations for a farm
    """

    __tablename__ = "crop_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(String(50), nullable=True)  # consider UUID if farms.id is UUID
    input_data = Column(JSONB, nullable=True)
    recommendations = Column(JSONB, nullable=True)
    model_version = Column(String(20), nullable=True)

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False
    )