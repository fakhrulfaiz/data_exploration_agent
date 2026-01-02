from typing import Dict, Any, AsyncGenerator, List
import json
from uuid import uuid4

from .base_handler import ContentHandler, StreamContext


class ExplanationContentHandler(ContentHandler):
    """Handler for explanation content blocks from the explain node."""
    
    def __init__(self, context: StreamContext):
        super().__init__(context)
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Check specifically for is_explanation flag from ExplainerNode
        is_marked_explanation = False
        if hasattr(msg, 'additional_kwargs'):
            is_marked_explanation = msg.additional_kwargs.get('is_explanation', False)

        return (
            hasattr(msg, 'content') and 
            msg.content and 
            type(msg).__name__ == 'AIMessage' and
            (node_name == 'explainer' or is_marked_explanation)
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle explanation messages from the explain node."""
        try:
            # Parse the explanation JSON (should be complete in one message)
            explanation_data = json.loads(msg.content)
            
            # Generate unique block ID for this specific explanation
            block_id = f"explanation-{uuid4().hex[:12]}"
            
            # Yield as content_block event with type 'explanation'
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "explanation",
                    "block_id": block_id,
                    "data": explanation_data,
                    "node": "explain",
                    "stream_id": self._extract_msg_id(msg),
                    "message_id": self.context.assistant_message_id,
                    "action": "add_block"
                })
            }
        except json.JSONDecodeError as e:
            # Log error if JSON parsing fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to parse explanation JSON: {e}")
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
        """Return the explanation content block."""
        # Explanations are sent immediately, no accumulation needed
        return []
