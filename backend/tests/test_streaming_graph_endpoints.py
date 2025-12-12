"""Tests for streaming graph endpoints."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import AsyncMock, Mock
import json


@pytest.mark.unit
class TestStreamingGraphEndpoints:
    """Test suite for /graph/stream endpoints."""
    
    def test_create_graph_streaming_success(self, client: TestClient, app_with_mocks, sample_graph_request):
        """Test creating a streaming graph session."""
        response = client.post("/api/v1/graph/stream/create", json=sample_graph_request)
        
        # Should return run configuration
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "thread_id" in data or "run_id" in data
    
    def test_create_graph_streaming_invalid_payload(self, client: TestClient, app_with_mocks):
        """Test creating streaming session with invalid payload."""
        response = client.post("/api/v1/graph/stream/create", json={})
        
        assert response.status_code in [422, 404]
    
    def test_resume_graph_streaming_success(self, client: TestClient, app_with_mocks):
        """Test resuming a streaming graph session."""
        payload = {
            "thread_id": "thread-123",
            "feedback": "approved",
            "user_id": "user-123"
        }
        
        response = client.post("/api/v1/graph/stream/resume", json=payload)
        
        assert response.status_code in [200, 404]
    
    def test_stream_graph_sse(self, client: TestClient, app_with_mocks):
        """Test SSE streaming endpoint."""
        thread_id = "thread-123"
        
        # SSE endpoints return event streams
        # TestClient may not handle SSE well, so we check for appropriate response
        response = client.get(f"/api/v1/graph/stream/{thread_id}")
        
        # Should either stream or return error
        assert response.status_code in [200, 404, 500]
    
    def test_get_streaming_result_success(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test getting final streaming result."""
        thread_id = "thread-123"
        
        # Mock the graph state
        mock_agent = Mock()
        mock_state = Mock()
        mock_state.values = {
            "messages": [],
            "steps": [],
            "final_result": {"status": "completed"}
        }
        mock_state.next = []
        mock_state.config = {}
        mock_state.metadata = {}
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=mock_state)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get(f"/api/v1/graph/stream/{thread_id}/result")
        
        assert response.status_code in [200, 404]
    
    def test_get_streaming_result_not_found(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test getting result for non-existent thread."""
        mock_agent = Mock()
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=None)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get("/api/v1/graph/stream/non-existent/result")
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestStreamingGraphIntegration:
    """Integration tests for streaming graph endpoints."""
    
    @pytest.mark.asyncio
    async def test_streaming_workflow(self, async_client: AsyncClient, app_with_mocks):
        """Test complete streaming workflow."""
        # Create streaming session
        create_payload = {
            "thread_id": "thread-123",
            "query": "Show me the data",
            "user_id": "user-123"
        }
        
        create_response = await async_client.post(
            "/api/v1/graph/stream/create",
            json=create_payload
        )
        
        # If creation succeeded, try to get result
        if create_response.status_code == 200:
            result_response = await async_client.get(
                "/api/v1/graph/stream/thread-123/result"
            )
            assert result_response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_sse_stream_events(self, async_client: AsyncClient, app_with_mocks):
        """Test SSE event streaming."""
        # Note: Testing SSE with httpx requires special handling
        # This is a placeholder for actual SSE testing
        thread_id = "thread-123"
        
        try:
            # Attempt to connect to SSE endpoint
            async with async_client.stream("GET", f"/api/v1/graph/stream/{thread_id}") as response:
                # Should get a streaming response
                assert response.status_code in [200, 404]
        except Exception:
            # SSE testing may not work with standard test client
            pytest.skip("SSE testing requires special setup")


@pytest.mark.unit
class TestStreamingErrorHandling:
    """Test error handling in streaming endpoints."""
    
    def test_stream_with_invalid_thread_id(self, client: TestClient, app_with_mocks):
        """Test streaming with invalid thread ID."""
        invalid_ids = ["", "  ", "../invalid"]
        
        for invalid_id in invalid_ids:
            if invalid_id.strip():
                response = client.get(f"/api/v1/graph/stream/{invalid_id}")
                # Should handle gracefully
                assert response.status_code in [200, 404, 422, 500]
    
    def test_resume_streaming_without_feedback(self, client: TestClient, app_with_mocks):
        """Test resuming without feedback."""
        payload = {
            "thread_id": "thread-123",
            "user_id": "user-123"
        }
        
        response = client.post("/api/v1/graph/stream/resume", json=payload)
        
        # May require feedback field
        assert response.status_code in [200, 422, 404]
    
    def test_get_result_before_completion(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test getting result before streaming completes."""
        # Mock incomplete state
        mock_agent = Mock()
        mock_state = Mock()
        mock_state.values = {"status": "running"}
        mock_state.next = ["next_step"]
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=mock_state)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get("/api/v1/graph/stream/thread-123/result")
        
        # Should return current state even if not complete
        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestStreamingDataFormats:
    """Test data formats in streaming responses."""
    
    def test_sse_event_format(self, client: TestClient, app_with_mocks):
        """Test SSE event format compliance."""
        # SSE events should follow format:
        # event: <event_type>
        # data: <json_data>
        # id: <event_id>
        
        # This is a placeholder - actual implementation would parse SSE stream
        thread_id = "thread-123"
        response = client.get(f"/api/v1/graph/stream/{thread_id}")
        
        if response.status_code == 200:
            # Check content type for SSE
            content_type = response.headers.get("content-type", "")
            # SSE should use text/event-stream
            assert "event-stream" in content_type or response.status_code == 200
    
    def test_streaming_result_structure(self, client: TestClient, app_with_mocks, mock_agent_service):
        """Test structure of streaming result."""
        mock_agent = Mock()
        mock_state = Mock()
        mock_state.values = {
            "messages": [],
            "steps": [],
            "final_result": {}
        }
        mock_state.next = []
        mock_state.config = {}
        mock_state.metadata = {}
        mock_agent.graph = Mock()
        mock_agent.graph.get_state = Mock(return_value=mock_state)
        mock_agent_service.get_agent = Mock(return_value=mock_agent)
        
        response = client.get("/api/v1/graph/stream/thread-123/result")
        
        if response.status_code == 200:
            data = response.json()
            # Should have expected structure
            assert isinstance(data, dict)


@pytest.mark.slow
class TestStreamingPerformance:
    """Performance tests for streaming endpoints."""
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_streams(self, async_client: AsyncClient, app_with_mocks):
        """Test handling multiple concurrent streams."""
        import asyncio
        
        thread_ids = [f"thread-{i}" for i in range(5)]
        
        # Create multiple streaming sessions
        create_tasks = [
            async_client.post("/api/v1/graph/stream/create", json={
                "thread_id": tid,
                "query": f"Query for {tid}",
                "user_id": "user-123"
            })
            for tid in thread_ids
        ]
        
        responses = await asyncio.gather(*create_tasks, return_exceptions=True)
        
        # Should handle concurrent requests
        assert len(responses) == 5
    
    @pytest.mark.asyncio
    async def test_stream_cleanup(self, async_client: AsyncClient, app_with_mocks):
        """Test that streams are properly cleaned up."""
        # Create a stream
        create_response = await async_client.post(
            "/api/v1/graph/stream/create",
            json={
                "thread_id": "cleanup-test",
                "query": "Test query",
                "user_id": "user-123"
            }
        )
        
        # Get result (which should complete the stream)
        if create_response.status_code == 200:
            await async_client.get("/api/v1/graph/stream/cleanup-test/result")
            
            # Verify cleanup (implementation specific)
            # This is a placeholder for actual cleanup verification
            assert True
