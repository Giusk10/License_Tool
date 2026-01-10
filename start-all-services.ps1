# Script per avviare tutti i servizi necessari per License Tool
# Utilizzo: .\start-all-services.ps1

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   License Tool - Avvio Servizi                 " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Verifica se Ollama è installato
Write-Host "1. Verifica installazione Ollama..." -ForegroundColor Yellow
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaPath) {
    Write-Host "   [ERRORE] Ollama non è installato!" -ForegroundColor Red
    Write-Host "   Scaricalo da: https://ollama.ai/download" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] Ollama trovato: $($ollamaPath.Source)" -ForegroundColor Green

# Verifica se Ollama è già in esecuzione
Write-Host ""
Write-Host "2. Verifica se Ollama è già in esecuzione..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/version" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "   [OK] Ollama è già in esecuzione!" -ForegroundColor Green
} catch {
    Write-Host "   Ollama non è in esecuzione. Avvio in corso..." -ForegroundColor Yellow

    # Avvia Ollama in una nuova finestra
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'Ollama Server' -ForegroundColor Cyan; Write-Host 'Non chiudere questa finestra!' -ForegroundColor Yellow; Write-Host ''; ollama serve" -WindowStyle Normal

    Write-Host "   Attesa avvio di Ollama..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5

    # Verifica l'avvio
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/version" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Host "   [OK] Ollama avviato con successo!" -ForegroundColor Green
    } catch {
        Write-Host "   [ERRORE] Ollama non risponde. Verificare manualmente." -ForegroundColor Red
        exit 1
    }
}

# Verifica i modelli AI installati
Write-Host ""
Write-Host "3. Verifica modelli AI installati..." -ForegroundColor Yellow
$models = ollama list 2>&1 | Out-String
$hasDeepseek = $models -match "deepseek"
$hasQwen = $models -match "qwen"

if (-not $hasDeepseek) {
    Write-Host "   [ATTENZIONE] Modello deepseek-r1 non trovato!" -ForegroundColor Yellow
    Write-Host "   Scaricalo con: ollama pull deepseek-r1:1.5b" -ForegroundColor Yellow
}

if (-not $hasQwen) {
    Write-Host "   [ATTENZIONE] Modello qwen2.5-coder non trovato!" -ForegroundColor Yellow
    Write-Host "   Scaricalo con: ollama pull qwen2.5-coder:1.5b" -ForegroundColor Yellow
}

if ($hasDeepseek -and $hasQwen) {
    Write-Host "   [OK] Tutti i modelli necessari sono installati!" -ForegroundColor Green
}

# Verifica se Python è installato
Write-Host ""
Write-Host "4. Verifica installazione Python..." -ForegroundColor Yellow
$pythonPath = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonPath) {
    Write-Host "   [ERRORE] Python non trovato!" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] Python trovato: $($pythonPath.Source)" -ForegroundColor Green

# Avvia il Backend FastAPI
Write-Host ""
Write-Host "5. Avvio Backend FastAPI..." -ForegroundColor Yellow
$backendPath = Get-Location
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; Write-Host 'Backend FastAPI' -ForegroundColor Cyan; Write-Host 'Non chiudere questa finestra!' -ForegroundColor Yellow; Write-Host ''; uvicorn app.main:app --reload" -WindowStyle Normal
Write-Host "   [OK] Backend avviato su http://localhost:8000" -ForegroundColor Green

# Verifica se npm è installato
Write-Host ""
Write-Host "6. Verifica installazione Node.js/npm..." -ForegroundColor Yellow
$npmPath = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmPath) {
    Write-Host "   [ERRORE] npm non trovato!" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] npm trovato: $($npmPath.Source)" -ForegroundColor Green

# Avvia il Frontend React
Write-Host ""
Write-Host "7. Avvio Frontend React..." -ForegroundColor Yellow
$frontendPath = Join-Path $backendPath "frontend"
if (Test-Path $frontendPath) {
    Start-Sleep -Seconds 3
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; Write-Host 'Frontend React' -ForegroundColor Cyan; Write-Host 'Non chiudere questa finestra!' -ForegroundColor Yellow; Write-Host ''; npm run dev" -WindowStyle Normal
    Write-Host "   [OK] Frontend avviato su http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "   [ERRORE] Cartella frontend non trovata!" -ForegroundColor Red
}

# Riepilogo
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   Tutti i servizi sono stati avviati!          " -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Servizi in esecuzione:" -ForegroundColor White
Write-Host "  - Ollama:   http://localhost:11434" -ForegroundColor White
Write-Host "  - Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  - Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Apri il browser su: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANTE: Non chiudere le finestre dei servizi!" -ForegroundColor Yellow
Write-Host "Premi CTRL+C in questa finestra per uscire." -ForegroundColor Gray
Write-Host ""

# Mantiene la finestra aperta
Read-Host "Premi INVIO per chiudere..."
