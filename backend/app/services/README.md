# Service Layer Migration Summary

This document summarizes the new service files created for the project, adapted from the old MongoDB-based services to work with the new SQLAlchemy/PostgreSQL architecture.

## Files Created

### 1. `chat_thread_service.py`
**Purpose**: Manages chat thread operations (adapted from `chat_history_service.py`)

**Key Features**:
- Thread creation with UUID generation
- Thread retrieval with messages
- Thread listing with pagination
- Thread summaries with message counts and previews
- Thread deletion (cascades to messages and content blocks)
- Thread title updates
- Thread counting

**Key Differences from Old Service**:
- ❌ Removed `CheckpointService` dependency (checkpoint operations handled separately via LangGraph)
- ✅ Uses SQLAlchemy repositories instead of MongoDB repositories
- ✅ Thread ID generation handled in service (not from agent service)
- ✅ Properly loads content blocks from `message_content` table

**Methods**:
- `create_thread()` - Create new chat thread
- `get_thread()` - Get thread with all messages
- `get_thread_messages()` - Get messages for a thread
- `get_all_threads()` - List threads with pagination
- `get_all_threads_summary()` - Get thread summaries
- `delete_thread()` - Delete thread and all related data
- `update_thread_title()` - Update thread title
- `get_thread_count()` - Count threads for user

### 2. `message_management_service.py`
**Purpose**: Manages individual message operations

**Key Features**:
- User message creation
- Assistant message creation
- Message status updates
- Error handling for messages
- Message retrieval with filtering
- Block-level status updates
- Content sanitization
- Message ownership validation

**Key Differences from Old Service**:
- ✅ Updated imports to use SQLAlchemy repositories
- ✅ Same core functionality maintained
- ✅ Proper transaction handling with rollback on failures

**Methods**:
- `save_user_message()` - Save user message with content blocks
- `save_assistant_message()` - Save assistant message
- `update_message_status()` - Update message-level status
- `mark_message_error()` - Mark message as error
- `get_thread_messages()` - Get messages with filtering
- `get_last_message()` - Get last message in thread
- `update_block_status()` - Update block-level approval status
- `validate_message_ownership()` - Security validation
- `clear_previous_approvals()` - Efficiently clear pending approval status from previous assistant messages


### 3. `dependencies.py`
**Purpose**: FastAPI dependency injection for repositories and services

**Structure**:
```python
# Repository Dependencies
- get_chat_thread_repository()
- get_messages_repository()
- get_message_content_repository()

# Service Dependencies
- get_chat_thread_service()
- get_message_management_service()
```

**Usage Example**:
```python
from app.services.dependencies import get_chat_thread_service

@router.post("/threads")
async def create_thread(
    request: CreateChatRequest,
    service: ChatThreadService = Depends(get_chat_thread_service)
):
    return await service.create_thread(request)
```

## Architecture Overview

### Service Layer Responsibilities

1. **ChatThreadService** (Thread-level operations):
   - Thread CRUD operations
   - Thread listing and summaries
   - Cascading deletes (thread → messages → content blocks)
   - Thread metadata management

2. **MessageManagementService** (Message-level operations):
   - Message creation (user and assistant)
   - Message status management
   - Content block management
   - Message filtering and retrieval
   - Security validation

### Separation of Concerns

- **Thread ID Generation**: Handled by `ChatThreadService` (not agent service)
- **Checkpoint Management**: Handled separately via LangGraph's PostgresSaver
- **Message Content**: Stored in separate `message_content` table, loaded on demand
- **User Context**: Thread ownership tracked via `user_id` field

## Key Design Decisions

### 1. No Checkpoint Service Dependency
The old `chat_history_service.py` depended on `CheckpointService` for LangGraph state management. In this version:
- Checkpoints are managed directly by LangGraph's `PostgresSaver`
- Thread service doesn't need to know about checkpoint internals
- Cleaner separation of concerns

### 2. Thread ID from Service, Not Agent
- Thread IDs are generated in `ChatThreadService.create_thread()`
- Agent service receives thread_id as parameter
- Prevents circular dependencies

### 3. Content Blocks Separation
- Message content stored in separate `message_content` table
- Loaded on-demand when retrieving messages
- Supports block-level approval workflow
- Better performance for message listing

