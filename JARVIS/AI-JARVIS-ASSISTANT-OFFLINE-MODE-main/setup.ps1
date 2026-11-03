# J.A.R.V.I.S. Automated Setup Script
# Run this in PowerShell as Administrator

Write-Host "=================================="
Write-Host " J.A.R.V.I.S. SYSTEM SETUP SCRIPT "
Write-Host "=================================="
Write-Host ""
Write-Host "This script uses Winget to automatically download and install required dependencies."

# 1. Check/Install Python
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "[>] Python not found. Installing Python 3.10..."
    winget install Python.Python.3.10 --silent --accept-package-agreements --accept-source-agreements
    
    # Reload environment variables for the current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "[OK] Python is installed."
}

# 2. Check/Install Ollama
if (-not (Get-Command "ollama" -ErrorAction SilentlyContinue)) {
    Write-Host "[>] Ollama Engine not found. Installing via Winget..."
    winget install Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
    
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "[OK] Ollama is installed."
}

# 3. Pull Llama Model
Write-Host "[>] Starting Ollama Engine..."
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Host "[>] Pulling Llama 3.2:3b model... (This might take a while depending on your internet)"
ollama pull llama3.2:3b

# 4. Pip Dependencies
Write-Host "[>] Installing Python AI modules (Flask, SpeechRecognition, PyAutoGUI, PyAudio, Pyttsx3)..."
python -m pip install --upgrade pip
$installResult = python -m pip install SpeechRecognition pyttsx3 pyaudio pyautogui flask

if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] PyAudio failed to build. Falling back to pipwin method..."
    python -m pip install pipwin
    python -m pipwin install pyaudio
}

Write-Host ""
Write-Host "=================================="
Write-Host "      INSTALLATION COMPLETE       "
Write-Host "=================================="
Write-Host "To start the assistant, run:"
Write-Host "  python server.py"
Write-Host ""
