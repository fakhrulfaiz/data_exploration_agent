"""Task Parser Node - Converts natural language plan into sequential tool groups"""
from typing import Dict, Any, List
from langchain_core.messages import AIMessage
from app.agents.state import ExplainableAgentState
import re
import logging

logger = logging.getLogger(__name__)


class TaskParserNode:
    """Parses plan into sequential tool groups for agent-based execution"""
    
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Parse plan into sequential tool groups"""
        plan = state.get("plan", "")
        execution_mode = state.get("execution_mode", "sequential")
        
        # If sequential mode, return empty groups (use existing flow)
        if execution_mode == "sequential":
            return {
                "task_groups": [],
                "group_results": {}
            }
        
        # Parse plan into sequential tool groups
        task_groups = self._parse_plan_to_groups(plan)
        
        logger.info(f"Parsed {len(task_groups)} groups from plan")
        for idx, group in enumerate(task_groups):
            logger.info(f"  Group {idx}: {group}")
        
        return {
            "task_groups": task_groups,
            "group_results": {},
            "messages": state.get("messages", []) + [
                AIMessage(content=f"📋 Created {len(task_groups)} sequential group(s) for execution")
            ]
        }
    
    def _parse_plan_to_groups(self, plan: str) -> List[List[str]]:
        """Parse plan into sequential task descriptions
        
        Example plan:
        1. text2SQL: Convert question to SQL
        2. sql_db_to_df: Execute query
        3. smart_transform_for_viz: Create chart
        
        Returns: [["text2SQL: Convert question to SQL", "sql_db_to_df: Execute query", ...]]
        - Each item is the FULL task description (tool name + description)
        - Agent executor will parse out the tool name and use the description as context
        """
        # Extract full task lines from plan
        # Pattern matches: "1. tool_name: description"
        pattern = r"\d+\.\s+(\w+:\s*.+?)(?=\n\d+\.|\n*$)"
        matches = re.findall(pattern, plan, re.DOTALL)
        
        # Clean up matches and filter to valid tools
        all_tasks = []
        for match in matches:
            # Extract tool name from the task
            tool_name = match.split(':')[0].strip()
            if tool_name in self.tool_map:
                # Keep the full task description
                task_desc = match.strip()
                all_tasks.append(task_desc)
                logger.info(f"Parsed task: {task_desc[:80]}...")
        
        if not all_tasks:
            logger.warning(f"No valid tasks found in plan: {plan}")
            return []
        
        # Put ALL tasks in ONE sequential group
        logger.info(f"Created group with {len(all_tasks)} tasks")
        return [all_tasks]
