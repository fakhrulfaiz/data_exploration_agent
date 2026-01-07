"""Handler for error explanation content blocks."""
from typing import Dict, Any, AsyncGenerator
import json
import logging
from .base_handler import ContentHandler, StreamContext

logger = logging.getLogger(__name__)


class ErrorExplanationHandler(ContentHandler):
    """Handles error explanation messages from error_explainer node."""
    
    def __init__(self, context: StreamContext):
        super().__init__(context)
        self.error_streamed = False  # Track if we already streamed this error
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Check if this is from error_explainer node
        if node_name != 'error_explainer':
            return False
        
        # Check if we already streamed this error
        if self.error_streamed:
            return False
        
        # Check if error_explanation exists in state
        try:
            state = self.context.agent.graph.get_state(self.context.config)
            values = getattr(state, 'values', {}) or {}
            has_error_explanation = values.get("error_explanation") is not None
            
            if has_error_explanation:
                logger.info("Error explanation found in state - will stream")
            
            return has_error_explanation
        except Exception as e:
            logger.error(f"Error checking for error_explanation: {e}")
            return False
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Stream error explanation as a content block."""
        logger.info("Streaming error explanation from error_explainer node")
        
        # Get error_explanation from state
        try:
            state = self.context.agent.graph.get_state(self.context.config)
            values = getattr(state, 'values', {}) or {}
            error_explanation = values.get("error_explanation")
            
            if error_explanation:
                block_id = f"error_{self.context.assistant_message_id}"
                
                yield {
                    "event": "content_block",
                    "data": json.dumps({
                        "block_type": "error",
                        "block_id": block_id,
                        "error_explanation": error_explanation,
                        "message_id": self.context.assistant_message_id,
                        "needsApproval": False,
                        "action": "add_error"
                    })
                }
                
                logger.info(f"Streamed error explanation block: {block_id}")
                self.error_streamed = True  # Mark as streamed
                
                # Save error block immediately to database
                error_block = {
                    "id": block_id,
                    "type": "error",
                    "needsApproval": False,
                    "data": error_explanation
                }
                await self.context.save_block(error_block)
                logger.info(f"✅ Error block {block_id} saved immediately")
            else:
                logger.warning("Error explainer node executed but no error_explanation in state")
                
        except Exception as e:
            logger.error(f"Failed to stream error explanation: {e}", exc_info=True)
    
    def get_content_blocks(self, needs_approval: bool = False) -> list:
        """Return empty list as blocks are already added during streaming."""
        return []
