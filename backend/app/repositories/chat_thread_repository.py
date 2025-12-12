"""Chat thread repository for async SQLAlchemy operations."""

import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.exc import SQLAlchemyError

from .base_repository import BaseRepository
from app.models.chat import ChatThread

logger = logging.getLogger(__name__)


class ChatThreadRepository(BaseRepository[ChatThread]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatThread)
    
    async def find_by_thread_id(
        self, 
        thread_id: str, 
        user_id: Optional[str] = None
    ) -> Optional[ChatThread]:
        thread = await self.find_by_id(thread_id, "thread_id")
        
        if thread and user_id:
            # Verify ownership
            if thread.user_id and thread.user_id != user_id:
                logger.warning(
                    f"User {user_id} attempted to access thread {thread_id} "
                    f"owned by {thread.user_id}"
                )
                return None
        
        return thread
    
    async def create_thread(self, thread: ChatThread) -> bool:
        return await self.create(thread)
    
    async def update_thread_title(self, thread_id: str, title: str) -> bool:
        return await self.update_by_id(
            thread_id,
            {"title": title, "updated_at": datetime.now()},
            "thread_id"
        )
    
    async def delete_thread(self, thread_id: str) -> bool:
        return await self.delete_by_id(thread_id, "thread_id")
    
    async def get_threads(
        self,
        limit: int = 50,
        skip: int = 0,
        user_id: Optional[str] = None
    ) -> List[ChatThread]:
        """
        Get list of threads with pagination and optional user filtering.
        
        Args:
            limit: Maximum number of threads to return
            skip: Number of threads to skip (offset)
            user_id: Optional user ID to filter by
            
        Returns:
            List of ChatThread instances
        """
        try:
            stmt = select(ChatThread)
            
            # Filter by user_id if provided
            if user_id:
                stmt = stmt.where(ChatThread.user_id == user_id)
            
            # Order by updated_at descending
            stmt = stmt.order_by(desc(ChatThread.updated_at))
            
            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)
            
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
            
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving chat threads: {e}")
            raise Exception(f"Failed to retrieve chat threads: {e}")
    
    async def count_threads(self, user_id: Optional[str] = None) -> int:
        """
        Count threads with optional user filter.
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            Count of threads
        """
        filter_criteria = {"user_id": user_id} if user_id else None
        return await self.count(filter_criteria)
