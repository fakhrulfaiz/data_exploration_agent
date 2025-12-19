"""Pydantic schemas for graph execution, explorer, and visualization endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

from .base import BaseResponse


# ==================== Enums ====================

class ExecutionStatus(str, Enum):
    """Graph execution status"""
    RUNNING = "running"
    USER_FEEDBACK = "user_feedback"
    FINISHED = "finished"
    ERROR = "error"
    PENDING = "pending"


class ApprovalStatus(str, Enum):
    """User approval status"""
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    UNKNOWN = "unknown"


# ==================== Graph Execution Schemas ====================

class StartGraphRequest(BaseModel):
    """Request to start graph execution"""
    human_request: str = Field(..., description="User's query or request")
    thread_id: Optional[str] = Field(None, description="Thread ID (auto-generated if not provided)")
    use_planning: bool = Field(True, description="Enable planning phase")
    use_explainer: bool = Field(True, description="Enable explainer phase")


class ResumeGraphRequest(BaseModel):
    """Request to resume graph execution with user feedback"""
    thread_id: str = Field(..., description="Thread ID to resume")
    message_id: Optional[str] = Field(None, description="Message ID to resume")
    review_action: Optional[ApprovalStatus] = Field(None, description="User's approval decision (for plan approval)")
    human_comment: Optional[str] = Field(None, description="Optional user feedback comment")
    tool_response: Optional[Dict[str, Any]] = Field(None, description="Tool approval response (for tool-level approval)")


class StepData(BaseModel):
    """Individual execution step data"""
    id: int = Field(..., description="Step ID")
    type: str = Field(..., description="Step type")
    decision: str = Field(..., description="Decision made")
    reasoning: str = Field(..., description="Reasoning for decision")
    input: str = Field(..., description="Step input")
    output: str = Field(..., description="Step output")
    confidence: float = Field(..., description="Confidence score")
    why_chosen: str = Field(..., description="Why this step was chosen")
    timestamp: str = Field(..., description="Step timestamp")


class FinalResult(BaseModel):
    """Final execution result"""
    summary: str = Field(..., description="Result summary")
    details: str = Field(..., description="Detailed results")
    source: str = Field(..., description="Data source")
    inference: str = Field(..., description="Inference method")
    extra_explanation: Optional[str] = Field(None, description="Additional explanation")


class GraphExecutionData(BaseModel):
    """Graph execution result data"""
    thread_id: str = Field(..., description="Thread identifier")
    checkpoint_id: Optional[str] = Field(None, description="Checkpoint identifier")
    query: Optional[str] = Field(None, description="User query")
    run_status: ExecutionStatus = Field(..., description="Execution status")
    assistant_response: Optional[str] = Field(None, description="Assistant's response")
    plan: Optional[str] = Field(None, description="Execution plan")
    response_type: Optional[str] = Field(None, description="Response type (plan/replan)")
    steps: Optional[List[StepData]] = Field(None, description="Execution steps")
    final_result: Optional[FinalResult] = Field(None, description="Final result")
    total_time: Optional[float] = Field(None, description="Total execution time")
    overall_confidence: Optional[float] = Field(None, description="Overall confidence score")
    visualizations: Optional[List[Dict[str, Any]]] = Field(None, description="Generated visualizations")
    error: Optional[str] = Field(None, description="Error message if any")
    assistant_message_id: Optional[str] = Field(None, description="Assistant message ID")
    explorer_message_id: Optional[str] = Field(None, description="Explorer message ID")
    visualization_message_id: Optional[str] = Field(None, description="Visualization message ID")


class GraphResponse(BaseResponse[GraphExecutionData]):
    """Response for graph execution"""
    pass


class GraphStatusData(BaseModel):
    """Graph status information"""
    thread_id: str = Field(..., description="Thread identifier")
    execution_status: ExecutionStatus = Field(..., description="Current execution status")
    next_nodes: List[str] = Field(..., description="Next nodes to execute")
    plan: str = Field(..., description="Current plan")
    step_count: int = Field(..., description="Number of steps completed")
    approval_status: ApprovalStatus = Field(..., description="Current approval status")


class GraphStatusResponse(BaseResponse[GraphStatusData]):
    """Response for graph status"""
    pass


# ==================== Explorer Schemas ====================

class ExplorerStepData(BaseModel):
    """Explorer step data"""
    id: int
    type: str
    decision: str
    reasoning: str
    input: str
    output: str
    confidence: float
    why_chosen: str
    timestamp: str


class ExplorerResultData(BaseModel):
    """Explorer final result"""
    summary: Optional[str] = None
    details: Optional[str] = None
    source: Optional[str] = None
    inference: Optional[str] = None
    extra_explanation: Optional[str] = None


class ExplorerData(BaseModel):
    """Explorer execution data"""
    thread_id: str
    checkpoint_id: str
    run_status: str
    assistant_response: Optional[str] = None
    query: Optional[str] = None
    plan: Optional[str] = None
    error: Optional[str] = None
    steps: Optional[List[ExplorerStepData]] = None
    final_result: Optional[ExplorerResultData] = None
    total_time: Optional[float] = None
    overall_confidence: Optional[float] = None


class ExplorerResponse(BaseResponse[ExplorerData]):
    """Response for explorer data"""
    pass


# ==================== Visualization Schemas ====================

class VisualizationData(BaseModel):
    """Visualization data"""
    thread_id: str = Field(..., description="Thread identifier")
    checkpoint_id: str = Field(..., description="Checkpoint identifier")
    visualizations: List[Dict[str, Any]] = Field(..., description="Visualization data")
    count: int = Field(..., description="Number of visualizations")
    types: List[str] = Field(..., description="Visualization types")


class VisualizationResponse(BaseResponse[VisualizationData]):
    """Response for visualization data"""
    pass


class VisualizationSummaryData(BaseModel):
    """Visualization summary data"""
    thread_id: str
    checkpoint_id: str
    count: int
    types: List[str]
    has_data: bool


class VisualizationSummaryResponse(BaseResponse[VisualizationSummaryData]):
    """Response for visualization summary"""
    pass
