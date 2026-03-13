#!/usr/bin/env python3
"""
NodeMesh Worker Agent - Cross-Platform Distributed Inference Worker
Runs on: Linux, Windows, Android/Termux

This agent:
1. Auto-detects hardware capabilities
2. Scans for available GGUF models
3. Starts llama.cpp HTTP server (or uses Ollama if available)
4. Registers with the mesh coordinator
5. Handles inference requests and streams responses
6. Sends periodic heartbeats
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading
import http.client

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nodemesh-worker")

# Global state
class WorkerState:
    def __init__(self):
        self.node_id = str(uuid.uuid4())
        self.node_name = ""
        self.coordinator_url = ""
        self.base_url = ""
        self.llama_process: Optional[subprocess.Popen] = None
        self.llama_port = 11436
        self.models_dir = ""
        self.available_models: List[Dict] = []
        self.capabilities: Dict = {}
        self.current_load = 0
        self.is_registered = False
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_heartbeat = threading.Event()
        self.platform = platform.system().lower()
        self.use_ollama = False
        self.ollama_url = "http://localhost:11434"

state = WorkerState()


def detect_platform() -> str:
    """Detect the operating system platform"""
    system = platform.system().lower()
    if system == "linux":
        # Check for Android/Termux
        if os.path.exists("/data/data/com.termux") or "ANDROID_ROOT" in os.environ:
            return "android"
        return "linux"
    elif system == "windows":
        return "windows"
    elif system == "darwin":
        return "macos"
    return system


def get_cpu_info() -> Dict:
    """Get CPU information cross-platform"""
    info = {
        "cores": os.cpu_count() or 1,
        "model": "Unknown",
        "architecture": platform.machine()
    }
    
    try:
        if state.platform in ["linux", "android"]:
            # Read from /proc/cpuinfo
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo") as f:
                    content = f.read()
                    # Extract model name
                    match = re.search(r'model name\s*:\s*(.+)', content)
                    if match:
                        info["model"] = match.group(1).strip()
                    elif "Hardware" in content:
                        hw_match = re.search(r'Hardware\s*:\s*(.+)', content)
                        if hw_match:
                            info["model"] = hw_match.group(1).strip()
        elif state.platform == "windows":
            try:
                import wmi
                c = wmi.WMI()
                for processor in c.Win32_Processor():
                    info["model"] = processor.Name
                    break
            except ImportError:
                # Fallback to wmic
                try:
                    result = subprocess.run(
                        ["wmic", "cpu", "get", "name", "/value"],
                        capture_output=True, text=True, timeout=5
                    )
                    match = re.search(r'Name=(.+)', result.stdout)
                    if match:
                        info["model"] = match.group(1).strip()
                except:
                    pass
    except Exception as e:
        logger.warning(f"Could not get CPU info: {e}")
    
    return info


def get_ram_info() -> Dict:
    """Get RAM information cross-platform"""
    info = {"total_mb": 1024, "available_mb": 512}
    
    try:
        if state.platform in ["linux", "android"]:
            # Use /proc/meminfo
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo") as f:
                    content = f.read()
                    total_match = re.search(r'MemTotal:\s*(\d+)\s*kB', content)
                    avail_match = re.search(r'MemAvailable:\s*(\d+)\s*kB', content)
                    free_match = re.search(r'MemFree:\s*(\d+)\s*kB', content)
                    
                    if total_match:
                        info["total_mb"] = int(total_match.group(1)) // 1024
                    if avail_match:
                        info["available_mb"] = int(avail_match.group(1)) // 1024
                    elif free_match:
                        info["available_mb"] = int(free_match.group(1)) // 1024
                        
            # Check for zRAM on Linux
            if state.platform == "linux" and os.path.exists("/sys/block/zram0"):
                try:
                    with open("/sys/block/zram0/disksize") as f:
                        zram_size = int(f.read().strip())
                        info["zram_mb"] = zram_size // (1024 * 1024)
                        info["total_mb"] += info.get("zram_mb", 0) // 2  # zRAM is compressed
                except:
                    pass
                    
        elif state.platform == "windows":
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                
                memStatus = MEMORYSTATUSEX()
                memStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memStatus))
                
                info["total_mb"] = memStatus.ullTotalPhys // (1024 * 1024)
                info["available_mb"] = memStatus.ullAvailPhys // (1024 * 1024)
            except:
                # Fallback to wmic
                try:
                    result = subprocess.run(
                        ["wmic", "computersystem", "get", "totalphysicalmemory", "/value"],
                        capture_output=True, text=True, timeout=5
                    )
                    match = re.search(r'TotalPhysicalMemory=(\d+)', result.stdout)
                    if match:
                        info["total_mb"] = int(match.group(1)) // (1024 * 1024)
                except:
                    pass
    except Exception as e:
        logger.warning(f"Could not get RAM info: {e}")
    
    return info


def get_gpu_info() -> Dict:
    """Detect GPU and VRAM if available"""
    info = {"has_gpu": False, "vram_mb": 0, "model": ""}
    
    try:
        if state.platform in ["linux", "android"]:
            # Try nvidia-smi for NVIDIA GPUs
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    if len(parts) >= 2:
                        info["has_gpu"] = True
                        info["model"] = parts[0].strip()
                        vram_str = parts[1].strip().replace("MiB", "").replace("MB", "").strip()
                        info["vram_mb"] = int(vram_str)
            except FileNotFoundError:
                pass
            
            # Try for Android GPU info
            if state.platform == "android":
                try:
                    result = subprocess.run(
                        ["getprop", "ro.hardware"],
                        capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0:
                        info["model"] = f"Android GPU ({result.stdout.strip()})"
                        # Assume some shared memory for GPU on Android
                        info["has_gpu"] = True
                        info["vram_mb"] = 512  # Conservative estimate
                except:
                    pass
                    
        elif state.platform == "windows":
            try:
                import wmi
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    if gpu.AdapterRAM:
                        info["has_gpu"] = True
                        info["model"] = gpu.Name
                        info["vram_mb"] = int(gpu.AdapterRAM) // (1024 * 1024)
                        break
            except ImportError:
                pass
    except Exception as e:
        logger.warning(f"Could not get GPU info: {e}")
    
    return info


def scan_models(models_dir: str) -> List[Dict]:
    """Scan directory for GGUF models and extract metadata"""
    models = []
    
    if not models_dir or not os.path.exists(models_dir):
        logger.warning(f"Models directory not found: {models_dir}")
        return models
    
    models_path = Path(models_dir)
    
    for gguf_file in models_path.glob("**/*.gguf"):
        try:
            # Extract model info from filename
            # Format often: model-name-Q4_K_M.gguf or model-name-7b-q4_0.gguf
            filename = gguf_file.stem
            
            # Try to extract parameter count
            params = 7  # default assumption
            param_match = re.search(r'(\d+)(\.[\d]+)?[bB]', filename)
            if param_match:
                params = int(float(param_match.group(1)))
            
            # Try to extract quantization
            quant = "Q4"
            quant_match = re.search(r'[qQ](\d)(_[kK]_[mMsSlL])?', filename)
            if quant_match:
                quant = f"Q{quant_match.group(1)}"
            
            # Estimate tokens per second based on hardware
            estimated_tps = estimate_tokens_per_second(params, quant)
            
            model_info = {
                "name": filename,
                "filename": str(gguf_file),
                "size_bytes": gguf_file.stat().st_size,
                "parameter_count_b": params,
                "quantization": quant,
                "estimated_tps": estimated_tps
            }
            models.append(model_info)
            logger.info(f"Found model: {filename} ({params}B, {quant}, ~{estimated_tps} tps)")
            
        except Exception as e:
            logger.warning(f"Error scanning {gguf_file}: {e}")
    
    return models


def estimate_tokens_per_second(params_b: int, quant: str) -> float:
    """Estimate tokens/second based on hardware capabilities"""
    ram_info = get_ram_info()
    gpu_info = get_gpu_info()
    cpu_info = get_cpu_info()
    
    # Base estimation factors
    base_tps = 1.0
    
    # Adjust for parameter count (larger = slower)
    if params_b <= 1:
        base_tps = 15
    elif params_b <= 3:
        base_tps = 8
    elif params_b <= 7:
        base_tps = 4
    elif params_b <= 13:
        base_tps = 1.5
    else:
        base_tps = 0.5
    
    # Adjust for quantization (lower = faster)
    q_mult = {"Q2": 1.4, "Q3": 1.2, "Q4": 1.0, "Q5": 0.85, "Q6": 0.75, "Q8": 0.6, "F16": 0.3}
    base_tps *= q_mult.get(quant.upper(), 1.0)
    
    # Hardware adjustments
    if gpu_info["has_gpu"] and gpu_info["vram_mb"] > 2048:
        # Dedicated GPU
        base_tps *= 3.0
    elif gpu_info["has_gpu"]:
        # Integrated/shared GPU
        base_tps *= 1.5
    
    # CPU adjustments
    if cpu_info["cores"] >= 8:
        base_tps *= 1.3
    elif cpu_info["cores"] <= 2:
        base_tps *= 0.6
    
    # RAM constraint check
    required_ram = params_b * 0.6 * 1024  # Rough estimate
    if ram_info["available_mb"] < required_ram:
        base_tps *= 0.3  # Will be swapping heavily
    
    # Platform adjustments
    if state.platform == "android":
        base_tps *= 0.7  # Mobile CPUs are generally slower for this workload
    
    return round(base_tps, 1)


def detect_capabilities(models_dir: str) -> Dict:
    """Detect all hardware capabilities"""
    cpu_info = get_cpu_info()
    ram_info = get_ram_info()
    gpu_info = get_gpu_info()
    
    capabilities = {
        "total_ram_mb": ram_info["total_mb"],
        "available_ram_mb": ram_info["available_mb"],
        "cpu_cores": cpu_info["cores"],
        "cpu_model": cpu_info["model"],
        "has_gpu": gpu_info["has_gpu"],
        "gpu_vram_mb": gpu_info["vram_mb"],
        "gpu_model": gpu_info["model"],
        "platform": state.platform,
        "architecture": cpu_info["architecture"]
    }
    
    return capabilities


def find_llama_server_binary() -> Optional[str]:
    """Find llama-server binary for the current platform"""
    # Common locations and names
    possible_names = ["llama-server", "llama-server.exe", "server"]
    
    # Check PATH
    for name in possible_names:
        try:
            result = subprocess.run(["which" if state.platform != "windows" else "where", name],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
        except:
            pass
    
    # Check common installation paths
    search_paths = []
    if state.platform in ["linux", "android"]:
        search_paths = [
            "./llama.cpp/build/bin/llama-server",
            "./llama-server",
            "~/llama.cpp/build/bin/llama-server",
            "/usr/local/bin/llama-server",
            os.path.expanduser("~/llama.cpp/llama-server"),
        ]
        # Termux specific
        if state.platform == "android":
            search_paths.extend([
                "/data/data/com.termux/files/usr/bin/llama-server",
                os.path.expanduser("~/llama.cpp/build/bin/llama-server"),
            ])
    elif state.platform == "windows":
        search_paths = [
            ".\\llama-server.exe",
            ".\\llama.cpp\\build\\bin\\Release\\llama-server.exe",
            "C:\\llama.cpp\\build\\bin\\Release\\llama-server.exe",
        ]
    
    for path in search_paths:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded) and os.access(expanded, os.X_OK):
            return expanded
    
    return None


def start_llama_server(models_dir: str, port: int) -> Optional[subprocess.Popen]:
    """Start llama.cpp HTTP server"""
    binary = find_llama_server_binary()
    
    if not binary:
        logger.error("llama-server binary not found. Please install llama.cpp or provide path.")
        return None
    
    logger.info(f"Using llama-server: {binary}")
    
    # Build command
    # Note: llama-server needs a model to start, we'll use the first available
    # and handle model switching via the API
    models = scan_models(models_dir)
    if not models:
        logger.error(f"No GGUF models found in {models_dir}")
        return None
    
    # Start with smallest model as default
    default_model = min(models, key=lambda m: m["size_bytes"])
    model_path = default_model["filename"]
    
    cmd = [
        binary,
        "-m", model_path,
        "--port", str(port),
        "-c", "4096",  # Context size
        "-np", "2",    # Parallel sequences
        "--host", "0.0.0.0"
    ]
    
    # Platform-specific adjustments
    if state.platform == "android":
        # Mobile optimizations
        cmd.extend(["-t", str(min(4, os.cpu_count() or 2))])  # Limit threads
        cmd.extend(["-b", "256"])  # Smaller batch size
    else:
        cmd.extend(["-t", str(os.cpu_count() or 2)])
    
    try:
        logger.info(f"Starting llama-server on port {port} with model {default_model['name']}")
        
        # Platform-specific process creation
        if state.platform == "windows":
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
        
        # Wait for server to be ready
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is None:
            logger.info("llama-server started successfully")
            return process
        else:
            stdout, stderr = process.communicate()
            logger.error(f"llama-server failed to start: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Error starting llama-server: {e}")
        return None


def check_ollama_available() -> bool:
    """Check if Ollama is running locally"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{state.ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except:
        return False


