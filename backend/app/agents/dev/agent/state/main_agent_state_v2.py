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
    # IMPORTANT: intent describes WHAT to do in NATURAL LANGUAGE
    # The executor will resolve actual file paths from accumulated context at runtime
    # For consecutive tasks, use markdown list format
    intent: str = Field(
        default="",
        description="""The task/query to send to the subagent in NATURAL LANGUAGE.
        
For SIMPLE tasks: Single sentence describing what to do.
Example: "Find the oldest painting in the database and include its img_path"

For CONSECUTIVE tasks: Use markdown list format.
Example:
"Please complete the following tasks:
- Query all Renaissance paintings
- Count how many exist per genre
- Include img_path for visual analysis
- Order by inception date"

NEVER include:
- Specific file paths like 'images/img_1.jpg'
- Hardcoded CSV paths like '/path/to/file.csv'
- Raw SQL queries (let the subagent handle SQL)

The subagents are intelligent and will understand natural language instructions."""
    )
    expected_output: str = Field(
        default="",
        description="What type of output this step should produce (e.g., 'CSV with painting metadata', 'Image analysis results', 'Bar chart visualization')"
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
        description="""INTELLIGENT SQL Database Exploration Subagent.

This is a SMART AGENT (not a simple tool) that can:
- Understand natural language queries and translate them to SQL
- Execute MULTIPLE database queries autonomously to gather complete data
- Handle complex multi-step database explorations (e.g., "find paintings, count by genre, then filter top 5")
- Automatically export results to CSV for downstream processing

Database Schema: paintings table with columns (title, inception, movement, genre, image_url, img_path)

CRITICAL: When visual analysis is needed downstream, instruct the agent to include img_path in results.

CANNOT: Analyze image visual content - only database metadata.""",
        required_args=["query"],
        optional_args=[],
        can_produce_csv=True,
        requires_csv_input=False,
        example_args_json='{"query": "Find all Renaissance paintings and include their img_path for visual analysis"}'
    ),
    "image_qna_agent": ToolCapability(
        name="image_qna_agent",
        description="""INTELLIGENT Image Analysis Subagent with GPU-accelerated BLIP VQA.

This is a SMART AGENT (not a simple tool) that can:
- Process MULTIPLE images in a single invocation
- Understand complex visual queries and analyze each image accordingly
- Handle batch operations (e.g., "analyze all images for subjects, then count people in each")
- Automatically synthesize results and export to CSV

Capabilities: Detect colors, subjects, objects, people count, art style, composition, mood, etc.

REQUIRES: img_path values from database_exploration_agent (format: 'images/img_N.jpg')
These are LOCAL file paths, NOT URLs. The img_path column from database must be queried first.""",
        required_args=["query", "img_path"],
        optional_args=[],
        can_produce_csv=True,
        requires_csv_input=False,
        example_args_json='{"query": "For each image: 1. Identify main subjects 2. Count number of people 3. Describe the color palette"}'
    ),
    "data_plotting_agent": ToolCapability(
        name="data_plotting_agent",
        description="""INTELLIGENT Data Visualization Subagent.

This is a SMART AGENT (not a simple tool) that can:
- Read and understand CSV data structure automatically
- Generate multiple plot types in a single invocation
- Choose appropriate visualizations based on data characteristics
- Handle complex requests (e.g., "create a bar chart for categories and a pie chart for distribution")

Supported: bar, line, scatter, pie, histogram charts with matplotlib

IMPORTANT: The CSV file path is automatically resolved from previous step outputs.
Just describe what visualizations you want.""",
        required_args=["task"],
        optional_args=[],
        can_produce_csv=False,
        requires_csv_input=True,
        example_args_json='{"task": "Create: 1. Bar chart showing count by genre 2. Pie chart showing movement distribution"}'
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
    - Conversation context for multi-turn memory
    """
    
    # Original query tracking
    original_query: str = Field(
        default="",
        description="The original user query/task"
    )
    
    # Conversation context - accumulates across turns for memory
    conversation_context: str = Field(
        default="",
        description="Accumulated conversation context (previous queries + answer summaries)"
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
    
    # Feedback from subagents - triggers interrupt when set
    feedback: Optional[str] = Field(
        default=None,
        description="Feedback from failed step or subagent. When set with pending_interrupt=True, triggers replan flow."
    )
    # Replan feedback - passed to planner after user approves replan
    replan_feedback: Optional[str] = Field(
        default=None,
        description="Feedback to show to planner during replan. Set when user approves replan, cleared after planner uses it."
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
    
    # Step resolver decision - dynamically resolved args for current step
    current_step_decision: Optional["StepExecutionDecision"] = Field(
        default=None,
        description="The resolved execution decision for the current step"
    )
    
    # ============================================================================
    # CROSS-STEP DATA PASSING (Structured, not via LLM messages)
    # ============================================================================
    # These fields pass structured data between steps without token limits
    
    extracted_img_paths: List[str] = Field(
        default_factory=list,
        description="Image paths extracted from data exploration, passed directly to image_qna (bypasses LLM token limits)"
    )
    
    extracted_csv_path: Optional[str] = Field(
        default=None,
        description="CSV file path from previous step, passed directly to plotting agent"
    )


# ============================================================================
# PLANNER OUTPUT SCHEMA
# ============================================================================

class ExecutionPlan(BaseModel):
    """Structured output from the planner."""
    
    understanding: str = Field(
        ...,
        description="Your understanding of what the user wants to achieve, including all sub-goals"
    )
    
    complexity_analysis: str = Field(
        ...,
        description="Analyze the complexity: Is this a simple single-step query, or a complex multi-step task? Complex tasks may need 5-15 steps. Consider: multiple data sources, multiple analyses, multiple visualizations, iterative refinement, etc."
    )
    
    steps: List[PlanStep] = Field(
        ...,
        description="Complete list of steps needed. Simple tasks may need 1-3 steps, complex tasks may need 5-15+ steps. DO NOT artificially limit the number of steps."
    )
    
    reasoning: str = Field(
        ...,
        description="Why this plan will accomplish ALL aspects of the user's goal"
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
    """What the executor decides to do for a step - with DYNAMICALLY resolved arguments."""
    
    action: Literal["execute", "skip", "replan"] = Field(
        ...,
        description="What action to take"
    )
    
    # IMPORTANT: These are the ACTUAL resolved arguments based on accumulated context
    # NOT the hallucinated args from the plan
    resolved_query: Optional[str] = Field(
        default=None,
        description="The actual query/task to execute (for database_exploration_agent or image_qna_agent)"
    )
    
    resolved_img_paths: Optional[List[str]] = Field(
        default=None,
        description="Actual image paths extracted from previous step results (for image_qna_agent). Extract from accumulated context, NOT from the plan."
    )
    
    resolved_csv_path: Optional[str] = Field(
        default=None,
        description="Actual CSV file path from previous step results (for data_plotting_agent). Extract from accumulated context, NOT from the plan."
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
        description="Explain how you resolved the actual arguments from the accumulated context"
    )


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
