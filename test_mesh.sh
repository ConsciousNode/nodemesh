#!/bin/bash
# NodeMesh Test Script
# Verifies that the mesh is working correctly

echo "==============================================="
echo "  NodeMesh Test Suite"
echo "==============================================="
echo ""

# Configuration
COORDINATOR_URL="${COORDINATOR_URL:-http://localhost:11434}"
echo "Testing coordinator at: $COORDINATOR_URL"
echo ""

# Test 1: Health Check
echo "Test 1: Health Check"
echo "--------------------"
if curl -s "$COORDINATOR_URL/health" > /dev/null 2>&1; then
    echo "✅ Coordinator is responding"
    curl -s "$COORDINATOR_URL/health" | python3 -m json.tool 2>/dev/null || curl -s "$COORDINATOR_URL/health"
else
    echo "❌ Coordinator not responding"
    echo "   Make sure coordinator is running: ./scripts/start_coordinator.sh"
    exit 1
fi
echo ""

# Test 2: Mesh Status
echo "Test 2: Mesh Status"
echo "-------------------"
STATUS=$(curl -s "$COORDINATOR_URL/mesh/status")
if [ -n "$STATUS" ]; then
    echo "✅ Mesh status retrieved"
    echo "$STATUS" | python3 -m json.tool 2>/dev/null || echo "$STATUS"
    
    # Count nodes
    NODE_COUNT=$(echo "$STATUS" | grep -o '"node_id"' | wc -l)
    echo ""
    echo "Registered nodes: $NODE_COUNT"
else
    echo "❌ Could not retrieve mesh status"
fi
echo ""

# Test 3: List Models
echo "Test 3: List Available Models"
echo "-----------------------------"
MODELS=$(curl -s "$COORDINATOR_URL/api/tags")
if [ -n "$MODELS" ]; then
    echo "✅ Models endpoint working"
    echo "$MODELS" | python3 -m json.tool 2>/dev/null || echo "$MODELS"
else
    echo "❌ Could not retrieve models"
    echo "   Make sure Ollama is running on the Tower"
fi
echo ""

# Test 4: Simple Generation (if models available)
echo "Test 4: Test Generation (optional)"
echo "----------------------------------"
read -p "Enter a model name to test (or press Enter to skip): " TEST_MODEL

if [ -n "$TEST_MODEL" ]; then
    echo "Testing with model: $TEST_MODEL"
    echo "Sending request..."
    
    RESPONSE=$(curl -s -X POST "$COORDINATOR_URL/api/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"$TEST_MODEL\", \"prompt\": \"Say 'NodeMesh is working!'\", \"stream\": false, \"options\": {\"num_predict\": 20}}")
    
    if [ -n "$RESPONSE" ]; then
        echo "✅ Generation successful"
        echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    else
        echo "❌ Generation failed"
        echo "   Check that the model exists and workers are running"
    fi
else
    echo "Skipped"
fi
echo ""

# Summary
echo "==============================================="
echo "  Test Summary"
echo "==============================================="
echo ""
echo "Coordinator URL: $COORDINATOR_URL"
echo "Dashboard: $COORDINATOR_URL"
echo ""
echo "If all tests passed, your mesh is ready!"
echo "Point Ollama clients to: $COORDINATOR_URL"
echo ""
