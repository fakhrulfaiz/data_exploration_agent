from typing import Dict, Any
from app.agents.state import ExplainableAgentState
import logging

logger = logging.getLogger(__name__)


class TaskSchedulerNode:
    def __init__(self, tools):
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        dynamic_plan = state.get("dynamic_plan")
        
        if dynamic_plan and len(dynamic_plan.steps) > 0:
            logger.info(f"Initializing dynamic plan execution with {len(dynamic_plan.steps)} steps")
            return {
                "current_step_index": 0,
                "continue_execution": True
            }
        else:
            logger.warning("No dynamic plan found or plan has no steps")
            return {
                "current_step_index": 0,
                "continue_execution": False
            }
    
    def route_tasks(self, state: ExplainableAgentState) -> str:
        dynamic_plan = state.get("dynamic_plan")
        
        if dynamic_plan and len(dynamic_plan.steps) > 0:
            logger.info("Routing to agent_executor for step execution")
            return "agent_executor"
        else:
            logger.warning("No steps to execute, routing to joiner")
            return "joiner"
