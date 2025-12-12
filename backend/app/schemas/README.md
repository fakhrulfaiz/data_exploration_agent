# API Response Schemas

This directory contains all Pydantic schemas for API requests and responses, organized with a standardized response structure for consistency across all endpoints.

## Schema Organization

### Base Response Structure (`base.py`)

All API responses inherit from `BaseResponse[T]` which provides:

- **Consistent Structure**: Standardized response format across all endpoints
- **Generic Type Support**: Type-safe data payloads with `BaseResponse[T]`
- **Status Indicators**: Success/Error/Warning status with enum values
- **Error Handling**: Structured error details with codes and messages
- **Metadata Support**: Pagination, timestamps, request IDs
- **Documentation**: Auto-generated OpenAPI docs with examples

#### Base Response Structure

```python
{
    "status": "success" | "error" | "warning",
    "data": T,  # Typed data payload
    "message": "Human-readable message",
    "errors": [
        {
            "code": "ERROR_CODE",
            "message": "Error description",
            "field": "field_name",  # Optional
            "details": {}  # Optional
        }
    ],
    "meta": {},  # Additional metadata
    "timestamp": "2024-12-09T10:30:00Z",
    "request_id": "req_abc123xyz"
}
```

### Agent Schemas (`agent.py`)

All agent-related API schemas with proper data models:

#### Request Schemas
- `AgentRequest` - Agent execution requests
- `StateUpdateRequest` - State update requests  
- `StateInitializeRequest` - State initialization requests
- `BulkDeleteRequest` - Bulk deletion requests
- `CheckpointSearchRequest` - Checkpoint search requests
- `ThreadSearchRequest` - Thread search requests
- `CleanupRequest` - Cleanup operation requests

#### Data Models
- `AgentExecutionData` - Agent execution results
- `ThreadData` - Thread information
- `ThreadStateData` - Thread state details
- `CheckpointData` - Individual checkpoint data
- `StatisticsData` - Statistics information
- `CleanupData` - Cleanup operation results

#### Response Schemas (inherit from BaseResponse)
- `AgentResponse` - Agent execution responses
- `ThreadListResponse` - Thread listing responses
- `ThreadMetadataResponse` - Thread metadata responses
- `StateResponse` - Thread state responses
- `CheckpointHistoryResponse` - Checkpoint history responses
- `CheckpointSearchResponse` - Checkpoint search responses
- `ThreadSearchResponse` - Thread search responses
- `BulkDeleteResponse` - Bulk deletion responses
- `StatisticsResponse` - Statistics responses
- `CleanupResponse` - Cleanup operation responses

## Benefits

### 1. **Consistency**
All API responses follow the same structure, making client integration predictable and reliable.

### 2. **Type Safety**
Generic `BaseResponse[T]` provides compile-time type checking for response data.

### 3. **Error Handling**
Standardized error structure with codes, messages, and optional field/detail information.

### 4. **Documentation**
Auto-generated OpenAPI documentation with proper examples and field descriptions.

### 5. **Extensibility**
Easy to add new response types by inheriting from `BaseResponse[T]`.

### 6. **Client-Friendly**
Consistent structure allows clients to handle responses generically.

## Usage Examples

### Success Response
```python
return AgentResponse(
    data=AgentExecutionData(
        messages=["Response message"],
        thread_id="thread-123",
        state={"key": "value"}
    ),
    message="Agent executed successfully"
)
```

### Error Response
```python
return AgentResponse(
    status=ResponseStatus.ERROR,
    message="Agent execution failed",
    errors=[
        ErrorDetail(
            code="AGENT_EXECUTION_ERROR",
            message="Detailed error description"
        )
    ]
)
```

### Paginated Response
```python
return PaginatedResponse(
    data=[item1, item2, item3],
    message="Data retrieved successfully",
    meta=PaginationMeta(
        page=1,
        page_size=10,
        total_items=25,
        total_pages=3,
        has_next=True,
        has_previous=False
    )
)
```

## Response Status Codes

- `SUCCESS` - Operation completed successfully
- `ERROR` - Operation failed with errors
- `WARNING` - Operation completed with warnings

## Error Codes

Error codes follow a consistent naming pattern:
- `THREAD_NOT_FOUND` - Thread does not exist
- `STATE_NOT_FOUND` - State not found for thread
- `AGENT_EXECUTION_ERROR` - Agent execution failed
- `VALIDATION_ERROR` - Request validation failed

This standardized approach ensures consistent, type-safe, and well-documented API responses across the entire application.





