"""Chat thread service for managing chat threads and related operations."""

from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
import uuid
import logging

if TYPE_CHECKING:
    from app.services.agent_service import AgentService

from app.repositories.chat_thread_repository import ChatThreadRepository
from app.repositories.messages_repository import MessagesRepository
from app.repositories.message_content_repository import MessageContentRepository
from app.models.chat import ChatThread
from app.schemas.chat import (
    ChatThreadSummary,
    ChatThreadWithMessages,
    CreateChatRequest,
    ChatMessageSchema
)

logger = logging.getLogger(__name__)


class ChatThreadService:
    """Service for managing chat threads using repository pattern."""
    
    def __init__(
        self,
        chat_thread_repo: ChatThreadRepository,
        messages_repo: MessagesRepository,
        message_content_repo: MessageContentRepository
    ):
        self.chat_thread_repo = chat_thread_repo
        self.messages_repo = messages_repo
        self.message_content_repo = message_content_repo
    
    async def create_thread(
        self, 
        request: CreateChatRequest, 
        user_id: Optional[str] = None
    ) -> ChatThread:
        """Create a new chat thread."""
        try:
            # Generate thread_id
            thread_id = str(uuid.uuid4())
            
            # Create thread object
            thread = ChatThread(
                thread_id=thread_id,
                title=request.title or "New Chat",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                user_id=user_id
            )
            
            if user_id:
                logger.info(f"Creating new chat thread: {thread_id} with user_id: {user_id}")
            
            # Save thread
            success = await self.chat_thread_repo.create_thread(thread)
            if not success:
                raise Exception("Failed to create chat thread in database")
            
            logger.info(f"Created new chat thread: {thread_id}")
            
            # Verify thread was actually created
            try:
                created_thread = await self.chat_thread_repo.find_by_id(thread_id, "thread_id")
                logger.info(f"Thread verification - exists: {created_thread is not None}")
            except Exception as e:
                logger.error(f"Error verifying thread creation: {e}")
            
            return thread
            
        except Exception as e:
            logger.error(f"Error creating chat thread: {e}")
            raise Exception(f"Failed to create chat thread: {e}")
    
    async def get_thread(
        self, 
        thread_id: str, 
        user_id: Optional[str] = None
    ) -> Optional[ChatThreadWithMessages]:
        """Get a thread with all its messages."""
        try:
            thread = await self.chat_thread_repo.find_by_thread_id(thread_id, user_id=user_id)
            if not thread:
                return None
            
            messages = await self.get_thread_messages(thread_id)
            return ChatThreadWithMessages(
                thread_id=thread.thread_id,
                title=thread.title,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                user_id=thread.user_id,
                messages=messages
            )
        except Exception as e:
            logger.error(f"Error retrieving chat thread {thread_id}: {e}")
            raise Exception(f"Failed to retrieve chat thread: {e}")
    
    async def get_thread_messages(self, thread_id: str) -> List[ChatMessageSchema]:
        """Get all messages for a thread with content blocks loaded."""
        try:
            messages = await self.messages_repo.get_all_messages_by_thread(thread_id)
            
            # Load content blocks for each message
            result_messages = []
            for message in messages:
                if message.message_id:  # Use message_id (UUID) which is the FK in message_content
                    try:
                        content_blocks = await self.message_content_repo.get_blocks_by_message_id(
                            message.message_id  # chat_message_id references chat_messages.message_id
                        )
                        # Convert to schema
                        message_schema = ChatMessageSchema(
                            thread_id=message.thread_id,
                            sender=message.sender,
                            content=content_blocks,
                            timestamp=message.timestamp,
                            message_id=message.message_id,
                            user_id=message.user_id,
                            checkpoint_id=message.checkpoint_id
                        )
                        result_messages.append(message_schema)
                    except Exception as e:
                        logger.warning(
                            f"Failed to load content blocks for message {message.message_id}: {e}"
                        )
            
            return result_messages
        except Exception as e:
            logger.error(f"Error retrieving chat thread messages {thread_id}: {e}")
            raise Exception(f"Failed to retrieve chat thread messages: {e}")
    
    async def get_all_threads(
        self, 
        limit: int = 50, 
        skip: int = 0, 
        user_id: Optional[str] = None
    ) -> List[ChatThread]:
        """Get all threads with pagination."""
        try:
            return await self.chat_thread_repo.get_threads(
                limit=limit, 
                skip=skip, 
                user_id=user_id
            )
        except Exception as e:
            logger.error(f"Error retrieving chat threads: {e}")
            raise Exception(f"Failed to retrieve chat threads: {e}")
    
    async def get_all_threads_summary(
        self, 
        limit: int = 50, 
        skip: int = 0, 
        user_id: Optional[str] = None
    ) -> List[ChatThreadSummary]:
        """Get thread summaries with message counts and last message preview."""
        try:
            chat_threads = await self.chat_thread_repo.get_threads(
                limit=limit, 
                skip=skip, 
                user_id=user_id
            )
            
            thread_summaries = []
            for thread in chat_threads:
                message_count = await self.messages_repo.count_messages_by_thread(thread.thread_id)
                last_message_obj = await self.messages_repo.get_last_message_by_thread(
                    thread.thread_id
                )
                
                # Extract text preview from content blocks
                last_message = None
                if last_message_obj and last_message_obj.message_id:
                    try:
                        content_blocks = await self.message_content_repo.get_blocks_by_message_id(
                            last_message_obj.message_id
                        )
                        
                        # Extract text from content blocks
                        if content_blocks:
                            text_parts = []
                            for block in content_blocks:
                                if isinstance(block, dict) and block.get('type') == 'text':
                                    text = block.get('data', {}).get('text', '')
                                    if text:
                                        text_parts.append(text)
                            
                            if text_parts:
                                # Join all text parts and truncate to 100 chars for preview
                                preview = ' '.join(text_parts)
                                last_message = preview[:100] + '...' if len(preview) > 100 else preview
                    except Exception as e:
                        logger.warning(
                            f"Failed to load content blocks for message {last_message_obj.message_id}: {e}"
                        )
                
                thread_summary = ChatThreadSummary(
                    thread_id=thread.thread_id,
                    title=thread.title,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                    last_message=last_message,
                    message_count=message_count
                )
                thread_summaries.append(thread_summary)
            
            return thread_summaries
        except Exception as e:
            logger.error(f"Error retrieving chat thread summaries: {e}")
            raise Exception(f"Failed to retrieve chat thread summaries: {e}")
    
    async def delete_thread(
        self, 
        thread_id: str, 
        delete_checkpoint: bool = True,
        agent_service: Optional['AgentService'] = None
    ) -> bool:
        try:
            logger.info(f"Deleting thread {thread_id} (delete_checkpoint={delete_checkpoint})")
            
            # Delete the thread - SQLAlchemy cascade will handle messages and content
            thread_deleted = await self.chat_thread_repo.delete_thread(thread_id)
            
            if not thread_deleted:
                logger.warning(f"Thread {thread_id} not found for deletion")
                return False
            
            logger.info(
                f"Deleted chat thread: {thread_id} "
                f"(messages and content blocks deleted via cascade)"
            )
            
            # Also delete the checkpoint if requested
            if delete_checkpoint and agent_service:
                try:
                    if agent_service.is_initialized():
                        checkpoint_deleted = await agent_service.delete_thread(thread_id)
                        if checkpoint_deleted:
                            logger.info(f"Deleted checkpoint for thread {thread_id}")
                        else:
                            logger.warning(f"Checkpoint for thread {thread_id} not found or already deleted")
                    else:
                        logger.warning("AgentService not initialized, skipping checkpoint deletion")
                except Exception as e:
                    logger.warning(f"Failed to delete checkpoint for thread {thread_id}: {e}")
                    # Don't fail the whole operation if checkpoint deletion fails
            elif delete_checkpoint and not agent_service:
                logger.warning(f"AgentService not provided, skipping checkpoint deletion for thread {thread_id}")
            
            return True
                
        except Exception as e:
            logger.error(f"Error deleting chat thread {thread_id}: {e}")
            raise Exception(f"Failed to delete chat thread: {e}")

    
    async def update_thread_title(self, thread_id: str, title: str) -> bool:
        """Update the title of a thread."""
        try:
            success = await self.chat_thread_repo.update_thread_title(thread_id, title)
            if success:
                logger.info(f"Updated title for thread {thread_id}")
            else:
                logger.warning(f"Thread {thread_id} not found for title update")
            return success
        except Exception as e:
            logger.error(f"Error updating thread title {thread_id}: {e}")
            raise Exception(f"Failed to update thread title: {e}")
    
    async def get_thread_count(self, user_id: Optional[str] = None) -> int:
        """Get the count of threads for a user."""
        try:
            return await self.chat_thread_repo.count_threads(user_id=user_id)
        except Exception as e:
            logger.error(f"Error counting chat threads: {e}")
            return 0