### 4. Repository Pattern
All database operations go through repositories:
- `ChatThreadRepository` - Thread operations
- `MessagesRepository` - Message operations
- `MessageContentRepository` - Content block operations

### 5. Transaction Safety
- Content blocks saved BEFORE message
- Rollback on failure to maintain consistency
- Proper error handling and logging

## Integration with Existing Code

### Using in API Routes

```python
from fastapi import APIRouter, Depends
from app.services.dependencies import get_chat_thread_service, get_message_management_service
from app.services import ChatThreadService, MessageManagementService

router = APIRouter()

@router.post("/threads")
async def create_thread(
    request: CreateChatRequest,
    thread_service: ChatThreadService = Depends(get_chat_thread_service)
):
    thread = await thread_service.create_thread(request, user_id="user123")
    return {"thread_id": thread.thread_id}

@router.post("/messages")
async def add_message(
    thread_id: str,
    content: str,
    msg_service: MessageManagementService = Depends(get_message_management_service)
):
    message = await msg_service.save_user_message(
        thread_id=thread_id,
        content=content
    )
    return message
```

### Using in Agent Service

```python
from app.services.dependencies import get_message_management_service

class AgentService:
    def __init__(self, msg_service: MessageManagementService):
        self.msg_service = msg_service
    
    async def process_user_input(self, thread_id: str, user_input: str):
        # Save user message
        user_msg = await self.msg_service.save_user_message(
            thread_id=thread_id,
            content=user_input
        )
        
        # Process with agent...
        response = await self.run_agent(thread_id, user_input)
        
        # Save assistant response
        assistant_msg = await self.msg_service.save_assistant_message(
            thread_id=thread_id,
            content=response
        )
        
        return assistant_msg
```

## Migration Notes

### From Old Services

If you're migrating from the old MongoDB-based services:

1. **Update Imports**:
   ```python
   # Old
   from src.services.chat_history_service import ChatHistoryService
   from src.services.message_management_service import MessageManagementService
   
   # New
   from app.services import ChatThreadService, MessageManagementService
   from app.services.dependencies import get_chat_thread_service, get_message_management_service
   ```

2. **Remove Checkpoint Service**:
   - Don't inject `CheckpointService` into thread service
   - Use LangGraph's checkpointer directly for state management

3. **Update Repository Initialization**:
   - Old: `await repo.ensure_indexes()` (MongoDB)
   - New: Repositories use SQLAlchemy session (no index setup needed)

4. **Thread ID Generation**:
   - Old: Thread ID from agent service
   - New: Thread ID from `ChatThreadService.create_thread()`

## Testing Recommendations

1. **Unit Tests**: Test each service method independently with mocked repositories
2. **Integration Tests**: Test service interactions with real database
3. **Transaction Tests**: Verify rollback behavior on failures
4. **Concurrency Tests**: Test concurrent message creation

## Future Enhancements

Potential improvements:
- Add caching layer for frequently accessed threads
- Implement soft deletes for threads
- Add message search functionality
- Implement message pagination improvements
- Add bulk operations for messages

## Additional Services

### Explorer & Visualization (Integrated into AgentService)

The explorer and visualization functionality has been integrated directly into `AgentService` rather than creating separate service classes. This provides a cleaner architecture and avoids unnecessary service proliferation.

**Methods Added to AgentService**:

1. **`get_explorer_data(thread_id, checkpoint_id)`**
   - Retrieves exploration data from a specific checkpoint
   - Returns steps, plan, confidence scores, and final results
   - Useful for displaying agent reasoning and execution flow

2. **`get_visualization_data(thread_id, checkpoint_id)`**
   - Retrieves visualization data from a specific checkpoint
   - Returns normalized visualization objects
   - Supports multiple visualization types

**Usage Example**:
```python
from app.services.agent_service import AgentService

agent_service = AgentService()
# ... initialize agent ...

# Get explorer data
explorer_data = await agent_service.get_explorer_data(
    thread_id="abc123",
    checkpoint_id="checkpoint_xyz"
)

# Get visualization data
viz_data = await agent_service.get_visualization_data(
    thread_id="abc123",
    checkpoint_id="checkpoint_xyz"
)
```

