# NodeMesh Worker Agent Startup Script
# For: Windows 11 (Laptop - lightweight tasks)
# PowerShell version with better error handling

$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  NodeMesh Worker (Windows 11)" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Configuration - UPDATE THESE FOR YOUR SETUP
$NODE_NAME = "windows-laptop"
$COORDINATOR_URL = "http://192.168.1.100:11434"  # Tower's IP address
$MODELS_DIR = "$env:USERPROFILE\GGUF-Models"
$WORKER_PORT = 11436
$LLAMA_PORT = 11437

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Node Name: $NODE_NAME"
Write-Host "  Coordinator: $COORDINATOR_URL"
Write-Host "  Models Dir: $MODELS_DIR"
Write-Host "  Worker Port: $WORKER_PORT"
Write-Host "  Llama.cpp Port: $LLAMA_PORT"
Write-Host ""

# Get script directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_DIR = Split-Path -Parent $SCRIPT_DIR
$WORKER_DIR = Join-Path $PROJECT_DIR "worker"

# Check hardware
Write-Host "Checking hardware..." -ForegroundColor Yellow

try {
    $computerSystem = Get-CimInstance Win32_ComputerSystem
    $TOTAL_RAM_MB = [math]::Round($computerSystem.TotalPhysicalMemory / 1MB)
    $CPU_CORES = $computerSystem.NumberOfLogicalProcessors
    
    Write-Host "  RAM: $TOTAL_RAM_MB MB"
    Write-Host "  CPU Cores: $CPU_CORES"
    Write-Host ""
    
    if ($TOTAL_RAM_MB -lt 4096) {
        Write-Host "NOTE: Limited RAM detected. Only small models (1B-3B) recommended." -ForegroundColor Yellow
        Write-Host "Consider using Q2 or Q3 quantization for better performance." -ForegroundColor Yellow
        Write-Host ""
    }
} catch {
    Write-Host "  Could not detect hardware details" -ForegroundColor Yellow
}

# Navigate to worker directory
Set-Location $WORKER_DIR

# Setup Python environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

# Check for llama.cpp server
Write-Host ""
Write-Host "Checking for llama-server.exe..." -ForegroundColor Yellow

$llamaServer = Get-Command llama-server.exe -ErrorAction SilentlyContinue
if (-not $llamaServer) {
    Write-Host "  llama-server.exe not found in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please build llama.cpp from source:" -ForegroundColor Yellow
    Write-Host "  1. Install Visual Studio 2022 with C++ workload"
    Write-Host "  2. git clone https://github.com/ggerganov/llama.cpp"
    Write-Host "  3. cd llama.cpp"
    Write-Host "  4. cmake -B build"
    Write-Host "  5. cmake --build build --config Release -j4"
    Write-Host "  6. Add build\bin\Release to your PATH"
    Write-Host ""
    Write-Host "Or download pre-built binaries from:" -ForegroundColor Yellow
    Write-Host "  https://github.com/ggerganov/llama.cpp/releases"
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
} else {
    Write-Host "  Found: $($llamaServer.Source)" -ForegroundColor Green
}

# Check for models directory
if (-not (Test-Path $MODELS_DIR)) {
    Write-Host ""
    Write-Host "WARNING: Models directory not found: $MODELS_DIR" -ForegroundColor Yellow
    Write-Host "Creating directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $MODELS_DIR -Force | Out-Null
    Write-Host ""
    Write-Host "Please download small GGUF models suitable for this hardware:" -ForegroundColor Yellow
    Write-Host "  - Phi-3 Mini (3.8B) Q4_K_M: ~2.3GB"
    Write-Host "  - Qwen2.5 1.5B Q4: ~1GB"
    Write-Host "  - TinyLlama 1.1B Q4: ~0.6GB"
    Write-Host ""
    Write-Host "Download from: https://huggingface.co/models?search=gguf" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to continue (or Ctrl+C to exit and download models first)"
}

Write-Host ""
Write-Host "Starting NodeMesh Worker..." -ForegroundColor Green
Write-Host "This node will register with: $COORDINATOR_URL" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Run the worker
try {
    python agent.py `
        --name $NODE_NAME `
        --coordinator $COORDINATOR_URL `
        --models-dir $MODELS_DIR `
        --port $WORKER_PORT `
        --llama-port $LLAMA_PORT
} catch {
    Write-Host "Error running worker: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
}
