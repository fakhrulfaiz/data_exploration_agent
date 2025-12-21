from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional, List
from dataclasses import dataclass

from app.services.message_management_service import MessageManagementService


@dataclass
class StreamContext:
    thread_id: str
    assistant_message_id: str
    text_block_id: str
    node_name: str
    message_service: Optional[MessageManagementService]
    config: Dict[str, Any]


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
    
    @abstractmethod
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        pass
