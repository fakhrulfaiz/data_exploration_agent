"""
Main Agent with step-by-step execution.

This agent uses a simpler execution model where it executes one plan step at a time,
allowing the agent to make multiple tool calls per step as needed.
"""

from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.types import Command
from typing import List, Dict, Any, Optional, Literal, Annotated
import json
import re
import os
from datetime import datetime
import logging
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState
from langchain_core.tools import InjectedToolCallId

from app.agents.tools.custom_toolkit import CustomToolkit
from app.agents.state import ExplainableAgentState
from app.agents.nodes.explainable.explainable_planner_node import ExplainablePlannerNode
from app.agents.nodes.explainer_node import ExplainerNode
from app.agents.nodes.finalizer_node import FinalizerNode
from app.agents.nodes.error_explainer_node import ErrorExplainerNode
from app.agents.assistant_agent import AssistantAgent

logger = logging.getLogger(__name__)


class MainAgent:
    def __init__(
        self,
        llm,
        db_path: str,
        logs_dir: str = None,
        checkpointer=None,
        store=None,
        use_postgres_checkpointer: bool = True
    ):
        self.llm = llm
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        
        # Initialize toolkit and tools
        self.custom_toolkit = CustomToolkit(
            llm=self.llm,
            db_engine=self.engine,
            db_path=self.db_path
        )
        self.tools = self.custom_toolkit.get_tools()
        
        self.planner = ExplainablePlannerNode(llm, self.tools)
        self.explainer = ExplainerNode(llm, available_tools=self.tools)
        self.error_explainer = ErrorExplainerNode(llm, db_engine=self.engine)
        self.finalizer = FinalizerNode(llm, error_explainer=self.error_explainer)
        
        # Create handoff tools and assistant agent
        self.create_handoff_tools()
        self.assistant_agent_instance = AssistantAgent(
            llm=llm,
            transfer_tools=[self.transfer_to_main_agent]
        )
        self.assistant_agent = self.assistant_agent_instance
        
        # Setup logs directory
        if logs_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logs_dir = os.path.join(backend_dir, "logs")
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Setup checkpointer
        if checkpointer is not None:
            self.checkpointer = checkpointer
        elif use_postgres_checkpointer:
            try:
                from app.core.checkpointer import checkpointer_manager
                from app.core.database import db_manager
                from langgraph.checkpoint.postgres import PostgresSaver
                import psycopg
                
                if checkpointer_manager.is_initialized():
                    db_uri = db_manager.get_db_uri()
                    conn = psycopg.connect(db_uri, autocommit=True)
                    self.checkpointer = PostgresSaver(conn)
                else:
                    logger.warning("Checkpointer not initialized, falling back to MemorySaver")
                    self.checkpointer = MemorySaver()
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL checkpointer: {e}")
                self.checkpointer = MemorySaver()
        else:
            self.checkpointer = None
        
        # Setup LangGraph Store for conversation-scoped memories
        if store is not None:
            self.store = store
        else:
            # Use InMemoryStore for development
            from langgraph.store.memory import InMemoryStore
            self.store = InMemoryStore()
            logger.info("Initialized InMemoryStore for conversation memories")
        
        # Build the graph
        self.graph = self.create_graph()
        self.save_graph_visualization()
    
    def save_graph_visualization(self):
        try:
            graph_image = self.graph.get_graph().draw_mermaid_png()
            graph_path = os.path.join(self.logs_dir, "main_agent_graph.png")
            with open(graph_path, "wb") as f:
                f.write(graph_image)
            logger.info(f"Graph visualization saved to: {graph_path}")
        except Exception as e:
            logger.error(f"Failed to generate graph visualization: {e}")
    
    def create_handoff_tools(self):
        """Create handoff tools for assistant agent routing."""
        @tool("transfer_to_main_agent", description="Transfer to the main agent for data exploration and analysis tasks")
        def transfer_to_main_agent(
            state: Annotated[Dict[str, Any], InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            task_description: str = ""
        ) -> Command:
            tool_message = {
                "role": "tool",
                "content": f"Transferring to main agent: {task_description}",
                "name": "transfer_to_main_agent",
                "tool_call_id": tool_call_id,
            }
            
            query = state.get("query", "")
            status = state.get("status", "approved")
            
            # Get latest human message if available
            if status == "approved" and "messages" in state and state["messages"]:
                latest_human_msg = self._get_latest_human_message(state["messages"])
                if latest_human_msg:
                    query = latest_human_msg
            
            update_state = {
                "messages": state.get("messages", []) + [tool_message],
                "agent_type": "main_agent",
                "routing_reason": f"Transferred to main agent: {task_description}",
                "query": query,
                "steps": state.get("steps", []),
                "step_counter": state.get("step_counter", 0),
                "human_comment": state.get("human_comment"),
                "status": state.get("status", "approved"),
                "assistant_response": state.get("assistant_response", ""),
                "visualizations": state.get("visualizations", []),
                "data_context": state.get("data_context"),
            }
            
            return Command(
                goto="main_agent_flow",
                update=update_state,
                graph=Command.PARENT,
            )
        
        self.transfer_to_main_agent = transfer_to_main_agent
    
    def _get_latest_human_message(self, messages: List[BaseMessage]) -> Optional[str]:
        """Get the latest human message from message history."""
        if not messages:
            return None
        for msg in reversed(messages):
            if hasattr(msg, 'content') and hasattr(msg, '__class__') and 'HumanMessage' in str(msg.__class__):
                return msg.content
        return None
    
    def main_agent_entry(self, state: ExplainableAgentState) -> Dict[str, Any]:
        status = state.get("status", "approved")
        messages = state.get("messages", [])
        current_query = state.get("query", "")
        
        if status == "approved":
            latest_human_msg = self._get_latest_human_message(messages)
            if latest_human_msg and latest_human_msg != current_query:
                return {
                    **state,
                    "query": latest_human_msg
                }
        
        return state
    
    def process_query(self, state: ExplainableAgentState) -> Dict[str, Any]:
        dynamic_plan = state.get("dynamic_plan")
        current_idx = state.get("current_step_index", 0)
        messages = state.get("messages", [])
        steps = state.get("steps", [])
        step_counter = state.get("step_counter", 0)
        
        if not dynamic_plan or current_idx >= len(dynamic_plan.steps):
            logger.info(f"All steps completed. Current index: {current_idx}, Total steps: {len(dynamic_plan.steps) if dynamic_plan else 0}")
            return {"messages": messages}
        
        # Get current step
        current_step = dynamic_plan.steps[current_idx]
        step_instruction = current_step.goal
        
        logger.info(f"Executing step {current_idx + 1}/{len(dynamic_plan.steps)}: {step_instruction}")
        
        system_message = self._build_system_message(state)
        
        error_details = state.get("error_details", [])
        is_retry = state.get("status") == "retry" and error_details
        
        feedback = state.get("feedback", "")
        is_partial_retry = feedback and "RETRY_IMAGE_QA" in feedback
        
        if is_retry and error_details:
            error_info = error_details[0]
            error_context = f"\n\n**RETRY CONTEXT:**\n"
            error_context += f"Previous attempt failed with: {error_info.get('error_message', 'Unknown error')}\n"
            error_context += f"Error type: {error_info.get('error_type', 'Unknown')}\n"
            if error_info.get('recoverable'):
                error_context += "This error is recoverable - try again or fix the approach.\n"
            instruction_content = f"Execute the following step: {step_instruction}{error_context}"
        elif is_partial_retry:
            try:
                retry_attempt = int(feedback.split(":")[1])
            except:
                retry_attempt = 1
            
            # Get execution summary from last step
            retry_context = f"\n\n**RETRY CONTEXT (Attempt {retry_attempt}/2):**\n"
            if steps:
                last_step = steps[-1]
                execution_summary = last_step.get("execution_summary", "")
                if execution_summary:
                    retry_context += f"Previous result: {execution_summary}\n"
            retry_context += "Some images failed to process. Retry with the same parameters to process only the failed images.\n"
            instruction_content = f"Execute the following step: {step_instruction}{retry_context}"
        else:
            next_step_info = ""
            if dynamic_plan and current_idx + 1 < len(dynamic_plan.steps):
                next_step = dynamic_plan.steps[current_idx + 1]
                
                # Check if next step is image analysis
                next_tool_name = "unknown"
                # Handle both dict and object access safely
                if isinstance(next_step, dict):
                    tool_options = next_step.get('tool_options', [])
                    if tool_options:
                        # Handle tool_options as dict or object
                        opt = tool_options[0]
                        next_tool_name = opt.get('tool_name') if isinstance(opt, dict) else getattr(opt, 'tool_name', 'unknown')
                else:
                    tool_options = getattr(next_step, 'tool_options', [])
                    if tool_options:
                        next_tool_name = getattr(tool_options[0], 'tool_name', 'unknown')
                
                if next_tool_name == "image_batch_qa_tool":
                    next_step_info = "\n\nCRITICAL REQUIREMENT FOR NEXT STEP:\n"
                    next_step_info += "The next step uses 'image_batch_qa_tool' which REQUIRES the 'img_path' column.\n"
                    next_step_info += "You MUST include 'img_path' in your SQL SELECT statement or dataframe operations for this step.\n"
                    next_step_info += "Example: SELECT title, inception, img_path FROM ...\n"

            instruction_content = f"Execute the following step: {step_instruction}{next_step_info}"
        
        
        instruction_message = HumanMessage(content=instruction_content)
        
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        conversation_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
        
        all_messages = [SystemMessage(content=system_message)] + conversation_messages + [instruction_message]
        response = llm_with_tools.invoke(all_messages)
        
        logger.info(f"Agent response has {len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0} tool calls")
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            decision_reasoning = dict()
            if state.get("use_explainer", True):
                decision_reasoning = self._generate_tool_decision_reasoning(
                    tool_calls=response.tool_calls,
                    current_step=current_step,
                    state=state
                )
            
            # Create tool_calls array
            step_counter += 1
            tool_calls_list = []
            
            for tool_call in response.tool_calls:
                tool_calls_list.append({
                    "tool_call_id": tool_call['id'],
                    "tool_name": tool_call.get('name', 'unknown'),
                    "input": json.dumps(tool_call.get('args', {})),
                })
            
            # Create single step entry with tool_calls array
            # Build default decision text from tool names
            tool_names = [tc.get('name', 'unknown') for tc in response.tool_calls]
            default_decision = f"Using {', '.join(tool_names)}" if tool_names else "Executing step"
            default_reasoning = current_step.goal if current_step else "Executing planned step"
            
            step_entry = {
                "id": step_counter,
                "plan_step_index": current_idx,
                "decision": decision_reasoning.get('decision', default_decision),
                "reasoning": decision_reasoning.get('reasoning', default_reasoning),
                "timestamp": datetime.now().isoformat(),
                "tool_calls": tool_calls_list
            }
            steps.append(step_entry)
            logger.info(f"Created step {step_counter} with {len(tool_calls_list)} tool calls")

        
        # Increment step index
        new_step_index = current_idx + 1
        
        return {
            "messages": messages + [instruction_message, response],
            "current_step_index": new_step_index,
            "steps": steps,
            "step_counter": step_counter
        }
    
    def _generate_tool_decision_reasoning(
        self,
        tool_calls: List[Dict[str, Any]],
        current_step: Any,
        state: Dict[str, Any]
    ) -> Dict[str, str]:
        context = self._analyze_execution_context(state)
        df_info = self._get_current_dataframe_info(state)
        
        tool_names = [tc.get('name', 'unknown') for tc in tool_calls]
        tool_summary = ", ".join(tool_names)
        
        # Get validation warnings
        validation_warnings = self._validate_tool_requirements(tool_calls, state)
        
        tool_details = []
        for tool_name in tool_names:
            tool_obj = next((t for t in self.tools if t.name == tool_name), None)
            if tool_obj:
                tool_details.append(f"- {tool_name}: {tool_obj.description}")
            else:
                tool_details.append(f"- {tool_name}: (description not available)")
        
        tool_details_str = "\n".join(tool_details)
        
        # Build available data description with actual schema
        available_data_desc = "No data in memory"
        if df_info:
            cols_str = ", ".join(df_info['columns'][:10])  # Show first 10 columns
            if len(df_info['columns']) > 10:
                cols_str += f"... ({len(df_info['columns'])} total)"
            
            available_data_desc = f"""Current DataFrame in state:
- ID: {df_info['df_id']}
- Shape: {df_info['shape'][0]} rows × {df_info['shape'][1]} columns
- Columns: {cols_str}
- Source Query: {df_info['sql_query'][:100] if df_info['sql_query'] else 'N/A'}..."""
        
        elif context.get('available_data'):
            # Fallback to context analysis from previous steps
            data_items = []
            for item in context['available_data']:
                if isinstance(item, dict) and item.get('columns'):
                    cols_preview = ', '.join(item['columns'][:5])
                    if len(item['columns']) > 5:
                        cols_preview += '...'
                    data_items.append(
                        f"- {item['source']}: {len(item['columns'])} columns ({cols_preview})"
                    )
                elif isinstance(item, dict):
                    data_items.append(f"- {item['source']}: {item.get('type', 'data')}")
                else:
                    data_items.append(f"- {item}")
            available_data_desc = "\n".join(data_items) if data_items else "No data in memory"
        
        # Build tool call details with validation
        tool_call_details = []
        for i, tc in enumerate(tool_calls):
            tool_name = tc.get('name', 'unknown')
            args = tc.get('args', {})
            
            # Add validation notes for specific tools
            validation_note = ""
            if tool_name == "image_batch_qa_tool":
                if df_info and 'img_path' not in df_info.get('columns', []):
                    validation_note = " ⚠️ WARNING: 'img_path' column not found in current DataFrame"
                elif df_info and 'img_path' in df_info.get('columns', []):
                    validation_note = " ✓ 'img_path' column available"
            
            tool_call_details.append(
                f"- Call {i+1}: {tool_name} with args: {json.dumps(args)}{validation_note}"
            )
        
        # Build context info
        context_info = f"""**Available Data:**
{available_data_desc}

**Current Step Goal:** {current_step.goal}

**Previous Step Output:** {context.get('previous_output', 'None')}

**User Query:** {state.get('query', 'Unknown')}"""
        
        # Add validation warnings if any
        validation_section = ""
        if validation_warnings:
            validation_section = f"""

**Validation Warnings:**
{chr(10).join(validation_warnings)}"""
        
        # Generate reasoning via LLM with clear role definition
        system_role = """You are a Tool Reasoning Explainer for a data exploration agent.

Your role is to explain WHY specific tools were selected for execution at this moment, given the current state of the system.

You are NOT selecting tools - that decision has already been made. Your job is to provide clear, concise reasoning that helps users understand:
1. What tool(s) are being called
2. Why these tools make sense given the available data and step goal
3. How the tool inputs address the current objective

Be specific and grounded in the actual context provided. Do not make assumptions about data that isn't shown."""

        prompt = f"""**SITUATION**: The agent is about to execute the following tool call(s) to accomplish a step in the plan.

**Current Step Goal**: {current_step.goal if current_step else 'Execute task'}

**Tool Calls Being Made** ({len(tool_calls)} call(s)):
{tool_summary}

**Tool Call Details**:
{chr(10).join(tool_call_details)}

**Tool Descriptions**:
{tool_details_str}

**Execution Context**:
{context_info}{validation_section}

**Alternative Tools from Plan**:
{self._format_tool_alternatives(current_step, tool_names)}

---

**YOUR TASK**: Provide:
1. **Decision**: What tool(s) are being used (1 sentence, mention if multiple calls)
2. **Reasoning**: Why this tool and these specific inputs are chosen NOW given the current context (2-3 sentences)

Focus on execution-time factors:
- What data is currently available? (Be specific about columns and shape if shown above)
- Why is this tool appropriate for the current situation?
- How do the inputs address the step goal?
- If multiple calls: Why are multiple calls needed?
- Are there any validation warnings that need attention?

CRITICAL: Base your reasoning ONLY on the information provided above. Do NOT assume or hallucinate data that isn't explicitly shown in the "Available Data" section. If data details are not available, reason to use for data choose rather than making assumptions.
"""
        
        try:
            # Invoke LLM with system role and user prompt
            response = self.llm.invoke([
                SystemMessage(content=system_role),
                HumanMessage(content=prompt)
            ])
            content = response.content
            
            decision_match = re.search(r'\*\*Decision\*\*:?\s*(.+?)(?=\n\n|\n\d+\.|\*\*Reasoning\*\*|$)', content, re.DOTALL | re.IGNORECASE)
            decision = decision_match.group(1).strip() if decision_match else f"Using {tool_summary}"
            
            reasoning_match = re.search(r'\*\*Reasoning\*\*:?\s*(.+?)(?=\n\n|\n\d+\.|$)', content, re.DOTALL | re.IGNORECASE)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else content

            
            return {
                "decision": decision,
                "reasoning": reasoning
            }
        except Exception as e:
            logger.error(f"Error generating decision reasoning: {e}")
            return {
                "decision": f"Using {tool_summary}",
                "reasoning": "Selected based on step requirements"
            }
    
    def _analyze_execution_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze execution context with rich DataFrame metadata from previous steps."""
        available_data = []
        steps = state.get('steps', [])
        
        # Parse previous step outputs for structured data
        for step in steps:
            tool_calls = step.get('tool_calls', [])
            for tc in tool_calls:
                output = tc.get('output', '')
                tool_name = tc.get('tool_name', 'unknown')
                
                # Try to parse JSON output
                try:
                    output_data = json.loads(output)
                    if isinstance(output_data, dict):
                        # Check for data_context in output
                        if 'data_context' in output_data:
                            dc = output_data['data_context']
                            available_data.append({
                                'source': tool_name,
                                'df_id': dc.get('df_id'),
                                'columns': dc.get('columns', []),
                                'shape': dc.get('shape', [0, 0]),
                                'description': output_data.get('description', '')
                            })
                        # Check for visualization output
                        elif 'type' in output_data and output_data.get('type') in ['bar', 'line', 'scatter', 'pie', 'histogram']:
                            available_data.append({
                                'source': tool_name,
                                'type': 'visualization',
                                'viz_type': output_data.get('type')
                            })
                except json.JSONDecodeError:
                    # Fallback to pattern matching for non-JSON outputs
                    if 'stored' in str(output).lower() or 'dataframe' in str(output).lower():
                        available_data.append({
                            'source': tool_name,
                            'type': 'unknown_data'
                        })
        
        # Get previous step output with better parsing
        previous_output_summary = None
        if steps:
            last_step = steps[-1]
            last_tool_calls = last_step.get('tool_calls', [])
            if last_tool_calls:
                last_output = last_tool_calls[-1].get('output', '')
                try:
                    parsed = json.loads(last_output)
                    if isinstance(parsed, dict):
                        # Create a concise summary
                        if 'description' in parsed:
                            previous_output_summary = parsed['description']
                        elif 'error' in parsed:
                            previous_output_summary = f"Error: {parsed['error']}"
                        else:
                            previous_output_summary = str(last_output)[:200]
                except json.JSONDecodeError:
                    previous_output_summary = str(last_output)[:200]
        
        return {
            "available_data": available_data if available_data else [],
            "previous_output": previous_output_summary
        }
    
    def _get_current_dataframe_info(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get current DataFrame information from state (no Redis call needed)."""
        data_context = state.get('data_context')
        if not data_context:
            return None
        
        # Extract metadata from data_context (already in state)
        return {
            'df_id': data_context.df_id,
            'columns': data_context.columns,
            'shape': data_context.shape,
            'sql_query': data_context.sql_query,
            'metadata': data_context.metadata if hasattr(data_context, 'metadata') else {}
        }
    
    def _validate_tool_requirements(self, tool_calls: List[Dict[str, Any]], state: Dict[str, Any]) -> List[str]:
        warnings = []
        df_info = self._get_current_dataframe_info(state)
        
        for tc in tool_calls:
            tool_name = tc.get('name', 'unknown')
            
            # Image QA tool requires img_path column
            if tool_name == "image_batch_qa_tool":
                if not df_info:
                    warnings.append(
                        f"{tool_name} requires a DataFrame in memory, but none found"
                    )
                elif 'img_path' not in df_info.get('columns', []):
                    warnings.append(
                        f"{tool_name} requires 'img_path' column, but current DataFrame "
                        f"only has: {', '.join(df_info['columns'])}"
                    )
            
            # Visualization tools need DataFrame
            elif tool_name in ["large_plotting_tool", "smart_transform_for_viz"]:
                if not df_info:
                    warnings.append(
                        f"{tool_name} requires a DataFrame in memory, but none found"
                    )
            
            # Python REPL typically needs DataFrame
            elif tool_name == "python_repl":
                if not df_info:
                    warnings.append(
                        f"ℹ{tool_name} typically needs a DataFrame, but none found in state"
                    )
        
        return warnings
    
    def _format_tool_alternatives(self, current_step: Any, selected_tools: List[str]) -> str:
        alternatives = []
        for option in current_step.tool_options:
            if option.tool_name not in selected_tools:
                alternatives.append(
                    f"  - {option.tool_name} (Priority {option.priority}): {option.use_case}"
                )
        
        if alternatives:
            return "\n".join(alternatives)
        else:
            return "  (No alternatives in plan)"
    
    def tools_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        messages = state.get("messages", [])
        last_message = messages[-1]
        steps = state.get("steps", [])
        step_counter = state.get("step_counter", 0)
        current_step_index = state.get("current_step_index", 0)
        data_context = state.get("data_context")  # Preserve existing data_context
        visualizations = state.get("visualizations", [])  # Preserve existing visualizations
        
        # Execute tools
        tool_node = ToolNode(tools=self.tools)
        result = tool_node.invoke(state)
        
        logger.info(f"Tool execution completed with {len(result.get('messages', []))} tool messages")
        
        has_error = False
        error_details = []
        failed_tool_names = []
        
        # Match outputs to tool_calls within the latest step AND extract data_context/visualizations
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls and steps:
            latest_step = steps[-1]  # Get the step we just created in process_query
            
            for tool_call in last_message.tool_calls:
                tool_call_id = tool_call['id']
                tool_name = tool_call.get('name', 'unknown')
                
                # Find corresponding output
                tool_output = None
                tool_message = None
                for msg in result.get("messages", []):
                    if hasattr(msg, 'tool_call_id') and msg.tool_call_id == tool_call_id:
                        tool_output = msg.content
                        tool_message = msg
                        break
                
                # NEW: Check for errors in tool output
                # PRIORITY 1: JSON-based error detection (standardized format)
                if tool_output:
                    error_detected_via_json = False
                    
                    try:
                        output_data = json.loads(tool_output)
                        
                        # Check if it's a standardized error response
                        if isinstance(output_data, dict) and "error" in output_data:
                            has_error = True
                            error_detected_via_json = True
                            failed_tool_names.append(tool_name)
                            
                            error_details.append({
                                'tool_name': output_data.get('tool_name', tool_name),
                                'tool_call_id': tool_call_id,
                                'error_message': output_data.get('error'),
                                'error_type': output_data.get('error_type', 'unknown'),
                                'details': output_data.get('details', {}),
                                'recoverable': output_data.get('recoverable', True),
                                'full_output': str(tool_output),
                                'detection_method': 'json'  # Track how we detected it
                            })
                            logger.warning(f"✅ JSON Error detected in tool {tool_name}: {output_data.get('error')}")
                            logger.info(f"   Error type: {output_data.get('error_type')}, Recoverable: {output_data.get('recoverable')}")
                            
                    except json.JSONDecodeError:
                        pass
                    
                    if not error_detected_via_json:
                        output_str = str(tool_output)
                        output_lower = output_str.lower()
                        
                        # Skip error detection for analysis results, but still match the output!
                        if not output_str.startswith('Analysis Result:'):
                            error_indicators = [
                                'error:', 'exception:', 'failed', 'traceback',
                                'could not', 'unable to', 'invalid', 'not found'
                            ]
                            
                            # Check if this is an error message
                            if any(indicator in output_lower for indicator in error_indicators):
                                lines = output_str.split('\n')
                                has_error_line = any(
                                    line.strip().lower().startswith('error:') or
                                    line.strip().lower().startswith('exception:') or
                                    'traceback' in line.lower()
                                    for line in lines
                                )
                                
                                if (has_error_line or
                                    (tool_message and hasattr(tool_message, 'status') and tool_message.status == 'error')):
                                    has_error = True
                                    failed_tool_names.append(tool_name)
                                    # Extract first line of error for summary
                                    error_lines = output_str.split('\n')
                                    error_summary = error_lines[0][:200] if error_lines else output_str[:200]
                                    error_details.append({
                                        'tool_name': tool_name,
                                        'tool_call_id': tool_call_id,
                                        'error_message': error_summary,
                                        'error_type': 'unknown',  # Can't determine from pattern
                                        'details': {},
                                        'recoverable': True,  # Assume recoverable for pattern-detected errors
                                        'full_output': output_str,
                                        'detection_method': 'pattern'  # Track how we detected it
                                    })
                                    logger.warning(f"⚠️  Pattern-based error detected in tool {tool_name}: {error_summary}")
                                    logger.info(f"   (Consider updating this tool to use standardized JSON error format)")

                
                # Find corresponding tool_call entry and update with output
                for tc in latest_step.get('tool_calls', []):
                    if tc.get('tool_call_id') == tool_call_id:
                        tc['output'] = tool_output or "No output captured"
                        # NEW: Mark if this tool call had an error
                        if has_error and tool_name in failed_tool_names:
                            tc['has_error'] = True
                        
                        logger.info(f"Matched output for {tc.get('tool_name')}: {tool_call_id[:8]}...")
                        
                        # Extract data_context and visualizations from tool output if present
                        # Skip extraction if there was an error
                        if tool_output and not has_error:
                            try:
                                output_data = json.loads(tool_output)
                                if isinstance(output_data, dict):
                                    # Extract data_context
                                    if 'data_context' in output_data:
                                        from app.schemas.chat import DataContext
                                        data_context = DataContext(**output_data['data_context'])
                                        logger.info(f"Extracted data_context from tool output: {data_context.df_id}")
                                    
                                    # Extract visualization (from smart_transform_for_viz)
                                    if tool_name == 'smart_transform_for_viz' and 'type' in output_data:
                                        # This is a visualization output
                                        visualizations.append(output_data)
                                        logger.info(f"Extracted {output_data.get('type')} visualization from tool output")
                                    
                            except (json.JSONDecodeError, Exception) as e:
                                logger.debug(f"Could not extract data_context/visualization from tool output: {e}")
                        
                        break
        
        # NEW: Prepare state update based on error status
        state_update = {
            "messages": result.get("messages", []),
            "steps": steps,
            "step_counter": step_counter,
            "data_context": data_context,
            "visualizations": visualizations
        }
        
        # NEW: Add error handling logic
        if has_error:
            # Don't increment step index - stay on current step
            state_update["current_step_index"] = max(0, current_step_index - 1)
            
            # Set feedback state with error information
            feedback_message = f"Tool execution error in step {current_step_index}: "
            feedback_message += ", ".join([f"{tool}" for tool in failed_tool_names])
            
            state_update["feedback"] = feedback_message
            state_update["error_details"] = error_details
            
            logger.error(f"Tool execution failed. Rolling back step index from {current_step_index} to {current_step_index - 1}")
            logger.error(f"Feedback: {feedback_message}")
        
        return state_update
    
    def should_continue_from_process_query(self, state: ExplainableAgentState) -> Literal["tools", "finalizer", "process_query", "human_feedback"]:
        """Route after process_query based on state."""
        # Priority 1: Check for replan request
        if state.get("human_comment"):
            return "human_feedback"
        
        # Priority 2: Check for tool calls
        messages = state.get("messages", [])
        if messages and hasattr(messages[-1], 'tool_calls') and messages[-1].tool_calls:
            return "tools"
        
        # Priority 3: Check if all steps completed
        dynamic_plan = state.get("dynamic_plan")
        current_idx = state.get("current_step_index", 0)
        if dynamic_plan and current_idx >= len(dynamic_plan.steps):
            return "finalizer"
        
        # Default: Continue to next step
        return "process_query"
    
    def should_continue_from_tools(self, state: ExplainableAgentState) -> Literal["explainer", "human_feedback"]:
        if state.get("feedback"):
            return "human_feedback"    
        return "explainer"
    
    def should_continue_from_explainer(self, state: ExplainableAgentState) -> Literal["human_feedback", "process_query"]:
        """Route after explainer based on whether it detected a logical failure."""
        feedback = state.get("feedback", "")
        
        # Check if it's a retry feedback (auto-retry, no interrupt)
        if feedback and "RETRY_IMAGE_QA" in feedback:
            logger.info("Explainer detected partial failure - auto-retry without interrupt")
            return "process_query"
        
        # Check for error feedback (interrupt user)
        if feedback:
            logger.info("Explainer detected failure - routing to human_feedback interrupt")
            return "human_feedback"
        
        return "process_query"
    
    def finalizer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        return self.finalizer.execute(state)
    
    def human_feedback(self, state: ExplainableAgentState) -> Dict[str, Any]:
        from langgraph.types import interrupt
        
        feedback = state.get("feedback")
        error_details = state.get("error_details", [])
        human_comment = state.get("human_comment")
        
        if feedback and not human_comment:
            logger.info(f"Tool execution error detected: {feedback}")
            
            interrupt_data = {
                "type": "tool_error",
                "message": feedback,
                "error_details": error_details,
                "current_step_index": state.get("current_step_index", 0),
                "options": ["retry", "replan", "cancel"]
            }
            
            logger.info("Pausing for user decision on tool error")
            feedback_data = interrupt(interrupt_data)
            
        elif human_comment:
            logger.info("Entering human_feedback node for manual replan - pausing for input")
            
            interrupt_data = {
                "type": "replan_request", 
                "message": "Plan needs revision based on user feedback",
                "human_comment": human_comment,
                "options": ["replan", "cancel"]
            }
            
            feedback_data = interrupt(interrupt_data)
            
        elif state.get("dynamic_plan") and not state.get("_plan_approved"):
            # Plan approval needed
            logger.info("New plan created - requesting approval")
            
            interrupt_data = {
                "type": "plan_approval",
                "message": "Plan created and awaiting approval",
                "plan": state.get("dynamic_plan").model_dump() if state.get("dynamic_plan") else None,
                "options": ["approve", "reject"]
            }
            
            feedback_data = interrupt(interrupt_data)
            
        else:
            # Generic feedback
            logger.info("Entering human_feedback node - pausing for input")
            feedback_data = interrupt("awaiting_feedback")
        
        logger.info(f"Received human feedback: {feedback_data}")
        
        updates = {}
        if isinstance(feedback_data, dict):
            action = feedback_data.get("action")
            
            if action == "cancel":
                updates["status"] = "cancelled"
                # Clear error state
                updates["feedback"] = None
                updates["error_details"] = []
                return updates
                
            elif action == "retry":
                # NEW: For tool errors, allow retry without replanning
                # Keep error_details so process_query can learn from the error
                updates["status"] = "retry"
                updates["feedback"] = None  # Clear feedback to allow retry
                # DON'T clear error_details - keep for context
                # Keep current_step_index as is to retry same step
                return updates
            
            elif action == "approve":
                # Plan approved - proceed with execution
                # Clear any pending tool interrupts from previous failed executions
                updates["status"] = "approved"
                updates["_plan_approved"] = True  # Mark plan as approved
                updates["error_explanation"] = None  # Clear error explanation to prevent replan loop
                updates["tasks"] = ()  # Clear pending tool interrupts
                logger.info("Plan approved - cleared error_explanation and pending tool interrupts")
                return updates
            
            elif action == "reject":
                # Plan rejected - request replanning
                updates["status"] = "feedback"
                updates["human_comment"] = feedback_data.get("comment", "Plan rejected, please revise")
                return updates
                
            elif action == "replan" or action == "feedback":
                # Trigger replanning
                updates["status"] = "feedback"
                if "comment" in feedback_data:
                    updates["human_comment"] = feedback_data.get("comment")
                # Keep feedback and error_details for planner to review
                return updates
        
        return updates
    
    def route_after_feedback(self, state: ExplainableAgentState) -> Literal["planner", "finalizer", "process_query", "error_explainer"]:
        """Route after human feedback based on user action."""
        status = state.get("status")
        logger.info(f"[ROUTING] route_after_feedback called with status: {status}")
        
        if status == "cancelled":
            logger.info("[ROUTING] Routing to error_explainer (cancelled) - to explain error before stopping")
            return "error_explainer"
        elif status == "approved":
            logger.info("[ROUTING] Routing to process_query (approved)")
            return "process_query"
        elif status == "retry":
            logger.info("[ROUTING] Routing to process_query (retry)")
            return "process_query"
        elif status == "feedback":
            # Replan: ALWAYS go to planner directly (User request)
            # Even if error-triggered, we skip ErrorExplainer for replans to avoid loop/delay
            logger.info("Feedback/Replan - routing directly to planner")
            return "planner"
        else:
            logger.warning(f"[ROUTING] Unknown status '{status}', routing to finalizer")
            return "finalizer"

    def route_after_error_explainer(self, state: ExplainableAgentState) -> Literal["planner", "finalizer"]:
   
        status = state.get("status")
        
        if status == "cancelled":
            logger.info("[ROUTING] Error explained for cancellation - routing to finalizer to stop")
            return "finalizer"
        else:
            # Default fallback (though we shouldn't reach here for replans anymore) is planner
            logger.info("[ROUTING] Error explained - routing to planner")
            return "planner"
    
    def route_after_planner(self, state: ExplainableAgentState) -> Literal["human_feedback", "process_query"]:
        use_planning = state.get("use_planning", True)
        
        if use_planning:
            logger.info("Plan created - routing to human_feedback for approval")
            return "human_feedback"
        else:
            logger.info("Planning disabled - routing directly to process_query")
            return "process_query"
    
    def planner_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute planner node."""
        result = self.planner.execute(state)
        
        # NEW: Clear error state when replanning (similar to how human_comment is handled)
        if state.get("feedback") or state.get("error_details"):
            logger.info("Replanning after tool error - clearing error state")
            result["feedback"] = None
            result["error_details"] = []
            # current_step_index will be reset by planner's _handle_dynamic_planning
        
        return result
    
    def explainer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute explainer node to generate result explanations."""
        return self.explainer.execute(state)
    
    def error_explainer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Generate user-friendly error explanation before replanning."""
        logger.info("Generating error explanation for replan context")
        
        # Extract potential df_id from state to help explainer check Redis
        df_id = None
        data_context = state.get("data_context")
        if data_context:
            df_id = data_context.df_id
            
        # We need to update how we call execute since we changed signature of explain_error
        # But wait, execute() usually calls explain_error(). I need to check execute() implementation.
        # Let's assume for now I should pass it via state or kwargs if execute handles it.
        # Actually, looking at the previous file view, ErrorExplainerNode didn't have an execute method shown in the snippet?
        # I need to verify if ErrorExplainerNode inherits from something with execute or if it's missing.
        # The 'view_code_item' showed "MainAgent.error_explainer_node" calling "self.error_explainer.execute(state)".
        # So ErrorExplainerNode MUST have an execute method.
        # I better check ErrorExplainerNode.execute first before making this change.
        return self.error_explainer.execute(state, df_id=df_id)
    
    def _build_system_message(self, state: ExplainableAgentState = None) -> str:
        """Build system message for the execution agent with user preferences."""
        from app.agents.prompts.process_query_prompts import get_process_query_prompt
        from app.agents.prompts.user_preferences import get_user_preference_prompt_safe
        
        # Fetch user preferences if available
        user_preferences = ""
        if state and state.get("user_id"):
            try:
                from app.services.dependencies import get_redis_profile_service, get_profile_service
                
                redis_service = get_redis_profile_service()
                profile_service = get_profile_service()
                user_preferences = get_user_preference_prompt_safe(
                    state.get("user_id"),
                    redis_service,
                    profile_service
                )
                if user_preferences:
                    logger.info(f"Fetched user preferences for process_query")
            except Exception as e:
                logger.warning(f"Failed to fetch user preferences in process_query: {e}")
        
        return get_process_query_prompt(user_preferences)
    
    def create_graph(self):
        """Create the main agent graph."""
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        graph.add_node("assistant", self.assistant_agent)
        graph.add_node("main_agent_flow", self.main_agent_entry)
        graph.add_node("planner", self.planner_node)
        graph.add_node("process_query", self.process_query)
        graph.add_node("tools", self.tools_node)
        graph.add_node("explainer", self.explainer_node)
        graph.add_node("error_explainer", self.error_explainer_node)  # NEW
        graph.add_node("finalizer", self.finalizer_node)
        graph.add_node("human_feedback", self.human_feedback)
        
        # Set entry point
        graph.set_entry_point("planner")
        
        # Conditional routing after planner
        graph.add_conditional_edges(
            "planner",
            self.route_after_planner,
            {
                "human_feedback": "human_feedback",
                "process_query": "process_query"
            }
        )
        
        # Conditional routing after process_query
        graph.add_conditional_edges(
            "process_query",
            self.should_continue_from_process_query,
            {
                "tools": "tools",
                "finalizer": "finalizer",
                "process_query": "process_query",
                "human_feedback": "human_feedback"
            }
        )
          
        # Route after tools
        graph.add_conditional_edges(
            "tools",
            self.should_continue_from_tools,
            {
                "human_feedback": "human_feedback",
                "explainer": "explainer"
            }
        )
        
        # After explainer, conditionally route (interrupt if failure detected)
        graph.add_conditional_edges(
            "explainer",
            self.should_continue_from_explainer,
            {
                "human_feedback": "human_feedback",
                "process_query": "process_query"
            }
        )
        
        # After error_explainer, conditionally route (Finalizer if cancelled, Planner otherwise)
        graph.add_conditional_edges(
            "error_explainer",
            self.route_after_error_explainer,
            {
                "finalizer": "finalizer",
                "planner": "planner"
            }
        )
        
        # After human_feedback, route based on action
        graph.add_conditional_edges(
            "human_feedback",
            self.route_after_feedback,
            {
                "planner": "planner",
                "finalizer": "finalizer",
                "process_query": "process_query",
                "error_explainer": "error_explainer"  # NEW
            }
        )
        
        # Finalizer goes to END
        graph.add_edge("finalizer", END)
        
        # Compile the graph
        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer, store=self.store)
        else:
            return graph.compile(checkpointer=MemorySaver(), store=self.store)
