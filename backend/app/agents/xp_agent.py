"""
Extended XpAgent - Adapted for production streaming.

This module wraps the experimental XpAgent from dev folder to work with
the production streaming infrastructure. It adapts XpAgent's multi-agent
architecture to produce streaming events compatible with MainAgent.

Key differences from dev/XpAgent.py:
- Uses ExplainableAgentState for streaming compatibility
- Produces AIMessages that streaming handlers can process
- Wrapped in a class with .graph attribute (like MainAgent)
- Uses PostgresSaver instead of MemorySaver
- Uses wrapped tools from tools/ directory
"""

import os
import json
import logging
import re
from typing import Any, Dict, List, Optional, Literal
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from app.agents.state import ExplainableAgentState
from app.schemas.chat import DataContext

logger = logging.getLogger(__name__)

# Import XpToolkit for wrapped tools
from app.agents.tools.xp_toolkit import XpToolkit

# Import state models from dev folder for internal use
from app.agents.dev.agent.state.main_agent_state_v2 import (
    PlanStep,
    StepResult,
    ExecutionPlan,
    FinalAnswer,
    TOOL_CAPABILITIES
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Calculate paths relative to this file's location for Docker compatibility
_CURRENT_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _CURRENT_DIR.parent.parent  # Goes from agents -> app -> backend

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DB_PATH = str(_BACKEND_ROOT / "app" / "resource" / "art.db")

# Workspace configuration
WORKSPACE_PATH = _CURRENT_DIR / "workspace"
OUTPUT_PATH = WORKSPACE_PATH / "outputs"
PLOT_PATH = WORKSPACE_PATH / "plot"

DATABASE_SCHEMA = """
## Table: paintings

### Columns
| Column Name | Data Type | Description |
|------------|-----------|-------------|
| title | TEXT | Name of the painting |
| inception | INTEGER | Year the painting was created |
| movement | TEXT | Art movement (e.g., Renaissance, Baroque) |
| genre | TEXT | Artistic genre (e.g., portrait, landscape) |
| image_url | TEXT | Public URL to the painting image (DO NOT USE for image analysis) |
| img_path | TEXT | Local file path to the image - USE THIS for image_qna_agent |

### Image Analysis Workflow
1. ALWAYS use `img_path` column (NOT image_url) for visual analysis
2. First query database to get img_path values
3. Then pass those img_path values to image_qna_agent
"""


# ============================================================================
# XP AGENT CLASS (Production-ready)
# ============================================================================

class XpAgent:
    """
    Extended XpAgent adapted for production streaming.
    
    This class wraps the XpAgent graph in a structure compatible with
    the existing streaming infrastructure (same interface as MainAgent).
    """
    
    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        db_path: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        use_gpu: Optional[bool] = None,
        checkpointer: Optional[Any] = None,
        use_postgres_checkpointer: bool = True
    ):
        self.model_name = model_name
        self.db_path = db_path or DEFAULT_DB_PATH
        self.use_gpu = use_gpu
        
        # Initialize LLM
        if llm is not None:
            self.llm = llm
        else:
            self.llm = init_chat_model(model_name)
        
        # Create toolkit (wrapped subagents as tools)
        self.toolkit = XpToolkit(
            model_name=model_name,
            db_path=self.db_path,
            use_gpu=use_gpu
        )
        
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
                    logger.info("XpAgent using PostgresSaver checkpointer")
                else:
                    logger.warning("Checkpointer not initialized, falling back to MemorySaver")
                    self.checkpointer = MemorySaver()
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL checkpointer for XpAgent: {e}")
                self.checkpointer = MemorySaver()
        else:
            self.checkpointer = MemorySaver()
        
        # Internal state for step execution
        self._plan_steps: List[PlanStep] = []
        self._step_results: List[StepResult] = []
        self._tool_context: str = ""
        self._generated_files: List[str] = []
        
        # Build the graph
        self.graph = self._create_graph()
        logger.info("XpAgent initialized successfully")
    
    def _create_graph(self):
        """Create the XpAgent graph using ExplainableAgentState."""
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        graph.add_node("planner", self._planner_node)
        graph.add_node("executor", self._executor_node)
        graph.add_node("finalizer", self._finalizer_node)
        graph.add_node("human_feedback", self._human_feedback_node)
        
        # Set entry point
        graph.set_entry_point("planner")
        
        # Add edges
        graph.add_conditional_edges(
            "planner",
            self._route_after_planner,
            {
                "executor": "executor",
                "human_feedback": "human_feedback"
            }
        )
        
        graph.add_conditional_edges(
            "executor",
            self._route_after_executor,
            {
                "executor": "executor",
                "finalizer": "finalizer",
                "human_feedback": "human_feedback"
            }
        )
        
        graph.add_conditional_edges(
            "human_feedback",
            self._route_after_feedback,
            {
                "executor": "executor",
                "finalizer": "finalizer"
            }
        )
        
        graph.add_edge("finalizer", END)
        
        # Compile with checkpointer
        return graph.compile(checkpointer=self.checkpointer)
    
    # ========================================================================
    # NODE: PLANNER
    # ========================================================================
    
    def _planner_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Plan how to accomplish the user's task."""
        query = state.get("query", "")
        use_planning = state.get("use_planning", True)
        
        if not query:
            for msg in state.get("messages", []):
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
        
        logger.info(f"XpAgent planner processing query: {query[:100]}...")
        
        # If planning is disabled, create a simple single-step plan
        if not use_planning:
            self._plan_steps = [PlanStep(
                step_number=1,
                description="Execute database query",
                tool_name="database_exploration_agent",
                tool_args_json=json.dumps({"query": query})
            )]
            
            return {
                "query": query,
                "plan": "Direct execution without planning",
                "status": "approved",
                "step_counter": 0,
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"**Executing query directly...**\n\nQuery: {query}")
                ]
            }
        
        # Build planning prompt
        system_prompt = f"""You are a Strategic AI Planner for an artwork database.

## Available Tools
{json.dumps({k: v.model_dump() for k, v in TOOL_CAPABILITIES.items()}, indent=2)}

## Database Schema
{DATABASE_SCHEMA}

## Planning Rules
1. Create the MINIMUM steps needed
2. database_exploration_agent: For database queries
3. image_qna_agent: ONLY for visual content analysis (requires img_path from database)
4. data_plotting_agent: ONLY when user explicitly asks for charts

Create a minimal, efficient plan.
"""
        
        user_content = f"**Query**: {query}\n\nCreate the MINIMUM steps needed."
        
        try:
            planner_llm = self.llm.with_structured_output(ExecutionPlan)
            plan: ExecutionPlan = planner_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            
            self._plan_steps = plan.steps
            self._step_results = []
            self._tool_context = ""
            self._generated_files = []
            
            # Format plan for display
            plan_text = f"**Plan for your request:**\n\n"
            plan_text += f"Understanding: {plan.understanding}\n\n"
            plan_text += "**Steps:**\n"
            for step in plan.steps:
                plan_text += f"{step.step_number}. {step.description} (using {step.tool_name})\n"
            
            return {
                "query": query,
                "plan": plan_text,
                "status": "user_feedback",  # Request approval
                "step_counter": 0,
                "messages": state.get("messages", []) + [
                    AIMessage(content=plan_text)
                ]
            }
            
        except Exception as e:
            logger.error(f"Planning error: {e}")
            return {
                "query": query,
                "plan": f"Planning failed: {str(e)}",
                "status": "error",
                "assistant_response": f"I encountered an error while planning: {str(e)}",
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"Error during planning: {str(e)}")
                ]
            }
    
    # ========================================================================
    # NODE: EXECUTOR
    # ========================================================================
    
    def _executor_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute the current step in the plan."""
        step_counter = state.get("step_counter", 0)
        
        if step_counter >= len(self._plan_steps):
            return {"status": "completed"}
        
        current_step = self._plan_steps[step_counter]
        logger.info(f"Executing step {current_step.step_number}: {current_step.description}")
        
        # Execute the tool - now returns (result, context, raw_json, data_context)
        result, context, raw_json, data_context = self._execute_tool(current_step)
        result.step_number = current_step.step_number
        
        self._step_results.append(result)
        self._tool_context += f"\n\n{context}"
        
        if result.output_file and result.output_file not in self._generated_files:
            self._generated_files.append(result.output_file)
        
        # Build step update for streaming
        step_info = {
            "step_number": current_step.step_number,
            "step_description": current_step.description,
            "tool": current_step.tool_name,
            "success": result.success,
            "result": result.result_content[:500] if result.success else result.error_message,
        }
        
        # Add tool_calls structure for frontend compatibility
        tool_call_id = f"xp_tool_{current_step.step_number}_{id(current_step)}"
        step_info["tool_calls"] = [{
            "tool_name": current_step.tool_name,
            "tool_call_id": tool_call_id,
            "input": current_step.get_tool_args(),
            "output": raw_json  # Raw JSON for frontend to parse data_context
        }]
        
        # Update state
        current_steps = state.get("steps", [])
        current_steps.append(step_info)
        
        # Create messages - include ToolMessage with raw JSON so streaming handlers can detect data_context
        new_messages = state.get("messages", [])
        
        # Add AIMessage with tool call (simulates LLM calling the tool)
        ai_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": tool_call_id,
                "name": current_step.tool_name,
                "args": current_step.get_tool_args()
            }]
        )
        new_messages.append(ai_msg)
        
        # Add ToolMessage with the raw JSON output (this is what streaming handlers look for)
        tool_msg = ToolMessage(
            content=raw_json,
            tool_call_id=tool_call_id,
            name=current_step.tool_name
        )
        new_messages.append(tool_msg)
        
        # Add summary AIMessage
        new_messages.append(
            AIMessage(content=f"**Step {current_step.step_number}**: {current_step.description}\n\n{result.result_content[:1000] if result.success else f'Error: {result.error_message}'}")
        )
        
        # Build state update
        state_update = {
            "step_counter": step_counter + 1,
            "steps": current_steps,
            "status": "error" if not result.success else "running",
            "messages": new_messages
        }
        
        # Store data_context in state if available
        if data_context:
            state_update["data_context"] = data_context
            logger.info(f"Stored data_context in state: {data_context.df_id}")
        
        if not result.success:
            state_update["assistant_response"] = f"Step {current_step.step_number} failed: {result.error_message}"
        
        return state_update
    
    def _execute_tool(self, step: PlanStep) -> tuple:
        """Execute a tool and return (result, context, raw_json, data_context).
        
        Returns:
            tuple: (StepResult, context_str, raw_json_str, DataContext or None)
        """
        tool_args = step.get_tool_args()
        
        def _extract_data_context(result_data: dict) -> Optional[DataContext]:
            """Extract DataContext from tool result if present."""
            if 'data_context' in result_data:
                try:
                    return DataContext(**result_data['data_context'])
                except Exception as e:
                    logger.warning(f"Failed to parse data_context: {e}")
            return None
        
        try:
            if step.tool_name == "database_exploration_agent":
                tool = self.toolkit.get_data_exploration_tool()
                query = tool_args.get("query", step.description)
                
                # Tool returns JSON string
                result_json = tool._run(query=query)
                result_data = json.loads(result_json)
                
                result_content = result_data.get("result", "")
                output_file = result_data.get("csv_file")
                data_context = _extract_data_context(result_data)
                
                # Check for error (tools use "success" key)
                if not result_data.get("success", True):
                    return (
                        StepResult(
                            step_number=step.step_number,
                            success=False,
                            error_message=result_data.get("error", "Unknown error")
                        ),
                        f"**Error**: {result_data.get('error', 'Unknown error')}",
                        result_json,
                        None
                    )
                
                # Track generated files
                if output_file:
                    self._generated_files.append(output_file)
                
                return (
                    StepResult(
                        step_number=step.step_number,
                        success=True,
                        result_content=str(result_content),
                        output_file=output_file
                    ),
                    f"**Database Query Result**:\n{result_content}",
                    result_json,
                    data_context
                )
                
            elif step.tool_name == "image_qna_agent":
                tool = self.toolkit.get_image_qna_tool()
                query = tool_args.get("query", step.description)
                img_paths = tool_args.get("img_path", [])
                
                if not img_paths:
                    # Try to extract from previous context
                    import re
                    matches = re.findall(r'images/img_\d+\.jpg', self._tool_context)
                    img_paths = list(set(matches))[:5]
                
                if not img_paths:
                    error_json = json.dumps({"success": False, "error": "No image paths available"})
                    return (
                        StepResult(
                            step_number=step.step_number,
                            success=False,
                            error_message="No image paths available"
                        ),
                        "**Error**: No image paths found",
                        error_json,
                        None
                    )
                
                # Tool returns JSON string
                result_json = tool._run(query=query, img_path=img_paths)
                result_data = json.loads(result_json)
                
                result_content = result_data.get("result", "")
                csv_file = result_data.get("csv_file")
                data_context = _extract_data_context(result_data)
                
                # Check for error (tools use "success" key)
                if not result_data.get("success", True):
                    return (
                        StepResult(
                            step_number=step.step_number,
                            success=False,
                            error_message=result_data.get("error", "Unknown error")
                        ),
                        f"**Error**: {result_data.get('error', 'Unknown error')}",
                        result_json,
                        None
                    )
                
                # Track generated files
                if csv_file:
                    self._generated_files.append(csv_file)
                
                return (
                    StepResult(
                        step_number=step.step_number,
                        success=True,
                        result_content=str(result_content)
                    ),
                    f"**Image Analysis Result**:\n{result_content}",
                    result_json,
                    data_context
                )
                
            elif step.tool_name == "data_plotting_agent":
                tool = self.toolkit.get_plotting_tool()
                task = tool_args.get("task", step.description)
                
                # Find latest CSV from context
                file_path = None
                if self._generated_files:
                    for f in reversed(self._generated_files):
                        if f.endswith('.csv'):
                            file_path = f
                            break
                
                # Tool returns JSON string
                result_json = tool._run(task=task, file_path=file_path)
                result_data = json.loads(result_json)
                
                result_content = result_data.get("result", "")
                output_file = result_data.get("plot_file")
                # Plotting tool doesn't create CSV, but might reference data_context from input
                
                # Check for error (tools use "success" key)
                if not result_data.get("success", True):
                    return (
                        StepResult(
                            step_number=step.step_number,
                            success=False,
                            error_message=result_data.get("error", "Unknown error")
                        ),
                        f"**Error**: {result_data.get('error', 'Unknown error')}",
                        result_json,
                        None
                    )
                
                # Track generated files
                if output_file:
                    self._generated_files.append(output_file)
                
                return (
                    StepResult(
                        step_number=step.step_number,
                        success=True,
                        result_content=str(result_content),
                        output_file=output_file
                    ),
                    f"**Plotting Result**:\n{result_content}",
                    result_json,
                    None  # Plotting tool doesn't create data_context
                )
                
            else:
                error_json = json.dumps({"success": False, "error": f"Unknown tool: {step.tool_name}"})
                return (
                    StepResult(
                        step_number=step.step_number,
                        success=False,
                        error_message=f"Unknown tool: {step.tool_name}"
                    ),
                    f"**Error**: Unknown tool {step.tool_name}",
                    error_json,
                    None
                )
                
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            error_json = json.dumps({"success": False, "error": str(e)})
            return (
                StepResult(
                    step_number=step.step_number,
                    success=False,
                    error_message=str(e)
                ),
                f"**Error**: {str(e)}",
                error_json,
                None
            )
    
    # ========================================================================
    # NODE: FINALIZER
    # ========================================================================
    
    def _finalizer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Aggregate results and create final response."""
        query = state.get("query", "")
        
        logger.info("XpAgent finalizing response...")
        
        # Build aggregation prompt
        system_prompt = """You are a helpful assistant that synthesizes execution results.
Create a clear, comprehensive answer based on the results.
Be concise but complete. Mention any generated files."""
        
        user_content = f"""## Original Query
{query}

## Execution Results
{self._tool_context}

## Generated Files
{json.dumps(self._generated_files) if self._generated_files else "None"}

Synthesize these results into a clear answer.
"""
        
        try:
            answer_llm = self.llm.with_structured_output(FinalAnswer)
            answer: FinalAnswer = answer_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            
            final_text = f"{answer.summary}\n\n{answer.detailed_answer}"
            if self._generated_files:
                final_text += f"\n\n**Generated Files**: {', '.join(self._generated_files)}"
            if answer.limitations:
                final_text += f"\n\n**Note**: {answer.limitations}"
                
        except Exception as e:
            logger.error(f"Aggregation error: {e}")
            final_text = f"Results for: {query}\n\n{self._tool_context}"
        
        return {
            "assistant_response": final_text,
            "status": "finished",
            "visualizations": self._generated_files,
            "messages": state.get("messages", []) + [AIMessage(content=final_text)]
        }
    
    # ========================================================================
    # NODE: HUMAN FEEDBACK (Simple Boolean Approval)
    # ========================================================================
    
    def _human_feedback_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Wait for human feedback on plan.
        
        XpAgent uses a simplified approval flow with only two options:
        - approve: Proceed with execution
        - reject: Cancel execution
        
        This differs from MainAgent which has additional options like
        retry, replan, etc.
        """
        status = state.get("status", "")
        plan = state.get("plan", "")
        query = state.get("query", "")
        steps = state.get("steps", [])
        
        logger.info(f"XpAgent human_feedback: status={status}, has_plan={bool(plan)}")
        
        # Build interrupt data based on current status
        if status == "error":
            # Error during execution - ask user if they want to continue
            interrupt_data = {
                "type": "xp_error",
                "message": "An error occurred during execution",
                "error_details": {
                    "step_counter": state.get("step_counter", 0),
                    "steps": steps
                },
                "options": ["approve", "reject"]  # approve = retry, reject = cancel
            }
            logger.info("XpAgent pausing for error recovery decision")
            
        elif status == "user_feedback":
            # Plan ready for approval
            interrupt_data = {
                "type": "xp_plan_approval",
                "message": "Plan created - please approve to execute",
                "plan": plan,
                "query": query,
                "steps": steps,
                "options": ["approve", "reject"]
            }
            logger.info("XpAgent pausing for plan approval")
            
        else:
            # Generic approval request
            interrupt_data = {
                "type": "xp_approval",
                "message": "Awaiting approval to proceed",
                "plan": plan,
                "query": query,
                "options": ["approve", "reject"]
            }
            logger.info("XpAgent pausing for generic approval")
        
        # Pause execution and wait for feedback
        feedback = interrupt(interrupt_data)
        
        # Parse feedback response
        if isinstance(feedback, dict):
            action = feedback.get("action", "approve")
            comment = feedback.get("comment", "")
        else:
            # Handle string feedback for backwards compatibility
            action = str(feedback) if feedback else "approve"
            comment = ""
        
        logger.info(f"XpAgent received feedback: action={action}, comment={comment}")
        
        # Process feedback - simple boolean logic
        if action == "approve":
            return {
                "status": "approved",
                "assistant_response": None  # Clear any error message
            }
        elif action == "reject":
            return {
                "status": "cancelled",
                "assistant_response": "Execution cancelled by user"
            }
        else:
            # Unknown action - default to approved
            logger.warning(f"Unknown feedback action '{action}', defaulting to approved")
            return {"status": "approved"}
    
    # ========================================================================
    # ROUTING FUNCTIONS
    # ========================================================================
    
    def _route_after_planner(self, state: ExplainableAgentState) -> Literal["executor", "human_feedback"]:
        """Route after planning."""
        status = state.get("status", "")
        use_planning = state.get("use_planning", True)
        
        if status == "error":
            return "human_feedback"
        
        if use_planning and status == "user_feedback":
            return "human_feedback"
        
        return "executor"
    
    def _route_after_executor(self, state: ExplainableAgentState) -> Literal["executor", "finalizer", "human_feedback"]:
        """Route after execution."""
        status = state.get("status", "")
        step_counter = state.get("step_counter", 0)
        
        if status == "error":
            return "human_feedback"
        
        if step_counter >= len(self._plan_steps):
            return "finalizer"
        
        return "executor"
    
    def _route_after_feedback(self, state: ExplainableAgentState) -> Literal["executor", "finalizer"]:
        """Route after feedback."""
        status = state.get("status", "")
        
        if status == "cancelled":
            return "finalizer"
        else:  # approved - proceed to executor
            return "executor"


# ============================================================================
# BUILD FUNCTION (for compatibility with existing code)
# ============================================================================

def build_xp_agent(
    model_name: str = DEFAULT_MODEL,
    db_path: Optional[str] = None,
    use_gpu: Optional[bool] = None,
    checkpointer: Optional[Any] = None
) -> XpAgent:
    """
    Build an XpAgent instance.
    
    This function provides compatibility with the existing codebase
    that expects a build_xp_agent function.
    """
    return XpAgent(
        model_name=model_name,
        db_path=db_path,
        use_gpu=use_gpu,
        checkpointer=checkpointer
    )
