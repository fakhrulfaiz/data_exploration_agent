from typing import Dict, Any, AsyncGenerator, List, Optional
import json
import logging

from .base_handler import ContentHandler, StreamContext

logger = logging.getLogger(__name__)


class PlanContentHandler(ContentHandler):
    def __init__(self, context: StreamContext, agent):
        super().__init__(context)
        self.agent = agent
        self.plan_content = ""
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        node_name = metadata.get('langgraph_node', 'unknown')
        return (
            node_name == 'planner' and
            hasattr(msg, 'content') and 
            msg.content and
            type(msg).__name__ == 'AIMessage'
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        self.plan_content = msg.content
        
        state = self.agent.graph.get_state(self.context.config)
        values = getattr(state, 'values', {}) or {}
        response_type = values.get("response_type")
        use_planning = values.get("use_planning", True)
     
        if response_type in ["plan", "replan"]:
            block_id = f"plan_{self.context.assistant_message_id}"
            action = "replan" if response_type == "replan" else "add_planner"
            
            # Determine if approval is needed based on use_planning flag
            needs_approval = use_planning
            
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "plan",
                    "block_id": block_id,
                    "content": msg.content,
                    "node": "planner",
                    "message_id": self.context.assistant_message_id,
                    "needsApproval": needs_approval,  # Include in streaming event
                    "action": action
                })
            }
            
            # Save plan block IMMEDIATELY to database
            # This ensures block exists before plan approval interrupt
            if hasattr(self.context, 'message_service') and self.context.message_service:
                try:
                    from app.api.v1.endpoints.streaming.streaming_persistence import StreamingMessagePersistence
                    persistence = StreamingMessagePersistence(self.context.message_service)
                    
                    plan_block = {
                        "id": block_id,
                        "type": "plan",
                        "needsApproval": needs_approval,
                        "data": {"plan": msg.content}
                    }
                    
                    user_id = self.context.config.get('configurable', {}).get('user_id')
                    checkpoint_id = self._extract_checkpoint_id(state)
                    
                    await persistence.save_with_content_blocks(
                        thread_id=self.context.thread_id,
                        user_id=user_id,
                        assistant_message_id=self.context.assistant_message_id,
                        content_blocks=[plan_block],
                        checkpoint_id=checkpoint_id,
                        needs_approval=needs_approval
                    )
                    logger.info(f"✅ Plan block {block_id} saved immediately (needsApproval={needs_approval})")
                except Exception as e:
                    logger.error(f"Failed to save plan block immediately: {e}", exc_info=True)
            
            # Append plan block to context in stream order
            plan_block = {
                "id": block_id,
                "type": "plan",
                "needsApproval": needs_approval,
                "data": {"plan": msg.content}
            }
            self.context.completed_blocks.append(plan_block)
        elif response_type == "answer":
            block_id = f"text_{self.context.assistant_message_id}"
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "text",
                    "block_id": block_id,
                    "content": msg.content,
                    "node": "planner",
                    "message_id": self.context.assistant_message_id,
                    "action": "append_text"
                })
            }
    
    def _extract_checkpoint_id(self, state: Any) -> Optional[str]:
        """Extract checkpoint ID from state."""
        try:
            if hasattr(state, 'config') and state.config and 'configurable' in state.config:
                configurable = state.config['configurable']
                if 'checkpoint_id' in configurable:
                    return str(configurable['checkpoint_id'])
        except Exception:
            pass
        return None
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        if not self.plan_content:
            return []
        
        state = self.agent.graph.get_state(self.context.config)
        values = getattr(state, 'values', {}) or {}
        response_type = values.get("response_type")
        
        if response_type == "answer":
            return [{
                "id": f"text_{self.context.assistant_message_id}",
                "type": "text",
                "needsApproval": False,
                "data": {"text": self.plan_content}
            }]
        else:
            return [{
                "id": f"plan_{self.context.assistant_message_id}",
                "type": "plan",
                "sequence": 0,  # Plan is always first
                "needsApproval": needs_approval,
                "data": {"plan": self.plan_content}
            }]

