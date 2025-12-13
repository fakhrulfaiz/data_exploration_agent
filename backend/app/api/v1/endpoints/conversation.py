"""Conversation/thread management endpoints."""

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional
import logging

from app.services.chat_thread_service import ChatThreadService
from app.services.message_management_service import MessageManagementService
from app.services.agent_service import AgentService
from app.services.dependencies import (
    get_chat_thread_service,
    get_message_management_service,
    get_messages_repository
)
from app.repositories.messages_repository import MessagesRepository
from app.models.supabase_user import SupabaseUser
from app.core.auth import get_current_user, get_optional_user
from app.schemas.conversation import (
    CreateConversationRequest,
    UpdateTitleRequest,
    ConversationData,
    ConversationResponse,
    ConversationSummary,
    ConversationListData,
    ConversationListResponse,
    MessageStatusUpdateRequest,
    BlockStatusUpdateRequest,
    MessageStatusInfo,
    MessageStatusListData,
    MessageStatusListResponse,
    CheckpointSummary,
    CheckpointListData,
    CheckpointListResponse,
    RestoreConversationData,
    RestoreConversationResponse
)
from app.schemas.base import SuccessResponse

logger = logging.getLogger(__name__)

# Dependency function to get agent service from app state
def get_agent_service(request: Request) -> AgentService:
    """Get the initialized agent service from app state."""
    agent_service = request.app.state.agent_service
    if not hasattr(agent_service, '_agent') or agent_service._agent is None:
        raise HTTPException(status_code=500, detail="Agent service not properly initialized")
    return agent_service

router = APIRouter(
    prefix="/conversation",
    tags=["conversation"]
)


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    chat_service: ChatThreadService = Depends(get_chat_thread_service)
) -> ConversationResponse:
    """Create a new conversation thread."""
    try:
        user_id = current_user.user_id
        logger.info(f"Creating conversation with title: '{request.title}' for user: {user_id}")
        
        # Create a CreateChatRequest object for the service
        from app.schemas.chat import CreateChatRequest
        chat_request = CreateChatRequest(
            title=request.title,
            initial_message=request.initial_message
        )
        
        thread = await chat_service.create_thread(chat_request, user_id=user_id)
        logger.info(f"Thread created successfully: {thread.thread_id}")
        
        # Get full thread data
        thread_data = await chat_service.get_thread(thread.thread_id)
        
        if not thread_data:
            raise HTTPException(
                status_code=500,
                detail="Thread created but could not be retrieved"
            )
        
        return ConversationResponse(
            data=ConversationData(
                thread_id=thread_data.thread_id,
                title=thread_data.title,
                created_at=thread_data.created_at,
                updated_at=thread_data.updated_at,
                messages=[],
                message_count=0
            ),
            message="Conversation created successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create chat thread: {str(e)}") from e


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=100, description="Number of conversations to return"),
    skip: int = Query(0, ge=0, description="Number of conversations to skip"),
    chat_service: ChatThreadService = Depends(get_chat_thread_service)
) -> ConversationListResponse:
    """List all conversation threads."""
    try:
        logger.info("Retrieving conversations")
        
        threads = await chat_service.get_all_threads_summary(limit=limit, skip=skip)
        total = await chat_service.get_thread_count()
        
        conversations = [
            ConversationSummary(
                thread_id=thread.thread_id,
                title=thread.title,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                message_count=0,
                last_message_preview=None
            )
            for thread in threads
        ]
        
        return ConversationListResponse(
            data=ConversationListData(
                conversations=conversations,
                total=total
            ),
            message=f"Retrieved {len(conversations)} conversations"
        )
    except Exception as e:
        logger.error(f"Error retrieving conversations: {e}")
        return ConversationListResponse(
            status="error",
            message=f"Error retrieving conversations: {str(e)}",
            errors=[{"code": "LIST_ERROR", "message": str(e)}]
        )


# ==================== Checkpoint Management ====================

@router.get("/checkpoints", response_model=CheckpointListResponse)
async def list_checkpoints(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Number of checkpoints to return"),
    skip: int = Query(0, ge=0, description="Number of checkpoints to skip"),
    messages_repo: MessagesRepository = Depends(get_messages_repository),
    current_user: Optional[SupabaseUser] = Depends(get_optional_user)
) -> CheckpointListResponse:
    """Get all checkpoints for the current user across all threads."""
    try:
        # If no user is authenticated, return empty results
        if not current_user:
            logger.info("No authenticated user - returning empty checkpoints")
            return CheckpointListResponse(
                data=CheckpointListData(
                    checkpoints=[],
                    total=0
                ),
                message="No checkpoints available (not authenticated)"
            )
        
        user_id = current_user.user_id
        logger.info(f"Retrieving checkpoints for user_id: {user_id}")
        
        # Get checkpoints and total count for this user
        checkpoints_data = await messages_repo.get_checkpoints_by_user_id(
            user_id=user_id,
            limit=limit,
            skip=skip
        )
        total = await messages_repo.count_checkpoints_by_user_id(user_id=user_id)
        
        # Convert to CheckpointSummary models
        checkpoints = [
            CheckpointSummary(
                checkpoint_id=item["checkpoint_id"],
                thread_id=item["thread_id"],
                timestamp=item["timestamp"],
                message_type=item.get("message_type"),
                message_id=item["message_id"],
                query=None  # Query can be added later if needed
            )
            for item in checkpoints_data
        ]
        
        return CheckpointListResponse(
            data=CheckpointListData(
                checkpoints=checkpoints,
                total=total
            ),
            message=f"Retrieved {len(checkpoints)} checkpoints"
        )
    except Exception as e:
        error_msg = f"Error retrieving checkpoints: {str(e)}"
        if current_user:
            error_msg = f"Error retrieving checkpoints for user {current_user.user_id}: {str(e)}"
        logger.error(error_msg)
        return CheckpointListResponse(
            status="error",
            message=error_msg,
            errors=[{"code": "CHECKPOINT_ERROR", "message": str(e)}]
        )


