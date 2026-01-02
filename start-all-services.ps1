# Script to start all necessary services for the License Tool
# Usage: .\start-all-services.ps1

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   License Tool - Starting Services             " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Ollama is installed
Write-Host "1. Checking Ollama installation..." -ForegroundColor Yellow
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaPath) {
    Write-Host "   [ERROR] Ollama is not installed!" -ForegroundColor Red
    Write-Host "   Download it from: https://ollama.ai/download" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] Ollama found: $($ollamaPath.Source)" -ForegroundColor Green

# Check if Ollama is already running
Write-Host ""
Write-Host "2. Checking if Ollama is already running..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/version" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "   [OK] Ollama is already running!" -ForegroundColor Green
} catch {
    Write-Host "   Ollama is not running. Starting now..." -ForegroundColor Yellow

    # Start Ollama in a new window
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'Ollama Server' -ForegroundColor Cyan; Write-Host 'Do not close this window!' -ForegroundColor Yellow; Write-Host ''; ollama serve" -WindowStyle Normal

    Write-Host "   Waiting for Ollama to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5

    # Verify startup
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/version" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Host "   [OK] Ollama started successfully!" -ForegroundColor Green
    } catch {
        Write-Host "   [ERROR] Ollama is not responding. Please check manually." -ForegroundColor Red
        exit 1
    }
}

# Check installed AI models
Write-Host ""
Write-Host "3. Checking installed AI models..." -ForegroundColor Yellow
$models = ollama list 2>&1 | Out-String
$hasDeepseek = $models -match "deepseek"
$hasQwen = $models -match "qwen"

if (-not $hasDeepseek) {
    Write-Host "   [WARNING] deepseek-r1 model not found!" -ForegroundColor Yellow
    Write-Host "   Download it with: ollama pull deepseek-r1:1.5b" -ForegroundColor Yellow
}

if (-not $hasQwen) {
    Write-Host "   [WARNING] qwen2.5-coder model not found!" -ForegroundColor Yellow
    Write-Host "   Download it with: ollama pull qwen2.5-coder:1.5b" -ForegroundColor Yellow
}

if ($hasDeepseek -and $hasQwen) {
    Write-Host "   [OK] All necessary models are installed!" -ForegroundColor Green
}

# Check if Python is installed
Write-Host ""
Write-Host "4. Checking Python installation..." -ForegroundColor Yellow
$pythonPath = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonPath) {
    Write-Host "   [ERROR] Python not found!" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] Python found: $($pythonPath.Source)" -ForegroundColor Green

# Start FastAPI Backend
Write-Host ""
Write-Host "5. Starting FastAPI Backend..." -ForegroundColor Yellow
$backendPath = Get-Location
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; Write-Host 'Backend FastAPI' -ForegroundColor Cyan; Write-Host 'Do not close this window!' -ForegroundColor Yellow; Write-Host ''; uvicorn app.main:app --reload" -WindowStyle Normal
Write-Host "   [OK] Backend started at http://localhost:8000" -ForegroundColor Green

# Check if npm is installed
Write-Host ""
Write-Host "6. Checking Node.js/npm installation..." -ForegroundColor Yellow
$npmPath = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmPath) {
    Write-Host "   [ERROR] npm not found!" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] npm found: $($npmPath.Source)" -ForegroundColor Green

# Start React Frontend
Write-Host ""
Write-Host "7. Starting React Frontend..." -ForegroundColor Yellow
$frontendPath = Join-Path $backendPath "frontend"
if (Test-Path $frontendPath) {
    Start-Sleep -Seconds 3
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; Write-Host 'Frontend React' -ForegroundColor Cyan; Write-Host 'Do not close this window!' -ForegroundColor Yellow; Write-Host ''; npm run dev" -WindowStyle Normal
    Write-Host "   [OK] Frontend started at http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] Frontend folder not found!" -ForegroundColor Red
}

# Summary
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   All services have been started!              " -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Running Services:" -ForegroundColor White
Write-Host "  - Ollama:   http://localhost:11434" -ForegroundColor White
Write-Host "  - Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  - Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Open your browser at: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT: Do not close the service windows!" -ForegroundColor Yellow
Write-Host "Press CTRL+C in this window to exit." -ForegroundColor Gray
Write-Host ""

# Keep the window open
Read-Host "Press ENTER to close..."