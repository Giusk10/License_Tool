from fastapi import FastAPI
from app.api.analysis import router as analysis_router

app = FastAPI(
    title="License Compatibility Checker + Ollama",
    version="1.0.0",
)

# API principali
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])

# per test rapido
@app.get("/")
def root():
    return {"message": "License Checker Backend is running"}
