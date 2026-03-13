# NodeMesh Setup Guide

Complete setup instructions for deploying the distributed AI inference mesh across your heterogeneous hardware.

## Overview

NodeMesh creates a unified AI compute cluster from:
- **Tower (Anchor)**: Debian Linux, Sandy Bridge, 12GB RAM + zRAM, 1GB GPU - Primary coordinator
- **Debian Laptop**: Core2Duo, 3GB RAM - Lightweight worker
- **Windows Laptop**: Core i3, 4GB RAM - Lightweight worker  
- **Android Phone**: OnePlus 7T Pro 5G, Termux - Mobile worker

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         NodeMesh Cluster                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐         ┌──────────────────────────────┐     │
│  │   Clients    │────────▶│  Coordinator (Tower:11434)   │     │
│  │  (OpenWebUI, │         │  - Request routing           │     │
│  │   Continue,  │         │  - Load balancing            │     │
│  │   etc.)      │◀────────│  - Failover handling         │     │
│  └──────────────┘         └──────────────────────────────┘     │
│                                      │                           │
│                    ┌─────────────────┼─────────────────┐        │
│                    ▼                 ▼                 ▼        │
│           ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│           │Tower Worker  │  │Linux Worker  │  │Windows Worker│ │
│           │(Ollama:11435)│  │(llama.cpp)   │  │(llama.cpp)   │ │
│           │- Large models│  │- Small models│  │- Small models│ │
│           └──────────────┘  └──────────────┘  └──────────────┘ │
│                    │                                            │
│                    ▼                                            │
│           ┌──────────────┐                                      │
│           │Android Worker│                                      │
│           │(llama.cpp)   │                                      │
│           │- Tiny models │                                      │
│           └──────────────┘                                      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### All Nodes
- Python 3.8+ installed
- Network connectivity (same LAN)
- Git (for building llama.cpp)

### Tower (Debian)
- Ollama installed and running
- `curl` for health checks

### Laptops (Debian/Windows)
- llama.cpp built from source
- GGUF models downloaded

### Android/Termux
- Termux app installed
- Storage permission granted (`termux-setup-storage`)

---

## Step 1: Tower (Coordinator) Setup

The Tower is your anchor node. It runs both the coordinator AND Ollama natively.

### 1.1 Install Ollama (if not already installed)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama on port 11435 (coordinator uses 11434)
OLLAMA_HOST=0.0.0.0:11435 ollama serve
```

### 1.2 Download Models for Tower

```bash
# Large models for Tower (7B-13B)
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull qwen2.5:7b
ollama pull phi3:14b
ollama pull nomic-embed-text  # For embeddings
```

### 1.3 Setup NodeMesh Coordinator

```bash
# Navigate to project
cd /path/to/nodemesh

# Run the coordinator
chmod +x scripts/start_coordinator.sh
./scripts/start_coordinator.sh
```

The coordinator will start on port 11434. Note your Tower's IP address:

```bash
ip addr show | grep "inet " | head -1
# Example: 192.168.1.100
```

You'll need this IP for all worker nodes.

---

## Step 2: Debian Laptop Setup

### 2.1 Install Dependencies

```bash
# Update system
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git build-essential cmake

# For better performance on older CPUs
sudo apt install -y libopenblas-dev  # Optional: BLAS acceleration
```

### 2.2 Build llama.cpp

```bash
# Clone llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Build with optimizations for Core2Duo (SSE2 only, no AVX)
cmake -B build \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_NATIVE=OFF \
  -DLLAMA_SSE2=ON \
  -DLLAMA_AVX=OFF \
  -DLLAMA_AVX2=OFF \
  -DLLAMA_FMA=OFF

cmake --build build --config Release -j2

# Install to system
sudo cp build/bin/llama-server /usr/local/bin/
sudo cp build/bin/llama-cli /usr/local/bin/
```

### 2.3 Download Models

```bash
# Create models directory
mkdir -p ~/GGUF-Models
cd ~/GGUF-Models

# Download small models suitable for 3GB RAM
# Qwen2.5 1.5B - Excellent small model
wget https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf

