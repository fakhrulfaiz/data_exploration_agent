"""Messages repository for async SQLAlchemy operations."""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, func, distinct
from sqlalchemy.exc import SQLAlchemyError

from .base_repository import BaseRepository
from app.models.chat import ChatMessage

logger = logging.getLogger(__name__)


class MessagesRepository(BaseRepository[ChatMessage]):
    """Repository for ChatMessage operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatMessage)
    
    async def add_message(self, message: ChatMessage) -> bool:
        """
        Add a new message.
        
        Args:
            message: ChatMessage instance to create
            
        Returns:
            True if successful
        """
        return await self.create(message)
    
    async def update_message_by_message_id(
        self, 
        message_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update specific fields of a message using its message_id.
        
        Args:
            message_id: Message ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if updated
        """
        # Remove None values to avoid overwriting fields with null
        safe_updates = {k: v for k, v in updates.items() if v is not None}
        return await self.update_by_id(message_id, safe_updates, id_field="message_id")
    
    async def get_message_by_id(
        self, 
        thread_id: str, 
        message_id: str
    ) -> Optional[ChatMessage]:
        """
        Get a specific message by its ID within a thread.
        
        Args:
            thread_id: Thread ID
            message_id: Message ID
            
        Returns:
            ChatMessage if found, None otherwise
        """
        try:
            stmt = select(ChatMessage).where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.message_id == message_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error finding message {message_id} in thread {thread_id}: {e}")
            raise Exception(f"Failed to find message: {e}")
    
    async def delete_message(self, message: ChatMessage) -> bool:
        """
        Delete a message.
        
        Args:
            message: ChatMessage instance to delete
            
        Returns:
            True if deleted
        """
        return await self.delete_by_id(message.message_id, "message_id")
    
    async def get_last_message_by_thread(self, thread_id: str) -> Optional[ChatMessage]:
        """
        Get the last message in a thread.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            ChatMessage if found, None otherwise
        """
        try:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.thread_id == thread_id)
                .order_by(desc(ChatMessage.timestamp))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error finding last message for thread {thread_id}: {e}")
            raise Exception(f"Failed to find last message: {e}")
    
    async def get_all_messages_by_thread(
        self,
        thread_id: str,
        limit: Optional[int] = None,
        skip: Optional[int] = None
    ) -> List[ChatMessage]:
        """
        Get all messages from a specific thread, ordered by timestamp.
        
        Args:
            thread_id: Thread ID
            limit: Maximum number of messages
            skip: Number of messages to skip
            
        Returns:
            List of ChatMessage instances
        """
        try:
            return await self.find_many(
                filter_criteria={"thread_id": thread_id},
                limit=limit,
                skip=skip,
                order_by=[asc(ChatMessage.timestamp)]
            )
        except SQLAlchemyError as e:
            logger.error(f"Error finding messages for thread {thread_id}: {e}")
            raise Exception(f"Failed to find messages for thread: {e}")
    
    async def get_messages_by_thread_paginated(
        self,
        thread_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Get paginated messages from a thread with metadata.
        
        Args:
            thread_id: Thread ID
            page: Page number (1-indexed)
            page_size: Number of messages per page
            
        Returns:
            Dictionary with messages and pagination metadata
        """
        try:
            skip = (page - 1) * page_size
            
            # Get messages and total count
            messages = await self.get_all_messages_by_thread(
                thread_id=thread_id,
                limit=page_size,
                skip=skip
            )
            total_count = await self.count_messages_by_thread(thread_id)
            
            return {
                "messages": messages,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_messages": total_count,
                    "total_pages": (total_count + page_size - 1) // page_size,
                    "has_next": page * page_size < total_count,
                    "has_previous": page > 1
                }
            }
        except SQLAlchemyError as e:
            logger.error(f"Error getting paginated messages for thread {thread_id}: {e}")
            raise Exception(f"Failed to get paginated messages: {e}")
    
    async def count_messages_by_thread(self, thread_id: str) -> int:
        """
        Count messages in a thread.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            Count of messages
        """
        return await self.count({"thread_id": thread_id})
    
    async def delete_messages_by_thread(self, thread_id: str) -> bool:
        """
        Delete all messages for a specific thread.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            True if any messages were deleted
        """
        try:
            deleted_count = await self.delete_many({"thread_id": thread_id})
            logger.info(f"Deleted {deleted_count} messages for thread {thread_id}")
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting messages for thread {thread_id}: {e}")
            raise Exception(f"Failed to delete messages: {e}")
    
    async def get_checkpoints_by_user_id(
        self,
        user_id: str,
        limit: Optional[int] = None,
        skip: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get distinct checkpoints for a user across all threads.
        
        Args:
            user_id: User ID
            limit: Maximum number of checkpoints
            skip: Number of checkpoints to skip
            
        Returns:
            List of checkpoint dictionaries with metadata
        """
        try:
            # Subquery to get the first occurrence of each checkpoint_id
            subquery = (
                select(
                    ChatMessage.checkpoint_id,
                    func.min(ChatMessage.id).label('min_id')
                )
                .where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.checkpoint_id.isnot(None)
                )
                .group_by(ChatMessage.checkpoint_id)
                .subquery()
            )
            
            # Main query to get checkpoint details
            stmt = (
                select(ChatMessage)
                .join(subquery, ChatMessage.id == subquery.c.min_id)
                .order_by(desc(ChatMessage.timestamp))
            )
            
            if skip:
                stmt = stmt.offset(skip)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.session.execute(stmt)
            messages = result.scalars().all()
            
            # Convert to checkpoint format
            checkpoints = []
            for msg in messages:
                checkpoints.append(                {
                    "checkpoint_id": msg.checkpoint_id,
                    "thread_id": msg.thread_id,
                    "timestamp": msg.timestamp,
                    "message_id": msg.message_id
                })
            
            return checkpoints
        except SQLAlchemyError as e:
            logger.error(f"Error finding checkpoints for user {user_id}: {e}")
            raise Exception(f"Failed to find checkpoints: {e}")
    
    async def count_checkpoints_by_user_id(self, user_id: str) -> int:
        """
        Count distinct checkpoints for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Count of distinct checkpoints
        """
        try:
            stmt = (
                select(func.count(distinct(ChatMessage.checkpoint_id)))
                .where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.checkpoint_id.isnot(None)
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"Error counting checkpoints for user {user_id}: {e}")
            raise Exception(f"Failed to count checkpoints: {e}")
