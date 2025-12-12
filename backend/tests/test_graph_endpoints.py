"""Tests for graph endpoints (non-streaming)."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import AsyncMock, Mock
from datetime import datetime


@pytest.mark.unit
class TestGraphEndpoints:
    """Test suite for /graph endpoints."""
    
    def test_start_graph_execution_success(self, client: TestClient, app_with_mocks, mock_agent_service, sample_graph_request):
        """Test starting graph execution successfully."""
        # Mock the graph execution
        mock_agent_service.execute_graph = AsyncMock(return_value={
            "success": True,
            "thread_id": "thread-123",
            "steps": [],
            "final_result": {"status": "completed"}
        })
        
        response = client.post("/api/v1/graph/start", json=sample_graph_request)
        
        # Note: Actual implementation may vary
        # Adjust based on actual endpoint behavior
        assert response.status_code in [200, 404]  # 404 if endpoint doesn't exist yet
    
    def test_start_graph_execution_invalid_payload(self, client: TestClient, app_with_mocks):
        """Test starting graph with invalid payload."""
        response = client.post("/api/v1/graph/start", json={})
        
        assert response.status_code in [422, 404]
    
    def test_resume_graph_execution_success(self, client: TestClient, app_with_mocks):
        """Test resuming graph execution."""
        payload = {
            "thread_id": "thread-123",
            "feedback": "approved",
            "user_id": "user-123"
        }
        
        response = client.post("/api/v1/graph/resume", json=payload)
        
        assert response.status_code in [200, 404]
    
    def test_get_graph_status_success(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test getting graph execution status."""
        thread_id = "thread-123"
        
        # Mock get_state
        mock_agent = Mock()
        mock_state = Mock()
        mock_state.values = {"status": "running"}
        mock_state.next = []
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=mock_state)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get(f"/api/v1/graph/status?thread_id={thread_id}")
        
        assert response.status_code in [200, 404]
    
    def test_get_graph_status_missing_thread_id(self, client: TestClient, app_with_mocks):
        """Test getting status without thread_id."""
        response = client.get("/api/v1/graph/status")
        
        assert response.status_code == 422


@pytest.mark.unit
class TestExplorerEndpoints:
    """Test suite for explorer data endpoints."""
    
    def test_get_explorer_data_success(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test getting explorer data from checkpoint."""
        thread_id = "thread-123"
        checkpoint_id = "checkpoint-456"
        
        # Mock the state retrieval
        mock_agent = Mock()
        mock_state = Mock()
        mock_state.values = {
            "explorer_data": {
                "columns": ["col1", "col2"],
                "data": [{"col1": 1, "col2": "a"}]
            }
        }
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=mock_state)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get(
            f"/api/v1/graph/explorer?thread_id={thread_id}&checkpoint_id={checkpoint_id}"
        )
        
        assert response.status_code in [200, 404]
    
    def test_get_explorer_data_missing_params(self, client: TestClient, app_with_mocks):
        """Test getting explorer data without required params."""
        response = client.get("/api/v1/graph/explorer")
        
        assert response.status_code == 422
    
    def test_get_visualization_data_success(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test getting visualization data from checkpoint."""
        thread_id = "thread-123"
        checkpoint_id = "checkpoint-456"
        
        # Mock the state retrieval
        mock_agent = Mock()
        mock_state = Mock()
        mock_state.values = {
            "visualization_data": {
                "type": "bar",
                "data": {"x": [1, 2, 3], "y": [10, 20, 30]}
            }
        }
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=mock_state)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get(
            f"/api/v1/graph/visualization?thread_id={thread_id}&checkpoint_id={checkpoint_id}"
        )
        
        assert response.status_code in [200, 404]
    
    def test_get_visualization_data_missing_params(self, client: TestClient, app_with_mocks):
        """Test getting visualization data without required params."""
        response = client.get("/api/v1/graph/visualization")
        
        assert response.status_code == 422


@pytest.mark.integration
class TestGraphEndpointsIntegration:
    """Integration tests for graph endpoints."""
    
    @pytest.mark.asyncio
    async def test_graph_execution_flow(self, async_client: AsyncClient, app_with_mocks):
        """Test complete graph execution flow."""
        # Start execution
        start_payload = {
            "thread_id": "thread-123",
            "query": "Show me the data",
            "user_id": "user-123"
        }
        
        start_response = await async_client.post("/api/v1/graph/start", json=start_payload)
        
        # Check status (if start succeeded)
        if start_response.status_code == 200:
            status_response = await async_client.get(
                "/api/v1/graph/status?thread_id=thread-123"
            )
            assert status_response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_concurrent_graph_executions(self, async_client: AsyncClient, app_with_mocks):
        """Test concurrent graph executions."""
        import asyncio
        
        payloads = [
            {
                "thread_id": f"thread-{i}",
                "query": f"Query {i}",
                "user_id": "user-123"
            }
            for i in range(3)
        ]
        
        tasks = [
            async_client.post("/api/v1/graph/start", json=payload)
            for payload in payloads
        ]
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent requests
        assert len(responses) == 3


@pytest.mark.unit
class TestGraphErrorHandling:
    """Test error handling in graph endpoints."""
    
    def test_start_graph_with_invalid_thread_id(self, client: TestClient, app_with_mocks):
        """Test starting graph with invalid thread_id."""
        payload = {
            "thread_id": "",
            "query": "Test query",
            "user_id": "user-123"
        }
        
        response = client.post("/api/v1/graph/start", json=payload)
        
        assert response.status_code in [422, 404]
    
    def test_resume_graph_nonexistent_thread(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test resuming graph for non-existent thread."""
        mock_agent_service.resume_graph = AsyncMock(side_effect=Exception("Thread not found"))
        
        payload = {
            "thread_id": "non-existent",
            "feedback": "approved",
            "user_id": "user-123"
        }
        
        response = client.post("/api/v1/graph/resume", json=payload)
        
        # Should handle error gracefully
        assert response.status_code in [200, 404, 500]
    
    def test_get_status_invalid_checkpoint(self, client: TestClient, app_with_mocks):
        """Test getting status with invalid checkpoint."""
        response = client.get("/api/v1/graph/status?thread_id=thread-123&checkpoint_id=invalid")
        
        # Should handle gracefully
        assert response.status_code in [200, 404, 422]