# TinyLlama 1.1B - Very small, fast
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

# Phi-3 Mini 3.8B - Good quality, may be slow on 3GB
wget https://huggingface.co/bartowski/Phi-3.1-mini-4k-instruct-GGUF/resolve/main/Phi-3.1-mini-4k-instruct-Q4_K_M.gguf
```

### 2.4 Setup NodeMesh Worker

```bash
cd /path/to/nodemesh

# Edit the script to set your Tower's IP
nano scripts/start_worker_linux.sh
# Change: COORDINATOR_URL="http://YOUR_TOWER_IP:11434"

# Run the worker
chmod +x scripts/start_worker_linux.sh
./scripts/start_worker_linux.sh
```

---

## Step 3: Windows Laptop Setup

### 3.1 Install Prerequisites

1. **Install Python 3.8+** from https://python.org
   - Check "Add Python to PATH" during installation

2. **Install Git** from https://git-scm.com/download/win

3. **Install Visual Studio 2022 Build Tools**
   - Download from: https://visualstudio.microsoft.com/downloads/
   - Install "Desktop development with C++" workload

### 3.2 Build llama.cpp

Open PowerShell or Command Prompt:

```powershell
# Clone llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Build with CMake
cmake -B build -DLLAMA_BUILD_TESTS=OFF

cmake --build build --config Release -j4

# Add to PATH (optional - makes it available everywhere)
# Or note the path: C:\path\to\llama.cpp\build\bin\Release
```

### 3.3 Download Models

```powershell
# Create models directory
mkdir $env:USERPROFILE\GGUF-Models
cd $env:USERPROFILE\GGUF-Models

# Download using PowerShell
# Qwen2.5 1.5B
Invoke-WebRequest -Uri "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf" -OutFile "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# TinyLlama 1.1B
Invoke-WebRequest -Uri "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf" -OutFile "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
```

Or download manually from:
- https://huggingface.co/models?search=gguf

### 3.4 Setup NodeMesh Worker

```powershell
cd C:\path\to\nodemesh

# Edit the script to set your Tower's IP
notepad scripts\start_worker_windows.bat
# Change: set COORDINATOR_URL=http://YOUR_TOWER_IP:11434

# Run the worker
.\scripts\start_worker_windows.bat
```

Or use PowerShell:
```powershell
.\scripts\start_worker_windows.ps1
```

---

## Step 4: Android/Termux Setup

### 4.1 Install Termux

1. Install Termux from F-Droid (recommended): https://f-droid.org/packages/com.termux/
   - **Do NOT use Google Play version** - it's outdated

2. Open Termux and update packages:
```bash
pkg update && pkg upgrade -y
```

### 4.2 Setup Storage Access

```bash
# Grant storage permission
termux-setup-storage

# This creates ~/storage/shared linking to /sdcard
```

### 4.3 Install Dependencies

```bash
# Install required packages
pkg install -y python git cmake clang pkg-config

# Optional: For better performance
pkg install -y libopenblas  # If available
```

### 4.4 Build llama.cpp for Android

```bash
# Clone llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Build for ARM64 with optimizations
cmake -B build \
  -DLLAMA_BUILD_TESTS=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_NATIVE=OFF \
  -DLLAMA_ARM_NEON=ON

cmake --build build --config Release -j$(nproc)

# Copy binary to accessible location
cp build/bin/llama-server $PREFIX/bin/
```

### 4.5 Download Models

```bash
# Create models directory on internal storage
mkdir -p ~/storage/shared/AI-Models
cd ~/storage/shared/AI-Models

# Download tiny models for mobile
# Qwen2.5 0.5B - Very small, works well on phone
wget https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf

# TinyLlama 1.1B
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

**Note**: Downloading large files on mobile data may be expensive. Use Wi-Fi.

### 4.6 Setup NodeMesh Worker

```bash
cd /path/to/nodemesh

# Edit the script
nano scripts/start_worker_android.sh
# Change: COORDINATOR_URL="http://YOUR_TOWER_IP:11434"

# Run the worker
chmod +x scripts/start_worker_android.sh
./scripts/start_worker_android.sh
```

