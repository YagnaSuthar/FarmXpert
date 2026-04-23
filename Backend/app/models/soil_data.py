from sqlalchemy import Column, Float, String, Integer, TIMESTAMP, ForeignKey,DateTime
from core.config import Base
from sqlalchemy import func

class SoilData(Base):
    """
    Stores soil health and nutrient data for a farm

    - SQL Parameters
    id SERIAL PRIMARY KEY
    farm_id VARCHAR(50) REFERENCES farms(id)
    ph FLOAT
    nitrogen FLOAT
    phosphorus FLOAT
    potassium FLOAT
    organic_matter FLOAT
    texture VARCHAR(50)
    recorded_at TIMESTAMP DEFAULT NOW()
    """

    __tablename__ = "soil_data"

    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(String(50), ForeignKey("farms.id"), nullable=True)

    ph = Column(Float, nullable=True)
    nitrogen = Column(Float, nullable=True)
    phosphorus = Column(Float, nullable=True)
    potassium = Column(Float, nullable=True)
    organic_matter = Column(Float, nullable=True)

    texture = Column(String(50), nullable=True)

    recorded_at = Column(
            DateTime,
            server_default=func.now(),
            nullable=False
        )