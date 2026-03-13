#!/bin/bash
# NodeMesh Worker Agent Startup Script
# For: Android/Termux (Phone - mobile inference)
# This registers the Android device as a worker node in the mesh

set -e

# Termux-specific setup
if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
    echo "Termux environment detected"
    export TERMUX=1
    # Ensure we're using Termux's Python
    export PATH="/data/data/com.termux/files/usr/bin:$PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORKER_DIR="$PROJECT_DIR/worker"

# Configuration - UPDATE THESE FOR YOUR SETUP
export NODE_NAME="${NODE_NAME:-android-phone}"
export COORDINATOR_URL="${COORDINATOR_URL:-http://192.168.1.100:11434}"  # Tower's IP
export MODELS_DIR="${MODELS_DIR:-$HOME/storage/shared/AI-Models}"
export WORKER_PORT="${WORKER_PORT:-11436}"
export LLAMA_PORT="${LLAMA_PORT:-11437}"

echo "==============================================="
echo "  NodeMesh Worker (Android/Termux)"
echo "==============================================="
echo ""
echo "Configuration:"
echo "  Node Name: $NODE_NAME"
echo "  Coordinator: $COORDINATOR_URL"
echo "  Models Dir: $MODELS_DIR"
echo "  Worker Port: $WORKER_PORT"
echo "  Llama.cpp Port: $LLAMA_PORT"
echo ""

# Check Termux storage permission
if [ -n "$TERMUX" ]; then
    if [ ! -d "$HOME/storage" ]; then
        echo "Setting up Termux storage access..."
        echo "  Run: termux-setup-storage"
        echo "  Then re-run this script"
        exit 1
    fi
fi

# Detect hardware
echo "Checking hardware..."
# Get RAM info from Android
if [ -f "/proc/meminfo" ]; then
    TOTAL_RAM=$(cat /proc/meminfo | grep MemTotal | awk '{print $2}')
    TOTAL_RAM=$((TOTAL_RAM / 1024))
else
    TOTAL_RAM=8192  # Default assumption for modern phones
fi

# Get CPU cores
CPU_CORES=$(nproc)

# Get device info
DEVICE_MODEL=$(getprop ro.product.model 2>/dev/null || echo "Unknown Android Device")
ANDROID_VERSION=$(getprop ro.build.version.release 2>/dev/null || echo "Unknown")

echo "  Device: $DEVICE_MODEL"
echo "  Android: $ANDROID_VERSION"
echo "  RAM: ${TOTAL_RAM}MB"
echo "  CPU Cores: $CPU_CORES"
echo ""

# Mobile-specific warnings
if [ "$TOTAL_RAM" -lt 6144 ]; then
    echo "NOTE: Limited RAM for mobile inference."
    echo "  Recommended models:"
    echo "    - Qwen2.5 0.5B Q4: ~300MB"
    echo "    - Phi-2 2.7B Q2_K: ~1.2GB (slow)"
    echo "    - TinyLlama 1.1B Q4: ~600MB"
    echo ""
fi

cd "$WORKER_DIR"

# Check Python installation
echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found. Installing..."
    pkg update -y
    pkg install -y python
fi

python3 --version

# Setup Python environment
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies (lightweight versions)
echo "Installing dependencies..."
pip install -q --upgrade pip

# Install without heavy dependencies for mobile
pip install -q fastapi uvicorn httpx python-multipart

# Check for llama.cpp server
echo ""
echo "Checking for llama-server..."
LLAMA_SERVER=$(which llama-server 2>/dev/null || echo "")

if [ -z "$LLAMA_SERVER" ]; then
    echo "  llama-server not found"
    echo ""
    echo "  Installing llama.cpp for Termux..."
    echo ""
    echo "  Option 1: Build from source (recommended)"
    echo "    pkg install git cmake clang"
    echo "    git clone https://github.com/ggerganov/llama.cpp"
    echo "    cd llama.cpp"
    echo "    cmake -B build -DLLAMA_BUILD_TESTS=OFF"
    echo "    cmake --build build --config Release -j$(nproc)"
    echo "    cp build/bin/llama-server \$PREFIX/bin/"
    echo ""
    echo "  Option 2: Use pre-built package (if available)"
    echo "    pkg install llama-cpp"
    echo ""
    
    # Try to install from package
    echo "Attempting to install llama-cpp package..."
    pkg install -y llama-cpp 2>/dev/null || true
    
    LLAMA_SERVER=$(which llama-server 2>/dev/null || echo "")
    if [ -z "$LLAMA_SERVER" ]; then
        echo "ERROR: llama-server installation required"
        exit 1
    fi
else
    echo "  Found: $LLAMA_SERVER"
fi

# Check for models
if [ ! -d "$MODELS_DIR" ]; then
    echo ""
    echo "WARNING: Models directory not found: $MODELS_DIR"
    echo ""
    echo "Recommended setup:"
    echo "  1. Create folder on internal storage: /sdcard/AI-Models"
    echo "  2. Download small GGUF models suitable for mobile:"
    echo "     - Qwen2.5 0.5B Q4: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    echo "     - TinyLlama 1.1B: https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
    echo "  3. Set MODELS_DIR to point to that folder"
    echo ""
    echo "Creating fallback directory..."
    mkdir -p "$HOME/models"
    MODELS_DIR="$HOME/models"
fi

# Mobile optimizations
export LLAMA_THREADS=4
export LLAMA_BATCH_SIZE=256

echo ""
echo "Starting NodeMesh Worker (Android)..."
echo "  This node will register with: $COORDINATOR_URL"
echo ""
echo "  Mobile optimizations enabled:"
echo "    - Limited threads: $LLAMA_THREADS"
echo "    - Small batch size: $LLAMA_BATCH_SIZE"
echo ""
echo "Press Ctrl+C to stop"
echo "==============================================="
echo ""

# Run the worker with mobile-specific flags
exec python agent.py \
    --name "$NODE_NAME" \
    --coordinator "$COORDINATOR_URL" \
    --models-dir "$MODELS_DIR" \
    --port "$WORKER_PORT" \
    --llama-port "$LLAMA_PORT" \
    --host "0.0.0.0"
