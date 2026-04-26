import httpx
from typing import List, Optional
from app.core.settings import settings
from app.schemas.mandi import MandiPrice
import logging

logger = logging.getLogger(__name__)


# 🔥 Utility function (cleaner outside class)
def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class MandiService:

    BASE_URL = "https://api.data.gov.in/resource/YOUR_RESOURCE_ID"

    def __init__(self):
        self.api_key = settings.MANDI_API_KEY
        self.timeout = 10.0
        self.max_retries = 3

    async def fetch_prices(
        self,
        commodity: str,
        state: Optional[str] = None,
        district: Optional[str] = None,
        market: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[MandiPrice]:

        params = {
            "api-key": self.api_key,
            "format": "json",
            "filters[commodity]": commodity,
            "limit": limit,
            "offset": offset,
        }

        if state:
            params["filters[state.keyword]"] = state
        if district:
            params["filters[district]"] = district
        if market:
            params["filters[market]"] = market

        # 🔁 Retry mechanism
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(self.BASE_URL, params=params)

                    response.raise_for_status()

                    data = response.json()
                    records = data.get("records", [])

                    if not records:
                        logger.warning(f"No mandi data found for {commodity}")

                    return self._normalize_records(records)

            except httpx.TimeoutException:
                logger.warning(f"Timeout attempt {attempt + 1}")

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e.response.status_code}")
                break  # no point retrying on bad request

            except Exception as e:
                logger.exception("Unexpected error in MandiService")

        logger.error("Failed to fetch mandi data after retries")
        return []

    # 🔥 Data Cleaning Layer
    def _normalize_records(self, records: List[dict]) -> List[MandiPrice]:
        cleaned_data = []

        for r in records:
            try:
                item = MandiPrice(
                    commodity=r.get("commodity"),
                    market=r.get("market"),
                    state=r.get("state"),
                    district=r.get("district"),
                    min_price=safe_float(r.get("min_price")),
                    max_price=safe_float(r.get("max_price")),
                    modal_price=safe_float(r.get("modal_price")),
                    arrival_date=r.get("arrival_date"),
                    variety=r.get("variety"),
                    grade=r.get("grade"),
                )
                cleaned_data.append(item)

            except (ValueError, TypeError):
                logger.warning(f"Skipping invalid record: {r}")
                continue

        return cleaned_data


# ✅ Singleton instance
mandi_service = MandiService()