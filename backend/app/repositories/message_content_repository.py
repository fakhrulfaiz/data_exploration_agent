"""Message content repository for async SQLAlchemy operations."""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc
from sqlalchemy.exc import SQLAlchemyError

from .base_repository import BaseRepository
from app.models.chat import MessageContent, MessageStatusEnum

logger = logging.getLogger(__name__)


class MessageContentRepository(BaseRepository[MessageContent]):
    """Repository for MessageContent operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, MessageContent)
    
    async def add_content_blocks(
        self, 
        chat_message_id: str,  # Message ID UUID string from message_id field
        blocks: List[Dict[str, Any]]
    ) -> bool:
        """
        Bulk insert content blocks for a message.
        
        Args:
            chat_message_id: Message ID (UUID string from message_id field, not integer PK)
            blocks: List of block dictionaries with id, type, needsApproval, data
            
        Returns:
            True if successful
        """
        try:
            if not blocks:
                return True  # No blocks to insert
            
            content_entities = []
            for block in blocks:
               
                needs_approval = block.get('needsApproval', block.get('needs_approval', False))
                block_id = block.get('id', block.get('block_id'))
                block_type = block.get('type')
                block_data = block.get('data', {})
                message_status = block.get('messageStatus', block.get('message_status'))
                
                if not block_id or not block_type:
                    logger.warning(f"Skipping block with missing id or type: {block}")
                    continue
                
                # Convert message_status string to enum if needed
                if message_status and isinstance(message_status, str):
                    try:
                        message_status = MessageStatusEnum(message_status)
                    except ValueError:
                        logger.warning(f"Invalid message_status: {message_status}")
                        message_status = None
                
                content = MessageContent(
                    chat_message_id=chat_message_id,
                    block_id=block_id,
                    type=block_type,
                    needs_approval=needs_approval,
                    message_status=message_status,
                    data=block_data,
                    created_at=datetime.now()
                )
                content_entities.append(content)
            
            if content_entities:
                self.session.add_all(content_entities)
                await self.session.flush()
                logger.info(f"Inserted {len(content_entities)} content blocks for message {chat_message_id}")
                return True
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error adding content blocks for message {chat_message_id}: {e}")
            await self.session.rollback()
            raise Exception(f"Failed to add content blocks: {e}")
    
    async def add_content_block_with_sequence(
        self,
        chat_message_id: str,
        block: Dict[str, Any]
    ) -> bool:
        try:
            # Get next sequence number for this message
            stmt = select(MessageContent).where(MessageContent.chat_message_id == chat_message_id)
            result = await self.session.execute(stmt)
            existing_blocks = result.scalars().all()
            next_sequence = len(existing_blocks)  # 0-indexed
            
            needs_approval = block.get('needsApproval', block.get('needs_approval', False))
            block_id = block.get('id', block.get('block_id'))
            block_type = block.get('type')
            block_data = block.get('data', {})
            message_status = block.get('messageStatus', block.get('message_status'))
            
            if not block_id or not block_type:
                logger.warning(f"Skipping block with missing id or type: {block}")
                return False
            
            # Convert message_status string to enum if needed
            if message_status and isinstance(message_status, str):
                try:
                    message_status = MessageStatusEnum(message_status)
                except ValueError:
                    logger.warning(f"Invalid message_status: {message_status}")
                    message_status = None
            
            content = MessageContent(
                chat_message_id=chat_message_id,
                block_id=block_id,
                type=block_type,
                needs_approval=needs_approval,
                message_status=message_status,
                data=block_data,
                sequence=next_sequence,  # Auto-assigned sequence
                created_at=datetime.now()
            )
            
            self.session.add(content)
            await self.session.flush()
            logger.info(f"Inserted content block {block_id} with sequence {next_sequence} for message {chat_message_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error adding content block for message {chat_message_id}: {e}")
            await self.session.rollback()
            raise Exception(f"Failed to add content block: {e}")
    
    async def get_blocks_by_message_id(self, chat_message_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all content blocks for a message, ordered by created_at.
        
        Args:
            chat_message_id: Chat message ID
            
        Returns:
            List of block dictionaries in frontend format
        """
        try:
            stmt = (
                select(MessageContent)
                .where(MessageContent.chat_message_id == chat_message_id)
                .order_by(asc(MessageContent.sequence))  # Order by sequence instead of created_at
            )
            result = await self.session.execute(stmt)
            documents = result.scalars().all()
            
            # Convert to frontend format
            blocks = []
            for doc in documents:
                blocks.append({
                    "id": doc.block_id,
                    "type": doc.type,
                    "needsApproval": doc.needs_approval,
                    "messageStatus": doc.message_status.value if doc.message_status else None,
                    "data": doc.data
                })
            
            return blocks
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving blocks for message {chat_message_id}: {e}")
            raise Exception(f"Failed to retrieve content blocks: {e}")
    
    async def update_block(self, block_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a content block by block_id.
        
        Args:
            block_id: Block ID to update
            updates: Dictionary with needsApproval, messageStatus, or data
            
        Returns:
            True if updated
        """
        try:
            # Normalize field names for updates
            normalized_updates = {}
            
            # Handle needsApproval
            if 'needsApproval' in updates:
                normalized_updates['needs_approval'] = updates['needsApproval']
            if 'needs_approval' in updates:
                normalized_updates['needs_approval'] = updates['needs_approval']
            
            # Handle message_status
            if 'messageStatus' in updates:
                status = updates['messageStatus']
                if isinstance(status, str):
                    try:
                        normalized_updates['message_status'] = MessageStatusEnum(status)
                    except ValueError:
                        logger.warning(f"Invalid messageStatus: {status}")
                else:
                    normalized_updates['message_status'] = status
            if 'message_status' in updates:
                normalized_updates['message_status'] = updates['message_status']
            
            # If message_status is set to approved or rejected, set needs_approval to False
            if 'message_status' in normalized_updates:
                status = normalized_updates['message_status']
                if status in [MessageStatusEnum.APPROVED, MessageStatusEnum.REJECTED]:
                    normalized_updates['needs_approval'] = False
                elif status == MessageStatusEnum.PENDING:
                    normalized_updates['needs_approval'] = True
            
            # Handle data updates
            if 'data' in updates:
                normalized_updates['data'] = updates['data']
            
            if not normalized_updates:
                logger.warning(f"No valid updates provided for block {block_id}")
                return False
            
            result = await self.update_by_id(block_id, normalized_updates, id_field="block_id")
            
            if result:
                logger.info(f"Updated block {block_id} with fields: {list(normalized_updates.keys())}")
            return result
        except SQLAlchemyError as e:
            logger.error(f"Error updating block {block_id}: {e}")
            raise Exception(f"Failed to update block: {e}")
    
    async def delete_blocks_by_message_id(self, chat_message_id: str) -> int:
        """
        Delete all content blocks for a message (cleanup operation).
        
        Args:
            chat_message_id: Chat message ID
            
        Returns:
            Number of deleted blocks
        """
        try:
            result = await self.delete_many({"chat_message_id": chat_message_id})
            logger.info(f"Deleted {result} content blocks for message {chat_message_id}")
            return result
        except SQLAlchemyError as e:
            logger.error(f"Error deleting blocks for message {chat_message_id}: {e}")
            raise Exception(f"Failed to delete content blocks: {e}")
    
    async def get_block_by_id(self, block_id: str) -> Optional[MessageContent]:
        """
        Get a single content block by block_id.
        
        Args:
            block_id: Block ID
            
        Returns:
            MessageContent if found, None otherwise
        """
        try:
            return await self.find_by_id(block_id, id_field="block_id")
        except Exception as e:
            logger.error(f"Error finding block {block_id}: {e}")
            return None
