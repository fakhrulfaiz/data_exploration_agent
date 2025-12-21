"""Pydantic schemas for conversation/thread management endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

from .base import BaseResponse, PaginatedResponse


# ==================== Enums ====================

class MessageStatus(str, Enum):
    """Message status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"
    TIMEOUT = "timeout"


class MessageType(str, Enum):
    """Message type"""
    MESSAGE = "message"
    EXPLORER = "explorer"
    VISUALIZATION = "visualization"
    FEEDBACK = "feedback"


# ==================== Conversation/Thread Schemas ====================

class CreateConversationRequest(BaseModel):
    """Request to create a new conversation"""
    title: str = Field(..., description="Conversation title")
    initial_message: Optional[str] = Field(None, description="Optional initial message")


class UpdateTitleRequest(BaseModel):
    """Request to update conversation title"""
    title: str = Field(..., description="New conversation title")


class ConversationSummary(BaseModel):
    """Summary of a conversation"""
    thread_id: str = Field(..., description="Thread identifier")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    message_count: int = Field(0, description="Number of messages")
    last_message_preview: Optional[str] = Field(None, description="Preview of last message")


class ConversationData(BaseModel):
    """Detailed conversation data"""
    thread_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    message_count: int = 0


class ConversationResponse(BaseResponse[ConversationData]):
    """Response for single conversation"""
    pass


class ConversationListData(BaseModel):
    """List of conversations"""
    conversations: List[ConversationSummary]
    total: int


class ConversationListResponse(BaseResponse[ConversationListData]):
    """Response for conversation list"""
    pass


# ==================== Message Management Schemas ====================

class MessageStatusUpdateRequest(BaseModel):
    """Request to update message status"""
    message_status: Optional[MessageStatus] = Field(None, description="New message status")


class BlockStatusUpdateRequest(BaseModel):
    """Request to update block approval status"""
    needsApproval: Optional[bool] = Field(None, description="Whether block needs approval")
    messageStatus: Optional[MessageStatus] = Field(None, description="Block message status")


class MessageStatusInfo(BaseModel):
    """Message status information"""
    message_id: str
    sender: str
    timestamp: datetime
    checkpoint_id: Optional[str] = None
    has_content_blocks: bool = False


class MessageStatusListData(BaseModel):
    """List of message status"""
    thread_id: str
    message_count: int
    messages: List[MessageStatusInfo]


class MessageStatusListResponse(BaseResponse[MessageStatusListData]):
    """Response for message status list"""
    pass


# ==================== Checkpoint Schemas ====================

class CheckpointSummary(BaseModel):
    """Checkpoint summary"""
    checkpoint_id: str
    thread_id: str
    timestamp: datetime
    message_id: str
    query: Optional[str] = None


class CheckpointListData(BaseModel):
    """List of checkpoints"""
    checkpoints: List[CheckpointSummary]
    total: int


class CheckpointListResponse(BaseResponse[CheckpointListData]):
    """Response for checkpoint list"""
    pass


# ==================== Data Context Schema ====================

class DataContext(BaseModel):
    """Data context information"""
    df_id: str
    sql_query: str
    columns: List[str]
    shape: List[int]
    created_at: str
    expires_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RestoreConversationData(BaseModel):
    """Restored conversation data with context"""
    thread_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[Dict[str, Any]]
    message_count: int
    data_context: Optional[DataContext] = None


class RestoreConversationResponse(BaseResponse[RestoreConversationData]):
    """Response for restored conversation"""
    pass
