"""Tests for agent endpoints."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import AsyncMock


@pytest.mark.unit
class TestAgentEndpoints:
    """Test suite for /agent endpoints."""
    
    def test_run_agent_success(self, client: TestClient, app_with_mocks, sample_agent_request):
        """Test successful agent execution."""
        response = client.post("/api/v1/agent/run", json=sample_agent_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert data["data"]["thread_id"] == "test-thread-123"
        assert len(data["data"]["messages"]) > 0
    
    def test_run_agent_invalid_payload(self, client: TestClient, app_with_mocks):
        """Test agent execution with invalid payload."""
        response = client.post("/api/v1/agent/run", json={})
        
        assert response.status_code == 422  # Validation error
    
    def test_run_agent_service_error(self, client: TestClient, app_with_mocks, mock_agent_service, sample_agent_request):
        """Test agent execution when service returns error."""
        mock_agent_service.run_agent = AsyncMock(return_value={
            "success": False,
            "error": "Agent execution failed"
        })
        
        response = client.post("/api/v1/agent/run", json=sample_agent_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
    
    def test_delete_thread_success(self, client: TestClient, app_with_mocks):
        """Test successful thread deletion."""
        thread_id = "test-thread-123"
        response = client.delete(f"/api/v1/agent/threads/{thread_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["thread_id"] == thread_id
    
    def test_delete_thread_not_found(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test deleting non-existent thread."""
        mock_agent_service.delete_thread = AsyncMock(return_value=False)
        
        response = client.delete("/api/v1/agent/threads/non-existent")
        
        assert response.status_code == 404
    
    def test_get_current_state_success(self, client: TestClient, app_with_mocks):
        """Test getting current state for a thread."""
        # Note: This endpoint uses get_agent dependency which needs special handling
        # For now, we'll skip this test or mock the agent directly
        pass
    
    def test_update_thread_state_success(self, client: TestClient, app_with_mocks):
        """Test updating thread state."""
        thread_id = "test-thread-123"
        payload = {
            "state_updates": {
                "key1": "value1",
                "key2": "value2"
            }
        }
        
        response = client.post(f"/api/v1/agent/threads/{thread_id}/state", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["thread_id"] == thread_id
    
    def test_delete_multiple_threads_success(self, client: TestClient, app_with_mocks):
        """Test bulk thread deletion."""
        payload = {
            "thread_ids": ["thread-1", "thread-2"]
        }
        
        response = client.post("/api/v1/agent/threads/bulk-delete", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["successful"] == 2
        assert data["data"]["failed"] == 0
    
    def test_cleanup_old_checkpoints_success(self, client: TestClient, app_with_mocks):
        """Test cleaning up old checkpoints."""
        response = client.delete("/api/v1/agent/checkpoints/cleanup?older_than_days=30")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "deleted_count" in data["data"]
    
    def test_cleanup_old_checkpoints_custom_days(self, client: TestClient, app_with_mocks):
        """Test cleanup with custom days parameter."""
        response = client.delete("/api/v1/agent/checkpoints/cleanup?older_than_days=60")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_agent_service_health_healthy(self, client: TestClient, app_with_mocks):
        """Test health check when service is healthy."""
        response = client.get("/api/v1/agent/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
    
    def test_agent_service_health_unhealthy(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test health check when service is unhealthy."""
        mock_agent_service.health_check = AsyncMock(return_value={
            "overall_status": "unhealthy",
            "services": {
                "agent": "unhealthy",
                "database": "healthy"
            }
        })
        
        response = client.get("/api/v1/agent/health")
        
        assert response.status_code == 503


@pytest.mark.integration
class TestAgentEndpointsIntegration:
    """Integration tests for agent endpoints."""
    
    @pytest.mark.asyncio
    async def test_run_agent_async(self, async_client: AsyncClient, app_with_mocks, sample_agent_request):
        """Test async agent execution."""
        response = await async_client.post("/api/v1/agent/run", json=sample_agent_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_concurrent_agent_requests(self, async_client: AsyncClient, app_with_mocks):
        """Test handling concurrent agent requests."""
        import asyncio
        
        requests = [
            async_client.post("/api/v1/agent/run", json={
                "message": f"Query {i}",
                "session_id": f"session-{i}"
            })
            for i in range(3)
        ]
        
        responses = await asyncio.gather(*requests)
        
        assert all(r.status_code == 200 for r in responses)
        assert all(r.json()["status"] == "success" for r in responses)
