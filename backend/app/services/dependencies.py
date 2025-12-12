"""Dependency injection for repositories and services."""

from typing import Optional
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis

from app.core.database import get_db
from app.core.config import settings
from app.repositories.chat_thread_repository import ChatThreadRepository
from app.repositories.message_content_repository import MessageContentRepository
from app.repositories.messages_repository import MessagesRepository
from app.services.chat_thread_service import ChatThreadService
from app.services.message_management_service import MessageManagementService
from app.services.agent_service import AgentService
from app.services.redis_dataframe_service import RedisDataFrameService
from app.services.storage_service import SupabaseStorageService


# ==================== Repository Dependencies ====================

async def get_chat_thread_repository(
    session: AsyncSession = Depends(get_db)
) -> ChatThreadRepository:
    """Dependency to get ChatThreadRepository."""
    return ChatThreadRepository(session)


async def get_messages_repository(
    session: AsyncSession = Depends(get_db)
) -> MessagesRepository:
    """Dependency to get MessagesRepository."""
    return MessagesRepository(session)


async def get_message_content_repository(
    session: AsyncSession = Depends(get_db)
) -> MessageContentRepository:
    """Dependency to get MessageContentRepository."""
    return MessageContentRepository(session)


# ==================== Service Dependencies ====================

async def get_chat_thread_service(
    chat_thread_repo: ChatThreadRepository = Depends(get_chat_thread_repository),
    messages_repo: MessagesRepository = Depends(get_messages_repository),
    message_content_repo: MessageContentRepository = Depends(get_message_content_repository)
) -> ChatThreadService:
    """Dependency to get ChatThreadService."""
    return ChatThreadService(chat_thread_repo, messages_repo, message_content_repo)


async def get_message_management_service(
    messages_repo: MessagesRepository = Depends(get_messages_repository),
    chat_thread_repo: ChatThreadRepository = Depends(get_chat_thread_repository),
    message_content_repo: MessageContentRepository = Depends(get_message_content_repository)
) -> MessageManagementService:
    """Dependency to get MessageManagementService."""
    return MessageManagementService(messages_repo, chat_thread_repo, message_content_repo)


# Global service instances (singleton pattern)
_agent_service: Optional[AgentService] = None
_redis_df_service: Optional[RedisDataFrameService] = None
_storage_service: Optional[SupabaseStorageService] = None


def get_agent_service() -> AgentService:
    global _agent_service
    
    if _agent_service is None:
        _agent_service = AgentService()
    
    return _agent_service


def get_redis_dataframe_service() -> RedisDataFrameService:
    global _redis_df_service
    
    if _redis_df_service is None:
        _redis_df_service = RedisDataFrameService()
    
    return _redis_df_service


def get_supabase_storage_service() -> SupabaseStorageService:
    global _storage_service
    
    if _storage_service is None:
        _storage_service = SupabaseStorageService(
            supabase_url=settings.supabase_url,
            supabase_service_role_key=settings.supabase_service_role_key
        )
    
    return _storage_service



def initialize_agent_service(llm, db_path: str, use_postgres_checkpointer: bool = True) -> AgentService:
    global _agent_service
    
    if _agent_service is None:
        _agent_service = AgentService()
    
    _agent_service.initialize_agent(llm, db_path, use_postgres_checkpointer)
    return _agent_service


def reset_services() -> None:
    global _agent_service, _redis_df_service, _storage_service
    
    _agent_service = None
    _redis_df_service = None
    _storage_service = None
