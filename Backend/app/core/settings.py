import os
from dotenv import load_dotenv

load_dotenv()


class _Settings:
    """Centralized settings loaded from environment variables."""

    @property
    def DATABASE_URL(self) -> str:
        return os.getenv("DATABASE_URL", "")

    @property
    def MANDI_API_KEY(self) -> str:
        return os.getenv("DATA_GOV_API_KEY", "")

    @property
    def LOG_LEVEL(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def MANDI_FETCH_INTERVAL_MINUTES(self) -> int:
        return int(os.getenv("MANDI_FETCH_INTERVAL_MINUTES", "60"))

    @property
    def MANDI_COMMODITIES(self) -> list[str]:
        raw = os.getenv("MANDI_COMMODITIES", "Wheat,Rice,Tomato,Onion,Potato")
        return [c.strip() for c in raw.split(",") if c.strip()]


settings = _Settings()
