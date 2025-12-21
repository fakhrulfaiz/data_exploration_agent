from typing import Dict, Any, AsyncGenerator, List
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
        
        if response_type in ["plan", "replan"]:
            block_id = f"plan_{self.context.assistant_message_id}"
            action = "replan" if response_type == "replan" else "add_planner"
            
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "plan",
                    "block_id": block_id,
                    "content": msg.content,
                    "node": "planner",
                    "message_id": self.context.assistant_message_id,
                    "action": action
                })
            }
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
                "needsApproval": needs_approval,
                "data": {"plan": self.plan_content}
            }]
