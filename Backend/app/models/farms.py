from sqlalchemy import Column,DateTime,ForeignKey,Float,String
from sqlalchemy.dialects.postgresql import UUID
import uuid 
from Backend.app.core.config import Base
# from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from Backend.app.models.market_intelligence import MarketRecommendation
# from geoalchemy2 import Geography

class Farm(Base):
    """
    Stores the data Which is related to the farm 
    """
    __tablename__ = "farms"
    id = Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    # user_id = Column(UUID(as_uuid=True),ForeignKey("users.id"))
    user_id = Column(UUID(as_uuid=True)) # Temporarily removed ForeignKey
    farm_size_acres = Column(Float)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, server_default=func.now())
    # location = Column(Geography(geometry_type='POINT', srid=4326))
    
    # user = relationship("User", back_populates="farms")
    # Farm
    soil_data = relationship("SoilData", back_populates="farm") 
    
    # market recommendations
    market_recommendations = relationship("MarketRecommendation",back_populates="farm")
    
    # mandi price data
    mandi_prices = relationship("MandiPriceData", back_populates="farm")