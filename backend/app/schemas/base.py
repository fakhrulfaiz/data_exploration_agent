"""Base response schemas for consistent API responses."""

from typing import Generic, TypeVar, Optional, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

# Generic type for data payload
T = TypeVar('T')

class ResponseStatus(str, Enum):
    """Standard response status codes"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"

class ErrorDetail(BaseModel):
    """Detailed error information"""
    code: str = Field(..., description="Error code for client handling")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field name if validation error")
    details: Optional[dict] = Field(None, description="Additional error context")

class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_items: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)
    has_next: bool
    has_previous: bool

class BaseResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper for all endpoints
    
    Usage:
        # Success response
        return BaseResponse(data=user, message="User created successfully")
        
        # Error response
        return BaseResponse(
            status=ResponseStatus.ERROR,
            errors=[ErrorDetail(code="USER_NOT_FOUND", message="User does not exist")]
        )
    """
    status: ResponseStatus = Field(
        default=ResponseStatus.SUCCESS,
        description="Response status indicator"
    )
    data: Optional[T] = Field(
        default=None,
        description="Response payload data"
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable response message"
    )
    errors: Optional[List[ErrorDetail]] = Field(
        default=None,
        description="List of errors if any"
    )
    meta: Optional[dict] = Field(
        default=None,
        description="Additional metadata (pagination, etc.)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Unique request identifier for tracing"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {"id": 1, "name": "John Doe"},
                "message": "Operation completed successfully",
                "errors": None,
                "meta": None,
                "timestamp": "2024-12-09T10:30:00Z",
                "request_id": "req_abc123xyz"
            }
        }

class PaginatedResponse(BaseResponse[List[T]], Generic[T]):
    """Response wrapper for paginated data"""
    meta: PaginationMeta

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}],
                "message": "Data retrieved successfully",
                "meta": {
                    "page": 1,
                    "page_size": 10,
                    "total_items": 25,
                    "total_pages": 3,
                    "has_next": True,
                    "has_previous": False
                },
                "timestamp": "2024-12-09T10:30:00Z",
                "request_id": "req_abc123xyz"
            }
        }

# Convenience type aliases for common response patterns
SuccessResponse = BaseResponse[dict]
ListResponse = BaseResponse[List[dict]]
StringResponse = BaseResponse[str]
BooleanResponse = BaseResponse[bool]





