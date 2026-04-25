from sqlalchemy import Integer,Float,String,Column
from sqlalchemy.dialects.postgresql import UUID
import uuid 
from app.core.config import Base
# from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship


class User(Base):

    """
    Table Defination of user table which owns the Farm 
    """
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4) 
    name = Column(String,nullable=False)


    farms = relationship("Farm", back_populates="user")