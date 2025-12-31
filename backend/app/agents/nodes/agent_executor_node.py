"""Agent Executor Node - Executes steps from dynamic plan with internal agent"""
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, END, MessagesState
from app.agents.state import ExplainableAgentState
from app.schemas.chat import DataContext
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class AgentExecutorNode: 
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        dynamic_plan = state.get("dynamic_plan")
        current_step_index = state.get("current_step_index", 0)
        
        logger.info(f"AgentExecutor ENTERED - Current index: {current_step_index}")
        if dynamic_plan:
            logger.info(f"Plan has {len(dynamic_plan.steps)} steps")
            for i, step in enumerate(dynamic_plan.steps):
                logger.info(f"  Step {i}: {step.goal}")
        else:
            logger.warning("No dynamic plan found in state!")
        
        if not dynamic_plan or current_step_index >= len(dynamic_plan.steps):
            logger.warning(f"No more steps to execute (Index {current_step_index} >= {len(dynamic_plan.steps) if dynamic_plan else 0})")
            return {
                "continue_execution": False
            }
        
        current_step = dynamic_plan.steps[current_step_index]
        logger.info(f"Executing step {current_step_index + 1}/{len(dynamic_plan.steps)}: {current_step.goal}")
        
        # Get tools for current step
        step_tool_names = [opt.tool_name for opt in current_step.tool_options]
        
        next_step_index = current_step_index + 1
        if next_step_index < len(dynamic_plan.steps):
            next_step = dynamic_plan.steps[next_step_index]
            next_step_tool_names = [opt.tool_name for opt in next_step.tool_options]
            step_tool_names = list(set(step_tool_names + next_step_tool_names))
            logger.info(f"Exposing tools from steps {current_step_index + 1} and {next_step_index + 1}: {step_tool_names}")
        else:
            logger.info(f"Exposing tools from step {current_step_index + 1}: {step_tool_names}")
        
        step_tools = [self.tool_map[name] for name in step_tool_names if name in self.tool_map]
        
        if not step_tools:
            logger.error(f"No valid tools found for step {current_step_index + 1}")
            return {
                "current_step_index": current_step_index + 1,
                "continue_execution": current_step_index + 1 < len(dynamic_plan.steps)
            }
        
        messages = state.get("messages", [])
        
        # Filter out explanation messages - they're for streaming only, not for agent context
        # Explanation messages have additional_kwargs["is_explanation"] = True
        filtered_messages = [
            msg for msg in messages
            if not (hasattr(msg, 'additional_kwargs') and 
                    msg.additional_kwargs.get('is_explanation', False))
        ]
        
        # Build step prompt with next step context  
        next_step_index = current_step_index + 1
        next_step = dynamic_plan.steps[next_step_index] if next_step_index < len(dynamic_plan.steps) else None
        step_prompt = self._build_step_prompt(current_step, current_step_index + 1, len(dynamic_plan.steps), next_step)
        step_messages = [SystemMessage(content=step_prompt)] + filtered_messages
        
        llm_with_tools = self.llm.bind_tools(step_tools)
        
        try:
            response = llm_with_tools.invoke(step_messages)
            
            if response.tool_calls:
                logger.info(f"Step {current_step_index + 1} generated {len(response.tool_calls)} tool call(s)")
                return {
                    "messages": [response],
                    "continue_execution": True
                }
            
            # No tool calls - agent says step is done
            next_step_index = current_step_index + 1
            has_more_steps = next_step_index < len(dynamic_plan.steps)
            
            logger.info(f"Step {current_step_index + 1} complete (no tool calls). More steps: {has_more_steps}")
            
            return {
                "messages": [response],
                "current_step_index": next_step_index,
                "continue_execution": has_more_steps
            }
            
        except Exception as e:
            logger.error(f"Error executing step {current_step_index + 1}: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content=f"Error in step {current_step_index + 1}: {str(e)}")],
                "current_step_index": current_step_index + 1,
                "continue_execution": current_step_index + 1 < len(dynamic_plan.steps)
            }
    
    def _build_step_prompt(self, step, step_num: int, total_steps: int, next_step=None) -> str:
        tool_options_text = self._format_tool_options(step.tool_options)
        context_req = step.context_requirements or "None"
        
        next_step_info = ""
        if next_step:
            next_step_info = f"\n**Next Step After This**: Step {step_num + 1} - {next_step.goal}"
        elif step_num == total_steps:
            next_step_info = "\n**This is the FINAL step**"
        
        return f"""You are a ReAct agent executing step {step_num} of {total_steps} in a multi-step plan.

**Current Step Goal**: {step.goal}

**Context Requirements**: {context_req}

**Available Tools**: {', '.join([opt.tool_name for opt in step.tool_options])}
{next_step_info}

**Your Process**:
1. **Check history**: Look at recent messages - has this step's goal already been achieved?
2. **If YES (tool succeeded)**: 
   - Be EXTREMELY concise: "Step {step_num} complete. Proceeding to step {step_num + 1}."
   - DO NOT repeat the tool output or results
3. **If NO (need to act)**:
   - Call the appropriate tool to achieve the goal
   - If the required tool is NOT in **Available Tools**:
     * STOP immediately
     * Respond: "Required tool for this step is not available. Passing control back to planner."
   - You may call tools multiple times if there are errors, but limmited to two calls

**Tool Selection Priorities**:
{tool_options_text}

**Critical Rules**:
- **NO REPETITION**: Do not summarize what was just shown in the tool output
- **FOCUS ON NEXT**: Your goal is to move to the next step, not linger on the current one
- **Review tool results**: Check if the tool succeeded before moving on
- **Be concise**: One sentence status updates are preferred
"""
    
    def _format_tool_options(self, tool_options: List) -> str:
        lines = []
        for opt in sorted(tool_options, key=lambda x: x.priority):
            lines.append(f"  {opt.priority}. {opt.tool_name}: {opt.use_case}")
        return "\n".join(lines)
    
    def _extract_data_context(self, messages, current_context):
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and hasattr(msg, 'name') and msg.name == "sql_db_to_df":
                try:
                    parsed_output = json.loads(msg.content)
                    data_context_payload = parsed_output.get("data_context")
                    if data_context_payload:
                        # Convert shape list to tuple if needed
                        if "shape" in data_context_payload and isinstance(data_context_payload["shape"], list):
                            data_context_payload["shape"] = tuple(data_context_payload["shape"])
                        
                        # Parse datetime strings if needed
                        if "created_at" in data_context_payload and isinstance(data_context_payload["created_at"], str):
                            data_context_payload["created_at"] = datetime.fromisoformat(data_context_payload["created_at"])
                        
                        if "expires_at" in data_context_payload and isinstance(data_context_payload["expires_at"], str):
                            data_context_payload["expires_at"] = datetime.fromisoformat(data_context_payload["expires_at"])
                        
                        return DataContext(**data_context_payload)
                except Exception as e:
                    logger.error(f"Failed to extract data_context: {e}")
        
        return current_context