@router.get("/{thread_id}", response_model=ConversationResponse)
async def get_conversation(
    thread_id: str,
    chat_service: ChatThreadService = Depends(get_chat_thread_service)
) -> ConversationResponse:
    """Get a specific conversation thread."""
    try:
        logger.info(f"Retrieving thread {thread_id}")
        
        thread = await chat_service.get_thread(thread_id)
        if not thread:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {thread_id} not found"
            )
        
        return ConversationResponse(
            data=ConversationData(
                thread_id=thread.thread_id,
                title=thread.title,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                messages=[],
                message_count=0
            ),
            message="Conversation retrieved successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{thread_id}/title", response_model=SuccessResponse)
async def update_conversation_title(
    thread_id: str,
    request: UpdateTitleRequest,
    chat_service: ChatThreadService = Depends(get_chat_thread_service)
) -> SuccessResponse:
    """Update the title of a conversation thread."""
    try:
        success = await chat_service.update_thread_title(thread_id, request.title)
        if not success:
            return SuccessResponse(
                status="error",
                message="Conversation not found",
                errors=[{"code": "CONVERSATION_NOT_FOUND", "message": f"Conversation {thread_id} not found"}]
            )
        
        return SuccessResponse(
            data={"thread_id": thread_id, "title": request.title},
            message="Conversation title updated successfully"
        )
    except Exception as e:
        logger.error(f"Error updating conversation title {thread_id}: {e}")
        return SuccessResponse(
            status="error",
            message=f"Error updating title: {str(e)}",
            errors=[{"code": "UPDATE_ERROR", "message": str(e)}]
        )


@router.delete("/{thread_id}", response_model=SuccessResponse)
async def delete_conversation(
    request: Request,
    thread_id: str,
    chat_service: ChatThreadService = Depends(get_chat_thread_service),
    agent_service: AgentService = Depends(get_agent_service)
) -> SuccessResponse:
    """Delete a conversation thread and its associated checkpoints."""
    try:
        success = await chat_service.delete_thread(
            thread_id, 
            delete_checkpoint=True,
            agent_service=agent_service
        )
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {thread_id} not found"
            )
        
        return SuccessResponse(
            data={"thread_id": thread_id},
            message="Conversation deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation {thread_id}: {e}")
        return SuccessResponse(
            status="error",
            message=f"Error deleting conversation: {str(e)}",
            errors=[{"code": "DELETE_ERROR", "message": str(e)}]
        )


