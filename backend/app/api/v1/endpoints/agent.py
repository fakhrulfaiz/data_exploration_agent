"""Expose AgentService via HTTP endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from langchain_core.messages import HumanMessage

from app.agents import DataExplorationAgent
from app.services.agent_service import AgentService
from app.schemas.agent import (
    AgentRequest,
    AgentResponse,
    AgentExecutionData,
    StateResponse,
    ThreadStateData,
    StateUpdateRequest,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteData,
    CleanupResponse,
    CleanupData
)
from app.schemas.base import SuccessResponse

router = APIRouter()


# All schemas are now imported from app.schemas.agent


def get_agent(request: Request) -> DataExplorationAgent:
    """Get the initialized agent from app state (backward compatibility)."""
    return request.app.state.agent


def get_agent_service(request: Request) -> AgentService:
    agent_service = request.app.state.agent_service
    if not agent_service.is_initialized():
        raise HTTPException(status_code=500, detail="Agent service not properly initialized")
    return agent_service


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    payload: AgentRequest, 
    agent_service: AgentService = Depends(get_agent_service)
) -> AgentResponse:
    """Run the agent with a single user message using AgentService."""
    try:
        result = await agent_service.run_agent(
            message=payload.message,
            thread_id=payload.session_id
        )
        
        if result["success"]:
            return AgentResponse(
                data=AgentExecutionData(
                    messages=result["messages"],
                    thread_id=result["thread_id"],
                    state=result.get("state")
                ),
                message="Agent executed successfully"
            )
        else:
            return AgentResponse(
                status="error",
                message="Agent execution failed",
                errors=[{"code": "AGENT_EXECUTION_ERROR", "message": result.get("error", "Unknown error")}]
            )
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ==================== Thread Management Endpoints ====================


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    agent_service: AgentService = Depends(get_agent_service)
) -> SuccessResponse:
    """Delete all checkpoints for a specific thread."""
    try:
        success = await agent_service.delete_thread(thread_id)
        
        if success:
            return SuccessResponse(
                data={"thread_id": thread_id},
                message=f"Thread {thread_id} deleted successfully"
            )
        else:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found or could not be deleted")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error deleting thread: {str(exc)}") from exc


# ==================== State Management Endpoints ====================

@router.get("/threads/{thread_id}/state", response_model=StateResponse)
async def get_current_state(
    thread_id: str,
    agent: DataExplorationAgent = Depends(get_agent)
) -> StateResponse:
    """Get the current state for a thread."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = agent.graph.get_state(config)
        
        if state:
            state_data = {
                "thread_id": thread_id,
                "state": state.values,
                "next": state.next,
                "config": state.config,
                "metadata": state.metadata,
                "created_at": state.created_at if hasattr(state, 'created_at') else None
            }
            return StateResponse(
                data=ThreadStateData(**state_data),
                message=f"Current state retrieved for thread {thread_id}"
            )
            
        else:
            return StateResponse(
                status="error",
                message=f"No state found for thread {thread_id}",
                errors=[{"code": "STATE_NOT_FOUND", "message": f"No state exists for thread {thread_id}"}]
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/threads/{thread_id}/state")
async def update_thread_state(
    thread_id: str,
    request: StateUpdateRequest,
    agent_service: AgentService = Depends(get_agent_service)
) -> SuccessResponse:
    """Update state for an existing thread."""
    try:
        success = await agent_service.update_thread_state(thread_id, request.state_updates)
        if success:
            return SuccessResponse(
                data={"thread_id": thread_id, "updated_fields": list(request.state_updates.keys())},
                message=f"State updated for thread {thread_id}"
            )
        else:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found or could not be updated")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@router.post("/threads/bulk-delete", response_model=BulkDeleteResponse)
async def delete_multiple_threads(
    request: BulkDeleteRequest,
    agent_service: AgentService = Depends(get_agent_service)
) -> BulkDeleteResponse:
    """Delete multiple threads in bulk."""
    try:
        results = await agent_service.delete_multiple_threads(request.thread_ids)
        successful = sum(1 for success in results.values() if success)
        failed = len(request.thread_ids) - successful
        
        return BulkDeleteResponse(
            data=BulkDeleteData(
                results=results,
                successful=successful,
                failed=failed
            ),
            message=f"Bulk deletion completed: {successful}/{len(request.thread_ids)} threads deleted"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/checkpoints/cleanup", response_model=CleanupResponse)
async def cleanup_old_checkpoints(
    older_than_days: int = Query(30, description="Delete checkpoints older than this many days"),
    agent_service: AgentService = Depends(get_agent_service)
) -> CleanupResponse:
    """Clean up checkpoints older than specified days."""
    try:
        result = await agent_service.cleanup_old_checkpoints(older_than_days)
        return CleanupResponse(
            data=CleanupData(**result),
            message="Cleanup completed successfully"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc










@router.get("/health")
async def agent_service_health(
    agent_service: AgentService = Depends(get_agent_service)
) -> Dict[str, Any]:
    """Get agent service health status."""
    try:
        health_status = await agent_service.health_check()
        status_code = 200 if health_status.get("overall_status") == "healthy" else 503
        
        # Return the health status with appropriate HTTP status code
        if status_code == 503:
            raise HTTPException(status_code=503, detail=health_status)
        
        return health_status
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

