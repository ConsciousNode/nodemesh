# NodeMesh Coordinator Dockerfile
# Builds a containerized version of the mesh coordinator

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create dashboard directory and copy (if building from coordinator dir)
RUN mkdir -p /app/dashboard

# Expose coordinator port
EXPOSE 11434

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:11434/health || exit 1

# Run the coordinator
CMD ["python", "main.py"]
