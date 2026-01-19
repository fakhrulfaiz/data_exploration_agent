"""
XpAgentV2 Output Handler.

Handles the final output from XpAgentV2's aggregator and finalizer nodes.
Since the aggregator uses llm.invoke() (non-streaming), this handler processes
state updates to extract and stream the final_answer to the frontend.
"""

from typing import Dict, Any, AsyncGenerator, List, Optional
import json
import logging
from uuid import uuid4

from .base_handler import ContentHandler, StreamContext

logger = logging.getLogger(__name__)


class XpOutputHandler(ContentHandler):
    """
    Handler for XpAgentV2's aggregator output.
    
    This handler processes state updates from the aggregator node and emits
    the final_answer as a text block to the frontend.
    """
    
    def __init__(self, context: StreamContext, agent: Any):
        super().__init__(context)
        self.agent = agent
        self.output_emitted = False
        self.block_id = f"xp_output_{uuid4().hex[:12]}"
    
    async def can_handle_state_update(self, node_name: str, state_values: Dict) -> bool:
        """
        Check if this state update should be handled.
        
        Returns True if:
        - Node is aggregator or finalizer
        - Agent type is xp_agent_v2
        - final_answer is present in state
        - Output hasn't been emitted yet
        """
        if self.output_emitted:
            logger.debug(f"XpOutputHandler.can_handle_state_update: already emitted, skipping")
            return False
        
        agent_type = state_values.get("agent_type", "")
        if agent_type != "xp_agent_v2":
            logger.debug(f"XpOutputHandler.can_handle_state_update: agent_type={agent_type}, not xp_agent_v2")
            return False
        
        if node_name not in ("aggregator", "finalizer"):
            logger.debug(f"XpOutputHandler.can_handle_state_update: node_name={node_name}, not aggregator/finalizer")
            return False
        
        final_answer = state_values.get("final_answer")
        has_answer = bool(final_answer and final_answer.strip())
        logger.info(f"XpOutputHandler.can_handle_state_update: node={node_name}, has_final_answer={has_answer}")
        return has_answer
    
    async def handle_state_update(self, node_name: str, state_values: Dict) -> AsyncGenerator[Dict, None]:
        """
        Handle state update from aggregator/finalizer node.
        
        Extracts final_answer from state and emits it as a text block.
        """
        final_answer = state_values.get("final_answer", "")
        
        if not final_answer:
            logger.warning(f"XpOutputHandler: No final_answer found in state for node {node_name}")
            return
        
        self.output_emitted = True
        
        logger.info(f"XpOutputHandler: Emitting final answer from {node_name} ({len(final_answer)} chars)")
        
        # Create text block for persistence
        text_block = {
            "id": self.block_id,
            "type": "text",
            "needsApproval": False,
            "data": {"text": final_answer}
        }
        
        # Save to database
        await self.context.save_block(text_block)
        logger.info(f"✅ XpAgentV2 output block {self.block_id} saved")
        
        # Emit content_block event for frontend streaming
        # Use action "finalize_text" so frontend handles it as complete text
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "text",
                "block_id": self.block_id,
                "content": final_answer,
                "node": node_name,
                "message_id": self.context.assistant_message_id,
                "needsApproval": False,
                "action": "finalize_text"
            })
        }
    
    # Standard ContentHandler interface - not used for state updates
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        """Check if this message can be handled - not used for state updates."""
        return False
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle message - not used for state updates."""
        # This handler uses handle_state_update instead
        return
        yield  # Make this a generator
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        """Get content blocks for persistence."""
        if not self.output_emitted:
            return []
        
        return [{
            "id": self.block_id,
            "type": "text",
            "needsApproval": False,
            "data": {"text": ""}  # Content already saved
        }]
    
    def reset(self):
        """Reset handler state for new message."""
        self.output_emitted = False
        self.block_id = f"xp_output_{uuid4().hex[:12]}"
