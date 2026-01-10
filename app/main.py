"""
Punto di Ingresso Principale dell'Applicazione.

Questo modulo inizializza l'applicazione FastAPI per il License Compatibility Checker.
Configura le policy di Cross-Origin Resource Sharing (CORS) per consentire la comunicazione
con il frontend e registra i router API principali.
"""

from typing import Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.controllers.analysis import router as analysis_router

# Inizializza l'istanza dell'applicazione
app = FastAPI(
    title="License Compatibility Checker + Ollama",
    version="1.0.0",
)

# ------------------------------------------------------------------
# CONFIGURAZIONE CORS
# ------------------------------------------------------------------

# Lista delle origini consentite (server di sviluppo del frontend)
origins = [
    "http://localhost:5173",  # Vite dev server (locale)
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
# REGISTRAZIONE ROUTER
# ------------------------------------------------------------------

# Registra il controller di analisi principale con il prefisso /api
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])


# ------------------------------------------------------------------
# ENDPOINT ROOT
# ------------------------------------------------------------------

@app.get("/")
def root() -> Dict[str, str]:
    """
    Endpoint root per verificare la disponibilità del backend.

    Returns:
        Dict[str, str]: Un semplice messaggio di stato che indica che il servizio è in esecuzione.
    """
    return {"message": "License Checker Backend is running"}
