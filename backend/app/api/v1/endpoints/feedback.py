"""
API endpoints for explanation feedback system.

Features:
- Submit feedback
- Semantic search
- Analytics and stats
- Maintenance operations (cleanup, archival)
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.services.feedback_vector_store import get_feedback_store, FeedbackVectorStore

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class FeedbackCreate(BaseModel):
    """Feedback submission model"""
    conversation_id: str = Field(..., description="ID of the conversation")
    message_id: str = Field(..., description="ID of the message being rated")
    helpful: bool = Field(..., description="Whether explanation was helpful")
    feedback_comment: Optional[str] = Field(None, description="Optional user comment")
    tool_name: Optional[str] = Field(None, description="Name of tool being explained")
    explanation_type: Optional[str] = Field(None, description="Type of explanation")
    explanation_text: Optional[str] = Field(None, description="Full explanation text for embedding")


class FeedbackResponse(BaseModel):
    """Response after submitting feedback"""
    status: str
    feedback_id: str
    message: str


class StatsResponse(BaseModel):
    """Feedback statistics response"""
    total_feedback: int
    helpful_count: int
    unhelpful_count: int
    helpfulness_rate: float
    feedback_with_comments: int
    comment_rate: float
    tool_name: Optional[str] = None
    explanation_type: Optional[str] = None
    days_range: Optional[int] = None


class StorageInfoResponse(BaseModel):
    """Storage usage information"""
    hot_storage: Dict[str, Any]
    archive_storage: Dict[str, Any]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/explanation-feedback", response_model=FeedbackResponse)
async def submit_explanation_feedback(
    feedback: FeedbackCreate,
    background_tasks: BackgroundTasks,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Submit feedback on an explanation.
    
    Stores in vector database for semantic analysis.
    Automatically triggers cleanup if storage limit reached.
    """
    try:
        # Submit feedback (may trigger auto-cleanup)
        feedback_id = store.add_feedback(
            conversation_id=feedback.conversation_id,
            message_id=feedback.message_id,
            helpful=feedback.helpful,
            feedback_comment=feedback.feedback_comment,
            tool_name=feedback.tool_name,
            explanation_type=feedback.explanation_type,
            explanation_text=feedback.explanation_text
        )
        
        logger.info(
            f"Feedback submitted: {feedback_id[:8]}... "
            f"(tool={feedback.tool_name}, helpful={feedback.helpful})"
        )
        
        return FeedbackResponse(
            status="success",
            feedback_id=feedback_id,
            message="Thank you for your feedback!"
        )
    
    except Exception as e:
        logger.error(f"Failed to store feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to store feedback: {str(e)}"
        )


