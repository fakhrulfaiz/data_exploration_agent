#!/bin/bash

# Data Exploration Agent - Setup Script
# This script sets up the project after cloning from git

set -e  # Exit on error

echo "🚀 Setting up Data Exploration Agent..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo ""
    echo "IMPORTANT: Please update .env with your API keys!"
    echo "Required:"
    echo "   - OPENAI_API_KEY (get from https://platform.openai.com/api-keys)"
    echo "   - SUPABASE_URL and keys (get from https://supabase.com/dashboard)"
    echo ""
    echo "Optional:"
    echo "   - LANGSMITH_TRACING should be 'false' unless you have a LangSmith account"
    echo ""
    echo "  Press Enter when ready..."
    read
else
    echo ".env file already exists"
fi

# Start Docker containers
echo "Starting Docker containers..."
docker compose up -d

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 5

# Run migrations
echo "Running database migrations..."
docker exec -it agent-backend alembic upgrade head

echo ""
echo "Setup complete!"
echo ""
echo "Application URLs:"
echo "   - Frontend: http://localhost:8080"
echo "   - Backend API: http://localhost:8080/api"
echo "   - API Docs: http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "   - View logs: docker compose logs -f"
echo "   - Stop: docker compose down"
echo "   - Restart: docker compose restart"
echo ""
