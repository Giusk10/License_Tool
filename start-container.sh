#!/bin/bash

# 1. Avvia Ollama in background
echo "Starting Ollama server..."
ollama serve &

# 2. Attendi che Ollama sia pronto
echo "Waiting for Ollama..."
until curl -s http://localhost:11434/api/version > /dev/null; do
    sleep 2
done
echo "Ollama is ready!"

# 3. Pull dei Modelli Cloud (Dal tuo ENV)
# Usa le variabili d'ambiente passate da docker-compose
echo "Setting up Cloud Models from ENV..."

if [ ! -z "$OLLAMA_CODING_MODEL" ]; then
    echo "Pulling Coding Model: $OLLAMA_CODING_MODEL"
    # Poiché sono modelli cloud e hai montato ~/.ollama, questo sarà velocissimo
    ollama pull "$OLLAMA_CODING_MODEL"
fi

if [ ! -z "$OLLAMA_GENERAL_MODEL" ]; then
    echo "Pulling General Model: $OLLAMA_GENERAL_MODEL"
    ollama pull "$OLLAMA_GENERAL_MODEL"
fi

# 4. Avvia il Backend
echo "Starting FastAPI Backend..."
# Qui userà SCANCODE_BIN=/opt/scancode-toolkit/scancode come definito nel compose
uvicorn app.main:app --host 0.0.0.0 --port 8000