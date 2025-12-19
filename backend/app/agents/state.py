"""State definition for simple test agent."""

from typing import Annotated, List, Dict, Any, Optional, Literal, TypedDict
from langgraph.graph.message import MessagesState
from langchain_core.messages import BaseMessage
from app.schemas.chat import DataContext
import operator





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
    response_type: Optional[Literal["answer", "replan", "cancel"]] = None
    agent_type: str = "data_exploration_agent"
    routing_reason: str = ""
    visualizations: Optional[List[Dict[str, Any]]] = []
    data_context: Optional[DataContext] = None
    
    
    # ===== AGENT-BASED PARALLEL EXECUTION FIELDS =====
    task_groups: Optional[List[List[str]]] = []  # Sequential tool groups (e.g., [["text2SQL", "sql_db_to_df"]])
    current_group_index: Optional[int] = 0  # Current group being executed
    current_group_tools: Optional[List[str]] = []  # Tools for current group
    group_context: Optional[List[BaseMessage]] = []  # Context for current group (tool messages)
    group_results: Optional[Dict[int, Any]] = {}  # Results from each group
    continue_group: Optional[bool] = False  # Flag to continue current group (for error recovery)
    execution_mode: Optional[Literal["sequential", "parallel"]] = "parallel"  # Execution strategy
    joiner_decision: Optional[Literal["finish", "replan"]] = None  # Joiner's decision
    
    # ===== ERROR HANDLING FIELDS =====
    error_info: Optional[Dict[str, Any]] = None  # Error details (error_message, error_type, tool_name, tool_input)
    error_explanation: Optional[Dict[str, Any]] = None  # User-friendly error explanation
    require_tool_approval: Optional[bool] = False  # Whether tool-level approval is enabled

