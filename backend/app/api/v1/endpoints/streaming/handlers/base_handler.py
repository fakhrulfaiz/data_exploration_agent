from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional, List
from dataclasses import dataclass
import logging

from app.services.message_management_service import MessageManagementService

logger = logging.getLogger(__name__)


@dataclass
class StreamContext:
    thread_id: str
    assistant_message_id: str
    node_name: str
    message_service: Optional[MessageManagementService]
    config: Dict[str, Any]
    # completed_blocks removed - blocks are now saved immediately via save_block()
    
    async def save_block(self, block: Dict[str, Any]) -> None:
        if not self.message_service:
            logger.warning("No message_service available, cannot save block")
            return
        
        try:
            # Get next sequence number
            sequence = await self._get_next_sequence(self.assistant_message_id)
            
            # Save to database
            await self.message_service.append_content_block(
                thread_id=self.thread_id,
                message_id=self.assistant_message_id,
                block=block,
                sequence=sequence
            )
            
            logger.info(
                f"✓ Saved block {block['id']} (type: {block['type']}) "
                f"with sequence {sequence}"
            )
        except Exception as e:
            logger.error(f"Failed to save block {block.get('id')}: {e}", exc_info=True)
            raise
    
    async def _get_next_sequence(self, message_id: str) -> int:
        max_seq = await self.message_service.get_max_sequence(
            thread_id=self.thread_id,
            message_id=message_id
        )
        return (max_seq or -1) + 1  # Start from 0 if no blocks exist



@dataclass
class ToolCallState:
    tool_call_id: str
    tool_name: str
    node: str
    index: int
    sequence: int
    args: str = ""
    output: Optional[str] = None
    content: Optional[str] = None
    saved: bool = False


class ContentHandler(ABC):
    
    def __init__(self, context: StreamContext):
        self.context = context
    
    @abstractmethod
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        pass
    
    @abstractmethod
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        pass
    
    async def finalize(self) -> AsyncGenerator[Dict, None]:
        if False:  # Make this a generator
            yield {}
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        """
        DEPRECATED: Blocks are now saved immediately via save_block().
        This method is kept for backward compatibility and returns an empty list.
        """
        return []

