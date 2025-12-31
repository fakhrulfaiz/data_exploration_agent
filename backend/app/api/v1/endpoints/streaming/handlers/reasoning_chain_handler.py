from typing import Dict, Any, AsyncGenerator, List
import json
from uuid import uuid4

from .base_handler import ContentHandler, StreamContext


class ReasoningChainContentHandler(ContentHandler):
    """Handler for reasoning chain content blocks from the joiner node."""
    
    def __init__(self, context: StreamContext):
        super().__init__(context)
        self.reasoning_chain_block_id = f"reasoning_chain-{uuid4().hex[:12]}"
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        """Check if this is a reasoning chain message from joiner node."""
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Check if it's from joiner node and has is_reasoning_chain flag
        is_reasoning_chain = (
            hasattr(msg, 'additional_kwargs') and 
            msg.additional_kwargs.get('is_reasoning_chain', False)
        )
        
        return (
            hasattr(msg, 'content') and 
            msg.content and 
            type(msg).__name__ == 'AIMessage' and
            node_name == 'joiner' and
            is_reasoning_chain
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle reasoning chain messages from the joiner node."""
        try:
            # Parse the reasoning chain JSON (should be complete in one message)
            chain_data = json.loads(msg.content)
            
            # Validate it has the expected structure
            if chain_data.get('type') != 'reasoning_chain' or 'steps' not in chain_data:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Invalid reasoning chain data structure: {chain_data}")
                return
            
            # Create the content block for database persistence
            reasoning_chain_block = {
                "id": self.reasoning_chain_block_id,
                "type": "reasoning_chain",
                "needsApproval": False,
                "data": {
                    "steps": chain_data.get('steps', [])
                }
            }
            
            # Add to context.completed_blocks for database persistence
            self.context.completed_blocks.append(reasoning_chain_block)
            
            # Yield as content_block event for frontend streaming
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "reasoning_chain",
                    "block_id": self.reasoning_chain_block_id,
                    "data": {
                        "steps": chain_data.get('steps', [])
                    },
                    "node": "joiner",
                    "stream_id": self._extract_msg_id(msg),
                    "message_id": self.context.assistant_message_id,
                    "action": "add_block"
                })
            }
        except json.JSONDecodeError as e:
            # Log error if JSON parsing fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to parse reasoning chain JSON: {e}")
            return
    
    def _extract_msg_id(self, msg: Any) -> Any:
        """Extract message ID from the message."""
        tool_call_id = getattr(msg, 'tool_call_id', None)
        if tool_call_id is not None and tool_call_id != "":
            if isinstance(tool_call_id, str) and tool_call_id.isdigit():
                return int(tool_call_id)
            return tool_call_id
        
        msg_id = getattr(msg, 'id', None)
        if not msg_id and hasattr(msg, 'response_metadata'):
            meta = getattr(msg, 'response_metadata') or {}
            for key in ['message_id', 'id']:
                mid = meta.get(key)
                if mid is not None:
                    msg_id = mid
                    break
        
        if isinstance(msg_id, str):
            try:
                if msg_id.isdigit():
                    return int(msg_id)
            except:
                pass
        
        if msg_id is None or (isinstance(msg_id, str) and not msg_id):
            return int(_time.time() * 1000000)
        
        return msg_id
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        """Return the reasoning chain content block."""
        # Reasoning chains are sent immediately, no accumulation needed
        return []
