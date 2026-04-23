from sqlalchemy import Column, Float, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from core.config import Base


class CropHistory(Base):
    """
    Stores historical crop performance data for farms
    """

    __tablename__ = "crop_history"

    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(String(50), ForeignKey("farms.id"), nullable=True)
    crop_id = Column(Integer, ForeignKey("crops.id"), nullable=True)
    season = Column(String(20), nullable=True)
    yield_per_acre = Column(Float, nullable=True)
    profit = Column(Float, nullable=True)

    year = Column(Integer, nullable=True)