def register_with_coordinator() -> bool:
    """Register this worker with the mesh coordinator"""
    if not state.coordinator_url:
        logger.warning("No coordinator URL configured, running standalone")
        return False
    
    registration_data = {
        "node_id": state.node_id,
        "name": state.node_name,
        "host": state.base_url.split("://")[-1].split(":")[0],
        "port": state.llama_port,
        "base_url": state.base_url,
        **state.capabilities,
        "available_models": state.available_models,
        "estimated_tps": {m["name"]: m["estimated_tps"] for m in state.available_models}
    }
    
    try:
        response = httpx.post(
            f"{state.coordinator_url}/mesh/register",
            json=registration_data,
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            state.node_id = result.get("node_id", state.node_id)
            state.is_registered = True
            logger.info(f"Successfully registered with coordinator as {state.node_id}")
            return True
        else:
            logger.error(f"Registration failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Could not reach coordinator: {e}")
        return False


def send_heartbeat():
    """Send heartbeat to coordinator"""
    if not state.is_registered or not state.coordinator_url:
        return
    
    try:
        # Update available RAM
        ram_info = get_ram_info()
        
        heartbeat_data = {
            "current_load": state.current_load,
            "available_ram_mb": ram_info["available_mb"],
            "timestamp": time.time()
        }
        
        response = httpx.post(
            f"{state.coordinator_url}/mesh/heartbeat/{state.node_id}",
            json=heartbeat_data,
            timeout=5
        )
        if response.status_code != 200:
            logger.warning(f"Heartbeat failed: {response.status_code}")
    except Exception as e:
        logger.warning(f"Heartbeat error: {e}")


def heartbeat_loop():
    """Background thread for heartbeats"""
    while not state.stop_heartbeat.is_set():
        send_heartbeat()
        state.stop_heartbeat.wait(15)  # Heartbeat every 15 seconds


def start_heartbeat_thread():
    """Start the heartbeat background thread"""
    state.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    state.heartbeat_thread.start()


def cleanup():
    """Cleanup on exit"""
    logger.info("Shutting down worker...")
    state.stop_heartbeat.set()
    
    # Unregister from coordinator
    if state.is_registered and state.coordinator_url:
        try:
            httpx.post(f"{state.coordinator_url}/mesh/unregister/{state.node_id}", timeout=5)
        except:
            pass
    
    # Stop llama-server
    if state.llama_process:
        logger.info("Stopping llama-server...")
        state.llama_process.terminate()
        try:
            state.llama_process.wait(timeout=5)
        except:
            state.llama_process.kill()


# FastAPI app for local API
app = FastAPI(title="NodeMesh Worker")


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "node_id": state.node_id,
        "load": state.current_load,
        "models": len(state.available_models)
    }


