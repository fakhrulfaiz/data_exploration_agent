# main_agent_state_v2.py - Enhanced state management for main agent/supervisor

"""
Key Improvements:
1. Structured PlanStep with tool validation
2. Step result tracking for context accumulation
3. Proper completion detection
4. Subagent result integration
"""

from typing import Annotated, Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from langgraph.graph import MessagesState
import operator
import json


# ============================================================================
# STRUCTURED PLAN STEP
# ============================================================================

class PlanStep(BaseModel):
    """A single step in the execution plan."""
    step_number: int = Field(..., description="Step number (1-indexed)")
    description: str = Field(..., description="What this step accomplishes")
    tool_name: Literal["database_exploration_agent", "image_qna_agent", "data_plotting_agent"] = Field(
        ..., 
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
    result_summary: str = Field(
        default="",
        description="Summary of the step's result"
    )
    output_file: Optional[str] = Field(
        default=None,
        description="Path to output file if step produces one"
    )
    
    # Note: Using a method instead of @property to avoid Pydantic including it in JSON schema
    # which causes OpenAI structured output to fail with additionalProperties error
    def get_tool_args(self) -> Dict[str, Any]:
        """Parse tool_args_json and return as dict."""
        try:
            return json.loads(self.tool_args_json)
        except json.JSONDecodeError:
            return {}
    
    def to_prompt_string(self) -> str:
        """Format step for prompt context."""
        status_icon = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
            "failed": "❌",
            "skipped": "⏭️"
        }
        return f"{status_icon[self.status]} Step {self.step_number}: {self.description} (tool: {self.tool_name})"


class StepResult(BaseModel):
    """Result from executing a step."""
    step_number: int = Field(..., description="Which step this result is for")
    success: bool = Field(..., description="Whether the step succeeded")
    result_content: str = Field(default="", description="The actual result content")
    output_file: Optional[str] = Field(default=None, description="Output file path if any")
    error_message: str = Field(default="", description="Error message if failed")
    

# ============================================================================
# TOOL CONTEXT - Simple string accumulator for sharing results between tools
# ============================================================================

def merge_tool_context(left: str, right: str) -> str:
    """Append new context to existing context."""
    if not right:
        return left or ""
    if not left:
        return right
    return f"{left}\n\n---\n\n{right}"
    

# ============================================================================
# TOOL CAPABILITY DEFINITIONS
# ============================================================================

class ToolCapability(BaseModel):
    """Defines what a tool can and cannot do."""
    name: str
    description: str
    required_args: List[str]
    optional_args: List[str]
    can_produce_csv: bool
    requires_csv_input: bool
    example_args_json: str  # JSON string to avoid OpenAI additionalProperties issue


TOOL_CAPABILITIES = {
    "database_exploration_agent": ToolCapability(
        name="database_exploration_agent",
        description="Queries SQL database for artwork metadata. Can access: title, inception, movement, genre, image_url, img_path. CANNOT analyze image content. IMPORTANT: When visual analysis is needed, ALWAYS include img_path column in your query to get local image paths.",
        required_args=["query"],
        optional_args=[],
        can_produce_csv=True,
        requires_csv_input=False,
        example_args_json='{"query": "SELECT title, inception, img_path FROM paintings WHERE movement = \"Renaissance\" LIMIT 10"}'
    ),
    "image_qna_agent": ToolCapability(
        name="image_qna_agent",
        description="Analyzes visual content of images using BLIP VQA. Can describe: colors, subjects, objects, people, style, composition. REQUIRES img_path values from the database (e.g., 'images/img_0.jpg'). These are LOCAL paths, not URLs.",
        required_args=["query", "img_path"],
        optional_args=[],
        can_produce_csv=True,
        requires_csv_input=False,
        example_args_json='{"query": "Count the number of people visible in this image", "img_path": ["images/img_0.jpg", "images/img_1.jpg"]}'
    ),
    "data_plotting_agent": ToolCapability(
        name="data_plotting_agent",
        description="Creates visualizations from CSV data. Supports: bar, line, scatter, pie charts.",
        required_args=["task", "file_path"],
        optional_args=[],
        can_produce_csv=False,
        requires_csv_input=True,
        example_args_json='{"task": "Create a bar chart showing painting counts by genre", "file_path": "workspace/outputs/genre_counts.csv"}'
    )
}


# ============================================================================
# CUSTOM REDUCERS
# ============================================================================

def merge_plan_steps(left: List[PlanStep], right: List[PlanStep]) -> List[PlanStep]:
    """Replace plan steps entirely when new plan is created."""
    if not right:
        return left or []
    return right


def merge_step_results(left: List[StepResult], right: List[StepResult]) -> List[StepResult]:
    """Append new step results."""
    return (left or []) + (right or [])


# ============================================================================
# ENHANCED MAIN AGENT STATE
# ============================================================================

