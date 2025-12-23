"""Schemas for dynamic tool selection in planner node."""

from pydantic import BaseModel, Field
from typing import List, Optional


class ToolOption(BaseModel):
    tool_name: str = Field(description="Exact name of the tool")
    use_case: str = Field(description="When to use this tool for this step")
    priority: int = Field(
        description="Priority level (1=highest, 5=lowest)",
        ge=1,
        le=5
    )


class PlanStep(BaseModel):
    step_number: int = Field(description="Sequential step number")
    goal: str = Field(description="What this step aims to accomplish")
    tool_options: List[ToolOption] = Field(
        description="All tools that could accomplish this goal"
    )
    context_requirements: Optional[str] = Field(
        default=None,
        description="What context/data this step needs from previous steps"
    )


class DynamicPlan(BaseModel):
    query: str = Field(description="Original user query")
    overall_strategy: str = Field(
        description="High-level explanation of the approach"
    )
    steps: List[PlanStep] = Field(description="Ordered list of execution steps")
