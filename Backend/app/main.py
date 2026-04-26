from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.blynk_token import router as blynk_token_router
from app.api.soil_data import router as soil_data_router
from api.routers import farm_router
from app.api.market import router as market_router
from app.core.scheduler import init_scheduler, shutdown_scheduler

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────
    init_scheduler()
    yield
    # ── Shutdown ──────────────────────────────────
    shutdown_scheduler()


app = FastAPI(
    debug=True,
    title="Welcome to the FarmXpert Swagger Docx",
    version="1.0.0",
    description="Multi Agent Farm Advisory System",
    lifespan=lifespan,
)

origins = [""]

# Cors middlewares allowance
app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"]
)
app.include_router(blynk_token_router)
app.include_router(soil_data_router)
app.include_router(farm_router.router)
app.include_router(market_router)

@app.get("/")
def root():

    return {"message": " FarmXpert System Running"}
