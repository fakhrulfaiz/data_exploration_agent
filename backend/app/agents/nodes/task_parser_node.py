"""Task Parser Node - Converts natural language plan into sequential tool groups"""
from typing import Dict, Any, List
from langchain_core.messages import AIMessage
from app.agents.state import ExplainableAgentState
import re
import logging

logger = logging.getLogger(__name__)


class TaskParserNode:
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        dynamic_plan = state.get("dynamic_plan")
        
        if dynamic_plan:
            logger.info(f"Initializing dynamic plan execution with {len(dynamic_plan.steps)} steps")
            return {
                "current_step_index": 0,
                "continue_execution": True
            }
        else:
            logger.warning("No dynamic plan found")
            return {
                "current_step_index": 0,
                "continue_execution": False
            }
