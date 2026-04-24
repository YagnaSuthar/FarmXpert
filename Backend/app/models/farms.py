from sqlalchemy import Column,DateTime,ForeignKey,Float,String
from sqlalchemy.dialects.postgresql import UUID
import uuid 
from app.core.config import Base
# from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geography

class Farm(Base):
    """
    Stores the data Which is related to the farm 
    """
    __tablename__ = "farms"
    id = Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    # user_id = Column(UUID(as_uuid=True),ForeignKey("users.id"))
    user_id = Column(UUID(as_uuid=True)) # Temporarily removed ForeignKey
    farm_size_acres = Column(Float)
    created_at = Column(DateTime, server_default=func.now())
    location = Column(Geography(geometry_type='POINT', srid=4326))
    
    # user = relationship("User", back_populates="farms")