class MainAgentState(MessagesState):
    """
    Enhanced state for main agent/supervisor with:
    - Structured plan tracking
    - Step result accumulation
    - Proper completion detection
    - Subagent feedback integration
    """
    
    # Original query tracking
    original_query: str = Field(
        default="",
        description="The original user query/task"
    )
    
    # Structured plan
    plan_steps: Annotated[List[PlanStep], merge_plan_steps] = Field(
        default_factory=list,
        description="Structured execution plan"
    )
    
    # Step execution tracking
    current_step_index: int = Field(
        default=0,
        description="Index of current step being executed (0-indexed)"
    )
    step_results: Annotated[List[StepResult], merge_step_results] = Field(
        default_factory=list,
        description="Results from completed steps"
    )
    
    # Tool context - accumulated markdown summaries from tools for downstream use
    tool_context: Annotated[str, merge_tool_context] = Field(
        default="",
        description="Accumulated markdown context from previous tool executions"
    )
    
    # Plan metadata
    total_steps: int = Field(
        default=0,
        description="Total number of steps in current plan"
    )
    completed_steps: int = Field(
        default=0,
        description="Number of successfully completed steps"
    )
    
    # Replan tracking
    replan_count: int = Field(default=0, description="Number of times plan was revised")
    max_replans: int = Field(default=3, description="Maximum allowed replans")
    
    # Feedback from subagents
    feedback: Optional[str] = Field(
        default=None,
        description="Feedback from failed step or subagent"
    )
    pending_interrupt: bool = Field(
        default=False,
        description="Whether there's a pending interrupt for replan"
    )
    
    # Final result
    final_answer: Optional[str] = Field(
        default=None,
        description="The aggregated final answer to return to user"
    )
    execution_complete: bool = Field(
        default=False,
        description="Whether execution is complete"
    )
    
    # Output tracking
    generated_files: List[str] = Field(
        default_factory=list,
        description="List of files generated during execution"
    )


# ============================================================================
# PLANNER OUTPUT SCHEMA
# ============================================================================

class ExecutionPlan(BaseModel):
    """Structured output from the planner."""
    
    understanding: str = Field(
        ...,
        description="Your understanding of what the user wants to achieve"
    )
    
    minimal_approach: str = Field(
        ...,
        description="Explain why this is the MINIMUM number of steps needed. What tools are NOT needed and why?"
    )
    
    steps: List[PlanStep] = Field(
        ...,
        description="MINIMAL list of steps - only include steps that are absolutely necessary"
    )
    
    reasoning: str = Field(
        ...,
        description="Why this minimal plan will accomplish the user's goal efficiently"
    )
    
    potential_issues: List[str] = Field(
        default_factory=list,
        description="Potential issues or limitations with this plan"
    )
    
    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: List[PlanStep]) -> List[PlanStep]:
        """Ensure steps are properly numbered and have valid dependencies."""
        for i, step in enumerate(steps):
            step.step_number = i + 1
            # Validate dependencies
            for dep in step.depends_on:
                if dep >= step.step_number:
                    raise ValueError(f"Step {step.step_number} cannot depend on step {dep}")
        return steps


# ============================================================================
# STEP EXECUTOR OUTPUT SCHEMA
# ============================================================================

class StepExecutionDecision(BaseModel):
    """What the executor decides to do for a step."""
    
    action: Literal["execute", "skip", "replan"] = Field(
        ...,
        description="What action to take"
    )
    
    tool_call_args_json: Optional[str] = Field(
        default=None,
        description="JSON string of arguments to pass to the tool if executing. E.g. '{\"query\": \"Find paintings\"}'"
    )
    
    skip_reason: str = Field(
        default="",
        description="Reason for skipping if action is skip"
    )
    
    replan_reason: str = Field(
        default="",
        description="Reason for replanning if action is replan"
    )
    
    reasoning: str = Field(
        ...,
        description="Reasoning behind the decision"
    )
    
    # Note: Using a method instead of @property to avoid Pydantic including it in JSON schema
    # which causes OpenAI structured output to fail with additionalProperties error
    def get_tool_call_args(self) -> Optional[Dict[str, Any]]:
        """Parse tool_call_args_json and return as dict."""
        if self.tool_call_args_json is None:
            return None
        try:
            return json.loads(self.tool_call_args_json)
        except json.JSONDecodeError:
            return {}


# ============================================================================
# AGGREGATOR OUTPUT SCHEMA
# ============================================================================

class FinalAnswer(BaseModel):
    """Structured final answer to return to user."""
    
    summary: str = Field(
        ...,
        description="Brief summary of what was accomplished"
    )
    
    detailed_answer: str = Field(
        ...,
        description="Detailed answer to the user's original query"
    )
    
    generated_files: List[str] = Field(
        default_factory=list,
        description="List of files generated during execution"
    )
    
    limitations: str = Field(
        default="",
        description="Any limitations or caveats about the answer"
    )
