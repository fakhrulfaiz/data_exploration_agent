"""
XpAgent V2 - Simplified experimental agent.

This is a minimal agent implementation following the XpAgent architecture
but using the same integration pattern as MainAgent for streaming compatibility.

Key design principles:
- Uses ExplainableAgentState for streaming compatibility
- Starts with no tools (will be added incrementally)
- Has its own workspace: backend/app/agents/workspace
- Used in experiment_mode

v2.1 Changes:
- Added planning node to generate execution plans
- Added human_feedback node with simple boolean approval (matches XpAgent pattern)
- Graph flow: START -> planner -> human_feedback -> responder -> finalizer -> END
- Uses "xp_plan_approval" interrupt type for frontend compatibility
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Literal
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

from app.agents.state import ExplainableAgentState

logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================

class PlanStep(BaseModel):
    """A single step in the execution plan - matches XpAgent dev blueprint."""
    step_number: int = Field(description="Step number (1-indexed)")
    description: str = Field(description="What this step accomplishes")
    tool_name: Literal["database_exploration_agent", "image_qna_agent", "data_plotting_agent"] = Field(
        description="Which tool to use for this step"
    )
    tool_args_json: str = Field(
        default="{}",
        description="JSON string of arguments to pass to the tool. E.g. '{\"query\": \"Find all paintings\"}'"
    )
    depends_on: List[int] = Field(
        default_factory=list,
        description="Step numbers this step depends on"
    )
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = Field(
        default="pending",
        description="Current status of this step"
    )


class ExecutionPlan(BaseModel):
    """Structured execution plan - matches XpAgent dev blueprint."""
    understanding: str = Field(
        description="Your understanding of what the user wants to achieve"
    )
    minimal_approach: str = Field(
        description="Explain why this is the MINIMUM number of steps needed"
    )
    steps: List[PlanStep] = Field(
        description="MINIMAL list of steps - only include steps that are absolutely necessary",
        default_factory=list
    )
    reasoning: str = Field(
        description="Why this minimal plan will accomplish the user's goal efficiently"
    )


# Database schema context for planning
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


# Tool capabilities for planning
TOOL_CAPABILITIES = {
    "database_exploration_agent": {
        "description": "Queries SQL database for artwork metadata. Can access: title, inception, movement, genre, image_url, img_path.",
        "can_produce_csv": True,
        "requires_csv_input": False
    },
    "image_qna_agent": {
        "description": "Analyzes visual content of images using AI. REQUIRES img_path from database.",
        "can_produce_csv": True,
        "requires_csv_input": False
    },
    "data_plotting_agent": {
        "description": "Creates visualizations from CSV data. Supports: bar, line, scatter, pie charts.",
        "can_produce_csv": False,
        "requires_csv_input": True
    }
}


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DB_PATH = "/home/afiq/fyp/fafa-repo/backend/app/resource/art.db"

# XpAgentV2 has its own workspace
WORKSPACE_PATH = Path("/home/afiq/fyp/fafa-repo/backend/app/agents/workspace")
OUTPUT_PATH = WORKSPACE_PATH / "outputs"
PLOT_PATH = WORKSPACE_PATH / "plot"

# Ensure workspace directories exist
os.makedirs(OUTPUT_PATH, exist_ok=True)
os.makedirs(PLOT_PATH, exist_ok=True)


# ============================================================================
# XP AGENT V2 CLASS
# ============================================================================

class XpAgentV2:
    """
    Simplified experimental agent following XpAgent architecture.
    
    This version starts with no tools and will be extended incrementally.
    Uses ExplainableAgentState for streaming compatibility.
    """
    
    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        db_path: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        checkpointer: Optional[Any] = None,
        use_postgres_checkpointer: bool = True,
        logs_dir: Optional[str] = None
    ):
        self.model_name = model_name
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Initialize LLM
        if llm is not None:
            self.llm = llm
        else:
            self.llm = init_chat_model(model_name)
        
        # No tools for now - will be added incrementally
        self.tools = []
        
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
                    logger.info("XpAgentV2 using PostgresSaver checkpointer")
                else:
                    logger.warning("Checkpointer not initialized, falling back to MemorySaver")
                    self.checkpointer = MemorySaver()
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL checkpointer for XpAgentV2: {e}")
                self.checkpointer = MemorySaver()
        else:
            self.checkpointer = MemorySaver()
        
        # Build the graph
        self.graph = self._create_graph()
        self._save_graph_visualization()
        logger.info("XpAgentV2 initialized successfully")
    
    def _save_graph_visualization(self):
        """Save graph visualization for debugging."""
        try:
            graph_image = self.graph.get_graph().draw_mermaid_png()
            graph_path = os.path.join(self.logs_dir, "xp_agent_v2_graph.png")
            with open(graph_path, "wb") as f:
                f.write(graph_image)
            logger.info(f"XpAgentV2 graph visualization saved to: {graph_path}")
        except Exception as e:
            logger.warning(f"Failed to generate XpAgentV2 graph visualization: {e}")
    
    # ========================================================================
    # GRAPH NODES
    # ========================================================================
    
    def _planner_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Planning node that analyzes the user query and creates an execution plan.
        
        This node follows the XpAgent dev blueprint:
        1. Analyzes the user's query
        2. Generates a structured plan with minimal steps
        3. Sets the plan in state for approval
        """
        query = state.get("query", "")
        messages = state.get("messages", [])
        
        # Extract query from messages if not set
        if not query:
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
        
        logger.info(f"XpAgentV2 planner processing query: {query[:100]}...")
        
        # Build planning prompt following XpAgent dev blueprint
        system_prompt = f"""## Role
You are a Strategic AI Planner for an artwork database analysis system.

## Available Tools
{json.dumps(TOOL_CAPABILITIES, indent=2)}

## Database Schema
{DATABASE_SCHEMA}

## Critical Planning Rules

1. **MINIMUM STEPS PRINCIPLE**: Create the SHORTEST possible plan.
   - If only database info is needed → 1 step (database_exploration_agent)
   - If visual analysis is needed → 2 steps (database to get img_path, then image_qna_agent)
   - Add plotting ONLY if user explicitly asks for visualizations

2. **Tool Selection Rules**:
   - database_exploration_agent: Use for ANY database query (counts, lists, filtering, etc.)
   - image_qna_agent: Use ONLY when you need to analyze visual content of images
   - data_plotting_agent: Use ONLY when user explicitly asks for charts/graphs/plots

3. **Image Analysis Protocol**:
   - ALWAYS get img_path from database FIRST
   - NEVER use image_url for visual analysis
   - Pass img_path list to image_qna_agent

4. **Efficiency**:
   - Don't add steps "just in case"
   - Skip plotting unless explicitly requested

5. **CRITICAL - File Path Rules**:
   - For data_plotting_agent: DO NOT specify file_path in tool_args_json
   - The system will AUTOMATICALLY use the CSV file from the previous step
   - Just specify the "task" (what plot to create)

## Your Task
Create a minimal, efficient plan to answer the user's query.
"""

        user_content = f"**Current Query**: {query}\n\nCreate the MINIMUM number of steps needed to answer this query."
        
        # Get structured plan from LLM
        try:
            planner_llm = self.llm.with_structured_output(ExecutionPlan)
            plan_result = planner_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            plan: ExecutionPlan = plan_result  # type: ignore
            
            logger.info(f"XpAgentV2 generated plan: {plan.understanding}")
            logger.info(f"  Steps: {len(plan.steps)}, Approach: {plan.minimal_approach[:50]}...")
            
            # ===== DEV BLUEPRINT: Build plan_steps (List[PlanStep] as dicts) =====
            # This matches the dev blueprint's MainAgentState.plan_steps
            plan_steps = []
            for step in plan.steps:
                plan_steps.append({
                    "step_number": step.step_number,
                    "description": step.description,
                    "tool_name": step.tool_name,
                    "tool_args_json": step.tool_args_json,
                    "depends_on": step.depends_on,
                    "status": step.status,
                    "result_summary": "",
                    "output_file": None
                })
            
            # ===== DISPLAY FORMAT: Build plan_text for frontend PlanMessage =====
            # PlanMessage expects: **Strategy**: ..., **Step N**: ..., Tool Options: (numbered list)
            plan_text = f"**Strategy**: {plan.understanding} {plan.minimal_approach}\n\n"
            
            for step in plan.steps:
                # Step header (PlanMessage parses **Step N**: title)
                plan_text += f"**Step {step.step_number}**: {step.description}\n"
                
                # Tool Options section (PlanMessage parses "Tool Options:" followed by numbered list)
                plan_text += "Tool Options:\n"
                # Parse tool_args_json for description
                try:
                    args = json.loads(step.tool_args_json) if step.tool_args_json != "{}" else {}
                    args_desc = ", ".join(f"{k}={v}" for k, v in args.items()) if args else "default parameters"
                except:
                    args_desc = step.tool_args_json
                plan_text += f"  1. {step.tool_name}: {args_desc}\n"
                
                # Add dependency info as Requires (PlanMessage parses "Requires:")
                if step.depends_on:
                    deps_str = ", ".join(f"Step {d}" for d in step.depends_on)
                    plan_text += f"Requires: {deps_str}\n"
                
                plan_text += "\n"
            
            # ===== RETURN STATE UPDATE (matches dev blueprint + streaming) =====
            return {
                # === Streaming layer fields ===
                "query": query,
                "plan": plan_text.strip(),  # Display format for PlanMessage
                "steps": plan_steps,  # Legacy field - same as plan_steps for compatibility
                "step_counter": 0,
                "status": "user_feedback",  # Triggers routing to human_feedback node
                "agent_type": "xp_agent_v2",
                
                # === Dev blueprint MainAgentState fields ===
                "original_query": query,
                "plan_steps": plan_steps,  # Structured plan steps (dev blueprint)
                "total_steps": len(plan_steps),
                "current_step_index": 0,
                "completed_steps": 0,
                "step_results": [],
                "tool_context": "",
                "feedback": None,
                "pending_interrupt": False,
                "execution_complete": False,
                "final_answer": None,
                "generated_files": []
            }
            
        except Exception as e:
            logger.error(f"XpAgentV2 planning error: {e}")
            # Fallback: create a simple plan with dev blueprint fields
            return {
                # Streaming layer fields
                "query": query,
                "plan": f"**Strategy**: Answer the query directly.\n\n_Planning error occurred: {str(e)}_",
                "steps": [],
                "step_counter": 0,
                "status": "user_feedback",
                "agent_type": "xp_agent_v2",
                # Dev blueprint fields
                "original_query": query,
                "plan_steps": [],
                "total_steps": 0,
                "current_step_index": 0,
                "completed_steps": 0,
                "step_results": [],
                "tool_context": "",
                "feedback": f"Planning failed: {str(e)}",
                "pending_interrupt": True,
                "execution_complete": False,
                "final_answer": None,
                "generated_files": []
            }
    
    def _interrupt_for_approval_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Interrupt node that pauses execution and waits for user approval.
        
        This node:
        1. Displays the plan to the user
        2. Waits for a simple boolean approval (approve/reject)
        3. Updates state based on user decision
        
        Uses langgraph's interrupt() for human-in-the-loop functionality.
        """
        plan = state.get("plan", "No plan available")
        query = state.get("query", "")
        # Use plan_steps (dev blueprint) if available, fallback to steps
        plan_steps = state.get("plan_steps") or state.get("steps", [])
        
        logger.info("XpAgentV2 interrupt_for_approval: Waiting for user approval...")
        
        # Create interrupt data for the frontend - use xp_plan_approval type
        # This matches XpAgent's pattern and is recognized by handle_xp_approval
        interrupt_data = {
            "type": "xp_plan_approval",
            "message": "Plan created - please approve to execute",
            "plan": plan,
            "query": query,
            "steps": plan_steps,  # Send structured plan_steps
            "options": ["approve", "reject"]
        }
        
        # This will pause execution and wait for user input
        # The user's response will be returned when they resume the graph
        user_response = interrupt(interrupt_data)
        
        logger.info(f"XpAgentV2 received approval response: {user_response}")
        
        # Process user response
        # Handle different response formats (string, bool, dict)
        is_approved = False
        
        if isinstance(user_response, bool):
            is_approved = user_response
        elif isinstance(user_response, str):
            is_approved = user_response.lower() in ("approve", "approved", "yes", "true", "ok")
        elif isinstance(user_response, dict):
            action = user_response.get("action", "")
            is_approved = action.lower() in ("approve", "approved", "yes")
        
        if is_approved:
            logger.info("XpAgentV2 plan approved - proceeding to execution")
            return {
                "status": "approved",
                "human_comment": None,
                "pending_interrupt": False,
                "feedback": None
            }
        else:
            logger.info("XpAgentV2 plan rejected - cancelling execution")
            # Provide a rejection message as the response
            rejection_reason = ""
            if isinstance(user_response, dict):
                rejection_reason = user_response.get("reason", user_response.get("comment", ""))
            elif isinstance(user_response, str) and user_response.lower() not in ("reject", "rejected", "no", "false", "cancel"):
                rejection_reason = user_response
            
            return {
                "status": "cancelled",
                "human_comment": rejection_reason if rejection_reason else "Plan was rejected by user.",
                "assistant_response": f"Plan was rejected. {rejection_reason}".strip(),
                "execution_complete": True,
                "final_answer": f"Plan was rejected by user. {rejection_reason}".strip()
            }
    
    def _responder_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Simple responder node that processes user query and generates a response.
        
        This is a minimal implementation that will be extended with planning
        and tool execution in future versions.
        """
        query = state.get("query", "")
        messages = state.get("messages", [])
        
        logger.info(f"XpAgentV2 responder processing query: {query[:100]}...")
        
        # Build system prompt
        system_prompt = """You are a helpful AI assistant specialized in data exploration and analysis.

Currently, you have no tools available. You can:
1. Answer questions about data analysis concepts
2. Explain how you would approach a data exploration task
3. Provide guidance on what tools would be needed

When tools become available, you will be able to:
- Query databases
- Analyze images
- Create visualizations

For now, respond helpfully to the user's query and explain what you would do if you had the tools.

Be concise and helpful."""

        # Build conversation for LLM
        llm_messages: list = [SystemMessage(content=system_prompt)]
        
        # Add message history (last 10 messages for context)
        for msg in messages[-10:]:
            if isinstance(msg, HumanMessage):
                llm_messages.append(msg)
            elif isinstance(msg, AIMessage):
                llm_messages.append(msg)
        
        # If query is not in messages, add it
        if query and (not messages or messages[-1].content != query):
            llm_messages.append(HumanMessage(content=query))
        
        # Generate response
        try:
            response = self.llm.invoke(llm_messages)
            response_content = response.content
        except Exception as e:
            logger.error(f"XpAgentV2 LLM error: {e}")
            response_content = f"I encountered an error processing your request: {str(e)}"
        
        # Build response message
        response_message = AIMessage(content=response_content)
        
        # Update state with dev blueprint fields
        new_messages = list(messages) + [response_message]
        
        # Mark all steps as completed (mock execution for now)
        plan_steps = state.get("plan_steps") or []
        for step in plan_steps:
            step["status"] = "completed"
        
        return {
            "messages": new_messages,
            "assistant_response": response_content,
            "status": "approved",
            "agent_type": "xp_agent_v2",
            # Dev blueprint fields
            "plan_steps": plan_steps,
            "completed_steps": len(plan_steps),
            "execution_complete": True,
            "final_answer": response_content
        }
    
    def _finalizer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Finalizer node to complete the response.
        
        For now, this just ensures the response is properly formatted.
        """
        assistant_response = state.get("assistant_response", "")
        final_answer = state.get("final_answer") or assistant_response
        
        logger.info("XpAgentV2 finalizer completing response...")
        
        return {
            "status": "approved",
            "response_type": "answer",
            "execution_complete": True,
            "final_answer": final_answer
        }
    
    # ========================================================================
    # ROUTING FUNCTIONS
    # ========================================================================
    
    def _route_after_approval(self, state: ExplainableAgentState) -> Literal["responder", "finalizer"]:
        """
        Route based on the approval status after interrupt.
        
        If approved -> proceed to responder
        If cancelled -> skip to finalizer (with rejection message)
        """
        status = state.get("status", "approved")
        
        if status == "cancelled":
            logger.info("XpAgentV2 routing: Plan cancelled, going to finalizer")
            return "finalizer"
        else:
            logger.info("XpAgentV2 routing: Plan approved, going to responder")
            return "responder"
    
    # ========================================================================
    # GRAPH CONSTRUCTION
    # ========================================================================
    
    def _create_graph(self):
        """
        Create the XpAgentV2 graph with planning and approval flow.
        
        Flow (v2.1):
            START -> planner -> human_feedback -> [conditional]
                                                       |
                                 approved -> responder -> finalizer -> END
                                 cancelled -> finalizer -> END
        
        Note: The node is named 'human_feedback' to match the streaming layer's
        detection logic in streaming_graph.py which checks for 'human_feedback' in state.next
        """
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        # Note: "human_feedback" name is important - streaming layer checks for this
        graph.add_node("planner", self._planner_node)
        graph.add_node("human_feedback", self._interrupt_for_approval_node)
        graph.add_node("responder", self._responder_node)
        graph.add_node("finalizer", self._finalizer_node)
        
        # Set entry point
        graph.set_entry_point("planner")
        
        # Flow: planner -> human_feedback (approval interrupt)
        graph.add_edge("planner", "human_feedback")
        
        # Conditional edge after approval: route based on status
        graph.add_conditional_edges(
            "human_feedback",
            self._route_after_approval,
            {
                "responder": "responder",
                "finalizer": "finalizer"
            }
        )
        
        # Flow: responder -> finalizer -> END
        graph.add_edge("responder", "finalizer")
        graph.add_edge("finalizer", END)
        
        # Compile with checkpointer (required for interrupt to work)
        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        else:
            # interrupt() requires a checkpointer, so always use one
            return graph.compile(checkpointer=MemorySaver())
