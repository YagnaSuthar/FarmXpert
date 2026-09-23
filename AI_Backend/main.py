import sys
import os
from pathlib import Path

# Make both import styles resolve, so the app starts from the repository root
# (`uvicorn AI_Backend.main:app`) or from this folder (`uvicorn main:app`):
# the root for `AI_Backend.*`, this folder for `routers.*`.
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routers import weather_watcher , irrigation_planner
from routers import crop_prediction
from routers import orchestrator
from routers import task_scheduler

# --- Routers ---
from routers.soil_health import router as soil_health_router
from routers.market_intelligence import router as market_intelligence_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # The crop recommender loads a 3.4 MB bundle plus the variety table; doing
    # it at startup keeps the first real request off that cost. Warmup never
    # raises - a failure leaves /crop-prediction/health reporting not-loaded.
    await asyncio.to_thread(crop_prediction.crop_prediction_agent.warmup)
    yield
    # Weather calls and the language model each share one pooled HTTP client;
    # close both cleanly so a reload does not leak sockets.
    from AI_Backend.agents.crop_planning_growth.weather_watcher.service import (
        aclose_http_clients)
    from AI_Backend.orchestration.llm import aclose_clients as aclose_llm_clients
    await aclose_http_clients()
    await aclose_llm_clients()
    from AI_Backend.core.database import dispose as dispose_database
    await dispose_database()


app = FastAPI(
    lifespan=lifespan,
    debug=os.getenv("AI_DEBUG", "").lower() in ("1", "true"),
    title="Welcome to the AI FarmXpert Swagger Docx",
    version="1.0.0",
    description="Multi Agent Farm Advisory System"
    
)

origins = ["*"]

# Cors middlewares allowance
app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"]
)

# Only the Node backend calls this service. When INTERNAL_API_KEY is set,
# every route except liveness and the docs requires it in x-internal-key.
_INTERNAL_KEY = os.getenv("INTERNAL_API_KEY", "")
_OPEN_PATHS = {"/", "/docs", "/redoc", "/openapi.json", "/orchestrator/health"}


@app.middleware("http")
async def require_internal_key(request: Request, call_next):
    if _INTERNAL_KEY and request.method != "OPTIONS" and request.url.path not in _OPEN_PATHS:
        supplied = request.headers.get("x-internal-key", "")
        if not hmac.compare_digest(supplied.encode(), _INTERNAL_KEY.encode()):
            return JSONResponse(status_code=401,
                                content={"detail": "A valid internal key is required."})
    return await call_next(request)


# --- Register Routers ---
app.include_router(soil_health_router, prefix="/api/soil-health", tags=["Soil Health"])

@app.get("/")
def root():

    return {"message": "AI Agent System Running"}


#  All Routers 
app.include_router(weather_watcher.router)
app.include_router(crop_prediction.router)
app.include_router(irrigation_planner.router)
app.include_router(orchestrator.router)
app.include_router(task_scheduler.router)
app.include_router(market_intelligence_router)
