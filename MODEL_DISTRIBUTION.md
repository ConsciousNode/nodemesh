# NodeMesh Model Distribution Map

Recommended model distribution across your heterogeneous hardware for optimal performance.

## Hardware Summary

| Node | Platform | CPU | RAM | GPU | Role |
|------|----------|-----|-----|-----|------|
| Tower | Debian Linux | Sandy Bridge | 12GB DDR3 + zRAM | 1GB VRAM | Coordinator + Primary Inference |
| Debian Laptop | Debian 13 | Core2Duo | 3GB | None | Lightweight Worker |
| Windows Laptop | Windows 11 | Core i3 | 4GB | None | Lightweight Worker |
| Phone | Android/Termux | Snapdragon 855+ | 8GB (shared) | Adreno 640 | Mobile Worker |

## Model Size Guidelines

### VRAM/RAM Requirements by Quantization

| Model Size | Q2_K | Q3_K | Q4_K | Q5_K | Q6_K | Q8_0 | F16 |
|------------|------|------|------|------|------|------|-----|
| 0.5B | 250MB | 300MB | 400MB | 450MB | 500MB | 600MB | 1GB |
| 1B | 500MB | 600MB | 800MB | 900MB | 1GB | 1.2GB | 2GB |
| 3B | 1.2GB | 1.5GB | 2GB | 2.3GB | 2.6GB | 3GB | 6GB |
| 7B | 2.8GB | 3.5GB | 4.5GB | 5.2GB | 6GB | 7GB | 14GB |
| 13B | 5GB | 6.5GB | 8GB | 9.5GB | 11GB | 13GB | 26GB |

*Includes ~20% overhead for context and KV cache*

---

## Recommended Model Distribution

### Tower (Debian Linux) - Primary Node

**Capabilities**: 12GB RAM + zRAM (~16GB effective), 1GB GPU VRAM

**Recommended Models**:

| Model | Size | Quant | VRAM Needed | Use Case |
|-------|------|-------|-------------|----------|
| llama3.1 | 8B | Q4_K_M | ~5.5GB | General chat, coding |
| mistral | 7B | Q4_K_M | ~5GB | Fast general purpose |
| qwen2.5 | 7B | Q4_K_M | ~5GB | Multilingual, reasoning |
| phi3 | 14B | Q4_K_M | ~10GB | High quality, slower |
| qwen2.5 | 14B | Q4_K_M | ~10GB | Advanced reasoning |
| nomic-embed-text | - | - | ~500MB | Embeddings, RAG |

**Performance Estimates**:
- 7B Q4: ~8-12 tokens/sec (CPU), ~15-25 tokens/sec (GPU if offloaded)
- 8B Q4: ~6-10 tokens/sec (CPU)
- 14B Q4: ~3-5 tokens/sec (CPU)

**Notes**:
- With 1GB VRAM, GPU offloading is limited (~2-3 layers)
- zRAM helps but adds compression overhead
- Best for 7B-8B models, 14B will be slower but functional

---

### Debian Laptop (Core2Duo, 3GB RAM)

**Capabilities**: 3GB RAM, no GPU, older CPU (SSE2 only)

**Recommended Models**:

| Model | Size | Quant | RAM Needed | Expected tps |
|-------|------|-------|------------|--------------|
| qwen2.5 | 0.5B | Q4_K_M | ~400MB | 15-25 tps |
| qwen2.5 | 1.5B | Q4_K_M | ~1.2GB | 8-12 tps |
| tinyllama | 1.1B | Q4_K_M | ~900MB | 10-15 tps |
| phi3 | 3.8B | Q3_K_M | ~2GB | 3-5 tps |
| phi3 | 3.8B | Q2_K | ~1.5GB | 4-6 tps |

**Avoid**:
- 7B models (will cause heavy swapping)
- Q5+ quantizations (waste of limited RAM)
- Models requiring AVX (build llama.cpp with SSE2 only)

**Notes**:
- Build llama.cpp with `-DLLAMA_AVX=OFF -DLLAMA_SSE2=ON`
- Use Q2 or Q3 for 3B models to stay within RAM
- Expect slower performance due to Core2Duo architecture
- Good for: simple Q&A, basic summarization, embeddings

---

### Windows Laptop (Core i3, 4GB RAM)