@router.get("/{thread_id}/restore", response_model=RestoreConversationResponse)
async def restore_conversation(
    request: Request,
    thread_id: str,
    chat_service: ChatThreadService = Depends(get_chat_thread_service),
    agent_service: AgentService = Depends(get_agent_service)
) -> RestoreConversationResponse:
    """
    Restore a conversation thread for continuing conversation.
    Returns the full conversation history with data context if available.
    """
    try:
        logger.info(f"Restoring conversation {thread_id}")
        
        thread = await chat_service.get_thread(thread_id)
        if not thread:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {thread_id} not found"
            )

        data_context = None
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state = await agent_service.get_current_state(thread_id)
            if state and state.get("state"):
                dc = state["state"].get("data_context")
                # Convert DataContext instance to dict for Pydantic validation
                if dc is not None:
                    if hasattr(dc, 'model_dump'):
                        # Use mode='json' to serialize datetime objects to ISO strings
                        data_context = dc.model_dump(mode='json')
                    elif hasattr(dc, 'dict'):
                        data_context = dc.dict()
                    elif isinstance(dc, dict):
                        data_context = dc
        except Exception as state_error:
            logger.debug(f"Could not fetch data_context for thread {thread_id}: {state_error}")

        # Convert ChatMessageSchema objects to dict format for the response
        messages_data = []
        if thread.messages:
            for message in thread.messages:
                messages_data.append({
                    "thread_id": message.thread_id,
                    "sender": message.sender,
                    "content": message.content,
                    "timestamp": message.timestamp.isoformat() if message.timestamp else None,
                    "message_type": message.message_type,
                    "message_id": message.message_id,
                    "user_id": message.user_id,
                    "message_status": message.message_status,
                    "checkpoint_id": message.checkpoint_id
                })

        return RestoreConversationResponse(
            data=RestoreConversationData(
                thread_id=thread.thread_id,
                title=thread.title,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                messages=messages_data,
                message_count=len(messages_data),
                data_context=data_context
            ),
            message=f"Conversation restored successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ==================== Message Management Endpoints ====================

@router.get("/{thread_id}/messages/status", response_model=MessageStatusListResponse)
async def get_messages_status(
    thread_id: str,
    message_service: MessageManagementService = Depends(get_message_management_service)
) -> MessageStatusListResponse:
    """
    Get status information for all messages in a conversation.
    Helps the frontend sync its local state with the backend.
    """
    try:
        messages = await message_service.get_thread_messages(thread_id)
        
        status_info = [
            MessageStatusInfo(
                message_id=message.id,
                sender=message.sender,
                timestamp=message.timestamp,
                message_status=message.message_status,
                message_type=message.message_type,
                checkpoint_id=message.checkpoint_id,
                has_content_blocks=bool(message.content and len(message.content) > 0)
            )
            for message in messages
        ]
        
        return MessageStatusListResponse(
            data=MessageStatusListData(
                thread_id=thread_id,
                message_count=len(status_info),
                messages=status_info
            ),
            message=f"Retrieved status for {len(status_info)} messages"
        )
    except Exception as e:
        logger.error(f"Error getting message status for thread {thread_id}: {e}")
        return MessageStatusListResponse(
            status="error",
            message=f"Error getting message status: {str(e)}",
            errors=[{"code": "STATUS_ERROR", "message": str(e)}]
        )


@router.patch("/{thread_id}/messages/{message_id}/status", response_model=SuccessResponse)
async def update_message_status(
    thread_id: str,
    message_id: str,
    request: MessageStatusUpdateRequest,
    message_service: MessageManagementService = Depends(get_message_management_service)
) -> SuccessResponse:
    """
    Update message-level status (deprecated - use block-level approval endpoint instead).
    Kept for backward compatibility.
    """
    try:
        # Convert request to dict, excluding None values
        status_updates = {k: v for k, v in request.dict().items() if v is not None}
        
        if not status_updates:
            raise HTTPException(
                status_code=422,
                detail="No valid status updates provided"
            )
        
        success = await message_service.update_message_status(
            thread_id=thread_id,
            message_id=message_id,
            **status_updates
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Message {message_id} not found"
            )
        
        return SuccessResponse(
            data={"thread_id": thread_id, "message_id": message_id, "updated_fields": list(status_updates.keys())},
            message="Message status updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating message status for thread {thread_id}, message {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{thread_id}/messages/{message_id}/blocks/{block_id}/approval", response_model=SuccessResponse)
async def update_block_approval(
    thread_id: str,
    message_id: str,
    block_id: str,
    request: BlockStatusUpdateRequest,
    message_service: MessageManagementService = Depends(get_message_management_service)
) -> SuccessResponse:
    """
    Update block-level approval status.
    Allows the frontend to update individual block approval status within a message's content_blocks.
    """
    try:
        # Convert request to dict, excluding None values
        status_updates = {k: v for k, v in request.dict().items() if v is not None}
        
        if not status_updates:
            raise HTTPException(
                status_code=422,
                detail="No valid block status updates provided"
            )
        
        success = await message_service.update_block_status(
            thread_id=thread_id,
            message_id=message_id,
            block_id=block_id,
            **status_updates
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Block {block_id} not found"
            )
        
        return SuccessResponse(
            data={
                "thread_id": thread_id,
                "message_id": message_id,
                "block_id": block_id,
                "updated_fields": list(status_updates.keys())
            },
            message="Block status updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating block status for thread {thread_id}, message {message_id}, block {block_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{thread_id}/messages/{message_id}/error", response_model=SuccessResponse)
async def mark_message_error(
    thread_id: str,
    message_id: str,
    error_message: Optional[str] = None,
    message_service: MessageManagementService = Depends(get_message_management_service)
) -> SuccessResponse:
    """
    Mark a message as having an error.
    Useful for handling failed operations or timeout scenarios.
    """
    try:
        success = await message_service.mark_message_error(
            thread_id=thread_id,
            message_id=message_id,
            error_message=error_message
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Message {message_id} not found"
            )
        
        return SuccessResponse(
            data={"thread_id": thread_id, "message_id": message_id},
            message="Message marked as error successfully"
        )
    except Exception as e:
        logger.error(f"Error marking message as error for thread {thread_id}, message {message_id}: {e}")
        return SuccessResponse(
            status="error",
            message=f"Error marking message as error: {str(e)}",
            errors=[{"code": "ERROR_MARK_FAILED", "message": str(e)}]
        )

