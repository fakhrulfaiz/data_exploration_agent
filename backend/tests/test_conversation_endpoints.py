"""Tests for conversation endpoints."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import AsyncMock


@pytest.mark.unit
class TestConversationEndpoints:
    """Test suite for /conversation endpoints."""
    
    def test_create_conversation_success(self, client: TestClient, app_with_mocks, sample_thread_data):
        """Test successful conversation creation."""
        response = client.post("/api/v1/conversation/", json=sample_thread_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert data["data"]["title"] == sample_thread_data["title"]
    
    def test_create_conversation_invalid_data(self, client: TestClient, app_with_mocks):
        """Test conversation creation with invalid data."""
        response = client.post("/api/v1/conversation/", json={})
        
        assert response.status_code == 422  # Validation error
    
    def test_list_conversations_success(self, client: TestClient, app_with_mocks):
        """Test listing conversations."""
        response = client.get("/api/v1/conversation/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "conversations" in data["data"]
    
    def test_list_conversations_with_pagination(self, client: TestClient, app_with_mocks):
        """Test listing conversations with pagination."""
        response = client.get("/api/v1/conversation/?limit=10&skip=5")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_list_conversations_invalid_limit(self, client: TestClient, app_with_mocks):
        """Test listing conversations with invalid limit."""
        response = client.get("/api/v1/conversation/?limit=200")
        
        assert response.status_code == 422  # Validation error
    
    def test_get_conversation_success(self, client: TestClient, app_with_mocks):
        """Test getting a specific conversation."""
        thread_id = "thread-123"
        response = client.get(f"/api/v1/conversation/{thread_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["thread_id"] == thread_id
    
    def test_get_conversation_not_found(self, client: TestClient, app_with_mocks, mock_chat_thread_service):
        """Test getting non-existent conversation."""
        mock_chat_thread_service.get_thread = AsyncMock(return_value=None)
        
        response = client.get("/api/v1/conversation/non-existent")
        
        assert response.status_code == 404
    
    def test_update_conversation_title_success(self, client: TestClient, app_with_mocks):
        """Test updating conversation title."""
        thread_id = "thread-123"
        payload = {"title": "Updated Title"}
        
        response = client.patch(f"/api/v1/conversation/{thread_id}/title", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["title"] == "Updated Title"
    
    def test_update_conversation_title_invalid(self, client: TestClient, app_with_mocks):
        """Test updating conversation title with invalid data."""
        response = client.patch("/api/v1/conversation/thread-123/title", json={})
        
        assert response.status_code == 422
    
    def test_delete_conversation_success(self, client: TestClient, app_with_mocks):
        """Test deleting a conversation."""
        thread_id = "thread-123"
        response = client.delete(f"/api/v1/conversation/{thread_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_delete_conversation_not_found(self, client: TestClient, app_with_mocks, mock_chat_thread_service):
        """Test deleting non-existent conversation."""
        mock_chat_thread_service.delete_thread = AsyncMock(return_value=False)
        
        response = client.delete("/api/v1/conversation/non-existent")
        
        assert response.status_code == 404
    
    def test_restore_conversation_success(self, client: TestClient, app_with_mocks):
        """Test restoring a conversation."""
        thread_id = "thread-123"
        response = client.get(f"/api/v1/conversation/{thread_id}/restore")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["thread_id"] == thread_id


@pytest.mark.unit
class TestMessageManagementEndpoints:
    """Test suite for message management endpoints."""
    
    def test_get_messages_status_success(self, client: TestClient, app_with_mocks):
        """Test getting messages status."""
        thread_id = "thread-123"
        response = client.get(f"/api/v1/conversation/{thread_id}/messages/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["thread_id"] == thread_id
    
    def test_update_message_status_success(self, client: TestClient, app_with_mocks):
        """Test updating message status."""
        thread_id = "thread-123"
        message_id = 1
        payload = {
            "status": "approved",
            "approved": True
        }
        
        response = client.patch(
            f"/api/v1/conversation/{thread_id}/messages/{message_id}/status",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_update_block_approval_success(self, client: TestClient, app_with_mocks):
        """Test updating block approval status."""
        thread_id = "thread-123"
        message_id = 1
        block_id = "block-123"
        payload = {
            "approved": True
        }
        
        response = client.patch(
            f"/api/v1/conversation/{thread_id}/messages/{message_id}/blocks/{block_id}/approval",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_update_block_approval_invalid_data(self, client: TestClient, app_with_mocks):
        """Test updating block approval with invalid data."""
        response = client.patch(
            "/api/v1/conversation/thread-123/messages/1/blocks/block-123/approval",
            json={}
        )
        
        assert response.status_code == 422
    
    def test_mark_message_error_success(self, client: TestClient, app_with_mocks):
        """Test marking message as error."""
        thread_id = "thread-123"
        message_id = 1
        
        response = client.post(
            f"/api/v1/conversation/{thread_id}/messages/{message_id}/error",
            params={"error_message": "Test error"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_mark_message_error_without_message(self, client: TestClient, app_with_mocks):
        """Test marking message as error without error message."""
        thread_id = "thread-123"
        message_id = 1
        
        response = client.post(
            f"/api/v1/conversation/{thread_id}/messages/{message_id}/error"
        )
        
        assert response.status_code == 200


@pytest.mark.unit
class TestCheckpointEndpoints:
    """Test suite for checkpoint management endpoints."""
    
    def test_list_checkpoints_success(self, client: TestClient, app_with_mocks):
        """Test listing checkpoints."""
        # This endpoint needs special mocking for repositories
        # Skipping for now as it requires more complex setup
        pass


@pytest.mark.integration
class TestConversationEndpointsIntegration:
    """Integration tests for conversation endpoints."""
    
    @pytest.mark.asyncio
    async def test_conversation_lifecycle(self, async_client: AsyncClient, app_with_mocks):
        """Test complete conversation lifecycle."""
        # Create conversation
        create_response = await async_client.post(
            "/api/v1/conversation/",
            json={"title": "Test Conversation", "user_id": "user-123"}
        )
        assert create_response.status_code == 200
        thread_id = create_response.json()["data"]["thread_id"]
        
        # Get conversation
        get_response = await async_client.get(f"/api/v1/conversation/{thread_id}")
        assert get_response.status_code == 200
        
        # Update title
        update_response = await async_client.patch(
            f"/api/v1/conversation/{thread_id}/title",
            json={"title": "Updated Title"}
        )
        assert update_response.status_code == 200
        
        # Delete conversation
        delete_response = await async_client.delete(f"/api/v1/conversation/{thread_id}")
        assert delete_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_concurrent_conversation_operations(self, async_client: AsyncClient, app_with_mocks):
        """Test concurrent conversation operations."""
        import asyncio
        
        # Create multiple conversations concurrently
        create_tasks = [
            async_client.post(
                "/api/v1/conversation/",
                json={"title": f"Conversation {i}", "user_id": "user-123"}
            )
            for i in range(3)
        ]
        
        responses = await asyncio.gather(*create_tasks)
        assert all(r.status_code == 200 for r in responses)