@app.get("/api/tags")
async def list_models():
    """List available models (Ollama-compatible)"""
    if state.use_ollama:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{state.ollama_url}/api/tags", timeout=10)
                return resp.json()
        except:
            pass
    
    # Format like Ollama
    models = []
    for m in state.available_models:
        models.append({
            "name": m["name"],
            "model": m["name"],
            "size": m["size_bytes"],
            "digest": "local",
            "details": {
                "parameter_size": f"{m['parameter_count_b']}B",
                "quantization_level": m["quantization"]
            }
        })
    return {"models": models}


@app.post("/api/generate")
async def generate(request_data: Dict):
    """Generate completion (Ollama-compatible)"""
    import httpx
    
    model = request_data.get("model", "")
    stream = request_data.get("stream", True)
    
    state.current_load += 1
    
    try:
        if state.use_ollama:
            # Forward to Ollama
            async with httpx.AsyncClient() as client:
                if stream:
                    async def ollama_stream():
                        async with client.stream(
                            "POST",
                            f"{state.ollama_url}/api/generate",
                            json=request_data,
                            timeout=300
                        ) as response:
                            async for line in response.aiter_lines():
                                if line:
                                    yield line + "\n"
                        state.current_load -= 1
                    return StreamingResponse(ollama_stream(), media_type="application/x-ndjson")
                else:
                    resp = await client.post(f"{state.ollama_url}/api/generate", json=request_data, timeout=300)
                    return resp.json()
        
        # Use llama.cpp server
        async with httpx.AsyncClient() as client:
            if stream:
                async def llama_stream():
                    async with client.stream(
                        "POST",
                        f"http://localhost:{state.llama_port}/completion",
                        json={
                            "prompt": request_data.get("prompt", ""),
                            "stream": True,
                            "temperature": request_data.get("options", {}).get("temperature", 0.7),
                            "max_tokens": request_data.get("options", {}).get("num_predict", 2048),
                        },
                        timeout=300
                    ) as response:
                        async for line in response.aiter_lines():
                            if line:
                                # Convert llama.cpp format to Ollama format
                                try:
                                    data = json.loads(line)
                                    ollama_format = {
                                        "model": model,
                                        "created_at": datetime.now().isoformat(),
                                        "response": data.get("content", ""),
                                        "done": data.get("stop", False)
                                    }
                                    yield json.dumps(ollama_format) + "\n"
                                except:
                                    yield line + "\n"
                    state.current_load -= 1
                return StreamingResponse(llama_stream(), media_type="application/x-ndjson")
            else:
                resp = await client.post(
                    f"http://localhost:{state.llama_port}/completion",
                    json={
                        "prompt": request_data.get("prompt", ""),
                        "temperature": request_data.get("options", {}).get("temperature", 0.7),
                        "max_tokens": request_data.get("options", {}).get("num_predict", 2048),
                    },
                    timeout=300
                )
                return resp.json()
                
    except Exception as e:
        state.current_load -= 1
        raise HTTPException(status_code=502, detail=f"Inference failed: {e}")


