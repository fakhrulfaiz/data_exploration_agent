"""Tool Execution Node - Executes individual tool calls"""
from typing import Dict, Any
from langchain_core.messages import ToolMessage
from app.agents.state import ExplainableAgentState
import logging

logger = logging.getLogger(__name__)


class ToolExecutionNode:
    """Executes a single tool call"""
    
    def __init__(self, tools):
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute a single tool call
        
        This node receives a single tool call via Send API and executes it.
        """
        current_tool_call = state.get("current_tool_call")
        
        if not current_tool_call:
            logger.error("No tool call provided to execute")
            return {"messages": []}
        
        tool_name = current_tool_call.get('name')
        tool_args = current_tool_call.get('args', {})
        tool_call_id = current_tool_call.get('id')
        
        logger.info(f"Executing tool: {tool_name}")
        
        # Find and execute the tool
        tool = self.tool_map.get(tool_name)
        
        if not tool:
            logger.error(f"Tool {tool_name} not found")
            return {
                "messages": [ToolMessage(
                    content=f"Error: Tool {tool_name} not found",
                    tool_call_id=tool_call_id,
                    name=tool_name
                )]
            }
        
        try:
            # Execute the tool
            result = tool.invoke(tool_args)
            logger.info(f"Tool {tool_name} executed successfully")
            
            return {
                "messages": [ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id,
                    name=tool_name
                )]
            }
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {
                "messages": [ToolMessage(
                    content=f"Error: {str(e)}",
                    tool_call_id=tool_call_id,
                    name=tool_name
                )]
            }