### Storage Service (Supabase)

**File**: `storage_service.py`

Handles image uploads to Supabase Storage for plot/visualization images.

**Features**:
- Unique file path generation with timestamps
- Automatic content-type handling
- Public URL generation
- File deletion support
- Global singleton pattern

**Usage Example**:
```python
from app.services import get_supabase_storage_service

# Get storage service instance
storage = get_supabase_storage_service()

# Upload image
public_url = storage.upload_plot_image(
    image_data=plot_bytes,
    filename="chart.png",
    content_type="image/png"
)

# Delete image
success = storage.delete_plot_image("plots/20231209/abc123.png")
```

**Configuration**:
Requires the following settings in your config:
- `supabase_url`: Your Supabase project URL
- `supabase_service_role_key`: Service role key for authentication

### Visualization Utils

**File**: `utils/visualization_utils.py`

Utility functions for processing visualization data.

**Functions**:
- `normalize_visualizations(visualizations)` - Normalizes mixed format visualizations
- `get_visualization_summary(visualizations)` - Creates summary statistics

**Usage Example**:
```python
from app.utils.visualization_utils import normalize_visualizations, get_visualization_summary

# Normalize visualizations
normalized = normalize_visualizations(raw_viz_data)

# Get summary
summary = get_visualization_summary(normalized)
# Returns: {
#   "visualization_count": 3,
#   "has_visualizations": True,
#   "visualization_types": ["bar", "line"],
#   "visualizations_preview": [...]
# }
```

## Architecture Decisions

### Why Integrate Explorer/Visualization into AgentService?

1. **Tight Coupling**: Explorer and visualization data are tightly coupled to checkpoint state
2. **Single Responsibility**: AgentService already manages checkpoint access
3. **Reduced Complexity**: Avoids creating multiple service classes for related functionality
4. **Better Performance**: Direct access to graph state without additional abstraction layers

### Why Separate Storage Service?

1. **External Dependency**: Supabase is an external service, not core to agent logic
2. **Reusability**: Storage service can be used by multiple parts of the application
3. **Configuration**: Separate service allows for easier configuration management
4. **Testing**: Easier to mock and test independently

## Service Comparison

| Service | Location | Purpose | Dependencies |
|---------|----------|---------|--------------|
| ChatThreadService | `chat_thread_service.py` | Thread CRUD operations | Repositories |
| MessageManagementService | `message_management_service.py` | Message operations | Repositories |
| AgentService | `agent_service.py` | Agent execution, checkpoints, explorer, viz | LangGraph, Agent |
| SupabaseStorageService | `storage_service.py` | Image uploads | Supabase client |

## Migration from Old Services

### Agent Explorer Service → AgentService

**Old**:
```python
from src.services.agent_explorer_service import AgentExplorerService

explorer_service = AgentExplorerService(explainable_agent)
data = explorer_service.get_explorer_data(thread_id, checkpoint_id)
```

**New**:
```python
from app.services.agent_service import AgentService

agent_service = AgentService()
# ... initialize ...
data = await agent_service.get_explorer_data(thread_id, checkpoint_id)
```

### Agent Visualization Service → AgentService

**Old**:
```python
from src.services.agent_visualization_service import AgentVisualizationService

viz_service = AgentVisualizationService(explainable_agent)
data = viz_service.get_visualization_data(thread_id, checkpoint_id)
```

**New**:
```python
from app.services.agent_service import AgentService

agent_service = AgentService()
# ... initialize ...
data = await agent_service.get_visualization_data(thread_id, checkpoint_id)
```

### Supabase Storage Service → storage_service.py

**Old**:
```python
from src.services.supabase_storage_service import get_supabase_storage_service

storage = get_supabase_storage_service()
url = storage.upload_plot_image(image_data, filename)
```

**New**:
```python
from app.services import get_supabase_storage_service

storage = get_supabase_storage_service()
url = storage.upload_plot_image(image_data, filename)
```

**Key Changes**:
- Import path changed from `src.services` to `app.services`
- Explorer and visualization now use async methods
- Configuration now uses `app.core.config.settings`

