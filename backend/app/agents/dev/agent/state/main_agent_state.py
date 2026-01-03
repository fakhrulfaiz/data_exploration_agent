from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Annotated
from langgraph.graph import MessagesState
import operator

from .data_exploration_state import DataExplorationState


# Main agent state
class MainAgentState(MessagesState):
    """Main agent state."""
    query: str = None
    base_plan: List[str] = []
    current_step: int = 0
    step_history: List[str] = []
    replan_count: int = 0
    feedback: str | None = None
    replan_approval: bool = False

    # Image analysis history
    image_analysis_history: Annotated[list[str], operator.add]

    # from data_exploration_subagent, can include by appending it in a static format in tool message then parse it into this state.        
    tool_results: DataExplorationState