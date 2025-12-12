# Backend API Tests

Comprehensive pytest test suite for all backend API endpoints.

## Quick Start (Docker)

**Windows:**
```bash
.\run_tests.bat
```

**Linux/Mac:**
```bash
chmod +x run_tests.sh
./run_tests.sh
```

## Running Tests in Docker (Recommended)

Since the backend runs in Docker, run tests inside the container:

### Windows

```bash
# Run all tests
.\run_tests.bat

# Run specific test file
.\run_tests.bat tests/test_agent_endpoints.py

# Run specific test
.\run_tests.bat tests/test_agent_endpoints.py::TestAgentEndpoints::test_run_agent_success

# Run by marker
.\run_tests.bat -m unit
.\run_tests.bat -m integration
.\run_tests.bat -m "not slow"

# Run with coverage
.\run_tests.bat --cov=app --cov-report=html

# Run with verbose output
.\run_tests.bat -v
```

### Linux/Mac

```bash
# Run all tests
./run_tests.sh

# Run specific test file
./run_tests.sh tests/test_agent_endpoints.py

# Run by marker
./run_tests.sh -m unit

# Run with coverage
./run_tests.sh --cov=app --cov-report=html
```

### Manual Docker Commands

```bash
# Install test dependencies (first time only)
docker compose exec backend pip install -r requirements-test.txt

# Run all tests
docker compose exec backend pytest tests/ -v

# Run specific tests
docker compose exec backend pytest tests/test_agent_endpoints.py -v

# Run with coverage
docker compose exec backend pytest --cov=app --cov-report=html

# Access container shell for debugging
docker compose exec backend bash
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                          # Shared fixtures and configuration
├── test_agent_endpoints.py              # Tests for /agent endpoints
├── test_conversation_endpoints.py       # Tests for /conversation endpoints
├── test_data_endpoints.py               # Tests for /data endpoints
├── test_graph_endpoints.py              # Tests for /graph endpoints
└── test_streaming_graph_endpoints.py    # Tests for /graph/stream endpoints
```

## Test Markers

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests (may require services)
- `@pytest.mark.e2e` - End-to-end tests (full workflow)
- `@pytest.mark.slow` - Slow running tests

### Examples

```bash
# Run only unit tests
docker compose exec backend pytest -m unit

# Run only integration tests
docker compose exec backend pytest -m integration

# Skip slow tests
docker compose exec backend pytest -m "not slow"
```

## Test Coverage

### Agent Endpoints (`/api/v1/agent`)
- ✅ POST `/run` - Run agent with message
- ✅ DELETE `/threads/{thread_id}` - Delete thread
- ✅ GET `/threads/{thread_id}/state` - Get thread state
- ✅ POST `/threads/{thread_id}/state` - Update thread state
- ✅ DELETE `/threads/bulk` - Bulk delete threads
- ✅ DELETE `/checkpoints/cleanup` - Cleanup old checkpoints
- ✅ GET `/health` - Health check

### Conversation Endpoints (`/api/v1/conversation`)
- ✅ POST `/` - Create conversation
- ✅ GET `/` - List conversations
- ✅ GET `/{thread_id}` - Get conversation
- ✅ PATCH `/{thread_id}/title` - Update title
- ✅ DELETE `/{thread_id}` - Delete conversation
- ✅ GET `/{thread_id}/restore` - Restore conversation
- ✅ GET `/{thread_id}/messages/status` - Get messages status
- ✅ PATCH `/{thread_id}/messages/{message_id}/status` - Update message status
- ✅ PATCH `/{thread_id}/messages/{message_id}/blocks/{block_id}/approval` - Update block approval
- ✅ POST `/{thread_id}/messages/{message_id}/error` - Mark message error

### Data Endpoints (`/api/v1/data`)
- ✅ GET `/{df_id}/preview` - Get DataFrame preview
- ✅ POST `/recreate` - Recreate DataFrame

