from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_db
from app.schemas.blynk_token import BlynkTokenCreate, BlynkTokenResponse
from app.services.blynk_token_store import BlynkTokenService

router = APIRouter(prefix="/blynk", tags=["Blynk Token store with specific Farm id "])

@router.post("/blynk/token", response_model=BlynkTokenResponse)
async def create_token(
    data: BlynkTokenCreate,
    db: AsyncSession = Depends(get_db)
):
    service = BlynkTokenService(db)
    return await service.create_token(data.farm_id, data.token)