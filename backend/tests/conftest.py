"""Pytest configuration and shared fixtures."""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from unittest.mock import Mock, AsyncMock, MagicMock
import pandas as pd
from datetime import datetime

# Import app components
from server import app
from app.services.agent_service import AgentService
from app.services.chat_thread_service import ChatThreadService
from app.services.message_management_service import MessageManagementService
from app.services.redis_dataframe_service import RedisDataFrameService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client for synchronous tests."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for async tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ==================== Mock Services ====================

@pytest.fixture
def mock_agent_service() -> Mock:
    """Create a mock AgentService."""
    service = Mock(spec=AgentService)
    service.is_initialized = Mock(return_value=True)
    
    # Make run_agent return the thread_id from the input
    async def mock_run_agent(message: str, thread_id: str = None, **kwargs):
        # Use the provided thread_id parameter
        result_thread_id = thread_id if thread_id else "test-thread-123"
        return {
            "success": True,
            "messages": [{"role": "assistant", "content": "Test response"}],
            "thread_id": result_thread_id,
            "state": {}
        }
    
    service.run_agent = AsyncMock(side_effect=mock_run_agent)
    service.delete_thread = AsyncMock(return_value=True)
    service.update_thread_state = AsyncMock(return_value=True)
    service.delete_multiple_threads = AsyncMock(return_value={"thread-1": True, "thread-2": True})
    service.cleanup_old_checkpoints = AsyncMock(return_value={
        "deleted_count": 5,
        "older_than_days": 30,
        "cutoff_date": datetime.now().isoformat()
    })
    service.health_check = AsyncMock(return_value={
        "overall_status": "healthy",
        "services": {
            "agent": "healthy",
            "database": "healthy"
        }
    })
    service.get_agent = Mock()
    return service


@pytest.fixture
def mock_chat_thread_service() -> Mock:
    """Create a mock ChatThreadService."""
    service = Mock(spec=ChatThreadService)
    
    # Mock create_thread
    service.create_thread = AsyncMock(return_value={
        "id": "thread-123",
        "title": "Test Thread",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "user_id": "user-123"
    })
    
    # Mock list_threads
    service.list_threads = AsyncMock(return_value={
        "threads": [
            {
                "id": "thread-1",
                "title": "Thread 1",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        ],
        "total": 1,
        "limit": 50,
        "skip": 0
    })
    
    # Mock get_thread
    service.get_thread = AsyncMock(return_value={
        "id": "thread-123",
        "title": "Test Thread",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "messages": []
    })
    
    # Mock update_thread_title
    service.update_thread_title = AsyncMock(return_value={
        "id": "thread-123",
        "title": "Updated Title",
        "updated_at": datetime.now().isoformat()
    })
    
    # Mock delete_thread
    service.delete_thread = AsyncMock(return_value=True)
    
    # Mock restore_conversation
    service.restore_conversation = AsyncMock(return_value={
        "thread_id": "thread-123",
        "messages": [],
        "data_context": None
    })
    
    return service


@pytest.fixture
def mock_message_service() -> Mock:
    """Create a mock MessageManagementService."""
    service = Mock(spec=MessageManagementService)
    
    service.get_messages_status = AsyncMock(return_value={
        "thread_id": "thread-123",
        "messages": []
    })
    
    service.update_message_status = AsyncMock(return_value={
        "message_id": 1,
        "status": "approved",
        "updated_at": datetime.now().isoformat()
    })
    
    service.update_block_approval = AsyncMock(return_value={
        "message_id": 1,
        "block_id": "block-123",
        "approved": True,
        "updated_at": datetime.now().isoformat()
    })
    
    service.mark_message_error = AsyncMock(return_value={
        "message_id": 1,
        "status": "error",
        "error_message": "Test error",
        "updated_at": datetime.now().isoformat()
    })
    
    return service


@pytest.fixture
def mock_redis_service() -> Mock:
    """Create a mock RedisDataFrameService."""
    service = Mock(spec=RedisDataFrameService)
    
    # Create a sample DataFrame
    sample_df = pd.DataFrame({
        "col1": [1, 2, 3],
        "col2": ["a", "b", "c"]
    })
    
    service.exists = Mock(return_value=True)
    service.get_dataframe = Mock(return_value=sample_df)
    service.get_metadata = Mock(return_value={
        "created_at": datetime.now().isoformat(),
        "expires_at": datetime.now().isoformat(),
        "sql_query": "SELECT * FROM test"
    })
    service.store_dataframe = Mock(return_value={
        "df_id": "df-123",
        "sql_query": "SELECT * FROM test",
        "columns": ["col1", "col2"],
        "shape": [3, 2],
        "created_at": datetime.now().isoformat(),
        "expires_at": datetime.now().isoformat()
    })
    
    return service


# ==================== Sample Data Fixtures ====================

@pytest.fixture
def sample_agent_request() -> dict:
    """Sample agent request payload."""
    return {
        "message": "What is the average sales?",
        "session_id": "test-session-123"
    }


@pytest.fixture
def sample_thread_data() -> dict:
    """Sample thread data."""
    return {
        "title": "Test Conversation",
        "user_id": "user-123"
    }


@pytest.fixture
def sample_graph_request() -> dict:
    """Sample graph execution request."""
    return {
        "thread_id": "thread-123",
        "query": "Show me the sales data",
        "user_id": "user-123"
    }


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Sample pandas DataFrame."""
    return pd.DataFrame({
        "product": ["A", "B", "C"],
        "sales": [100, 200, 150],
        "region": ["North", "South", "East"]
    })


# ==================== Dependency Override Helpers ====================

def override_dependency(app, original_dependency, mock_service):
    """Helper to override FastAPI dependencies."""
    app.dependency_overrides[original_dependency] = lambda: mock_service
    return app


@pytest.fixture
def app_with_mocks(
    mock_agent_service,
    mock_chat_thread_service,
    mock_message_service,
    mock_redis_service
):
    """App instance with all dependencies mocked."""
    from app.services.dependencies import (
        get_agent_service,
        get_chat_thread_service,
        get_message_management_service,
        get_redis_dataframe_service
    )
    
    app.dependency_overrides[get_agent_service] = lambda: mock_agent_service
    app.dependency_overrides[get_chat_thread_service] = lambda: mock_chat_thread_service
    app.dependency_overrides[get_message_management_service] = lambda: mock_message_service
    app.dependency_overrides[get_redis_dataframe_service] = lambda: mock_redis_service
    
    yield app
    
    # Clean up
    app.dependency_overrides.clear()
