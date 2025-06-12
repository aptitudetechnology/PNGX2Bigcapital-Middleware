# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY middleware.py .
COPY config.ini .

# Create logs directory
RUN mkdir -p /app/logs

# Create non-root user
RUN useradd -m -u 1000 middleware && \
    chown -R middleware:middleware /app
USER middleware

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

ENTRYPOINT ["python", "middleware.py"]

---

# requirements.txt
requests>=2.31.0
configparser>=6.0.0

---

# docker-compose.yml
version: '3.8'

services:
  paperless-bigcapital-middleware:
    build: .
    container_name: paperless-bigcapital-middleware
    restart: unless-stopped
    volumes:
      - ./config.ini:/app/config.ini:ro
      - ./logs:/app/logs
    environment:
      - PYTHONUNBUFFERED=1
    networks:
      - paperless-bigcapital-net
    depends_on:
      - paperless-ngx
      - bigcapital
    command: ["--config", "/app/config.ini"]

  # Example Paperless-NGX service (adjust to your setup)
  paperless-ngx:
    image: ghcr.io/paperless-ngx/paperless-ngx:latest
    container_name: paperless-ngx
    restart: unless-stopped
    ports:
      - "8000:8000"
    networks:
      - paperless-bigcapital-net
    # Add your Paperless-NGX configuration here

  # Example Bigcapital service (adjust to your setup)
  bigcapital:
    image: bigcapital/bigcapital:latest
    container_name: bigcapital
    restart: unless-stopped
    ports:
      - "3000:3000"
    networks:
      - paperless-bigcapital-net
    # Add your Bigcapital configuration here

networks:
  paperless-bigcapital-net:
    driver: bridge

volumes:
  paperless_data:
  bigcapital_data:

---

# .env.example
# Copy this to .env and fill in your values

# Paperless-NGX Configuration
PAPERLESS_URL=http://paperless-ngx:8000
PAPERLESS_TOKEN=your-paperless-ngx-api-token

# Bigcapital Configuration  
BIGCAPITAL_URL=http://bigcapital:3000
BIGCAPITAL_TOKEN=your-bigcapital-api-token

# Processing Configuration
CHECK_INTERVAL=300
LOG_LEVEL=INFO

---

# run.sh
#!/bin/bash

# Script to run the middleware

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Check if config file exists
if [ ! -f "config.ini" ]; then
    echo "Config file not found. Creating from template..."
    cp config.ini.template config.ini
    echo "Please edit config.ini with your API tokens and settings."
    exit 1
fi

# Run the middleware
python middleware.py "$@"
