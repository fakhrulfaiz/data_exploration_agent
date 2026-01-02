from typing import Dict, Any, AsyncGenerator, Optional, List
import json
import logging

from .base_handler import ContentHandler, StreamContext, ToolCallState

logger = logging.getLogger(__name__)


class ToolCallHandler(ContentHandler):
    def __init__(self, context: StreamContext):
        super().__init__(context)
        self.pending_tools: Dict[str, ToolCallState] = {}
        self.completed_tools: Dict[str, Dict] = {}
        self.active_tool_id: Optional[str] = None
        self.active_tool_name: Optional[str] = None
        self.sequence_counter = 0  # Internal counter
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        return (
            (hasattr(msg, 'tool_call_chunks') and msg.tool_call_chunks) or
            (hasattr(msg, 'tool_call_id') and hasattr(msg, 'content'))
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        if hasattr(msg, 'tool_call_chunks') and msg.tool_call_chunks:
            async for event in self._handle_tool_chunk(msg, metadata):
                yield event
        elif hasattr(msg, 'tool_call_id') and hasattr(msg, 'content'):
            async for event in self._handle_tool_result(msg, metadata):
                yield event
    
    async def _handle_tool_chunk(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Only process tool calls from agent and agent_executor nodes
        if node_name not in ['agent', 'agent_executor', 'process_query']:
            return
        
        chunk = msg.tool_call_chunks[0]
        chunk_dict = chunk if isinstance(chunk, dict) else chunk.dict() if hasattr(chunk, 'dict') else {}
        
        chunk_id = chunk_dict.get('id')
        chunk_index = chunk_dict.get('index', 0)
        chunk_name = chunk_dict.get('name')
        chunk_args_str = chunk_dict.get('args', '')
        
        if chunk_name == 'transfer_to_data_exploration':
            return
        
        tool_key = chunk_id if chunk_id else f"index_{chunk_index}"
        
        if chunk_id and chunk_name and tool_key not in self.pending_tools:
            self.sequence_counter += 1
            self.pending_tools[tool_key] = ToolCallState(
                tool_call_id=chunk_id,
                tool_name=chunk_name,
                node=node_name,
                index=chunk_index,
                sequence=self.sequence_counter,
                args='',
                output=None,
                content=None,
                saved=False
            )
            
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "tool_calls",
                    "block_id": f"tool_{chunk_id}",
                    "tool_call_id": chunk_id,
                    "tool_name": chunk_name,
                    "args": "",
                    "node": node_name,
                    "action": "start_tool_call"
                })
            }
            
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "tool_calls",
                    "block_id": f"tool_{chunk_id}",
                    "tool_call_id": chunk_id,
                    "tool_name": chunk_name,
                    "node": node_name,
                    "action": "add_tool_call"
                })
            }
            
            self.active_tool_id = chunk_id
            self.active_tool_name = chunk_name
            return
        
        if chunk_args_str and self.active_tool_id in self.pending_tools:
            tool_state = self.pending_tools[self.active_tool_id]
            tool_state.args += chunk_args_str
            
            yield {
                "event": "content_block",
                "data": json.dumps({
                    "block_type": "tool_calls",
                    "block_id": f"tool_{tool_state.tool_call_id}",
                    "tool_call_id": tool_state.tool_call_id,
                    "tool_name": tool_state.tool_name,
                    "args_chunk": chunk_args_str,
                    "node": node_name,
                    "action": "stream_args"
                })
            }
    
    async def _handle_tool_result(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        tool_call_id = msg.tool_call_id
        node_name = metadata.get('langgraph_node', 'unknown')
        
        tool_state = self.pending_tools.get(tool_call_id)
        if not tool_state:
            for key, state in self.pending_tools.items():
                if state.tool_call_id == tool_call_id:
                    tool_state = state
                    break
        
        if not tool_state:
            tool_name = getattr(msg, 'name', None) or 'unknown'
            tool_state = ToolCallState(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                node=node_name,
                index=0,
                sequence=self.sequence_counter,
                args='',
                output=None,
                content=None,
                saved=False
            )
        
        tool_name = tool_state.tool_name
        
        if tool_name == 'transfer_to_data_exploration':
            for key in list(self.pending_tools.keys()):
                if self.pending_tools[key].tool_call_id == tool_call_id:
                    del self.pending_tools[key]
                    break
            return
        
        tool_state.output = msg.content
        
        parsed_args = {}
        if tool_state.args:
            try:
                parsed_args = json.loads(tool_state.args)
            except json.JSONDecodeError:
                parsed_args = {}
        
        # NEW: Check if tool output signals approval needed
        needs_approval = False
        internal_tools = None
        generated_content = None
        
        try:
            if isinstance(msg.content, str):
                output_data = json.loads(msg.content)
                if output_data.get("status") == "awaiting_approval":
                    needs_approval = True
                    internal_tools = output_data.get("internal_tools", [])
                    generated_content = output_data.get("generated_content")
                    logger.info(f"Tool {tool_name} requires approval. Type: {output_data.get('approval_type')}")
        except (json.JSONDecodeError, AttributeError):
            pass
        
        tool_call_object = {
            "name": tool_name,
            "input": parsed_args,
            "output": msg.content,
            "status": "pending" if needs_approval else "approved"
        }
        
        # Add internal tools and generated content if present
        if internal_tools:
            tool_call_object["internalTools"] = internal_tools
        if generated_content:
            tool_call_object["generatedContent"] = generated_content

        
        if tool_call_id not in self.completed_tools:
            self.completed_tools[tool_call_id] = {
                "id": f"tool_{tool_call_id}",
                "type": "tool_calls",
                "sequence": tool_state.sequence,
                "needsApproval": needs_approval,  # Set based on detection
                "data": {
                    "toolCalls": [tool_call_object],
                    "content": tool_state.content
                }
            }
        else:
            self.completed_tools[tool_call_id]["data"]["toolCalls"].append(tool_call_object)
            # Update needsApproval if any tool call needs it
            if needs_approval:
                self.completed_tools[tool_call_id]["needsApproval"] = True

        
        tool_state.saved = True
        
        # Append completed block to context in stream order
        block_to_save = {
            "id": f"tool_{tool_call_id}",
            "type": "tool_calls",
            "needsApproval": False,
            "data": {
                "toolCalls": [tool_call_object],
                "content": tool_state.content
            }
        }
        self.context.completed_blocks.append(block_to_save)
        
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "tool_calls",
                "block_id": f"tool_{tool_call_id}",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "node": node_name,
                "input": parsed_args,
                "output": msg.content,
                "action": "update_tool_result"
            })
        }
        
        for key in list(self.pending_tools.keys()):
            if self.pending_tools[key].tool_call_id == tool_call_id:
                del self.pending_tools[key]
                if self.active_tool_id == key:
                    self.active_tool_id = None
                    self.active_tool_name = None
                break
    
    async def handle_explanation(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        if not self.active_tool_id:
            return
        
        node_name = metadata.get('langgraph_node', 'unknown')
        
        # Update pending tool content
        if self.active_tool_id in self.pending_tools:
            tool_state = self.pending_tools[self.active_tool_id]
            if tool_state.content is None:
                tool_state.content = ''
            tool_state.content += msg.content
        
        if self.active_tool_id in self.completed_tools:
            if self.completed_tools[self.active_tool_id]["data"].get("content") is None:
                self.completed_tools[self.active_tool_id]["data"]["content"] = ''
            self.completed_tools[self.active_tool_id]["data"]["content"] += msg.content
        
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "tool_calls",
                "block_id": f"tool_{self.active_tool_id}",
                "tool_call_id": self.active_tool_id,
                "tool_name": self.active_tool_name,
                "content": msg.content,
                "node": node_name,
                "action": "update_tool_calls_explanation"
            })
        }
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        blocks = []
        
        sorted_completed = sorted(
            self.completed_tools.items(),
            key=lambda x: x[1].get('sequence', 0)
        )
        for tool_call_id, content_block in sorted_completed:
            if len(content_block["data"]["toolCalls"]) > 0:
                content_block["needsApproval"] = False
                blocks.append(content_block)
        
        if needs_approval:
            sorted_pending = sorted(
                self.pending_tools.items(),
                key=lambda x: x[1].sequence
            )
            
            for tool_key, tool_state in sorted_pending:
                if tool_state.output:
                    continue
                
                parsed_args = {}
                if tool_state.args:
                    try:
                        parsed_args = json.loads(tool_state.args)
                    except json.JSONDecodeError:
                        parsed_args = {}
                
                tool_call_object = {
                    "name": tool_state.tool_name,
                    "input": parsed_args,
                    "status": "pending"
                }
                
                content_block = {
                    "id": f"tool_{tool_state.tool_call_id}",
                    "type": "tool_calls",
                    "needsApproval": True,
                    "data": {
                        "toolCalls": [tool_call_object]
                    }
                }
                blocks.append(content_block)
        
        return blocks
    
    def load_existing_state(self, completed_tools: Dict[str, Dict], pending_tools: Dict[str, Dict]):
        """Load existing tool state when resuming"""
        self.completed_tools = completed_tools
        self.sequence_counter = len(completed_tools)
        
        for tool_id, tool_info in pending_tools.items():
            self.pending_tools[tool_id] = ToolCallState(
                tool_call_id=tool_info['tool_call_id'],
                tool_name=tool_info['tool_name'],
                node='agent',
                index=0,
                sequence=tool_info.get('sequence', 0),
                args=tool_info.get('args', ''),
                output=None,
                content=None,
                saved=False
            )
