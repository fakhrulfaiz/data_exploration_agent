"""Database connection and configuration module."""

import os
import logging
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager, contextmanager

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text

from .config import settings

logger = logging.getLogger(__name__)




class DatabaseManager:
    """Manages PostgreSQL database connections and operations."""
    
    def __init__(self):
        self.pool: Optional[ConnectionPool] = None
        self._db_uri = self._build_db_uri()
        self._async_db_uri = self._build_async_db_uri()
        
        # SQLAlchemy engines and sessions
        self.async_engine = None
        self.sync_engine = None
        self.async_session_factory = None
        self.sync_session_factory = None
    
    def _build_db_uri(self) -> str:
        """Build database URI from settings (for psycopg)."""
        return (
            f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )
    
    def _build_async_db_uri(self) -> str:
        """Build async database URI for SQLAlchemy (asyncpg)."""
        return (
            f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )
    
    def _build_sync_db_uri(self) -> str:
        """Build sync database URI for SQLAlchemy (psycopg)."""
        return (
            f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )
    
    async def initialize(self):
        """Initialize the database connection pool and SQLAlchemy engines."""
        try:
            # Create psycopg connection pool (for LangGraph checkpointer)
            self.pool = ConnectionPool(
                self._db_uri,
                min_size=2,
                max_size=10,
                kwargs={
                    "autocommit": True,
                    "row_factory": dict_row
                }
            )
            
            # Create SQLAlchemy engines
            self.async_engine = create_async_engine(
                self._async_db_uri,
                echo=settings.debug,
                pool_size=10,
                max_overflow=20
            )
            
            self.sync_engine = create_engine(
                self._build_sync_db_uri(),
                echo=settings.debug,
                pool_size=10,
                max_overflow=20
            )
            
            # Create session factories
            self.async_session_factory = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            self.sync_session_factory = sessionmaker(
                bind=self.sync_engine,
                expire_on_commit=False
            )
            
            # Test connections
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version()")
                    version = cur.fetchone()
                    logger.info(f"✅ Connected to PostgreSQL (psycopg): {version['version']}")
            
            # Test SQLAlchemy async connection
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                logger.info(f"✅ Connected to PostgreSQL (SQLAlchemy async): {version}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
    
    async def close(self):
        """Close the database connection pools and engines."""
        if self.pool:
            self.pool.close()
            logger.info("psycopg connection pool closed")
        
        if self.async_engine:
            await self.async_engine.dispose()
            logger.info("SQLAlchemy async engine disposed")
        
        if self.sync_engine:
            self.sync_engine.dispose()
            logger.info("SQLAlchemy sync engine disposed")
    
    @contextmanager
    def get_connection(self):
        """Get a synchronous database connection from the pool."""
        if not self.pool:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        with self.pool.connection() as conn:
            yield conn
    
    @asynccontextmanager
    async def get_async_connection(self):
        """Get an asynchronous database connection."""
        conn = await psycopg.AsyncConnection.connect(
            self._db_uri,
            autocommit=True,
            row_factory=dict_row
        )
        try:
            yield conn
        finally:
            await conn.close()
    
    def get_db_uri(self) -> str:
        """Get the database URI for external libraries (psycopg format)."""
        return self._db_uri
    
    def get_async_session(self) -> AsyncSession:
        """Get an async SQLAlchemy session."""
        if not self.async_session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.async_session_factory()
    
    def get_sync_session(self):
        """Get a sync SQLAlchemy session."""
        if not self.sync_session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.sync_session_factory()
    
    @asynccontextmanager
    async def get_async_session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async SQLAlchemy session with context management."""
        async with self.get_async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    @contextmanager
    def get_sync_session_context(self):
        """Get a sync SQLAlchemy session with context management."""
        with self.get_sync_session() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
    
    def health_check(self) -> bool:
        """Check if database is healthy."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()


# Convenience functions for raw connections (LangGraph checkpointer)
def get_db_connection():
    """Get a database connection context manager."""
    return db_manager.get_connection()


def get_async_db_connection():
    """Get an async database connection context manager."""
    return db_manager.get_async_connection()


def get_db_uri() -> str:
    """Get the database URI."""
    return db_manager.get_db_uri()


# Convenience functions for SQLAlchemy ORM
async def get_async_session() -> AsyncSession:
    """Get an async SQLAlchemy session."""
    return db_manager.get_async_session()


def get_sync_session():
    """Get a sync SQLAlchemy session."""
    return db_manager.get_sync_session()


def get_async_session_context():
    """Get an async SQLAlchemy session with context management."""
    return db_manager.get_async_session_context()


def get_sync_session_context():
    """Get a sync SQLAlchemy session with context management."""
    return db_manager.get_sync_session_context()


# FastAPI dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database sessions."""
    async with db_manager.get_async_session_context() as session:
        yield session
