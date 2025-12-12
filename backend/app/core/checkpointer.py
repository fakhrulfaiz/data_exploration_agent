"""LangGraph checkpointer configuration and management."""

import logging
from typing import Optional
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .database import db_manager

logger = logging.getLogger(__name__)


class CheckpointerManager:
    """Manages LangGraph PostgreSQL checkpointers."""
    
    def __init__(self):
        self._sync_checkpointer: Optional[PostgresSaver] = None
        self._async_checkpointer: Optional[AsyncPostgresSaver] = None
        self._initialized = False
    
    def initialize(self):
        """Initialize checkpointer and create tables if needed."""
        try:
            db_uri = db_manager.get_db_uri()
            
            # Create sync checkpointer and setup tables
            with PostgresSaver.from_conn_string(db_uri) as checkpointer:
                checkpointer.setup()
                logger.info("✅ LangGraph checkpointer tables created/verified")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize checkpointer: {e}")
            raise
    
    @contextmanager
    def get_sync_checkpointer(self):
        """Get a synchronous PostgresSaver instance."""
        if not self._initialized:
            raise RuntimeError("Checkpointer not initialized. Call initialize() first.")
        
        db_uri = db_manager.get_db_uri()
        with PostgresSaver.from_conn_string(db_uri) as checkpointer:
            yield checkpointer
    
    def get_async_checkpointer(self):
        """Get an asynchronous PostgresSaver context manager."""
        if not self._initialized:
            raise RuntimeError("Checkpointer not initialized. Call initialize() first.")
        
        db_uri = db_manager.get_db_uri()
        return AsyncPostgresSaver.from_conn_string(db_uri)
    
    def is_initialized(self) -> bool:
        """Check if checkpointer is initialized."""
        return self._initialized


# Global checkpointer manager instance
checkpointer_manager = CheckpointerManager()


# Convenience functions
def get_sync_checkpointer():
    """Get a synchronous checkpointer context manager."""
    return checkpointer_manager.get_sync_checkpointer()


def get_async_checkpointer():
    """Get an asynchronous checkpointer context manager."""
    return checkpointer_manager.get_async_checkpointer()


def initialize_checkpointer():
    """Initialize the checkpointer."""
    return checkpointer_manager.initialize()
