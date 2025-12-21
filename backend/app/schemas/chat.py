"""Chat-related Pydantic schemas for API."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Dict, Any, Tuple
from datetime import datetime


class DataContext(BaseModel):
    """Context information for DataFrame stored in Redis."""
    df_id: Optional[str] = Field(None, description="Redis key for DataFrame")
    sql_query: Optional[str] = Field(None, description="Last executed SQL query")
    columns: List[str] = Field(default_factory=list, description="DataFrame column names")
    shape: Tuple[int, int] = Field(default=(0, 0), description="DataFrame dimensions (rows, cols)")
    created_at: Optional[datetime] = Field(None, description="When DataFrame was created")
    expires_at: Optional[datetime] = Field(None, description="When Redis key expires")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class MessageContentSchema(BaseModel):
    """Individual content block for a message."""
    chat_message_id: str = Field(..., description="Foreign key to chat messages (UUID)")
    block_id: str = Field(..., description="Unique block identifier")
    type: str = Field(..., description="Block type: text, tool_calls, explorer, visualizations")
    needs_approval: bool = Field(default=False, description="Whether this block needs approval")
    message_status: Optional[Literal["pending", "approved", "rejected", "error", "timeout"]] = Field(
        default=None, 
        description="Status of this content block"
    )
    data: Dict[str, Any] = Field(..., description="Block data content")
    created_at: datetime = Field(default_factory=datetime.now, description="Block creation timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatMessageSchema(BaseModel):
    """Individual chat message."""
    thread_id: Optional[str] = Field(None, description="Thread ID for this message")
    sender: Literal["user", "assistant"] = Field(..., description="Message sender")
    content: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Message content blocks"
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="Message timestamp")
    checkpoint_id: Optional[str] = Field(None, description="Checkpoint ID for explorer messages")
    user_id: Optional[str] = Field(None, description="User ID who owns this message")
    message_id: str = Field(..., description="Message ID (UUID)")


    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatThreadSchema(BaseModel):
    """Chat thread/conversation."""
    thread_id: str = Field(..., description="Unique thread identifier")
    title: Optional[str] = Field(None, description="Chat thread title")
    created_at: datetime = Field(default_factory=datetime.now, description="Thread creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    user_id: Optional[str] = Field(None, description="User ID who owns this thread")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatThreadWithMessages(ChatThreadSchema):
    """Chat thread with messages."""
    messages: List[ChatMessageSchema] = Field(..., description="Messages")


class ChatThreadSummary(BaseModel):
    """Summary view of chat thread for listing."""
    thread_id: str = Field(..., description="Thread ID")
    title: str = Field(..., description="Thread title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_message: Optional[str] = Field(None, description="Last message preview")
    message_count: int = Field(0, description="Total message count for thread")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreateChatRequest(BaseModel):
    """Request to create new chat thread."""
    title: Optional[str] = Field(None, description="Optional thread title")
    initial_message: Optional[str] = Field(None, description="Optional initial user message")


class AddMessageRequest(BaseModel):
    """Request to add message to existing thread."""
    thread_id: str = Field(..., description="Thread ID")
    sender: Literal["user", "assistant"] = Field(..., description="Message sender")
    content: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Message content blocks"
    )
    checkpoint_id: Optional[str] = Field(None, description="Checkpoint ID for explorer messages")
    message_id: str = Field(..., description="Message ID (UUID)")
    metadata: Optional[dict] = Field(None, description="Additional metadata")




class ChatHistoryResponse(BaseModel):
    """Response containing chat thread data."""
    success: bool = Field(..., description="Request success status")
    data: Optional[ChatThreadWithMessages] = Field(None, description="Chat thread data with messages")
    message: str = Field(..., description="Response message")
    data_context: Optional[DataContext] = Field(
        None, 
        description="Active data context for this thread if available"
    )


class ChatListResponse(BaseModel):
    """Response containing list of chat threads."""
    success: bool = Field(..., description="Request success status")
    data: List[ChatThreadSummary] = Field(default_factory=list, description="List of chat threads")
    message: str = Field(..., description="Response message")
    total: int = Field(0, description="Total number of threads")