**Capabilities**: 4GB RAM, no GPU, newer CPU (AVX support)

**Recommended Models**:

| Model | Size | Quant | RAM Needed | Expected tps |
|-------|------|-------|------------|--------------|
| qwen2.5 | 0.5B | Q4_K_M | ~400MB | 20-30 tps |
| qwen2.5 | 1.5B | Q4_K_M | ~1.2GB | 12-18 tps |
| tinyllama | 1.1B | Q4_K_M | ~900MB | 15-22 tps |
| phi3 | 3.8B | Q4_K_M | ~2.5GB | 5-8 tps |
| gemma2 | 2B | Q4_K_M | ~1.5GB | 8-12 tps |

**Avoid**:
- 7B models (will cause swapping)
- Running multiple models simultaneously

**Notes**:
- AVX support gives better performance than Core2Duo
- Can handle slightly larger models
- Good for: general chat, code completion, light RAG

---

### Android Phone (OnePlus 7T Pro 5G, Termux)

**Capabilities**: 8GB RAM (shared with GPU), Snapdragon 855+ (ARM64), Adreno 640 GPU

**Recommended Models**:

| Model | Size | Quant | RAM Needed | Expected tps |
|-------|------|-------|------------|--------------|
| qwen2.5 | 0.5B | Q4_K_M | ~400MB | 10-20 tps |
| qwen2.5 | 1.5B | Q4_K_M | ~1.2GB | 5-10 tps |
| tinyllama | 1.1B | Q4_K_M | ~900MB | 8-15 tps |
| stablelm2 | 1.6B | Q4_K_M | ~1.2GB | 6-12 tps |

**Avoid**:
- 3B+ models (will be very slow and drain battery)
- F16 quantization (wastes RAM)
- Continuous operation (battery drain)

**Notes**:
- Build llama.cpp with ARM NEON optimizations
- Use `-t 4` to limit threads (prevents overheating)
- Monitor battery temperature
- Good for: emergency inference, edge computing, offline use

---

## Model Download Commands

### Tower (via Ollama)

```bash
# Large models
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull qwen2.5:7b
ollama pull phi3:14b
ollama pull qwen2.5:14b
ollama pull nomic-embed-text

# Optional smaller models for testing
ollama pull llama3.2:3b
ollama pull qwen2.5:3b
```

### Workers (via wget/curl)

```bash
# Navigate to models directory
cd ~/GGUF-Models  # Linux/Windows
# or
cd ~/storage/shared/AI-Models  # Android

# Qwen2.5 0.5B (all nodes)
wget https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf

# Qwen2.5 1.5B (all nodes)
wget https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf

# TinyLlama 1.1B (all nodes)
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

# Phi-3 Mini 3.8B (Tower, Windows Laptop)
wget https://huggingface.co/bartowski/Phi-3.1-mini-4k-instruct-GGUF/resolve/main/Phi-3.1-mini-4k-instruct-Q4_K_M.gguf

# Phi-3 Mini 3.8B Q3 (Debian Laptop - limited RAM)
wget https://huggingface.co/bartowski/Phi-3.1-mini-4k-instruct-GGUF/resolve/main/Phi-3.1-mini-4k-instruct-Q3_K_M.gguf

# Gemma 2 2B (Windows Laptop)
wget https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf

# StableLM 2 1.6B (Android)
wget https://huggingface.co/TheBloke/stablelm-2-1_6b-chat-GGUF/resolve/main/stablelm-2-1_6b-chat.Q4_K_M.gguf
```

---

## Routing Strategy

The coordinator uses this logic to route requests:

### 1. Model Size Check

```python
if model_size >= 7B:
    route_to = "Tower"  # Only Tower can handle these
    
elif model_size >= 3B:
    route_to = ["Tower", "Windows Laptop"]  # Capable nodes
    
else:  # 1B and smaller
    route_to = ["Tower", "Debian Laptop", "Windows Laptop", "Phone"]
```

### 2. Load Balancing

```python
# Among capable nodes, select based on:
- Current active requests (lower is better)
- Estimated tokens/sec (higher is better)
- Last used for this conversation (stickiness)
```

### 3. Failover

```python
if selected_node_fails:
    # Retry on next capable node
    # If all workers fail, fallback to Tower's Ollama
    # If Tower fails, return error
```

