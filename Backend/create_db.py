import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from app.core.config import engine, Base
import app.models.blynk_token
import app.models.crop_history
import app.models.crop_recommendations
import app.models.crops
import app.models.farms
import app.models.soil_data

async def init_tables():
    from sqlalchemy import text
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(init_tables())
