"""Task Scheduler Node - Dispatches sequential tool groups using Send API"""
from typing import Dict, Any, List
from langgraph.types import Send
from app.agents.state import ExplainableAgentState
import logging

logger = logging.getLogger(__name__)


class TaskSchedulerNode:
    """Dispatches sequential tool groups for execution"""
    
    def __init__(self, tools):
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
    
    def route_tasks(self, state: ExplainableAgentState) -> List[Send]:
        """Dispatch each sequential group using Send API
        
        For now, all tools are in ONE group, so we send ONE execution.
        In future, if we have multiple groups, each group gets dispatched independently.
        """
        task_groups = state.get("task_groups", [])
        
        if not task_groups:
            # No groups to execute, skip to joiner
            logger.info("No task groups found, routing to joiner")
            return [Send("joiner", state)]
        
        logger.info(f"Dispatching {len(task_groups)} group(s) for execution")
        
        sends = []
        for idx, group in enumerate(task_groups):
            logger.info(f"  Dispatching group {idx}: {group}")
            sends.append(Send("agent_executor", {
                **state,
                "current_group_index": idx,
                "current_group_tools": group,
                "group_context": []
            }))
        
        return sends
