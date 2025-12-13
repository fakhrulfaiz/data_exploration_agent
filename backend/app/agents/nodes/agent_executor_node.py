from typing import Dict, Any
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
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
        """Execute the next tool in the sequence
        
        This node:
        1. Gets the current group's tasks (full descriptions)
        2. Pops the next task to execute
        3. Parses tool name and description
        4. Invokes LLM with ONLY that tool bound
        5. Executes the tool
        6. Returns results and updated task list
        """
        group_index = state.get("current_group_index", 0)
        group_tools = state.get("current_group_tools", [])
        messages = state.get("messages", [])
        query = state.get("query", "")
        plan = state.get("plan", "")
        
        if not group_tools:
            logger.error(f"No tasks in group {group_index}")
            return {
                "continue_group": False,
                "group_results": {group_index: "Error: No tasks to execute"}
            }
        
        current_task = group_tools[0]
        remaining_tasks = group_tools[1:]  
        
        if ':' not in current_task:
            logger.error(f"Invalid task format: {current_task}")
            return {
                "current_group_tools": remaining_tasks,
                "continue_group": len(remaining_tasks) > 0,
                "messages": [AIMessage(content=f"Error: Invalid task format")]
            }
        
        tool_name, task_description = current_task.split(':', 1)
        tool_name = tool_name.strip()
        task_description = task_description.strip()
        
        logger.info(f"Executing {tool_name} ({len(remaining_tasks)} tasks remaining)")
        logger.info(f"Task description: {task_description[:100]}...")
        
        tool = self.tool_map.get(tool_name)
        if not tool:
            logger.error(f"Tool {tool_name} not found")
            return {
                "current_group_tools": remaining_tasks,
                "continue_group": len(remaining_tasks) > 0,
                "messages": [AIMessage(content=f"Error: Tool {tool_name} not found")]
            }
    
        system_message = SystemMessage(content=f"""You are executing step {group_index + 1} of the plan.

Original Query: {query}

Current Task: {current_task}

INSTRUCTIONS:
- You have access to ONLY ONE tool: {tool_name}
- Your task: {task_description}
- Call the tool with appropriate arguments to accomplish this specific task
- Use the context from previous messages to inform your arguments

Remaining tasks after this: {len(remaining_tasks)}
{chr(10).join([f"  - {t.split(':')[0]}" for t in remaining_tasks]) if remaining_tasks else "  (This is the last task)"}
""")
        
        # Bind ONLY the current tool
        llm_with_tool = self.llm.bind_tools([tool])
        
        # Filter messages (remove system messages)
        conversation_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
        
        # Invoke agent with only this tool
        all_messages = [system_message] + conversation_messages
        response = llm_with_tool.invoke(all_messages)
        
        # Check if agent made a tool call
        if not hasattr(response, 'tool_calls') or not response.tool_calls:
            logger.warning(f"Agent didn't call {tool_name}")
            return {
                "current_group_tools": remaining_tasks,
                "continue_group": len(remaining_tasks) > 0,
                "messages": [response]
            }
        
        # Execute the tool call
        tool_call = response.tool_calls[0]
        logger.info(f"Executing {tool_call['name']} with args: {tool_call['args']}")
        
        try:
            # Use ToolNode to properly handle InjectedState
            from langgraph.prebuilt import ToolNode
            
            # Create a ToolNode with just this one tool
            tool_node = ToolNode(tools=[tool])
            
            # Build state for tool execution (must include messages with the AI message containing tool_calls)
            tool_state = {
                **state,
                "messages": messages + [response],  # Include the AI message with tool_calls
            }
            
            # Execute the tool through ToolNode (this properly injects state)
            tool_result = tool_node.invoke(tool_state)
            
            # Extract the tool message from the result
            tool_message = tool_result["messages"][0]  # ToolNode returns messages in result
            logger.info(f"Tool {tool_name} executed successfully")
            
            updated_data_context = state.get("data_context")
            if tool_name == "sql_db_to_df":
                logger.info(f"sql_db_to_df raw output: {tool_message.content}")
                try:
                    parsed_output = json.loads(tool_message.content)
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
                        
                        updated_data_context = DataContext(**data_context_payload)
                        logger.info(f"Successfully updated data_context: df_id={data_context_payload.get('df_id')}")
                except Exception as e:
                    logger.error(f"Failed to extract data_context from sql_db_to_df output: {e}")
            
            # Check if this was the last task
            if not remaining_tasks:
                logger.info(f"Group {group_index} complete - all tasks executed")
                
                # Build summary from recent tool executions
                group_summary = self._build_group_summary(messages + [response, tool_message])
                
                # Store actual results
                group_results = state.get("group_results", {})
                group_results[group_index] = group_summary
                
                # DEBUG: Log what we're returning
                logger.info(f"Group {group_index} complete - returning 2 messages (AI + Tool)")
                logger.info(f"  Total messages in state before: {len(messages)}")
                logger.info(f"  Returning messages: {len([response, tool_message])}")
                
                return {
                    "current_group_tools": [],
                    "continue_group": False,
                    "messages": [response, tool_message],
                    "group_results": group_results,
                    "data_context": updated_data_context
                }
            else:
                logger.info(f"Moving to next task: {remaining_tasks[0].split(':')[0]}")
                return {
                    "current_group_tools": remaining_tasks,
                    "continue_group": True,
                    "messages": [response, tool_message],
                    "data_context": updated_data_context
                }
                
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            tool_message = ToolMessage(
                content=f"Error: {str(e)}",
                tool_call_id=tool_call['id'],
                name=tool_call['name']
            )
            
            # Continue to next task even if this one failed
            return {
                "current_group_tools": remaining_tasks,
                "continue_group": len(remaining_tasks) > 0,
                "messages": [response, tool_message]
            }
    
    def _build_group_summary(self, messages) -> str:
        summary_parts = []
        
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for call in msg.tool_calls:
                    summary_parts.append(f"Called {call['name']} with args: {call['args']}")
            elif isinstance(msg, ToolMessage):
                summary_parts.append(f"{msg.name} result: {msg.content}")
        
        if not summary_parts:
            return "No tool executions found"
        
        return "\n".join(summary_parts)
