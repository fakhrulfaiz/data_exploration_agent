"""Chat-related SQLAlchemy models for PostgreSQL."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Integer, BigInteger, DateTime, Boolean, Enum as SQLEnum, 
    ForeignKey, Index, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum

from .base import Base, TimestampMixin


class SenderEnum(str, enum.Enum):
    """Message sender types."""
    USER = "user"
    ASSISTANT = "assistant"


class MessageTypeEnum(str, enum.Enum):
    """Message types."""
    MESSAGE = "message"
    EXPLORER = "explorer"
    VISUALIZATION = "visualization"
    STRUCTURED = "structured"


class MessageStatusEnum(str, enum.Enum):
    """Message status types."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"
    TIMEOUT = "timeout"


class ChatThread(Base, TimestampMixin):
    """Chat thread/conversation model."""
    
    __tablename__ = "chat_threads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    
    # Relationships
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index('idx_chat_threads_updated_at', 'updated_at'),
        Index('idx_chat_threads_user_updated', 'user_id', 'updated_at'),
    )
    
    def __repr__(self):
        return f"<ChatThread(thread_id='{self.thread_id}', title='{self.title}')>"


class ChatMessage(Base):
    """Individual chat message model."""
    
    __tablename__ = "chat_messages"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, unique=True)
    thread_id: Mapped[str] = mapped_column(
        String(255), 
        ForeignKey("chat_threads.thread_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sender: Mapped[SenderEnum] = mapped_column(
        SQLEnum(SenderEnum, name="sender_enum"),
        nullable=False
    )
    message_type: Mapped[MessageTypeEnum] = mapped_column(
        SQLEnum(MessageTypeEnum, name="message_type_enum"),
        nullable=False,
        default=MessageTypeEnum.STRUCTURED
    )
    message_status: Mapped[Optional[MessageStatusEnum]] = mapped_column(
        SQLEnum(MessageStatusEnum, name="message_status_enum"),
        nullable=True
    )
    checkpoint_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    # Relationships
    thread: Mapped["ChatThread"] = relationship("ChatThread", back_populates="messages")
    content_blocks: Mapped[List["MessageContent"]] = relationship(
        "MessageContent",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index('idx_chat_messages_thread_timestamp', 'thread_id', 'timestamp'),
        Index('idx_chat_messages_thread_sender', 'thread_id', 'sender', 'timestamp'),
        Index('idx_chat_messages_thread_status', 'thread_id', 'message_status'),
        Index('idx_chat_messages_thread_type', 'thread_id', 'message_type'),
        Index('idx_chat_messages_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_chat_messages_user_checkpoint', 'user_id', 'checkpoint_id'),
    )
    
    def __repr__(self):
        return f"<ChatMessage(message_id={self.message_id}, thread_id='{self.thread_id}', sender='{self.sender}')>"


class MessageContent(Base):
    """Message content blocks model."""
    
    __tablename__ = "message_content"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_message_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("chat_messages.message_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    block_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    needs_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message_status: Mapped[Optional[MessageStatusEnum]] = mapped_column(
        SQLEnum(MessageStatusEnum, name="message_status_enum"),
        nullable=True
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    # Relationships
    message: Mapped["ChatMessage"] = relationship("ChatMessage", back_populates="content_blocks")
    
    __table_args__ = (
        Index('idx_message_content_message_created', 'chat_message_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<MessageContent(block_id='{self.block_id}', type='{self.type}')>"
