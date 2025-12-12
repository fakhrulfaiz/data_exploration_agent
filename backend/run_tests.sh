#!/bin/bash
# Script to run pytest inside the Docker container

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running tests in Docker container...${NC}\n"

# Check if container is running
if ! docker ps | grep -q "agent-backend"; then
    echo -e "${RED}Error: agent-backend container is not running${NC}"
    echo "Please start the container with: docker compose up"
    exit 1
fi

# Install test dependencies if not already installed
echo -e "${YELLOW}Installing test dependencies...${NC}"
docker compose exec backend pip install -q -r requirements-test.txt

# Run pytest with arguments passed to this script
# If no arguments provided, run all tests
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}Running all tests...${NC}\n"
    docker compose exec backend pytest tests/ -v
else
    echo -e "${YELLOW}Running: pytest $@${NC}\n"
    docker compose exec backend pytest "$@"
fi

# Capture exit code
EXIT_CODE=$?

# Print summary
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Tests passed!${NC}"
else
    echo -e "${RED}❌ Tests failed!${NC}"
fi

exit $EXIT_CODE
