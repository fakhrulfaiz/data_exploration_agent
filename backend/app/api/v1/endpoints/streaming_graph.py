from fastapi import APIRouter, Depends, Request, HTTPException
from sse_starlette.sse import EventSourceResponse
from uuid import uuid4
from datetime import datetime
from typing import Annotated, Any, Dict
import logging
import json
import asyncio
import time
import time as _time

from app.schemas.graph import StartGraphRequest, GraphResponse, ResumeGraphRequest, ExecutionStatus, ApprovalStatus
from app.agents.state import ExplainableAgentState
from langchain_core.messages import HumanMessage
from app.services.dependencies import get_message_management_service, get_supabase_storage_service
from app.services.message_management_service import MessageManagementService
from app.services.agent_service import AgentService
from app.services.storage_service import SupabaseStorageService
from app.models.supabase_user import SupabaseUser
from app.core.auth import get_current_user
from app.api.v1.endpoints.streaming.handlers import (
    StreamContext,
    ToolCallHandler,
    TextContentHandler,
    PlanContentHandler,
    ExplanationContentHandler,
    ReasoningChainContentHandler
)
from app.api.v1.endpoints.streaming.streaming_persistence import StreamingMessagePersistence
from app.api.v1.endpoints.streaming.streaming_utils import (
    handle_tool_interrupt,
    handle_plan_approval,
    handle_completion,
    handle_error,
    check_for_interrupts
)

logger = logging.getLogger(__name__)

# Dependency function to get agent service from app state
def get_agent_service(request: Request) -> AgentService:
    agent_service = request.app.state.agent_service
    if not hasattr(agent_service, '_agent') or agent_service._agent is None:
        raise HTTPException(status_code=500, detail="Agent service not properly initialized")
    return agent_service

router = APIRouter(
    prefix="/graph/stream",
    tags=["streaming-graph"]
)

# Store run configurations for streaming
run_configs = {}

def _extract_stream_or_message_id(msg: Any, preferred_key: str = 'message_id') -> Any:
    tool_call_id = getattr(msg, 'tool_call_id', None)
    if tool_call_id is not None and tool_call_id != "":
        if isinstance(tool_call_id, str) and tool_call_id.isdigit():
            return int(tool_call_id)
        return tool_call_id
    msg_id = getattr(msg, 'id', None)
    if not msg_id and hasattr(msg, 'response_metadata'):
        meta = getattr(msg, 'response_metadata') or {}
        for key in [preferred_key, 'id']:
            mid = meta.get(key)
            if mid is not None:
                msg_id = mid
                break
    if isinstance(msg_id, str):
        try:
            if msg_id.isdigit():
                return int(msg_id)
        except:
            pass
    if msg_id is None or (isinstance(msg_id, str) and not msg_id):
        return int(_time.time() * 1000000)
    return msg_id

@router.post("/start", response_model=GraphResponse)
async def create_graph_streaming(
    request: StartGraphRequest,
    current_user: SupabaseUser = Depends(get_current_user)
):
    thread_id = request.thread_id or str(uuid4())
    user_id = current_user.user_id
    
    logger.info(f"Streaming graph /start - thread_id: {thread_id}, user_id: {user_id}")
    logger.info(f"Start request - human_request: '{request.human_request}', use_planning: {request.use_planning}, use_explainer: {request.use_explainer}")
    
    assistant_message_id = str(uuid4())
    run_configs[thread_id] = {
        "type": "start",
        "human_request": request.human_request,
        "use_planning": request.use_planning,
        "use_explainer": request.use_explainer,
        "assistant_message_id": assistant_message_id,
        "user_id": user_id  # Store user_id for streaming
    }
    
    
    return GraphResponse(
        data={
            "thread_id": thread_id,
            "run_status": "pending",
            "assistant_response": "", 
            "query": request.human_request,
            "plan": "",
            "steps": [],
            "final_result": None,
            "total_time": None,
            "overall_confidence": None,
            "assistant_message_id": assistant_message_id
        },
        message="Streaming graph created"
    )

@router.post("/resume", response_model=GraphResponse)
async def resume_graph_streaming(
    request: ResumeGraphRequest,
    current_user: SupabaseUser = Depends(get_current_user)
):
    thread_id = request.thread_id
    user_id = current_user.user_id
    
    logger.info(f"Streaming graph /resume - thread_id: {thread_id}, user_id: {user_id}")
    
    assistant_message_id = request.message_id or str(uuid4())
    
    if request.tool_response:
        logger.info(f"Tool approval response received - type: {request.tool_response.get('type')}")
        run_configs[thread_id] = {
            "type": "tool_resume",
            "tool_response": request.tool_response,
            "assistant_message_id": assistant_message_id,
            "user_id": user_id
        }
    else:
        run_configs[thread_id] = {
            "type": "resume",
            "review_action": request.review_action,
            "human_comment": request.human_comment,
            "assistant_message_id": assistant_message_id,
            "user_id": user_id
        }
    
    return GraphResponse(
        data={
            "thread_id": thread_id,
            "run_status": "pending",
            "assistant_response": None,
            "assistant_message_id": assistant_message_id
        },
        message="Streaming graph resume pending"
    )

