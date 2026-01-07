#!/bin/bash
set -e

# Funzione ausiliaria per estrarre il link di auth (serve se le chiavi falliscono)
get_auth_url() {
    echo "$1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('signin_url', ''))"
}

# ==============================================================================
# 1. INIEZIONE CHIAVI (Per Deployment su Render/Cloud)
# ==============================================================================
# Se le variabili d'ambiente esistono (su Render), le scriviamo su disco.
if [ ! -z "$OLLAMA_KEY_PRIV" ] && [ ! -z "$OLLAMA_KEY_PUB" ]; then
    echo "🔐 Injecting Ollama keys from Environment Variables..."
    mkdir -p /root/.ollama

    # Scriviamo la chiave privata
    echo "$OLLAMA_KEY_PRIV" > /root/.ollama/id_ed25519
    # Scriviamo la chiave pubblica
    echo "$OLLAMA_KEY_PUB" > /root/.ollama/id_ed25519.pub

    # Importante: permessi stretti (altrimenti SSH si rifiuta di usarle)
    chmod 600 /root/.ollama/id_ed25519
    echo "✅ Keys injected successfully."
fi

# ==============================================================================
# 2. AVVIO OLLAMA
# ==============================================================================
echo "🔴 Starting Ollama server..."
ollama serve &

# Aspettiamo che la porta sia aperta
echo "⏳ Waiting for Ollama startup..."
until curl -s http://127.0.0.1:11434/api/version > /dev/null; do
    sleep 1
done
echo "✅ Ollama is active!"

# ==============================================================================
# 3. SELEZIONE E PULL DEL MODELLO (CON FALLBACK DI SICUREZZA)
# ==============================================================================
# Qui sta la correzione dell'errore precedente.
# Se le variabili d'ambiente sono vuote, usiamo questi valori fissi.
DEFAULT_MODEL="deepseek-v3.1:671b-cloud"

# Logica:
# 1. Prova a usare OLLAMA_GENERAL_MODEL
# 2. Se vuoto, prova OLLAMA_CODING_MODEL
# 3. Se vuoto, usa DEFAULT_MODEL
MODEL_TO_USE="${OLLAMA_GENERAL_MODEL:-${OLLAMA_CODING_MODEL:-$DEFAULT_MODEL}}"

echo "📦 Ensuring model '$MODEL_TO_USE' is available..."
ollama pull "$MODEL_TO_USE"

# ==============================================================================
# 4. CONTROLLO AUTORIZZAZIONE (Fallback Interattivo)
# ==============================================================================
# Se le chiavi sono state iniettate sopra, questo passaggio sarà immediato.
if [[ "$MODEL_TO_USE" == *"-cloud" ]]; then
    echo "☁️  Verifying authorization for Cloud Model..."

    RESPONSE=$(curl -s -X POST http://127.0.0.1:11434/api/generate -d "{\"model\": \"$MODEL_TO_USE\", \"prompt\": \"hi\", \"stream\": false}" || true)

    if echo "$RESPONSE" | grep -q "unauthorized"; then
        AUTH_URL=$(get_auth_url "$RESPONSE")
        echo ""
        echo "🚨  AUTORIZZAZIONE RICHIESTA (Chiavi non valide o mancanti)"
        echo "👉  $AUTH_URL"
        echo "⏳ Waiting..."
        while echo "$RESPONSE" | grep -q "unauthorized"; do
            sleep 5
            RESPONSE=$(curl -s -X POST http://127.0.0.1:11434/api/generate -d "{\"model\": \"$MODEL_TO_USE\", \"prompt\": \"hi\", \"stream\": false}" || true)
        done
        echo "✅ Autorizzato!"
    else
        echo "✅ Il modello è già autorizzato (Auth via Environment Variables ok)."
    fi
fi

# ==============================================================================
# 5. AVVIO BACKEND PYTHON
# ==============================================================================
# Usa la porta fornita da Render ($PORT) o 8000 di default
SERVER_PORT=${PORT:-8000}
echo "🚀 Starting FastAPI Backend on port $SERVER_PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$SERVER_PORT"