from typing import Dict, Any, AsyncGenerator, List
import json
from uuid import uuid4

from .base_handler import ContentHandler, StreamContext


class FinalizerActionsContentHandler(ContentHandler):
    """Handler for finalizer response content blocks (combined response + actions)."""
    
    def __init__(self, context: StreamContext):
        super().__init__(context)
        self.finalizer_block_id = f"finalizer_response-{uuid4().hex[:12]}"
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Check if it's from finalizer node and has is_finalizer_response flag
        is_finalizer_response = (
            hasattr(msg, 'additional_kwargs') and 
            msg.additional_kwargs.get('is_finalizer_response', False)
        )
        
        return (
            hasattr(msg, 'content') and 
            msg.content and 
            type(msg).__name__ == 'AIMessage' and
            node_name == 'finalizer' and
            is_finalizer_response
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle finalizer response messages (combined response + actions)."""
        try:
            # Parse the combined JSON (should be complete in one message)
            response_data = json.loads(msg.content)
            
            # Validate structure
            if not isinstance(response_data, dict) or 'response' not in response_data or 'actions' not in response_data:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Invalid finalizer response data structure: {response_data}")
                return
            
            # Create the content block for database persistence
            finalizer_block = {
                "id": self.finalizer_block_id,
                "type": "finalizer_response",
                "needsApproval": False,
                "data": {
                    "response": response_data.get("response", ""),
                    "actions": response_data.get("actions", {})
                }
            }
            
            # Save immediately to database
            await self.context.save_block(finalizer_block)
            
            # Yield as content_block event for frontend streaming
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "finalizer_response",
                    "block_id": self.finalizer_block_id,
                    "data": {
                        "response": response_data.get("response", ""),
                        "actions": response_data.get("actions", {})
                    },
                    "node": "finalizer",
                    "stream_id": self._extract_msg_id(msg),
                    "message_id": self.context.assistant_message_id,
                    "action": "add_block"
                })
            }
        except json.JSONDecodeError as e:
            # Log error if JSON parsing fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to parse finalizer response JSON: {e}")
            return
    
    def _extract_msg_id(self, msg: Any) -> Any:
        """Extract message ID from the message."""
        import time as _time
        
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
        """Return the finalizer response content block."""
        # Response is sent immediately, no accumulation needed
        return []