@router.post("/cancel/{thread_id}", response_model=GraphResponse)
async def cancel_stream(
    thread_id: str,
    agent_service: AgentService = Depends(get_agent_service),
    current_user: SupabaseUser = Depends(get_current_user)
):
    """
    Cancel an ongoing stream execution
    """
    user_id = current_user.user_id
    logger.info(f"Cancelling stream - thread_id: {thread_id}, user_id: {user_id}")
    
    try:
        # Clean up run configs
        if thread_id in run_configs:
            del run_configs[thread_id]
            logger.info(f"Cleaned up run_configs for thread {thread_id}")
        
        # Update agent state to mark as cancelled
        agent = agent_service.get_agent()
        config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
        
        try:
            # Update state to cancelled status
            agent.graph.update_state(config, {"status": "cancelled"})
            logger.info(f"Updated agent state to cancelled for thread {thread_id}")
        except Exception as state_error:
            # State update might fail if thread doesn't exist, which is fine
            logger.warning(f"Could not update state for thread {thread_id}: {state_error}")
        
        return GraphResponse(
            data={
                "thread_id": thread_id,
                "run_status": "cancelled",
                "assistant_response": "Stream execution cancelled by user"
            },
            message="Stream cancelled successfully"
        )
    except Exception as e:
        logger.error(f"Error cancelling stream for thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel stream: {str(e)}")


