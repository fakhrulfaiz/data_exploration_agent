# data_plotting_state.py - State management for data plotting subagent

"""
Key Features:
1. Track files to plot and their content
2. Maintain plot history and generated outputs
3. Aggregate results and compare to original intent
4. Support context sharing with main agent via result_summary
"""

from typing import Annotated, Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
import operator


# ============================================================================
# STRUCTURED RECORDS
# ============================================================================

class PlotRecord(BaseModel):
    """Record of a single plot attempt."""
    plot_type: str = Field(default="", description="Type of plot (bar, line, scatter, pie, etc.)")
    file_path: str = Field(default="", description="Source CSV file path")
    output_path: str = Field(default="", description="Generated plot file path")
    description: str = Field(default="", description="What this plot shows")
    success: bool = Field(default=False, description="Whether plot was generated successfully")
    error_message: str = Field(default="", description="Error message if failed")


class FileInfo(BaseModel):
    """Information about a file to be plotted."""
    file_path: str = Field(default="", description="Path to the CSV file")
    file_content_preview: str = Field(default="", description="Preview of file content (first few rows)")
    columns: List[str] = Field(default_factory=list, description="Column names in the file")
    row_count: int = Field(default=0, description="Number of rows in the file")


# ============================================================================
# CUSTOM REDUCERS
# ============================================================================

def merge_plot_records(left: List[PlotRecord], right: List[PlotRecord]) -> List[PlotRecord]:
    """Append new plot records to existing list."""
    return (left or []) + (right or [])


def merge_file_list(left: List[str], right: List[str]) -> List[str]:
    """Merge file lists, avoiding duplicates."""
    existing = set(left or [])
    result = list(left or [])
    for item in (right or []):
        if item not in existing:
            result.append(item)
            existing.add(item)
    return result


# ============================================================================
# PLOTTING STATE
# ============================================================================

class DataPlottingState(MessagesState):
    """
    Enhanced state for data plotting subagent with:
    - Original task tracking from main agent
    - File information for plotting
    - Plot history and aggregation
    - Context sharing via result_summary
    """
    
    # Task tracking from main agent
    original_task: str = Field(
        default="",
        description="The original query/task from the main agent"
    )
    
    # File information
    file_info: Optional[FileInfo] = Field(
        default=None,
        description="Information about the primary file to plot"
    )
    
    files_to_plot: Annotated[List[str], merge_file_list] = Field(
        default_factory=list,
        description="List of CSV file paths to create plots from"
    )
    
    files_plotted: Annotated[List[str], merge_file_list] = Field(
        default_factory=list,
        description="List of files that have been successfully plotted"
    )
    
    # Plot tracking
    plot_records: Annotated[List[PlotRecord], merge_plot_records] = Field(
        default_factory=list,
        description="History of all plot attempts"
    )
    
    plots_generated: Annotated[List[str], merge_file_list] = Field(
        default_factory=list,
        description="List of successfully generated plot file paths"
    )
    
    # Completion tracking
    tools_complete: bool = Field(
        default=False,
        description="Whether all required plots have been generated"
    )
    
    # Error tracking
    error_occurred: bool = Field(
        default=False,
        description="Whether an error occurred during plotting"
    )
    
    error_message: str = Field(
        default="",
        description="Error message if something went wrong"
    )
    
    # Context sharing with main agent
    result_summary: str = Field(
        default="",
        description="Accumulated markdown summary of plotting results for sharing with main agent"
    )


# ============================================================================
# EVALUATOR OUTPUT
# ============================================================================

class PlottingEvaluatorOutput(BaseModel):
    """Structured output from the plotting evaluator."""
    
    task: str = Field(
        ...,
        description="The original plotting task"
    )
    
    task_complete: bool = Field(
        ...,
        description="Whether all required plots have been generated"
    )
    
    plots_summary: str = Field(
        default="",
        description="Summary of what plots were created"
    )
    
    missing_plots: List[str] = Field(
        default_factory=list,
        description="List of plots that still need to be created"
    )
    
    quality_score: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Quality score from 1-5"
    )
    
    error: bool = Field(
        default=False,
        description="Whether an error occurred"
    )
    
    error_message: str = Field(
        default="",
        description="Error details if any"
    )
    
    reasoning: str = Field(
        default="",
        description="Explanation of the evaluation"
    )
