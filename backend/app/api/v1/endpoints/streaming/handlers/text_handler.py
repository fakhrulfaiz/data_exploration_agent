"""
Handler for text content streaming.
"""

from typing import Dict, Any, AsyncGenerator, List
import json
import time as _time

from .base_handler import ContentHandler, StreamContext


class TextContentHandler(ContentHandler): 
    def __init__(self, context: StreamContext, nodes_to_stream: List[str] = None):
        super().__init__(context)
        self.nodes_to_stream = nodes_to_stream or ['agent', 'tool_explanation', 'joiner']
        self.accumulated_text = ""
        self.json_buffer = ""
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        node_name = metadata.get('langgraph_node', 'unknown')
        return (
            hasattr(msg, 'content') and 
            msg.content and 
            type(msg).__name__ in ['AIMessageChunk', 'AIMessage'] and
            node_name in self.nodes_to_stream
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        chunk_text = msg.content
        node_name = metadata.get('langgraph_node', 'unknown')
        
        if chunk_text.startswith("{") or self.json_buffer:
            self.json_buffer += chunk_text
            try:
                parsed = json.loads(self.json_buffer)
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "content": parsed.get("content", ""),
                        "node": node_name,
                        "type": "feedback_answer",
                        "stream_id": self._extract_msg_id(msg)
                    })
                }
                self.json_buffer = ""
            except json.JSONDecodeError:
                return  # Wait for more chunks
        else:
            # Stream text tokens
            self.accumulated_text += chunk_text
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "text",
                    "block_id": self.context.text_block_id,
                    "content": msg.content,
                    "node": node_name,
                    "stream_id": self._extract_msg_id(msg),
                    "message_id": self.context.assistant_message_id,
                    "action": "append_text"
                })
            }
    
    def _extract_msg_id(self, msg: Any) -> Any:
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
        if not self.accumulated_text:
            return []
        
        return [{
            "id": self.context.text_block_id,
            "type": "text",
            "needsApproval": False,
            "data": {"text": self.accumulated_text}
        }]