@router.get("/{thread_id}")
async def stream_graph(
    request: Request,
    thread_id: str,
    agent_service: AgentService = Depends(get_agent_service),
    message_service: MessageManagementService = Depends(get_message_management_service)
):
    logger.info(f"Stream graph endpoint called - thread_id: {thread_id}")
    logger.info(f"Dependencies injected - agent_service: {agent_service is not None}, message_service: {message_service is not None}")
    
    # Check if thread_id exists in our configurations
    if thread_id not in run_configs:
        logger.error(f"Thread ID {thread_id} not found in run_configs. Available configs: {list(run_configs.keys())}")
        return {"error": "Thread ID not found. You must first call /graph/stream/start or /graph/stream/resume"}
    
    # Get the stored configuration
    run_data = run_configs[thread_id]
    user_id = run_data.get("user_id")  # Get user_id from stored config
    
    logger.info(f"Streaming graph execution - thread_id: {thread_id}, user_id: {user_id}")
    logger.info(f"Message service availability: {message_service is not None}")
    logger.info(f"Run data: {run_data}")
    
    # Include user_id in config for proper isolation
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    
    assistant_message_id = run_data.get("assistant_message_id")
    if not assistant_message_id:
        assistant_message_id = str(uuid4())
        run_data["assistant_message_id"] = assistant_message_id
    
    # Get agent instance - needed for both start and resume cases
    agent = agent_service.get_agent()
    
    input_state = None
    if run_data["type"] == "start":
        event_type = "start"
        use_planning_value = run_data.get("use_planning", True)
        
        # Save user message to database before creating initial state
        logger.info(f"Attempting to save user message - message_service: {message_service is not None}, human_request: '{run_data.get('human_request')}'")
        if message_service and run_data.get("human_request"):
            try:
                logger.info(f"Calling save_user_message with thread_id: {thread_id}, user_id: {user_id}, content: '{run_data['human_request']}'")
                saved_message = await message_service.save_user_message(
                    thread_id=thread_id,
                    content=run_data["human_request"],
                    user_id=user_id
                )
                logger.info(f"Successfully saved user message for thread {thread_id}, message_id: {saved_message.message_id if saved_message else 'None'}")
            except Exception as e:
                # Log error but don't fail the request - message saving is important but shouldn't block execution
                logger.error(f"Failed to save user message for thread {thread_id}: {e}", exc_info=True)
        else:
            logger.warning(f"Skipping user message save - message_service: {message_service is not None}, human_request: '{run_data.get('human_request')}'")
        
        initial_state = ExplainableAgentState(
            messages=[HumanMessage(content=run_data["human_request"])],
            query=run_data["human_request"],
            plan="",
            steps=[],
            step_counter=0,
            status="approved",
            use_planning=use_planning_value,
            use_explainer=run_data.get("use_explainer", True),
            agent_type="data_exploration_agent",
            visualizations=[],
            user_id=user_id  # Add user_id for preference fetching
        )
        input_state = initial_state
    elif run_data["type"] == "tool_resume":
        event_type = "tool_resume"
        
        # Use LangGraph Command API to resume from interrupt
        from langgraph.types import Command
        
        tool_response = run_data.get("tool_response", {})
        logger.info(f"Resuming from tool interrupt with response: {tool_response}")
        
        input_state = Command(resume=tool_response)
        
    else:
        event_type = "resume"
        
        # Save user feedback message to database
        logger.info(f"Feedback debug - message_service: {message_service is not None}, human_comment: '{run_data.get('human_comment')}'")
        if message_service and run_data.get("human_comment"):
            try:
                logger.info(f"Calling save_user_message for feedback with thread_id: {thread_id}, user_id: {user_id}, content: '{run_data['human_comment']}'")
                saved_feedback = await message_service.save_user_message(
                    thread_id=thread_id,
                    content=run_data["human_comment"],
                    is_feedback=True,  # Mark as feedback directly
                    user_id=user_id
                )
                logger.info(f"Successfully saved user feedback message for thread {thread_id}, message_id: {saved_feedback.message_id if saved_feedback else 'None'}")
            except Exception as e:
                logger.error(f"Failed to save user feedback message for thread {thread_id}: {e}", exc_info=True)
        else:
            logger.warning(f"Skipping feedback save - message_service: {message_service is not None}, human_comment: '{run_data.get('human_comment')}'")
        
        state_update = {"status": run_data["review_action"].value}
        if run_data["human_comment"] is not None:
            state_update["human_comment"] = run_data["human_comment"]
        
        agent.graph.update_state(config, state_update)
        input_state = None
    
    async def event_generator():
        nonlocal assistant_message_id
        
        context = StreamContext(
            thread_id=thread_id,
            assistant_message_id=assistant_message_id,
            node_name="",
            message_service=message_service,
            config=config
        )
        
        # Initialize handlers (database handles sequencing)
        text_handler = TextContentHandler(context) 
        plan_handler = PlanContentHandler(context, agent)
        explanation_handler = ExplanationContentHandler(context)
        reasoning_chain_handler = ReasoningChainContentHandler(context)
        tool_call_handler = ToolCallHandler(context)
        persistence = StreamingMessagePersistence(message_service)

        handlers = [
            tool_call_handler,
            explanation_handler,  # Check explanations before text
            reasoning_chain_handler,  # Check reasoning chains before text
            plan_handler,
            text_handler
        ]
        
        # Load existing blocks for BOTH tool approval and plan approval
        if event_type in ["tool_resume", "resume"] and assistant_message_id and message_service:
            try:
                logger.info(f"Resuming from approval - loading existing content blocks for message {assistant_message_id}")
                completed, pending, other_blocks = await persistence.load_existing_blocks(
                    thread_id, assistant_message_id
                )
                tool_call_handler.load_existing_state(completed, pending)
                # Store other_blocks (plan, text) in context for later use
                context.existing_blocks = other_blocks
            except Exception as e:
                logger.error(f"Failed to load existing state: {e}", exc_info=True)
        
        initial_data = json.dumps({"thread_id": thread_id})
        yield {"event": event_type, "data": initial_data}
        
        try:
            for msg, metadata in agent.graph.stream(input_state, config, stream_mode="messages"):
                if await request.is_disconnected():
                    break
                
                context.node_name = metadata.get('langgraph_node', 'unknown')
                
                if context.node_name == 'error_explainer':
                    continue
                
                checkpoint_ns = metadata.get('langgraph_checkpoint_ns')
                if isinstance(checkpoint_ns, str):
                    normalized_checkpoint_ns = checkpoint_ns.replace(" ", "_")
                    if normalized_checkpoint_ns.startswith("assistant"):
                        logger.debug(f"Skipping chunk from assistant_keep_agent namespace: {checkpoint_ns}")
                        continue
                
                if await tool_call_handler.can_handle(msg, metadata):
                    async for event in tool_call_handler.handle(msg, metadata):
                        yield event
                elif await explanation_handler.can_handle(msg, metadata):
                     async for event in explanation_handler.handle(msg, metadata):
                        yield event
                elif await reasoning_chain_handler.can_handle(msg, metadata):
                    async for event in reasoning_chain_handler.handle(msg, metadata):
                        yield event
                elif await plan_handler.can_handle(msg, metadata):
                    async for event in plan_handler.handle(msg, metadata):
                        yield event
                elif await text_handler.can_handle(msg, metadata):
                    # Check if this is tool explanation content
                    if (type(msg).__name__ == 'AIMessageChunk' and tool_call_handler.active_tool_id):
                        async for event in tool_call_handler.handle_explanation(msg, metadata):
                            yield event
                    elif (type(msg).__name__ == 'AIMessage' and
                          context.node_name == 'tool_explanation' and
                          tool_call_handler.active_tool_id):
                        # Final tool explanation from tool_explanation node
                        async for event in tool_call_handler.handle_explanation(msg, metadata):
                            yield event
                    else:
                        # Regular text content (including planner thought process)
                        async for event in text_handler.handle(msg, metadata):
                            yield event
            
            state = agent.graph.get_state(config)
            values = getattr(state, 'values', {}) or {}
            
            error_explanation = values.get("error_explanation")
            if error_explanation:
                logger.info(f"Emitting error explanation: {error_explanation}")
                error_block_id = f"error_{assistant_message_id or str(uuid4())}"
                error_event_data = json.dumps({
                    "block_type": "error",
                    "block_id": error_block_id,
                    "error_explanation": error_explanation,
                    "message_id": assistant_message_id,
                    "action": "add_error"
                })
                yield {"event": "content_block", "data": error_event_data}
            
            interrupt_data = await check_for_interrupts(state)
            
            if interrupt_data:
                async for event in handle_tool_interrupt(
                    interrupt_data, tool_call_handler, persistence, context, state, config
                ):
                    yield event
            elif state.next and 'human_feedback' in state.next:
                async for event in handle_plan_approval(
                    tool_call_handler, text_handler, plan_handler, persistence, context, state, config
                ):
                    yield event
            else:
                # Finalize text handler to append all text blocks to context
                async for event in text_handler.finalize():
                    yield event
                
                # Normal completion - save all blocks
                async for event in handle_completion(
                    tool_call_handler, text_handler, plan_handler, persistence, context, state, config
                ):
                    yield event
        
        except Exception as e:
            async for event in handle_error(
                e, tool_call_handler, persistence, context, agent, config, run_data
            ):
                yield event
        finally:
            if thread_id in run_configs:
                del run_configs[thread_id]
    
    return EventSourceResponse(event_generator())

