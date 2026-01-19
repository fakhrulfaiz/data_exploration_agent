"""State definition for simple test agent."""

from typing import Annotated, List, Dict, Any, Optional, Literal, TypedDict
from langgraph.graph.message import MessagesState
from langchain_core.messages import BaseMessage
from app.schemas.chat import DataContext
import operator

# Import for type annotation - using string literal to avoid circular import issues
try:
    from app.agents.schemas.tool_selection import DynamicPlan
except ImportError:
    DynamicPlan = None  # Will use string annotation





class ExplainableAgentState(MessagesState):
    """State for the explainable agent - simplified version."""
    # ===== EXISTING FIELDS =====
    query: str
    plan: str
    steps: List[Dict[str, Any]]
    step_counter: int
    human_comment: Optional[str]
    status: Literal["approved", "feedback", "cancelled", "retry"]
    assistant_response: str
    use_planning: bool = True
    use_explainer: bool = True
    response_type: Optional[Literal["answer", "replan", "cancel", "continue", "plan"]] = None
    agent_type: str = "data_exploration_tool"
    routing_reason: str = ""
    visualizations: Optional[List[Dict[str, Any]]] = []
    data_context: Optional[DataContext] = None
    user_id: Optional[str] = None  # User ID for preference fetching
    
    # ===== DYNAMIC TOOL SELECTION FIELDS =====
    dynamic_plan: Optional[Any] = None  # DynamicPlan object from tool_selection schema
    current_step_index: int = 0  # Track which step is currently executing
    
    # ===== XP AGENT V2 FIELDS (from dev blueprint MainAgentState) =====
    # These fields are used by XpAgentV2 to match the dev blueprint exactly
    plan_steps: Optional[List[Dict[str, Any]]] = None  # Structured plan steps (PlanStep objects as dicts)
    step_results: Optional[List[Dict[str, Any]]] = None  # Results from completed steps (StepResult objects as dicts)
    tool_context: Optional[str] = None  # Accumulated markdown context from tool executions
    total_steps: int = 0  # Total number of steps in current plan
    completed_steps: int = 0  # Number of successfully completed steps
    original_query: Optional[str] = None  # Original user query (separate from 'query' which may change)
    conversation_context: Optional[str] = None  # Accumulated conversation context for multi-turn memory
    final_answer: Optional[str] = None  # The aggregated final answer to return to user
    execution_complete: bool = False  # Whether execution is complete
    generated_files: Optional[List[str]] = None  # List of files generated during execution
    pending_interrupt: bool = False  # Whether there's a pending interrupt
    
    # ===== REPLAN TRACKING FIELDS =====
    replan_count: int = 0  # Number of times replanning has occurred
    max_replans: int = 3  # Maximum allowed replans before forcing aggregation
    
    # ===== ERROR HANDLING FIELDS =====
    error_info: Optional[Dict[str, Any]] = None  # Error details (error_message, error_type, tool_name, tool_input) - Used by error_explainer_node
    error_explanation: Optional[Dict[str, Any]] = None  # User-friendly error explanation - Used by error_explainer_node

    feedback: Optional[str] = None  # Feedback message when tool errors occur (triggers interrupt)
    error_details: Optional[List[Dict[str, Any]]] = []  # Detailed list of tool errors with tool_name, error_message, etc.


