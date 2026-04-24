from sqlalchemy import select, update
from app.models.blynk_token import BlynkToken

class BlynkTokenService:

    def __init__(self, db):
        self.db = db

    async def create_token(self, farm_id: str, token: str):

        # Check duplicate
        result = await self.db.execute(select(BlynkToken).where(BlynkToken.token == token))
        existing = result.scalars().first()

        if existing:
            raise Exception("Token already exists")

        # Deactivate old tokens for same farm
        await self.db.execute(
            update(BlynkToken).where(BlynkToken.farm_id == farm_id).values(is_active=False)
        )

        # Create new token
        new_token = BlynkToken(
            farm_id=farm_id,
            token=token,
            is_active=True
        )

        self.db.add(new_token)
        await self.db.commit()
        await self.db.refresh(new_token)

        return new_token