@router.get("/result/{thread_id}", response_model=GraphResponse)
def get_streaming_result(thread_id: str, agent_service: AgentService = Depends(get_agent_service)):
    """
    Get the final complete GraphResponse after streaming completes.
    This provides all the structured data the UI needs (steps, final_result, etc.)
    """
    agent = agent_service.get_agent()
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # Get the final state from the agent
        state = agent.graph.get_state(config)
        if not state:
            raise HTTPException(status_code=404, detail=f"No graph execution found for thread_id: {thread_id}")
        
        next_nodes = state.next
        values = state.values
        query = values.get("query", "")
        checkpoint_id = None
        
        if hasattr(state, 'config') and state.config and 'configurable' in state.config:
            configurable = state.config['configurable']
            if 'checkpoint_id' in configurable:
                checkpoint_id = str(configurable['checkpoint_id'])
        
        if next_nodes and "human_feedback" in next_nodes:
            # Still waiting for user feedback
            execution_status = "user_feedback"
            assistant_response = values.get("assistant_response") or values.get("plan", "Plan generated - awaiting approval")
            plan = values.get("plan", "")
            
            return GraphResponse(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                query=query,
                run_status=execution_status,
                assistant_response=assistant_response,
                plan=plan,
                steps=values.get("steps", []),
                final_result=None,
                total_time=None,
                overall_confidence=None
            )
        else:
            # Execution completed - build complete response
            execution_status = "finished"
            messages = values.get("messages", [])
            
            # Get the last AI message as the assistant response
            assistant_response = ""
            for msg in reversed(messages):
                if (hasattr(msg, 'content') and msg.content and 
                    type(msg).__name__ == 'AIMessage' and
                    (not hasattr(msg, 'tool_calls') or not msg.tool_calls)):
                    assistant_response = msg.content
                    break
            
            steps = values.get("steps", [])
            plan = values.get("plan", "")
            
            # Calculate metrics if we have steps
            total_time = None
            overall_confidence = None
            final_result = None
            
            if steps:
                # Calculate overall confidence
                confidences = [step.get("confidence", 0.8) for step in steps if "confidence" in step]
                overall_confidence = sum(confidences) / len(confidences) if confidences else 0.8
                
                from src.models.schemas import FinalResult
                final_result = FinalResult(
                    summary=assistant_response[:200] + "..." if len(assistant_response) > 200 else assistant_response,
                    details=f"Executed {len(steps)} steps successfully",
                    source="Database query execution",
                    inference="Based on database analysis and tool execution",
                    extra_explanation=f"Plan: {plan}"
                )
            
            return GraphResponse(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                query=query,
                run_status=execution_status,
                assistant_response=assistant_response,
                plan=plan,
                steps=steps,
                final_result=final_result,
                total_time=total_time,
                overall_confidence=overall_confidence
            )
            
    except Exception as e:
        error_message = str(e) if e else "Unknown error occurred"
        return GraphResponse(
            thread_id=thread_id,
            checkpoint_id=None,
            query="",
            run_status="error",
            assistant_response="",
            error=error_message
        )