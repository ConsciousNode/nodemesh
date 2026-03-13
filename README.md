# NodeMesh - Distributed AI Inference Mesh

A distributed AI inference cluster that unifies heterogeneous hardware (Linux, Windows, Android) under a single Ollama-compatible API.

## Features

- **Ollama-Compatible API**: Drop-in replacement for Ollama - works with Open WebUI, Continue.dev, and any Ollama client
- **Cross-Platform Workers**: Runs on Linux, Windows, and Android/Termux
- **Intelligent Routing**: Automatically routes requests based on model size, node capabilities, and current load
- **Conversation Affinity**: Multi-turn conversations stay on the same node for context preservation
- **Automatic Failover**: If a node drops, requests reroute to available nodes
- **Web Dashboard**: Real-time monitoring of mesh status at http://coordinator-ip:11434
- **No Docker Required**: Runs natively on all platforms
- **Offline Capable**: No cloud dependencies after initial setup

## Quick Start

### 1. Tower (Coordinator) - Debian Linux

```bash
# 1. Ensure Ollama is running on port 11435
OLLAMA_HOST=0.0.0.0:11435 ollama serve

# 2. Start the coordinator
cd nodemesh
./scripts/start_coordinator.sh
```

### 2. Worker Nodes

**Debian Laptop:**
```bash
# Edit COORDINATOR_URL in the script first!
nano scripts/start_worker_linux.sh
./scripts/start_worker_linux.sh
```

**Windows Laptop:**
```powershell
# Edit COORDINATOR_URL in the script first!
notepad scripts\start_worker_windows.bat
.\scripts\start_worker_windows.bat
```

**Android/Termux:**
```bash
# Edit COORDINATOR_URL in the script first!
nano scripts/start_worker_android.sh
./scripts/start_worker_android.sh
```

### 3. Use It

Point any Ollama-compatible client to:
```
http://TOWER_IP:11434
```

View the dashboard at:
```
http://TOWER_IP:11434
```

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Client    │────▶│  Coordinator     │────▶│   Tower     │
│  (Any Ollama│     │  (Routing + API) │     │  (Ollama)   │
│   client)   │◀────│  Port: 11434     │◀────│  Port:11435 │
└─────────────┘     └──────────────────┘     └─────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │Linux Worker │   │Windows Worker│   │Android Worker│
    │(llama.cpp)  │   │(llama.cpp)  │   │(llama.cpp)  │
    │Port:11436   │   │Port:11436   │   │Port:11436   │
    └─────────────┘   └─────────────┘   └─────────────┘
```

## Project Structure

```
nodemesh/
├── coordinator/           # Mesh coordinator (runs on Tower)
│   ├── main.py           # FastAPI coordinator application
│   └── requirements.txt  # Python dependencies
├── worker/               # Worker agent (runs on all nodes)
│   ├── agent.py         # Worker agent application
│   └── requirements.txt # Python dependencies
├── scripts/              # Platform-specific startup scripts
│   ├── start_coordinator.sh      # Tower startup
│   ├── start_worker_linux.sh     # Debian worker
│   ├── start_worker_windows.bat  # Windows worker
│   ├── start_worker_windows.ps1  # Windows PowerShell
│   └── start_worker_android.sh   # Android/Termux worker
├── dashboard/            # Web dashboard
│   └── index.html       # Single-file dashboard
└── docs/                 # Documentation
    ├── SETUP.md         # Detailed setup instructions
    └── MODEL_DISTRIBUTION.md  # Model recommendations
```

## Hardware Requirements

| Node | Minimum | Recommended |
|------|---------|-------------|
| Coordinator | 4GB RAM, Python 3.8+ | 8GB+ RAM, Ollama installed |
| Linux Worker | 2GB RAM, Python 3.8+ | 4GB+ RAM, llama.cpp |
| Windows Worker | 2GB RAM, Python 3.8+ | 4GB+ RAM, llama.cpp |
| Android Worker | 4GB RAM, Termux | 6GB+ RAM, Termux |

## Supported Models

The mesh can run any GGUF model, but distribution depends on hardware:

- **Tower**: 7B-14B models (llama3.1, mistral, qwen2.5, phi3)
- **Laptops (4GB)**: 1B-3B models (qwen2.5-1.5b, tinyllama, phi3-mini)
- **Laptops (3GB)**: 0.5B-1.5B models (qwen2.5-0.5b, tinyllama)
- **Phone**: 0.5B-1.5B models (qwen2.5-0.5b, tinyllama)

See [MODEL_DISTRIBUTION.md](docs/MODEL_DISTRIBUTION.md) for detailed recommendations.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tags` | GET | List all available models |
| `/api/show` | POST | Show model information |
| `/api/generate` | POST | Generate completion |
| `/api/chat` | POST | Chat completion |
| `/api/embeddings` | POST | Generate embeddings |
| `/mesh/status` | GET | Mesh status and nodes |
| `/health` | GET | Health check |

All endpoints are Ollama-compatible.

## Environment Variables

### Coordinator

| Variable | Default | Description |
|----------|---------|-------------|
| `COORDINATOR_HOST` | `0.0.0.0` | Host to bind to |
| `COORDINATOR_PORT` | `11434` | Port to listen on |
| `OLLAMA_BASE_URL` | `http://localhost:11435` | Local Ollama URL |
| `HEARTBEAT_TIMEOUT` | `30` | Node timeout in seconds |

### Worker

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_NAME` | Auto-generated | Worker node name |
| `COORDINATOR_URL` | (required) | Coordinator URL |
| `MODELS_DIR` | `./models` | Path to GGUF models |
| `WORKER_PORT` | `11436` | Worker API port |
| `LLAMA_PORT` | `11437` | llama.cpp server port |

## Troubleshooting

### Coordinator won't start
```bash
# Check port availability
sudo lsof -i :11434
# Change port if needed
export COORDINATOR_PORT=11444
```

### Worker can't connect
```bash
# Test connectivity
ping COORDINATOR_IP
curl http://COordinator_IP:11434/health
```

### llama-server not found
```bash
# Build llama.cpp from source
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release
sudo cp build/bin/llama-server /usr/local/bin/
```

See [SETUP.md](docs/SETUP.md) for detailed troubleshooting.

## Security Notes

This setup is designed for **trusted LAN environments**. For production use:

1. Add API authentication
2. Use HTTPS with certificates
3. Implement firewall rules
4. Use VPN for remote workers

## Performance Tips

1. **Use appropriate quantization**: Q4 for most cases, Q2/Q3 for limited RAM
2. **Match model to hardware**: Don't run 7B on 3GB RAM
3. **Enable zRAM on Linux**: Helps with memory pressure
4. **Limit threads on mobile**: Prevents overheating
5. **Close unnecessary apps**: Free up RAM for inference

## Contributing

This is a reference implementation. Improvements welcome:
- Better load balancing algorithms
- GPU acceleration support
- Model caching/prefetching
- Metrics export (Prometheus)
- Kubernetes operator

## License

MIT License - See LICENSE file

## Acknowledgments

- [Ollama](https://ollama.com/) for the excellent API design
- [llama.cpp](https://github.com/ggerganov/llama.cpp) for efficient inference
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
