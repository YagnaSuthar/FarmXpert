from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.blynk_token import router as blynk_token_router
from app.api.soil_data import router as soil_data_router

app = FastAPI(
    debug=True,
    title="Welcome to the FarmXpert Swagger Docx",
    version="1.0.0",
    description="Multi Agent Farm Advisory System"
    
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

@app.get("/")
def root():

    return {"message": " FarmXpert System Running"}
