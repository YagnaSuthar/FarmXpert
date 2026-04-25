import asyncio 
from app.core.config import engine , Base 
from app.models import farms,users

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(init_db())