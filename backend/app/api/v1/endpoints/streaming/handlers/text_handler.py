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
        # Support both data_exploration_agent and main_agent node names
        self.nodes_to_stream = nodes_to_stream or [
            'agent',           # data_exploration_agent execution node
            'agent_executor',  # data_exploration_agent executor node
            'tool_explanation',# tool explanation node
            'joiner',          # data_exploration_agent joiner node
            'process_query',   # main_agent execution node
            'finalizer',        # main_agent finalizer node
            'planner'
        ]
        # Track text per message ID instead of accumulating per node
        self.message_texts: Dict[str, Dict[str, Any]] = {}  # msg_id -> {text, node, block_id}
        self.json_buffer = ""
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Skip messages with tool_calls - they're handled by tool_call_handler
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            return False
            
        # Skip reasoning chain and finalizer response messages - they're handled by their own handlers
        additional_kwargs = getattr(msg, 'additional_kwargs', {})
        if additional_kwargs.get('is_reasoning_chain', False) or additional_kwargs.get('is_finalizer_response', False):
            return False
        
        return (
            hasattr(msg, 'content') and 
            msg.content and 
            type(msg).__name__ in ['AIMessageChunk', 'AIMessage'] and
            node_name in self.nodes_to_stream
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        chunk_text = msg.content
        node_name = metadata.get('langgraph_node', 'unknown')
        msg_id = self._extract_msg_id(msg)
        
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
                        "stream_id": msg_id
                    })
                }
                self.json_buffer = ""
                return  # CRITICAL: Stop here to prevent duplicate content_block event
            except json.JSONDecodeError:
                return  # Wait for more chunks
        else:
            # Track text per message ID - each message gets its own block
            if msg_id not in self.message_texts:
                # Save the previous message's text block immediately
                if self.message_texts:
                    last_msg_id = list(self.message_texts.keys())[-1]
                    last_msg_data = self.message_texts[last_msg_id]
                    if last_msg_data["text"].strip():
                        block = {
                            "id": last_msg_data["block_id"],
                            "type": "text",
                            "needsApproval": False,
                            "data": {"text": last_msg_data["text"]}
                        }
                        await self.context.save_block(block)
                
                self.message_texts[msg_id] = {
                    "text": "",
                    "node": node_name,
                    "block_id": f"text_{msg_id}"
                }
                
                # Pre-save block to establish sequence
                initial_block = {
                    "id": f"text_{msg_id}",
                    "type": "text",
                    "needsApproval": False,
                    "data": {"text": chunk_text}
                }
                await self.context.save_block(initial_block)
            
            self.message_texts[msg_id]["text"] += chunk_text
            
            
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "text",
                    "block_id": f"text_{msg_id}",
                    "content": msg.content,
                    "node": node_name,
                    "stream_id": msg_id,
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
        """Return separate text blocks for each message that produced text."""
        blocks = []
        
        # Create a separate block for each message's text
        for msg_id, msg_data in self.message_texts.items():
            text = msg_data["text"]
            if text.strip():  # Only include non-empty text
                blocks.append({
                    "id": msg_data["block_id"],
                    "type": "text",
                    "needsApproval": False,
                    "data": {"text": text}
                })
        
        return blocks
    
    async def finalize(self) -> AsyncGenerator[Dict, None]:
        """Save the last text block when streaming completes."""
        # Save the last message immediately
        if self.message_texts:
            last_msg_id = list(self.message_texts.keys())[-1]
            last_msg_data = self.message_texts[last_msg_id]
            text = last_msg_data["text"]
            if text.strip():  # Only include non-empty text
                block = {
                    "id": last_msg_data["block_id"],
                    "type": "text",
                    "needsApproval": False,
                    "data": {"text": text}
                }
                # Save immediately instead of appending to completed_blocks
                await self.context.save_block(block)
        
        # Make this a generator
        if False:
            yield {}

