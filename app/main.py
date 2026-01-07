"""
Main Application Entry Point.

This module initializes the FastAPI application for the License Compatibility Checker.
It configures Cross-Origin Resource Sharing (CORS) policies to allow communication
with the frontend and registers the main API routers.
"""

from typing import Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.controllers.analysis import router as analysis_router

# Initialize the application instance
app = FastAPI(
    title="License Compatibility Checker + Ollama",
    version="1.0.0",
)

# ------------------------------------------------------------------
# CORS CONFIGURATION
# ------------------------------------------------------------------

# List of allowed origins (Frontend development server)
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://license-tool-nine.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# ROUTER REGISTRATION
# ------------------------------------------------------------------

# Register the main analysis controller with the /api prefix
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])


# ------------------------------------------------------------------
# ROOT ENDPOINT
# ------------------------------------------------------------------

@app.get("/")
def root() -> Dict[str, str]:
    """
    Root endpoint to verify backend availability.

    Returns:
        Dict[str, str]: A simple status message indicating the service is running.
    """
    return {"message": "License Checker Backend is running"}
