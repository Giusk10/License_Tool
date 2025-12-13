from fastapi import FastAPI
from app.controllers.analysis import router as analysis_router

app = FastAPI(
    title="License Compatibility Checker + Ollama",
    version="1.0.0",
)

# API principali
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])

# CORS Configuration
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# per test rapido
@app.get("/")
def root():
    return {"message": "License Checker Backend is running"}
