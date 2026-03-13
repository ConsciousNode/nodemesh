# NodeMesh Quick Start Guide

Get your distributed AI mesh running in 5 minutes.

## Prerequisites Checklist

- [ ] All devices on same network
- [ ] Tower has Ollama installed
- [ ] Python 3.8+ on all nodes
- [ ] Know your Tower's IP address

## 1-Minute Setup (Tower)

```bash
cd nodemesh
./scripts/start_coordinator.sh
```

Note your Tower's IP:
```bash
hostname -I | awk '{print $1}'
# Example output: 192.168.1.100
```

## 1-Minute Setup (Each Worker)

### Edit the script (replace with your Tower's IP):

**Linux:**
```bash
sed -i 's/192.168.1.100/YOUR_TOWER_IP/g' scripts/start_worker_linux.sh
./scripts/start_worker_linux.sh
```

**Windows (PowerShell):**
```powershell
(Get-Content scripts\start_worker_windows.ps1) -replace '192.168.1.100', 'YOUR_TOWER_IP' | Set-Content scripts\start_worker_windows.ps1
.\scripts\start_worker_windows.ps1
```

**Android (Termux):**
```bash
sed -i 's/192.168.1.100/YOUR_TOWER_IP/g' scripts/start_worker_android.sh
./scripts/start_worker_android.sh
```

## Verify It's Working

```bash
# List all models in the mesh
curl http://TOWER_IP:11434/api/tags

# Check mesh status
curl http://TOWER_IP:11434/mesh/status

# Generate text
curl -X POST http://TOWER_IP:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Hello from NodeMesh!",
  "stream": false
}'
```

Open http://TOWER_IP:11434 in browser for dashboard.

## Connect Your Tools

### Open WebUI
```bash
open-webui serve --ollama-url http://TOWER_IP:11434
```

### Continue.dev (VS Code)
```json
{
  "models": [{
    "title": "NodeMesh",
    "provider": "ollama",
    "model": "llama3.1:8b",
    "apiBase": "http://TOWER_IP:11434"
  }]
}
```

### AnythingLLM
Set Ollama Base URL to: `http://TOWER_IP:11434`

## Common Issues

| Problem | Solution |
|---------|----------|
| Port in use | `export COORDINATOR_PORT=11444` |
| Can't connect | Check firewall: `sudo ufw allow 11434/tcp` |
| llama-server not found | Build llama.cpp first (see SETUP.md) |
| Out of memory | Use smaller models (1B instead of 7B) |

## Next Steps

1. Download models (see MODEL_DISTRIBUTION.md)
2. Add more devices to the mesh
3. Configure client tools
4. Monitor via dashboard

## One-Line Status Check

```bash
curl -s http://TOWER_IP:11434/mesh/status | python3 -m json.tool
```
