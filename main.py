#!/usr/bin/env python3
"""
NodeMesh Coordinator - Distributed AI Inference Mesh Controller
Runs on the Tower (Anchor node) - Debian Linux

This is the central router and registry for the distributed inference mesh.
Exposes an Ollama-compatible REST API for seamless client integration.
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Any
import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nodemesh-coordinator")

# Configuration
COORDINATOR_HOST = os.getenv("COORDINATOR_HOST", "0.0.0.0")
COORDINATOR_PORT = int(os.getenv("COORDINATOR_PORT", "11434"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")  # Real Ollama runs here
HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", "30"))  # seconds
DEFAULT_TIMEOUT = 300  # 5 minutes for generation requests


@dataclass
class NodeCapabilities:
    """Hardware and software capabilities of a worker node"""
    total_ram_mb: int
    available_ram_mb: int
    cpu_cores: int
    cpu_model: str
    has_gpu: bool
    gpu_vram_mb: int = 0
    gpu_model: str = ""
    platform: str = ""  # linux, windows, android
    available_models: List[Dict] = field(default_factory=list)
    estimated_tps: Dict[str, float] = field(default_factory=dict)  # tokens per second by model
    
    def can_run_model(self, model_size_params: int, quantization: str = "Q4") -> bool:
        """Check if this node can run a model of given size"""
        # Rough VRAM/RAM estimation: ~0.5-0.8GB per billion params for Q4
        q_mult = {"Q2": 0.4, "Q3": 0.5, "Q4": 0.6, "Q5": 0.7, "Q6": 0.8, "Q8": 1.0, "F16": 2.0}
        mult = q_mult.get(quantization.upper(), 0.6)
        required_mb = int(model_size_params * mult * 1024)
        
        # Need buffer for context and overhead
        required_with_buffer = int(required_mb * 1.3)
        
        if self.has_gpu and self.gpu_vram_mb > 0:
            return self.gpu_vram_mb >= required_mb and self.available_ram_mb >= required_mb * 0.2
        return self.available_ram_mb >= required_with_buffer


@dataclass
class MeshNode:
    """Represents a worker node in the mesh"""
    node_id: str
    name: str
    host: str
    port: int
    base_url: str
    capabilities: NodeCapabilities
    last_heartbeat: float
    current_load: int = 0  # Number of active requests
    total_requests: int = 0
    is_online: bool = True
    registered_at: float = field(default_factory=time.time)
    
    def is_alive(self) -> bool:
        return time.time() - self.last_heartbeat < HEARTBEAT_TIMEOUT


@dataclass
class ConversationState:
    """Tracks conversation context for multi-turn interactions"""
    conversation_id: str
    messages: List[Dict] = field(default_factory=list)
    preferred_node: Optional[str] = None  # Node that handled last turn
    model: str = ""
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


# Global state
class MeshState:
    def __init__(self):
        self.nodes: Dict[str, MeshNode] = {}
        self.conversations: Dict[str, ConversationState] = {}
        self.request_routes: Dict[str, str] = {}  # request_id -> node_id
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "rerouted_requests": 0
        }
    
    def get_healthy_nodes(self) -> List[MeshNode]:
        """Get all nodes that are currently responsive"""
        healthy = []
        for node in self.nodes.values():
            if node.is_alive() and node.is_online:
                healthy.append(node)
        return healthy
    
    def select_node_for_model(self, model: str, conversation_id: Optional[str] = None) -> Optional[MeshNode]:
        """Intelligent node selection based on model requirements and load"""
        healthy = self.get_healthy_nodes()
        if not healthy:
            return None
        
        # Extract model size from name (e.g., "llama3.2:3b" -> 3)
        size_match = re.search(r'(\d+)(\.[\d]+)?[bB]', model)
        model_size = int(size_match.group(1)) if size_match else 7
        
        # Check for Q quantization
        q_match = re.search(r'[qQ](\d)', model)
        quant = f"Q{q_match.group(1)}" if q_match else "Q4"
        
        # If conversation exists, prefer same node for continuity
        if conversation_id and conversation_id in self.conversations:
            conv = self.conversations[conversation_id]
            if conv.preferred_node and conv.preferred_node in self.nodes:
                node = self.nodes[conv.preferred_node]
                if node.is_alive() and node.capabilities.can_run_model(model_size, quant):
                    return node
        
        # Filter nodes that can run this model
        capable_nodes = [
            n for n in healthy 
            if n.capabilities.can_run_model(model_size, quant)
        ]
        
        if not capable_nodes:
            # Fallback: try Tower node (should always be capable or have Ollama)
            tower = next((n for n in healthy if "tower" in n.name.lower()), None)
            if tower:
                return tower
            return None
        
        # Select node with lowest load (simple round-robin-ish)
        capable_nodes.sort(key=lambda n: (n.current_load, -n.capabilities.estimated_tps.get(model, 0)))
        return capable_nodes[0]
    
    def cleanup_stale_conversations(self, max_age_hours: int = 24):
        """Remove old conversation states"""
        now = time.time()
        stale = [
            cid for cid, conv in self.conversations.items()
            if now - conv.last_accessed > max_age_hours * 3600
        ]
        for cid in stale:
            del self.conversations[cid]


state = MeshState()


# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("NodeMesh Coordinator starting...")
    asyncio.create_task(health_check_loop())
    asyncio.create_task(cleanup_loop())
    yield
    # Shutdown
    logger.info("NodeMesh Coordinator shutting down...")


app = FastAPI(
    title="NodeMesh Coordinator",
    description="Distributed AI Inference Mesh - Ollama-compatible API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Background tasks
async def health_check_loop():
    """Periodic health check of all nodes"""
    while True:
        await asyncio.sleep(10)
        for node_id, node in list(state.nodes.items()):
            if not node.is_alive():
                logger.warning(f"Node {node.name} ({node_id}) appears offline")
                node.is_online = False
                
                # Failover: reroute any pending requests
                for req_id, routed_node in list(state.request_routes.items()):
                    if routed_node == node_id:
                        state.stats["rerouted_requests"] += 1


async def cleanup_loop():
    """Periodic cleanup tasks"""
    while True:
        await asyncio.sleep(3600)  # Every hour
        state.cleanup_stale_conversations()


# Worker Node Registration API
@app.post("/mesh/register")
async def register_node(node_info: Dict):
    """Worker nodes call this to register with the mesh"""
    node_id = node_info.get("node_id") or str(uuid.uuid4())
    
    capabilities = NodeCapabilities(
        total_ram_mb=node_info.get("total_ram_mb", 0),
        available_ram_mb=node_info.get("available_ram_mb", 0),
        cpu_cores=node_info.get("cpu_cores", 1),
        cpu_model=node_info.get("cpu_model", "Unknown"),
        has_gpu=node_info.get("has_gpu", False),
        gpu_vram_mb=node_info.get("gpu_vram_mb", 0),
        gpu_model=node_info.get("gpu_model", ""),
        platform=node_info.get("platform", "unknown"),
        available_models=node_info.get("available_models", []),
        estimated_tps=node_info.get("estimated_tps", {})
    )
    
    node = MeshNode(
        node_id=node_id,
        name=node_info.get("name", f"node-{node_id[:8]}"),
        host=node_info.get("host", "localhost"),
        port=node_info.get("port", 11436),
        base_url=node_info.get("base_url", f"http://{node_info.get('host', 'localhost')}:{node_info.get('port', 11436)}"),
        capabilities=capabilities,
        last_heartbeat=time.time()
    )
    
    state.nodes[node_id] = node
    logger.info(f"Node registered: {node.name} ({node.host}:{node.port}) - RAM: {capabilities.total_ram_mb}MB, GPU: {capabilities.gpu_model or 'None'})")
    
    return {"status": "registered", "node_id": node_id}


@app.post("/mesh/heartbeat/{node_id}")
async def node_heartbeat(node_id: str, heartbeat_data: Dict):
    """Worker nodes send periodic heartbeats"""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not registered")
    
    node = state.nodes[node_id]
    node.last_heartbeat = time.time()
    node.is_online = True
    node.current_load = heartbeat_data.get("current_load", 0)
    node.capabilities.available_ram_mb = heartbeat_data.get("available_ram_mb", node.capabilities.available_ram_mb)
    
    return {"status": "ok"}


@app.post("/mesh/unregister/{node_id}")
async def unregister_node(node_id: str):
    """Worker nodes call this to gracefully exit"""
    if node_id in state.nodes:
        node = state.nodes[node_id]
        node.is_online = False
        logger.info(f"Node unregistered: {node.name}")
        return {"status": "unregistered"}
    raise HTTPException(status_code=404, detail="Node not found")


# Ollama-Compatible API Endpoints
@app.get("/api/tags")
async def list_models():
    """List all available models across the mesh (Ollama-compatible)"""
    all_models = {}
    
    # First, try to get models from local Ollama on Tower
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for model in data.get("models", []):
                    model_name = model.get("name", "")
                    all_models[model_name] = model
                    all_models[model_name]["nodes"] = ["tower-local"]
    except Exception as e:
        logger.warning(f"Could not reach local Ollama: {e}")
    
    # Add models from worker nodes
    for node in state.get_healthy_nodes():
        for model in node.capabilities.available_models:
            model_name = model.get("name", "")
            if model_name in all_models:
                if "nodes" not in all_models[model_name]:
                    all_models[model_name]["nodes"] = []
                all_models[model_name]["nodes"].append(node.name)
            else:
                all_models[model_name] = model
                all_models[model_name]["nodes"] = [node.name]
    
    return {"models": list(all_models.values())}


@app.post("/api/show")
async def show_model(info_req: Dict):
    """Show model information (Ollama-compatible)"""
    model = info_req.get("name", "")
    
    # Try local Ollama first
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/show", json=info_req, timeout=10)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Local Ollama show failed: {e}")
    
    # Find a node that has this model
    for node in state.get_healthy_nodes():
        for m in node.capabilities.available_models:
            if m.get("name") == model:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(f"{node.base_url}/api/show", json=info_req, timeout=10)
                        if resp.status_code == 200:
                            return resp.json()
                except:
                    continue
    
    raise HTTPException(status_code=404, detail=f"Model '{model}' not found")


async def stream_from_node(node: MeshNode, request_data: Dict, request_id: str) -> AsyncGenerator[str, None]:
    """Stream response from a worker node"""
    try:
        node.current_load += 1
        state.request_routes[request_id] = node.node_id
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{node.base_url}/api/generate",
                json=request_data,
                timeout=DEFAULT_TIMEOUT
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        yield line + "\n"
        
        state.stats["successful_requests"] += 1
        
    except Exception as e:
        logger.error(f"Error streaming from {node.name}: {e}")
        state.stats["failed_requests"] += 1
        
        # Try failover to another node
        failover_node = state.select_node_for_model(request_data.get("model", ""))
        if failover_node and failover_node.node_id != node.node_id:
            logger.info(f"Failing over to {failover_node.name}")
            state.stats["rerouted_requests"] += 1
            async for chunk in stream_from_node(failover_node, request_data, request_id):
                yield chunk
        else:
            yield json.dumps({"error": f"Node failed and no failover available: {e}"}) + "\n"
    finally:
        node.current_load = max(0, node.current_load - 1)
        if request_id in state.request_routes:
            del state.request_routes[request_id]


@app.post("/api/generate")
async def generate(request_data: Dict, background_tasks: BackgroundTasks):
    """Generate completion (Ollama-compatible)"""
    model = request_data.get("model", "")
    stream = request_data.get("stream", True)
    conversation_id = request_data.get("options", {}).get("conversation_id")
    
    state.stats["total_requests"] += 1
    request_id = str(uuid.uuid4())
    
    # Select best node for this request
    selected_node = state.select_node_for_model(model, conversation_id)
    
    if not selected_node:
        # Fallback to local Ollama
        logger.info(f"No worker node available, using local Ollama for {model}")
        try:
            async with httpx.AsyncClient() as client:
                if stream:
                    async def local_stream():
                        async with client.stream(
                            "POST",
                            f"{OLLAMA_BASE_URL}/api/generate",
                            json=request_data,
                            timeout=DEFAULT_TIMEOUT
                        ) as response:
                            async for line in response.aiter_lines():
                                if line:
                                    yield line + "\n"
                    return StreamingResponse(local_stream(), media_type="application/x-ndjson")
                else:
                    resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=request_data, timeout=DEFAULT_TIMEOUT)
                    return resp.json()
        except Exception as e:
            logger.error(f"Local Ollama also failed: {e}")
            raise HTTPException(status_code=503, detail="No inference nodes available")
    
    logger.info(f"Routing request {request_id[:8]} for {model} to {selected_node.name}")
    
    # Update conversation state if applicable
    if conversation_id:
        if conversation_id not in state.conversations:
            state.conversations[conversation_id] = ConversationState(conversation_id=conversation_id, model=model)
        conv = state.conversations[conversation_id]
        conv.preferred_node = selected_node.node_id
        conv.last_accessed = time.time()
    
    if stream:
        return StreamingResponse(
            stream_from_node(selected_node, request_data, request_id),
            media_type="application/x-ndjson"
        )
    else:
        # Non-streaming response
        try:
            selected_node.current_load += 1
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{selected_node.base_url}/api/generate",
                    json=request_data,
                    timeout=DEFAULT_TIMEOUT
                )
                selected_node.current_load -= 1
                return resp.json()
        except Exception as e:
            selected_node.current_load = max(0, selected_node.current_load - 1)
            raise HTTPException(status_code=502, detail=f"Node request failed: {e}")


@app.post("/api/chat")
async def chat(request_data: Dict):
    """Chat completion with conversation history (Ollama-compatible)"""
    model = request_data.get("model", "")
    messages = request_data.get("messages", [])
    stream = request_data.get("stream", True)
    
    # Extract or create conversation ID from options
    options = request_data.get("options", {})
    conversation_id = options.get("conversation_id")
    
    if not conversation_id and messages:
        # Generate from message hash for consistency
        import hashlib
        msg_str = json.dumps(messages[-3:], sort_keys=True)  # Last 3 messages
        conversation_id = hashlib.md5(msg_str.encode()).hexdigest()[:16]
        options["conversation_id"] = conversation_id
        request_data["options"] = options
    
    # Reuse generate logic - Ollama's chat is similar to generate with message formatting
    return await generate(request_data, BackgroundTasks())


@app.post("/api/embeddings")
async def embeddings(request_data: Dict):
    """Generate embeddings - can be distributed to any capable node"""
    model = request_data.get("model", "")
    
    # Embeddings are lightweight, can go to any node
    healthy = state.get_healthy_nodes()
    
    # Prefer nodes with embedding models
    for node in healthy:
        if any("embed" in m.get("name", "").lower() for m in node.capabilities.available_models):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{node.base_url}/api/embeddings", json=request_data, timeout=60)
                    if resp.status_code == 200:
                        return resp.json()
            except:
                continue
    
    # Fallback to local Ollama
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/embeddings", json=request_data, timeout=60)
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No embedding service available: {e}")


# Mesh Status API
@app.get("/mesh/status")
async def mesh_status():
    """Get current mesh status for dashboard"""
    return {
        "coordinator": {
            "version": "1.0.0",
            "uptime": time.time(),  # Simplified - would track actual start time
            "stats": state.stats
        },
        "nodes": [
            {
                "node_id": n.node_id,
                "name": n.name,
                "host": n.host,
                "is_online": n.is_online and n.is_alive(),
                "current_load": n.current_load,
                "total_requests": n.total_requests,
                "capabilities": {
                    "total_ram_mb": n.capabilities.total_ram_mb,
                    "available_ram_mb": n.capabilities.available_ram_mb,
                    "cpu_cores": n.capabilities.cpu_cores,
                    "cpu_model": n.capabilities.cpu_model,
                    "has_gpu": n.capabilities.has_gpu,
                    "gpu_vram_mb": n.capabilities.gpu_vram_mb,
                    "gpu_model": n.capabilities.gpu_model,
                    "platform": n.capabilities.platform,
                    "model_count": len(n.capabilities.available_models)
                },
                "last_heartbeat": n.last_heartbeat
            }
            for n in state.nodes.values()
        ],
        "conversations": len(state.conversations),
        "active_routes": len(state.request_routes)
    }


@app.get("/")
async def root():
    """Serve dashboard HTML"""
    dashboard_path = os.path.join(os.path.dirname(__file__), "../dashboard/index.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path) as f:
            return HTMLResponse(content=f.read())
    return {"message": "NodeMesh Coordinator Running", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "nodes_online": len(state.get_healthy_nodes())}


if __name__ == "__main__":
    logger.info(f"Starting NodeMesh Coordinator on {COORDINATOR_HOST}:{COORDINATOR_PORT}")
    logger.info(f"Local Ollama expected at: {OLLAMA_BASE_URL}")
    uvicorn.run(app, host=COORDINATOR_HOST, port=COORDINATOR_PORT, log_level="info")
