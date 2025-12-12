"""Pydantic schemas for API request/response models."""

from .base import (
    BaseResponse,
    PaginatedResponse,
    ResponseStatus,
    ErrorDetail,
    PaginationMeta,
    SuccessResponse,
    ListResponse,
    StringResponse,
    BooleanResponse,
)

from .agent import (
    AgentRequest,
    AgentResponse,
    AgentExecutionData,
    ThreadStateData,
    StateResponse,
    StateUpdateRequest,
    BulkDeleteRequest,
    BulkDeleteData,
    BulkDeleteResponse,
    CleanupData,
    CleanupResponse,
)

from .chat import (
    DataContext,
    MessageContentSchema,
    ChatMessageSchema,
    ChatThreadSchema,
    ChatThreadWithMessages,
    ChatThreadSummary,
    CreateChatRequest,
    AddMessageRequest,
    ChatHistoryResponse,
    ChatListResponse,
)


__all__ = [
    # Base response schemas
    "BaseResponse",
    "PaginatedResponse",
    "ResponseStatus",
    "ErrorDetail",
    "PaginationMeta",
    "SuccessResponse",
    "ListResponse",
    "StringResponse",
    "BooleanResponse",
    # Agent schemas
    "AgentRequest",
    "AgentResponse",
    "AgentExecutionData",
    "ThreadStateData",
    "StateResponse",
    "StateUpdateRequest",
    "BulkDeleteRequest",
    "BulkDeleteData",
    "BulkDeleteResponse",
    "CleanupData",
    "CleanupResponse",
    # Chat schemas
    "DataContext",
    "MessageContentSchema",
    "ChatMessageSchema",
    "ChatThreadSchema",
    "ChatThreadWithMessages",
    "ChatThreadSummary",
    "CreateChatRequest",
    "AddMessageRequest",
    "ChatHistoryResponse",
    "ChatListResponse",
]
