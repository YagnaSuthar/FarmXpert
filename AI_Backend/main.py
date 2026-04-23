from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    debug=True,
    title="Welcome to the AI FarmXpert Swagger Docx",
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

@app.get("/")
def root():

    return {"message": "AI Agent System Running"}
