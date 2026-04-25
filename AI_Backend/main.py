from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routers import weather_watcher

# --- Routers ---
from routers.soil_health import router as soil_health_router

app = FastAPI(
    debug=True,
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

# --- Register Routers ---
app.include_router(soil_health_router, prefix="/api/soil-health", tags=["Soil Health"])

@app.get("/")
def root():

    return {"message": "AI Agent System Running"}


#  All Routers 
app.include_router(weather_watcher.router)