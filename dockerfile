# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including PostgreSQL client
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY middleware.py .
COPY config.ini .
COPY db/ ./db/

# Create necessary directories
RUN mkdir -p /app/logs

# Create non-root user
RUN useradd -m -u 1000 middleware && \
    chown -R middleware:middleware /app

# Copy and make the init script executable
COPY init.sh .
RUN chmod +x init.sh && chown middleware:middleware init.sh

USER middleware

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=5)" || exit 1

ENTRYPOINT ["./init.sh"]
