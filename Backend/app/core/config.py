# config.py
# Connects Database (Postgres to the backend service)
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker,declarative_base
import os 

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("Database can Not Connected")

engine = create_async_engine(DATABASE_URL,echo=True)

AsyncSessionLocal= sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db 