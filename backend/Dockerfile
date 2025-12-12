FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies (like curl for health checks)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code
COPY . /app

# Create logs directory
RUN mkdir -p logs

EXPOSE 8000

# Use uvicorn with --reload for hot reload in development
# The --reload flag enables automatic reloading when code changes
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]