### Graph Endpoints (`/api/v1/graph`)
- ✅ POST `/start` - Start graph execution
- ✅ POST `/resume` - Resume graph execution
- ✅ GET `/status` - Get graph status
- ✅ GET `/explorer` - Get explorer data
- ✅ GET `/visualization` - Get visualization data

### Streaming Graph Endpoints (`/api/v1/graph/stream`)
- ✅ POST `/create` - Create streaming session
- ✅ POST `/resume` - Resume streaming session
- ✅ GET `/{thread_id}` - Stream graph execution (SSE)
- ✅ GET `/{thread_id}/result` - Get streaming result

## Viewing Coverage Reports

After running tests with coverage:

```bash
# Generate HTML coverage report
docker compose exec backend pytest --cov=app --cov-report=html

# Copy report from container to host
docker compose cp backend:/app/htmlcov ./htmlcov

# Open in browser (Windows)
start htmlcov/index.html

# Open in browser (Linux/Mac)
open htmlcov/index.html
```

## Fixtures

### Client Fixtures
- `client` - Synchronous test client
- `async_client` - Async test client

### Mock Service Fixtures
- `mock_agent_service` - Mocked AgentService
- `mock_chat_thread_service` - Mocked ChatThreadService
- `mock_message_service` - Mocked MessageManagementService
- `mock_redis_service` - Mocked RedisDataFrameService

### Data Fixtures
- `sample_agent_request` - Sample agent request payload
- `sample_thread_data` - Sample thread data
- `sample_graph_request` - Sample graph request
- `sample_dataframe` - Sample pandas DataFrame

### App Fixture
- `app_with_mocks` - App with all dependencies mocked

## Writing New Tests

### Example Unit Test

```python
import pytest
from fastapi.testclient import TestClient

@pytest.mark.unit
def test_my_endpoint(client: TestClient, app_with_mocks):
    """Test my endpoint."""
    response = client.get("/api/v1/my-endpoint")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
```

### Example Integration Test

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_my_async_endpoint(async_client: AsyncClient, app_with_mocks):
    """Test my async endpoint."""
    response = await async_client.post(
        "/api/v1/my-endpoint",
        json={"key": "value"}
    )
    
    assert response.status_code == 200
```

## Debugging Tests

### Run tests with output
```bash
docker compose exec backend pytest -s
```

### Run tests with pdb debugger
```bash
docker compose exec backend pytest --pdb
```

### View test logs
```bash
docker compose exec backend pytest --log-cli-level=DEBUG
```

### Access container for debugging
```bash
docker compose exec backend bash
cd /app
python -m pytest tests/ -v
```

## Troubleshooting

### Tests not found
Make sure you're running from the backend directory or using the provided scripts.

### Import errors
Ensure test dependencies are installed:
```bash
docker compose exec backend pip install -r requirements-test.txt
```

### Container not running
Start the backend container:
```bash
docker compose up backend
```

### Mocks not working
Ensure you're using the `app_with_mocks` fixture in your test function.

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
name: Backend Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build Docker containers
        run: docker compose build backend
      
      - name: Start services
        run: docker compose up -d backend
      
      - name: Install test dependencies
        run: docker compose exec -T backend pip install -r requirements-test.txt
      
      - name: Run tests
        run: docker compose exec -T backend pytest --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          files: ./coverage.xml
```

## Best Practices

1. **Use Docker for testing** - Ensures consistency with production environment
2. **Use appropriate markers** - Mark tests as `unit`, `integration`, or `e2e`
3. **Keep tests isolated** - Each test should be independent
4. **Use fixtures** - Reuse common setup code
5. **Mock external dependencies** - Don't make real API calls in unit tests
6. **Test error cases** - Don't just test the happy path
7. **Use descriptive names** - Test names should describe what they test
8. **Keep tests fast** - Mark slow tests with `@pytest.mark.slow`
9. **Aim for high coverage** - Target 80%+ code coverage

## Contributing

When adding new endpoints:

1. Create tests in the appropriate test file
2. Add both success and error test cases
3. Mock all external dependencies
4. Update this README with new endpoint coverage
5. Ensure all tests pass before committing

## License

Same as the main project.
