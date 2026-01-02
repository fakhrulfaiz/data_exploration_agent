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
    status: Literal["approved", "feedback", "cancelled"]
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
    continue_execution: bool = False  # Flag to continue to next step
    
    # ===== JOINER FIELDS =====
    joiner_decision: Optional[Literal["finish", "replan", "continue"]] = None
    
    # ===== ERROR HANDLING FIELDS =====
    error_info: Optional[Dict[str, Any]] = None  # Error details (error_message, error_type, tool_name, tool_input)
    error_explanation: Optional[Dict[str, Any]] = None  # User-friendly error explanation
    require_tool_approval: Optional[bool] = False  # Whether tool-level approval is enabled