@app.post("/api/show")
async def show_model(info_req: Dict):
    """Show model info (Ollama-compatible)"""
    model_name = info_req.get("name", "")
    
    for m in state.available_models:
        if m["name"] == model_name:
            return {
                "license": "unknown",
                "modelfile": f"FROM {m['filename']}",
                "parameters": f"{m['parameter_count_b']}B",
                "template": "{{ .Prompt }}",
                "details": {
                    "parameter_size": f"{m['parameter_count_b']}B",
                    "quantization_level": m["quantization"]
                }
            }
    
    raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")


from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="NodeMesh Worker Agent")
    parser.add_argument("--name", default="", help="Node name (auto-generated if empty)")
    parser.add_argument("--coordinator", default="", help="Coordinator URL (e.g., http://192.168.1.100:11434)")
    parser.add_argument("--models-dir", default="./models", help="Directory containing GGUF models")
    parser.add_argument("--port", type=int, default=11436, help="Port for worker API")
    parser.add_argument("--llama-port", type=int, default=11437, help="Port for llama.cpp server")
    parser.add_argument("--use-ollama", action="store_true", help="Use local Ollama instead of llama.cpp")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    
    args = parser.parse_args()
    
    # Detect platform
    state.platform = detect_platform()
    logger.info(f"Detected platform: {state.platform}")
    
    # Set configuration
    state.node_name = args.name or f"{state.platform}-{uuid.uuid4().hex[:8]}"
    state.coordinator_url = args.coordinator
    state.llama_port = args.llama_port
    state.use_ollama = args.use_ollama
    state.ollama_url = args.ollama_url
    state.models_dir = os.path.expanduser(args.models_dir)
    state.base_url = f"http://{args.host}:{args.port}"
    
    # Detect capabilities
    logger.info("Detecting hardware capabilities...")
    state.capabilities = detect_capabilities(state.models_dir)
    logger.info(f"Capabilities: {json.dumps(state.capabilities, indent=2)}")
    
    # Scan for models
    logger.info(f"Scanning for models in {state.models_dir}...")
    state.available_models = scan_models(state.models_dir)
    logger.info(f"Found {len(state.available_models)} models")
    
    # Check for Ollama if requested
    if state.use_ollama:
        if check_ollama_available():
            logger.info("Ollama detected and will be used")
        else:
            logger.warning("Ollama not available, falling back to llama.cpp")
            state.use_ollama = False
    
    # Start llama.cpp server if needed
    if not state.use_ollama:
        state.llama_process = start_llama_server(state.models_dir, state.llama_port)
        if not state.llama_process:
            logger.error("Failed to start inference server. Exiting.")
            sys.exit(1)
    
    # Register with coordinator
    if state.coordinator_url:
        if register_with_coordinator():
            start_heartbeat_thread()
        else:
            logger.warning("Running in standalone mode (no coordinator)")
    
    # Setup cleanup
    import atexit
    atexit.register(cleanup)
    
    # Start worker API
    logger.info(f"Starting worker API on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