**To keep running in background**:
```bash
# Install termux-api (optional, for notifications)
pkg install termux-api

# Run with nohup
nohup ./scripts/start_worker_android.sh > worker.log 2>&1 &

# Check status
tail -f worker.log
```

---

## Step 5: Configure Clients

Point any Ollama-compatible client to your Tower's IP:

```
Ollama API URL: http://TOWER_IP:11434
```

### Open WebUI

```bash
# Install Open WebUI (if not already)
pip install open-webui

# Start pointing to NodeMesh
open-webui serve --ollama-url http://TOWER_IP:11434
```

Then access at http://localhost:8080

### Continue.dev (VS Code)

In `.continue/config.json`:
```json
{
  "models": [
    {
      "title": "NodeMesh",
      "provider": "ollama",
      "model": "llama3.1:8b",
      "apiBase": "http://TOWER_IP:11434"
    }
  ]
}
```

### Direct API Usage

```bash
# List available models
curl http://TOWER_IP:11434/api/tags

# Generate text
curl -X POST http://TOWER_IP:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Hello, world!",
  "stream": false
}'

# Chat
curl -X POST http://TOWER_IP:11434/api/chat -d '{
  "model": "llama3.1:8b",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ]
}'
```

---

## Troubleshooting

### Coordinator won't start

```bash
# Check if port 11434 is in use
sudo lsof -i :11434

# Kill process using port
sudo kill -9 $(sudo lsof -t -i:11434)

# Or change coordinator port
export COORDINATOR_PORT=11444
```

### Worker can't connect to coordinator

```bash
# Test connectivity
ping TOWER_IP

# Test coordinator API
curl http://TOWER_IP:11434/health

# Check firewall
sudo ufw status  # On Debian
# Allow port 11434
sudo ufw allow 11434/tcp
```

### llama-server fails to start

```bash
# Check binary exists
which llama-server

# Test manually
llama-server -m /path/to/model.gguf --port 11437

# Check for missing libraries
ldd $(which llama-server)
```

### Out of memory on worker

1. Use smaller models (1B instead of 3B)
2. Use lower quantization (Q2 instead of Q4)
3. Reduce context size in worker agent
4. Limit concurrent requests

### Android/Termux issues

```bash
# If llama-server crashes, try with fewer threads
export LLAMA_THREADS=2

# Clear Termux cache if weird errors
termux-reset

# Reinstall if needed
pkg uninstall python
pkg install python
```

---

## Monitoring

### View Dashboard

Open http://TOWER_IP:11434 in your browser to see:
- Nodes online/offline
- Current load per node
- Available models
- Request statistics

### Check Logs

```bash
# Coordinator logs (if redirected)
tail -f /path/to/coordinator.log

# Worker logs
tail -f /path/to/worker.log

# llama-server logs
# Usually visible in terminal where worker is running
```

### Health Check

```bash
# Coordinator health
curl http://TOWER_IP:11434/health

# Worker health
curl http://WORKER_IP:11436/health
```

---

## Security Considerations

This setup is designed for **trusted LAN environments**. For production:

1. **Add authentication** to coordinator API
2. **Use HTTPS** with self-signed certificates
3. **Firewall rules** - only allow mesh ports from trusted IPs
4. **VPN** for remote workers (Tailscale, WireGuard)

---

## Updating

### Update Coordinator

```bash
cd /path/to/nodemesh/coordinator
git pull  # If using git
pip install -r requirements.txt --upgrade
```

### Update Worker

```bash
cd /path/to/nodemesh/worker
pip install -r requirements.txt --upgrade
```

### Update llama.cpp

```bash
cd /path/to/llama.cpp
git pull
cmake --build build --config Release
```

---

## Next Steps

1. **Add more nodes** - Raspberry Pi, old laptops, cloud instances
2. **Model caching** - Implement model preloading on workers
3. **Queue management** - Add request queuing for busy periods
4. **Metrics** - Export Prometheus metrics for Grafana
5. **Auto-scaling** - Start/stop workers based on demand

---

## Support

For issues:
1. Check logs on all nodes
2. Verify network connectivity
3. Test individual components
4. Review this guide for common issues
