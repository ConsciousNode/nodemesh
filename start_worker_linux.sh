#!/bin/bash
# NodeMesh Worker Agent Startup Script
# For: Debian Linux (Laptop - lightweight tasks)
# This registers the laptop as a worker node in the mesh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORKER_DIR="$PROJECT_DIR/worker"

# Configuration - UPDATE THESE FOR YOUR SETUP
export NODE_NAME="${NODE_NAME:-debian-laptop}"
export COORDINATOR_URL="${COORDINATOR_URL:-http://192.168.1.100:11434}"  # Tower's IP
export MODELS_DIR="${MODELS_DIR:-$HOME/GGUF-Models}"
export WORKER_PORT="${WORKER_PORT:-11436}"
export LLAMA_PORT="${LLAMA_PORT:-11437}"

echo "==============================================="
echo "  NodeMesh Worker (Debian Linux)"
echo "==============================================="
echo ""
echo "Configuration:"
echo "  Node Name: $NODE_NAME"
echo "  Coordinator: $COORDINATOR_URL"
echo "  Models Dir: $MODELS_DIR"
echo "  Worker Port: $WORKER_PORT"
echo "  Llama.cpp Port: $LLAMA_PORT"
echo ""

# Detect if running on limited hardware (Core2Duo, 3GB RAM)
echo "Checking hardware..."
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
CPU_CORES=$(nproc)
echo "  RAM: ${TOTAL_RAM}MB"
echo "  CPU Cores: $CPU_CORES"

if [ "$TOTAL_RAM" -lt 4096 ]; then
    echo ""
    echo "  NOTE: Limited RAM detected. Only small models (1B-3B) recommended."
    echo "  Consider using Q2 or Q3 quantization for better performance."
fi

cd "$WORKER_DIR"

# Setup Python environment
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check for llama.cpp server
echo ""
echo "Checking for llama-server..."
LLAMA_SERVER=$(which llama-server 2>/dev/null || echo "")

if [ -z "$LLAMA_SERVER" ]; then
    echo "  llama-server not found in PATH"
    echo ""
    echo "  Please build llama.cpp from source:"
    echo "    git clone https://github.com/ggerganov/llama.cpp"
    echo "    cd llama.cpp"
    echo "    cmake -B build"
    echo "    cmake --build build --config Release -j$(nproc)"
    echo "    sudo cp build/bin/llama-server /usr/local/bin/"
    echo ""
    echo "  Or specify the path to llama-server binary:"
    echo "    export PATH=\$PATH:/path/to/llama.cpp/build/bin"
    exit 1
else
    echo "  Found: $LLAMA_SERVER"
fi

# Check for models
if [ ! -d "$MODELS_DIR" ]; then
    echo ""
    echo "  WARNING: Models directory not found: $MODELS_DIR"
    echo "  Creating directory..."
    mkdir -p "$MODELS_DIR"
    echo ""
    echo "  Please download small GGUF models suitable for this hardware:"
    echo "    - Phi-3 Mini (3.8B) Q4_K_M: ~2.3GB"
    echo "    - Qwen2.5 1.5B Q4: ~1GB"
    echo "    - TinyLlama 1.1B Q4: ~0.6GB"
fi

echo ""
echo "Starting NodeMesh Worker..."
echo "  This node will register with: $COORDINATOR_URL"
echo ""
echo "Press Ctrl+C to stop"
echo "==============================================="
echo ""

# Run the worker
exec python agent.py \
    --name "$NODE_NAME" \
    --coordinator "$COORDINATOR_URL" \
    --models-dir "$MODELS_DIR" \
    --port "$WORKER_PORT" \
    --llama-port "$LLAMA_PORT"
