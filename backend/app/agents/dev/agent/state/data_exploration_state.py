from typing import Annotated, Any, Dict, List
from pydantic import BaseModel, Field, field_validator

from langgraph.graph import MessagesState

# Query Args for sql execution tool query
class QueryArgs(BaseModel):
    """Args required to run a query"""
    query: str = Field(..., description="The query to run")
    columns: list[str] = Field(..., description="The columns or headers created/ return by the given query")

class ToolResult(BaseModel):
    """Structured Model to populate tool results"""
    tool_call_id: str = Field(..., description="The unique ID of the tool call")
    name: str = Field(..., description="The name of the tool")
    query: str = Field(..., description="The query to run")
    columns: List[str] = Field(default_factory=list)
    result: Any

    @field_validator("tool_call_id", mode="before")
    @classmethod
    def coerce_tool_call_id(cls, v):
        return str(v)

def append_tool_results(existing: List[ToolResult], new: List[ToolResult]) -> List[ToolResult]:
    """Appends new results to the existing list instead of overwriting."""
    return (existing or []) + new

# Custom State for data exploration
class DataExplorationState(MessagesState):
    import_tool_results: Annotated[List[ToolResult], append_tool_results]

# Make state to store query result

# Custom Output state for data exploration
class DataExplorationOutput(BaseModel):
    """Output state for data exploration"""
    query: str = Field(..., description="The query to run")
    final_tool_result: str = Field(..., description="The final tool result")
    error: bool = Field(..., description="Whether there is an error")
    error_message: str = Field(..., description="The error message")


