"""Graph execution endpoints (non-streaming)."""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import Response
from typing import Optional
import logging
from uuid import uuid4

from app.services.agent_service import AgentService
from app.services.message_management_service import MessageManagementService
from app.services.dependencies import get_message_management_service
from app.models.supabase_user import SupabaseUser
from app.core.auth import get_current_user
from app.schemas.graph import (
    StartGraphRequest,
    ResumeGraphRequest,
    GraphResponse,
    GraphExecutionData,
    GraphStatusResponse,
    GraphStatusData,
    ExecutionStatus,
    ApprovalStatus,
    ExplorerResponse,
    ExplorerData,
    VisualizationResponse,
    VisualizationData
)
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# Dependency function to get agent service from app state
def get_agent_service(request: Request) -> AgentService:
    agent_service = request.app.state.agent_service
    if not hasattr(agent_service, '_agent') or agent_service._agent is None:
        raise HTTPException(status_code=500, detail="Agent service not properly initialized")
    return agent_service

router = APIRouter(
    prefix="/graph",
    tags=["graph"]
)


@router.post("/start", response_model=GraphResponse)
async def start_graph_execution(
    request: StartGraphRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    message_service: MessageManagementService = Depends(get_message_management_service)
) -> GraphResponse:
    """Start graph execution with a user query."""
    try:
        thread_id = request.thread_id or str(uuid4())
        user_id = current_user.user_id
        
        logger.info(f"Starting graph execution for thread {thread_id}, user {user_id}")
        
        # Save user message with user_id
        if request.human_request and message_service:
            try:
                await message_service.save_user_message(
                    thread_id=thread_id,
                    content=request.human_request,
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Failed to save user message: {e}")
        
        # Prepare initial state
        from app.agents.state import ExplainableAgentState
        initial_state = ExplainableAgentState(
            messages=[HumanMessage(content=request.human_request)],
            query=request.human_request,
            plan="",
            steps=[],
            step_counter=0,
            status="approved",
            assistant_response="",
            use_planning=request.use_planning,
            use_explainer=request.use_explainer,
            agent_type="data_exploration_agent",
            routing_reason="Direct routing to data exploration agent",
            visualizations=[]
        )
        
        # Include user_id in config for proper isolation
        config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
        
        # Execute graph
        agent = agent_service.get_agent()
        events = list(agent.graph.stream(initial_state, config, stream_mode="values"))
        
        # Get final state
        state = agent.graph.get_state(config)
        next_nodes = state.next
        checkpoint_id = None
        query = state.values.get("query", "")
        
        if hasattr(state, 'config') and state.config and 'configurable' in state.config:
            configurable = state.config['configurable']
            if 'checkpoint_id' in configurable:
                checkpoint_id = str(configurable['checkpoint_id'])
        
        # Determine execution status
        if next_nodes and "human_feedback" in next_nodes:
            execution_status = ExecutionStatus.USER_FEEDBACK
            current_values = state.values
            assistant_response = current_values.get("assistant_response") or current_values.get("plan", "Plan generated - awaiting approval")
            plan = current_values.get("plan", "")
            response_type = current_values.get("response_type")
            
            # Save assistant message that needs approval
            assistant_message_id = None
            if assistant_response and message_service:
                try:
                    saved_message = await message_service.save_assistant_message(
                        thread_id=thread_id,
                        content=assistant_response,
                        checkpoint_id=checkpoint_id,
                        needs_approval=True
                    )
                    assistant_message_id = saved_message.id
                except Exception as e:
                    logger.error(f"Failed to save assistant message: {e}")
            
            return GraphResponse(
                data=GraphExecutionData(
                    thread_id=thread_id,
                    checkpoint_id=checkpoint_id,
                    query=query,
                    run_status=execution_status,
                    assistant_response=assistant_response,
                    plan=plan,
                    response_type=response_type,
                    assistant_message_id=assistant_message_id
                ),
                message="Graph execution paused for user feedback"
            )
        else:
            execution_status = ExecutionStatus.FINISHED
            final_values = state.values
            messages = final_values.get("messages", [])
            
            # Get last AI message
            assistant_response = ""
            for msg in reversed(messages):
                if (hasattr(msg, 'content') and msg.content and 
                    type(msg).__name__ == 'AIMessage' and
                    (not hasattr(msg, 'tool_calls') or not msg.tool_calls)):
                    assistant_response = msg.content
                    break
            
            steps = final_values.get("steps", [])
            plan = final_values.get("plan", "")
            visualizations = final_values.get("visualizations", [])
            
            # Save messages
            assistant_message_id = None
            if assistant_response and message_service:
                try:
                    saved_message = await message_service.save_assistant_message(
                        thread_id=thread_id,
                        content=assistant_response,
                        checkpoint_id=checkpoint_id,
                        needs_approval=False
                    )
                    assistant_message_id = saved_message.id
                except Exception as e:
                    logger.error(f"Failed to save assistant message: {e}")
            
            return GraphResponse(
                data=GraphExecutionData(
                    thread_id=thread_id,
                    checkpoint_id=checkpoint_id,
                    query=query,
                    run_status=execution_status,
                    assistant_response=assistant_response,
                    plan=plan,
                    steps=steps,
                    visualizations=visualizations,
                    assistant_message_id=assistant_message_id
                ),
                message="Graph execution completed successfully"
            )
            
    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        return GraphResponse(
            status="error",
            message=f"Graph execution failed: {str(e)}",
            errors=[{"code": "GRAPH_EXECUTION_ERROR", "message": str(e)}]
        )


@router.post("/resume", response_model=GraphResponse)
async def resume_graph_execution(
    request: ResumeGraphRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    message_service: MessageManagementService = Depends(get_message_management_service)
) -> GraphResponse:
    """Resume graph execution with user feedback."""
    try:
        user_id = current_user.user_id
        # Include user_id in config for proper isolation
        config = {"configurable": {"thread_id": request.thread_id, "user_id": user_id}}
        
        logger.info(f"Resuming graph for thread {request.thread_id}, user {user_id}, action: {request.review_action}")
        
        # Get current state
        agent = agent_service.get_agent()
        current_state = agent.graph.get_state(config)
        
        if not current_state:
            return GraphResponse(
                status="error",
                message=f"No graph execution found for thread {request.thread_id}",
                errors=[{"code": "THREAD_NOT_FOUND", "message": f"Thread {request.thread_id} not found"}]
            )
        
        # Check if waiting for feedback
        if not (current_state.next and "human_feedback" in current_state.next):
            return GraphResponse(
                status="error",
                message="Graph is not waiting for feedback",
                errors=[{"code": "NOT_WAITING_FEEDBACK", "message": "Graph execution is not waiting for human feedback"}]
            )
        
        # Save user feedback message
        if message_service and request.human_comment:
            try:
                await message_service.save_user_message(
                    thread_id=request.thread_id,
                    content=request.human_comment,
                    is_feedback=True
                )
            except Exception as e:
                logger.error(f"Failed to save feedback message: {e}")
        
        # Update state with user decision
        state_update = {"status": request.review_action.value}
        if request.human_comment:
            state_update["human_comment"] = request.human_comment
        
        agent.graph.update_state(config, state_update)
        
        # Continue execution
        events = list(agent.graph.stream(None, config, stream_mode="values"))
        
        # Get final state
        state = agent.graph.get_state(config)
        next_nodes = state.next
        checkpoint_id = None
        query = state.values.get("query", "")
        
        if hasattr(state, 'config') and state.config and 'configurable' in state.config:
            configurable = state.config['configurable']
            if 'checkpoint_id' in configurable:
                checkpoint_id = str(configurable['checkpoint_id'])
        
        # Check if finished or waiting again
        if next_nodes and "human_feedback" in next_nodes:
            execution_status = ExecutionStatus.USER_FEEDBACK
            current_values = state.values
            assistant_response = current_values.get("assistant_response") or current_values.get("plan", "")
            plan = current_values.get("plan", "")
            
            return GraphResponse(
                data=GraphExecutionData(
                    thread_id=request.thread_id,
                    checkpoint_id=checkpoint_id,
                    query=query,
                    run_status=execution_status,
                    assistant_response=assistant_response,
                    plan=plan
                ),
                message="Graph execution paused for user feedback"
            )
        else:
            execution_status = ExecutionStatus.FINISHED
            final_values = state.values
            messages = final_values.get("messages", [])
            
            # Get last AI message
            assistant_response = ""
            for msg in reversed(messages):
                if (hasattr(msg, 'content') and msg.content and 
                    type(msg).__name__ == 'AIMessage' and
                    (not hasattr(msg, 'tool_calls') or not msg.tool_calls)):
                    assistant_response = msg.content
                    break
            
            steps = final_values.get("steps", [])
            plan = final_values.get("plan", "")
            visualizations = final_values.get("visualizations", [])
            
            return GraphResponse(
                data=GraphExecutionData(
                    thread_id=request.thread_id,
                    checkpoint_id=checkpoint_id,
                    query=query,
                    run_status=execution_status,
                    assistant_response=assistant_response,
                    plan=plan,
                    steps=steps,
                    visualizations=visualizations
                ),
                message="Graph execution completed successfully"
            )
            
    except Exception as e:
        logger.error(f"Graph resume failed: {e}")
        return GraphResponse(
            status="error",
            message=f"Graph resume failed: {str(e)}",
            errors=[{"code": "GRAPH_RESUME_ERROR", "message": str(e)}]
        )


@router.get("/status/{thread_id}", response_model=GraphStatusResponse)
async def get_graph_status(
    thread_id: str,
    agent_service: AgentService = Depends(get_agent_service)
) -> GraphStatusResponse:
    """Get the current status of graph execution."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        agent = agent_service.get_agent()
        state = agent.graph.get_state(config)
        
        if not state:
            return GraphStatusResponse(
                status="error",
                message=f"No graph execution found for thread {thread_id}",
                errors=[{"code": "THREAD_NOT_FOUND", "message": f"Thread {thread_id} not found"}]
            )
        
        next_nodes = state.next
        values = state.values
        
        if next_nodes and "human_feedback" in next_nodes:
            execution_status = ExecutionStatus.USER_FEEDBACK
        elif next_nodes:
            execution_status = ExecutionStatus.RUNNING
        else:
            execution_status = ExecutionStatus.FINISHED
        
        return GraphStatusResponse(
            data=GraphStatusData(
                thread_id=thread_id,
                execution_status=execution_status,
                next_nodes=list(next_nodes) if next_nodes else [],
                plan=values.get("plan", ""),
                step_count=len(values.get("steps", [])),
                approval_status=ApprovalStatus(values.get("status", "unknown"))
            ),
            message=f"Graph status retrieved for thread {thread_id}"
        )
        
    except Exception as e:
        return GraphStatusResponse(
            status="error",
            message=f"Error getting graph status: {str(e)}",
            errors=[{"code": "STATUS_ERROR", "message": str(e)}]
        )


# ==================== Explorer & Visualization Endpoints ====================

@router.get("/explorer", response_model=ExplorerResponse)
async def get_explorer_data(
    thread_id: str = Query(..., description="Thread ID"),
    checkpoint_id: str = Query(..., description="Checkpoint ID"),
    agent_service: AgentService = Depends(get_agent_service)
) -> ExplorerResponse:
    """Get explorer data from a specific checkpoint."""
    try:
        logger.info(f"Fetching explorer data for thread_id: {thread_id}, checkpoint_id: {checkpoint_id}")
        
        explorer_data = await agent_service.get_explorer_data(thread_id, checkpoint_id)
        
        if explorer_data is None:
            return ExplorerResponse(
                status="error",
                message=f"No explorer data found for checkpoint {checkpoint_id}",
                errors=[{"code": "EXPLORER_NOT_FOUND", "message": f"No explorer data found"}]
            )
        
        return ExplorerResponse(
            data=ExplorerData(**explorer_data),
            message=f"Explorer data retrieved successfully for checkpoint {checkpoint_id}"
        )
        
    except Exception as e:
        logger.error(f"Error fetching explorer data: {str(e)}")
        return ExplorerResponse(
            status="error",
            message=f"Error fetching explorer data: {str(e)}",
            errors=[{"code": "EXPLORER_ERROR", "message": str(e)}]
        )


@router.get("/visualization", response_model=VisualizationResponse)
async def get_visualization_data(
    thread_id: str = Query(..., description="Thread ID"),
    checkpoint_id: str = Query(..., description="Checkpoint ID"),
    agent_service: AgentService = Depends(get_agent_service)
) -> VisualizationResponse:
    """Get visualization data from a specific checkpoint."""
    try:
        logger.info(f"Fetching visualization data for thread_id: {thread_id}, checkpoint_id: {checkpoint_id}")
        
        visualization_data = await agent_service.get_visualization_data(thread_id, checkpoint_id)
        
        if visualization_data is None:
            return VisualizationResponse(
                status="error",
                message=f"No visualization data found for checkpoint {checkpoint_id}",
                errors=[{"code": "VISUALIZATION_NOT_FOUND", "message": f"No visualization data found"}]
            )
        
        return VisualizationResponse(
            data=VisualizationData(**visualization_data),
            message=f"Visualization data retrieved successfully for checkpoint {checkpoint_id}"
        )
        
    except Exception as e:
        logger.error(f"Error fetching visualization data: {str(e)}")
        return VisualizationResponse(
            status="error",
            message=f"Error fetching visualization data: {str(e)}",
            errors=[{"code": "VISUALIZATION_ERROR", "message": str(e)}]
        )


# ==================== Graph Structure Visualization ====================

@router.get("/visualization-image")
async def get_graph_visualization_image(
    agent_service: AgentService = Depends(get_agent_service)
):
    """Generate and return the LangGraph structure visualization as a PNG image."""
    try:
        logger.info("Generating graph visualization image")
        
        # Get the agent
        agent = agent_service.get_agent()
        
        # Generate the graph visualization
        graph_image = agent.graph.get_graph().draw_mermaid_png()
        
        logger.info(f"Graph visualization generated successfully, size: {len(graph_image)} bytes")
        
        # Return as PNG image
        return Response(
            content=graph_image,
            media_type="image/png",
            headers={
                "Content-Disposition": "inline; filename=agent_graph.png"
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating graph visualization: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate graph visualization: {str(e)}"
        )

