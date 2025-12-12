"""Pydantic schemas for agent-related API endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseResponse


# ==================== Agent Execution Schemas ====================

class AgentRequest(BaseModel):
    """Request model for agent execution."""
    message: str = Field(..., description="User message to process")
    session_id: Optional[str] = Field(
        default=None, description="Optional session/thread identifier"
    )


class AgentExecutionData(BaseModel):
    """Data model for agent execution results."""
    messages: List[str] = Field(..., description="Agent response messages")
    thread_id: Optional[str] = Field(None, description="Thread identifier used")
    state: Optional[Dict[str, Any]] = Field(None, description="Final agent state")


class AgentResponse(BaseResponse[AgentExecutionData]):
    """Response model for agent execution."""
    pass


# ==================== State Management Schemas ====================

class ThreadStateData(BaseModel):
    """Data model for thread state information."""
    thread_id: str = Field(..., description="Thread identifier")
    state: Optional[Dict[str, Any]] = Field(None, description="Current thread state")
    next: Optional[List[str]] = Field(None, description="Next possible actions")
    config: Optional[Dict[str, Any]] = Field(None, description="Thread configuration")
    metadata: Optional[Dict[str, Any]] = Field(None, description="State metadata")
    created_at: Optional[datetime] = Field(None, description="State creation timestamp")


class StateResponse(BaseResponse[ThreadStateData]):
    """Response model for thread state."""
    pass


class StateUpdateRequest(BaseModel):
    """Request model for state updates."""
    state_updates: Dict[str, Any] = Field(..., description="State updates to apply")





# ==================== Bulk Operations Schemas ====================

class BulkDeleteRequest(BaseModel):
    """Request model for bulk thread deletion."""
    thread_ids: List[str] = Field(..., description="List of thread IDs to delete")


class BulkDeleteData(BaseModel):
    """Data model for bulk deletion results."""
    results: Dict[str, bool] = Field(..., description="Deletion results per thread")
    successful: int = Field(..., description="Number of successful deletions")
    failed: int = Field(..., description="Number of failed deletions")


class BulkDeleteResponse(BaseResponse[BulkDeleteData]):
    """Response model for bulk thread deletion."""
    pass


# ==================== Cleanup Schemas ====================

class CleanupData(BaseModel):
    """Data model for cleanup results."""
    deleted_count: int = Field(..., description="Number of checkpoints/threads deleted")
    older_than_days: int = Field(..., description="Age threshold in days")
    cutoff_date: Optional[str] = Field(None, description="Cutoff date for cleanup")


class CleanupResponse(BaseResponse[CleanupData]):
    """Response model for checkpoint cleanup."""
    pass


