#!/bin/bash
# NodeMesh Coordinator Startup Script
# For: Debian Linux (Tower - Anchor Node)
# This runs the central coordinator that manages the entire mesh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COORDINATOR_DIR="$PROJECT_DIR/coordinator"

# Configuration - adjust these for your network
export COORDINATOR_HOST="${COORDINATOR_HOST:-0.0.0.0}"
export COORDINATOR_PORT="${COORDINATOR_PORT:-11434}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11435}"
export HEARTBEAT_TIMEOUT="${HEARTBEAT_TIMEOUT:-30}"

echo "==============================================="
echo "  NodeMesh Coordinator (Tower)"
echo "==============================================="
echo ""
echo "Configuration:"
echo "  Host: $COORDINATOR_HOST"
echo "  Port: $COORDINATOR_PORT"
echo "  Ollama URL: $OLLAMA_BASE_URL"
echo ""

# Check if Ollama is running on the expected port
echo "Checking Ollama..."
if curl -s "$OLLAMA_BASE_URL/api/tags" > /dev/null 2>&1; then
    echo "  Ollama is running at $OLLAMA_BASE_URL"
else
    echo "  WARNING: Ollama not detected at $OLLAMA_BASE_URL"
    echo "  Make sure Ollama is running: ollama serve"
    echo "  Or adjust OLLAMA_BASE_URL if Ollama is on a different port"
fi

# Setup Python environment
cd "$COORDINATOR_DIR"

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "Starting NodeMesh Coordinator..."
echo "  API will be available at: http://$COORDINATOR_HOST:$COORDINATOR_PORT"
echo "  Dashboard: http://localhost:$COORDINATOR_PORT"
echo ""
echo "  Other devices should connect workers to:"
echo "    http://$(hostname -I | awk '{print $1}'):$COORDINATOR_PORT"
echo ""
echo "Press Ctrl+C to stop"
echo "==============================================="
echo ""

# Run the coordinator
exec python main.py
