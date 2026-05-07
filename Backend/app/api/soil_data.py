from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_db
from app.services.blynk_soil_extraction import BlynkSoilService
from uuid import UUID
router = APIRouter(prefix="/soil", tags=["Extracts Soil Data from provided farm id "])



@router.get("/extract/{farm_id}")
async def extract_soil_data(farm_id: UUID, db: AsyncSession = Depends(get_db)):
    service = BlynkSoilService(db)
    return await service.run(farm_id)   