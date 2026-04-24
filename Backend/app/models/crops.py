from sqlalchemy import Column, Float, String, Integer
from app.core.config import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid


class Crop(Base):
    """
    Stores all the data related to the crop 

    - SQL Parameters 
    id
    name
    season VARCHAR(20)
    duration_days INT
    water_requirement VARCHAR(20)
    soil_ph_min FLOAT
    soil_ph_max FLOAT
    npk_requirements JSONB
    climate_zone VARCHAR(50)
    """

    __tablename__ = "crops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    season = Column(String(20), nullable=False)
    duration_days = Column(Integer, nullable=True)
    water_requirement = Column(String(20), nullable=True)
    soil_ph_min = Column(Float, nullable=True)
    soil_ph_max = Column(Float, nullable=True)
    npk_requirements = Column(JSONB, nullable=True)
    climate_zone = Column(String(50), nullable=True)