@router.get("/explanation-feedback/stats", response_model=StatsResponse)
async def get_feedback_stats(
    tool_name: Optional[str] = None,
    explanation_type: Optional[str] = None,
    days: Optional[int] = None,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Get feedback statistics.
    
    Args:
        tool_name: Filter by specific tool
        explanation_type: Filter by explanation type
        days: Only include feedback from last N days
    """
    try:
        stats = store.get_feedback_stats(
            tool_name=tool_name,
            explanation_type=explanation_type,
            days=days
        )
        
        return StatsResponse(**stats)
    
    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )


@router.get("/explanation-feedback/similar")
async def find_similar_feedback(
    query: str,
    tool_name: Optional[str] = None,
    helpful_only: Optional[bool] = None,
    n_results: int = 5,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Find similar feedback using semantic search.
    
    Useful for identifying patterns in user feedback.
    
    Args:
        query: Text to search for
        tool_name: Filter by specific tool
        helpful_only: If True, only helpful; if False, only unhelpful
        n_results: Number of results to return
    """
    try:
        similar = store.find_similar_feedback(
            query_text=query,
            n_results=n_results,
            tool_name=tool_name,
            helpful_only=helpful_only
        )
        
        return {
            "query": query,
            "filters": {
                "tool_name": tool_name,
                "helpful_only": helpful_only
            },
            "similar_feedback": similar,
            "count": len(similar)
        }
    
    except Exception as e:
        logger.error(f"Failed to search feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search feedback: {str(e)}"
        )


@router.get("/explanation-feedback/issues")
async def get_common_issues(
    tool_name: Optional[str] = None,
    limit: int = 10,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Get common issues from unhelpful feedback.
    
    Helps identify what needs improvement.
    
    Args:
        tool_name: Filter by specific tool
        limit: Maximum number of issues to return
    """
    try:
        issues = store.get_common_issues(
            tool_name=tool_name,
            limit=limit
        )
        
        return {
            "tool_name": tool_name,
            "common_issues": issues,
            "total_issues": len(issues)
        }
    
    except Exception as e:
        logger.error(f"Failed to get issues: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve issues: {str(e)}"
        )


@router.get("/explanation-feedback/storage", response_model=StorageInfoResponse)
async def get_storage_info(
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Get information about storage usage.
    
    Shows:
    - Current vector count
    - Storage capacity
    - Archive size
    """
    try:
        info = store.get_storage_info()
        return StorageInfoResponse(**info)
    
    except Exception as e:
        logger.error(f"Failed to get storage info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve storage info: {str(e)}"
        )


@router.post("/explanation-feedback/maintenance/cleanup")
async def trigger_cleanup(
    force: bool = False,
    background_tasks: BackgroundTasks = None,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Manually trigger cleanup and archival.
    
    This is automatically done when storage limit is reached,
    but can be triggered manually for maintenance.
    
    Args:
        force: If True, cleanup even if not at limit
    """
    try:
        logger.info(f"Manual cleanup triggered (force={force})")
        
        # Run cleanup
        result = store.cleanup_old_feedback(force=force)
        
        return {
            "status": "success",
            "cleanup_result": result,
            "message": f"Cleaned {result['cleaned']} feedback entries"
        }
    
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/explanation-feedback/analytics/tool-performance")
async def analyze_tool_performance(
    days: Optional[int] = 30,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Analyze which tools have the best/worst explanations.
    
    Args:
        days: Analyze feedback from last N days
    """
    try:
        # List of tools to analyze
        tools = [
            "sql_db_query",
            "sql_db_to_df", 
            "text2SQL",
            "python_repl",
            "smart_transform_for_viz",
            "large_plotting_tool",
            "dataframe_info"
        ]
        
        performance = []
        for tool in tools:
            stats = store.get_feedback_stats(tool_name=tool, days=days)
            if stats['total_feedback'] > 0:
                performance.append({
                    "tool": tool,
                    **stats
                })
        
        # Sort by helpfulness rate
        performance.sort(key=lambda x: x['helpfulness_rate'], reverse=True)
        
        return {
            "analysis_period_days": days,
            "tool_performance": performance,
            "best_tool": performance[0] if performance else None,
            "worst_tool": performance[-1] if performance else None,
            "total_tools_analyzed": len(performance)
        }
    
    except Exception as e:
        logger.error(f"Failed to analyze performance: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze tool performance: {str(e)}"
        )


@router.get("/explanation-feedback/analytics/trends")
async def get_feedback_trends(
    tool_name: Optional[str] = None,
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Get feedback trends over time.
    
    Shows how feedback patterns change over different time periods.
    """
    try:
        periods = [7, 14, 30]  # Last 7, 14, 30 days
        
        trends = []
        for days in periods:
            stats = store.get_feedback_stats(
                tool_name=tool_name,
                days=days
            )
            trends.append({
                "period_days": days,
                **stats
            })
        
        return {
            "tool_name": tool_name or "all",
            "trends": trends
        }
    
    except Exception as e:
        logger.error(f"Failed to get trends: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve trends: {str(e)}"
        )


@router.get("/explanation-feedback/health")
async def health_check(
    store: FeedbackVectorStore = Depends(get_feedback_store)
):
    """
    Health check endpoint for monitoring.
    
    Returns system status and alerts if any issues.
    """
    try:
        storage_info = store.get_storage_info()
        vector_count = storage_info['hot_storage']['vector_count']
        max_vectors = storage_info['hot_storage']['max_vectors']
        usage_percent = storage_info['hot_storage']['usage_percent']
        
        # Determine health status
        status = "healthy"
        alerts = []
        
        if usage_percent > 90:
            status = "warning"
            alerts.append(f"Storage at {usage_percent:.1f}% capacity")
        
        if usage_percent >= 100:
            status = "critical"
            alerts.append("Storage full - cleanup needed")
        
        return {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "storage": {
                "vector_count": vector_count,
                "max_vectors": max_vectors,
                "usage_percent": usage_percent
            },
            "alerts": alerts
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }
