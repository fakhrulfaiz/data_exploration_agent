# data_exploration_state_v2.py - Enhanced state management for data exploration subagent

"""
Key Improvements:
1. Track original task for context
2. Structured query history with QueryRecord
3. Schema information cached in state
4. Clear separation between exploration and final results
5. Proper reducers for accumulating history
"""

from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from langgraph.graph import MessagesState
import operator


# ============================================================================
# STRUCTURED DATA MODELS
# ============================================================================

class QueryRecord(BaseModel):
    """A single query execution record for tracking."""
    tool_call_id: str = Field(..., description="Unique ID of the tool call")
    query: str = Field(..., description="The SQL query that was executed")
    columns: List[str] = Field(default_factory=list, description="Column names in the result")
    result: Any = Field(default=None, description="Raw query result")
    row_count: int = Field(default=0, description="Number of rows returned")
    success: bool = Field(default=True, description="Whether the query succeeded")
    error_message: str = Field(default="", description="Error message if failed")
    
    @field_validator("tool_call_id", mode="before")
    @classmethod
    def coerce_tool_call_id(cls, v):
        return str(v)
    
    def to_summary(self) -> str:
        """Create a summary string for context."""
        if self.success:
            return f"Query: {self.query[:100]}... | Columns: {self.columns} | Rows: {self.row_count}"
        else:
            return f"Query: {self.query[:100]}... | ERROR: {self.error_message}"


class SchemaInfo(BaseModel):
    """Cached schema information."""
    tables: List[str] = Field(default_factory=list, description="Available table names")
    schema_text: str = Field(default="", description="Full schema description")


# Query Args for sql execution tool query (kept for tool compatibility)
class QueryArgs(BaseModel):
    """Args required to run a query"""
    query: str = Field(..., description="The query to run")
    columns: list[str] = Field(..., description="The columns or headers created/returned by the given query")


# ============================================================================
# CUSTOM REDUCERS
# ============================================================================

def merge_query_records(left: List[QueryRecord], right: List[QueryRecord]) -> List[QueryRecord]:
    """Appends new query records to existing list."""
    return (left or []) + (right or [])


def merge_lists(left: List[str], right: List[str]) -> List[str]:
    """Merge string lists, avoiding duplicates."""
    existing = set(left or [])
    result = list(left or [])
    for item in (right or []):
        if item not in existing:
            result.append(item)
            existing.add(item)
    return result


# ============================================================================
# ENHANCED STATE DEFINITION
# ============================================================================

class DataExplorationState(MessagesState):
    """
    Enhanced state that properly tracks:
    - Original task for context
    - Database schema information
    - All queries executed with results
    - Completion status for evaluator
    """
    
    # Core task tracking
    original_task: str = Field(
        default="", 
        description="The original task/query this subagent was asked to accomplish"
    )
    
    # Schema information (cached after initial fetch)
    schema_info: Optional[SchemaInfo] = Field(
        default=None,
        description="Cached database schema information"
    )
    
    # Query history (structured for better tracking)
    query_history: Annotated[List[QueryRecord], merge_query_records] = Field(
        default_factory=list,
        description="History of all SQL queries executed"
    )
    
    # Tables that have been queried
    tables_queried: Annotated[List[str], merge_lists] = Field(
        default_factory=list,
        description="List of tables that have been queried"
    )
    
    # Final result tracking
    final_result: Optional[str] = Field(
        default=None,
        description="The final aggregated result ready for CSV export"
    )
    final_columns: List[str] = Field(
        default_factory=list,
        description="Column names for the final result"
    )
    
    # Status tracking
    exploration_complete: bool = Field(
        default=False, 
        description="Whether data exploration is complete"
    )
    ready_for_export: bool = Field(
        default=False,
        description="Whether data is ready for CSV export"
    )
    
    # Result summary for sharing with other agents (markdown format)
    result_summary: str = Field(
        default="",
        description="Accumulated markdown summary of query results for sharing with other agents"
    )
    
    # Error tracking
    error_occurred: bool = Field(default=False, description="Whether an error occurred")
    error_message: str = Field(default="", description="Error message if any")


# ============================================================================
# EVALUATOR OUTPUT SCHEMA
# ============================================================================

class DataExplorationOutput(BaseModel):
    """Structured output for evaluator to assess task completion."""
    
    # Task assessment
    task: str = Field(..., description="The original task that was requested")
    task_complete: bool = Field(
        ..., 
        description="Whether the task has been fully accomplished with sufficient data"
    )
    
    # Data quality assessment
    data_quality_score: int = Field(
        ...,
        ge=1, le=5,
        description="Quality score 1-5: 1=unusable, 3=acceptable, 5=excellent"
    )
    
    # Result summary
    final_query: str = Field(
        default="",
        description="The final SQL query that produces the desired result"
    )
    final_result_summary: str = Field(
        default="",
        description="Brief summary of what the final result contains"
    )
    
    # CSV preparation
    csv_columns: List[str] = Field(
        default_factory=list,
        description="Column headers for the CSV file"
    )
    csv_filename: str = Field(
        default="query_result.csv",
        description="Suggested filename for the CSV export"
    )
    storing_instruction: str = Field(
        default="",
        description="Instructions for how to format and store the data"
    )
    
    # Missing data tracking
    missing_data: List[str] = Field(
        default_factory=list,
        description="List of data that couldn't be found or needs additional queries"
    )
    
    # Error handling
    error: bool = Field(default=False, description="Whether there's an unrecoverable error")
    error_message: str = Field(default="", description="Error details")
    
    # Reasoning
    reasoning: str = Field(..., description="Explanation of the evaluation decision")


# ============================================================================
# LEGACY COMPATIBILITY (for existing code)
# ============================================================================

class ToolResult(BaseModel):
    """Legacy ToolResult for backward compatibility."""
    tool_call_id: str = Field(..., description="The unique ID of the tool call")
    name: str = Field(..., description="The name of the tool")
    query: str = Field(..., description="The query to run")
    columns: List[str] = Field(default_factory=list)
    result: Any

    @field_validator("tool_call_id", mode="before")
    @classmethod
    def coerce_tool_call_id(cls, v):
        return str(v)
    
    def to_query_record(self) -> QueryRecord:
        """Convert to new QueryRecord format."""
        return QueryRecord(
            tool_call_id=self.tool_call_id,
            query=self.query,
            columns=self.columns,
            result=self.result,
            row_count=len(self.result) if isinstance(self.result, list) else 0,
            success=True
        )


def append_tool_results(existing: List[ToolResult], new: List[ToolResult]) -> List[ToolResult]:
    """Legacy reducer for backward compatibility."""
    return (existing or []) + new
