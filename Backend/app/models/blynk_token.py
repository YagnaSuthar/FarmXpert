from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, Boolean
from datetime import datetime
from app.core.config import Base
from sqlalchemy.dialects.postgresql import UUID

class BlynkToken(Base):
    """
    Stores Blynk authentication tokens for farms
    """

    __tablename__ = "blynk_tokens"

    id = Column(Integer, primary_key=True, index=True)



    # Farm relation
    farm_id = Column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=False)

    # Blynk Token
    token = Column(String(100), nullable=False, unique=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)