---

## Example Request Flows

### Scenario 1: 7B Model Request

```
User Request: "Explain quantum computing" with llama3.1:8b

1. Coordinator checks: 8B requires significant RAM
2. Only Tower can handle this
3. Request routed to Tower's Ollama
4. Response streamed back to user
```

### Scenario 2: 1.5B Model Request

```
User Request: "Summarize this text" with qwen2.5:1.5b

1. Coordinator checks: 1.5B can run on any node
2. Check current loads:
   - Tower: 2 active requests
   - Windows Laptop: 0 active requests
   - Debian Laptop: 1 active request
   - Phone: offline
3. Route to Windows Laptop (lowest load)
4. Response streamed back
```

### Scenario 3: Multi-turn Conversation

```
Turn 1: User asks question with qwen2.5:1.5b
        → Routed to Windows Laptop
        
Turn 2: User follows up
        → Same conversation_id provided
        → Routed to Windows Laptop (conversation affinity)
        → Context preserved
        
Turn 3: Windows Laptop goes offline
        → Request fails
        → Coordinator retries on Debian Laptop
        → Context lost, but request succeeds
```

---

## Performance Optimization Tips

### For Tower

1. **Enable zRAM** (already done based on hardware spec):
   ```bash
   sudo modprobe zram
   echo 4G | sudo tee /sys/block/zram0/disksize
   sudo mkswap /dev/zram0
   sudo swapon /dev/zram0
   ```

2. **Use GPU offloading** (limited with 1GB VRAM):
   ```bash
   # In Ollama, set in Modelfile
   PARAMETER num_gpu 20  # Offload 20 layers if possible
   ```

3. **Limit concurrent requests**:
   ```bash
   export OLLAMA_NUM_PARALLEL=2
   ```

### For Laptops

1. **Build with appropriate CPU flags**:
   - Debian Laptop (Core2Duo): `-DLLAMA_AVX=OFF -DLLAMA_SSE2=ON`
   - Windows Laptop (Core i3): `-DLLAMA_AVX=ON -DLLAMA_AVX2=OFF`

2. **Use appropriate thread count**:
   ```bash
   # Don't exceed physical cores
   -t 2  # For dual-core
   ```

3. **Close other applications** to free RAM

### For Android

1. **Limit threads to prevent overheating**:
   ```bash
   -t 4  # Snapdragon 855+ has 8 cores, use half
   ```

2. **Use smaller batch sizes**:
   ```bash
   -b 256  # Instead of default 2048
   ```

3. **Monitor temperature**:
   ```bash
   # In Termux
   cat /sys/class/thermal/thermal_zone*/temp
   ```

---

## Quick Reference: What Runs Where

| Model | Tower | Win Laptop | Deb Laptop | Phone |
|-------|-------|------------|------------|-------|
| llama3.1 8B | ✅ Fast | ❌ No | ❌ No | ❌ No |
| mistral 7B | ✅ Fast | ❌ No | ❌ No | ❌ No |
| qwen2.5 7B | ✅ Fast | ❌ No | ❌ No | ❌ No |
| phi3 14B | ⚠️ Slow | ❌ No | ❌ No | ❌ No |
| phi3 3.8B | ✅ Fast | ✅ Good | ⚠️ Slow | ❌ No |
| qwen2.5 3B | ✅ Fast | ✅ Good | ✅ Slow | ❌ No |
| qwen2.5 1.5B | ✅ Very Fast | ✅ Fast | ✅ Good | ✅ Slow |
| tinyllama 1.1B | ✅ Very Fast | ✅ Fast | ✅ Good | ✅ Good |
| qwen2.5 0.5B | ✅ Very Fast | ✅ Very Fast | ✅ Fast | ✅ Fast |

**Legend**: ✅ Good fit | ⚠️ Works but slow | ❌ Won't run

---

## Updating Models

### Check for updates monthly:

```bash
# Tower (Ollama)
ollama list
ollama pull llama3.1:8b  # Updates to latest version

# Workers (Manual)
# Check HuggingFace for new GGUF releases
# Re-download with wget, replacing old files
```

### Model cleanup:

```bash
# Remove old versions to save space
# Tower
ollama rm llama3.1:8b-old-tag

# Workers
rm ~/GGUF-Models/old-model-version.gguf
```
