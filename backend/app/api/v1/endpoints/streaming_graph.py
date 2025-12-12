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
from app.services.dependencies import get_message_management_service
from app.services.message_management_service import MessageManagementService
from app.services.agent_service import AgentService
from app.models.supabase_user import SupabaseUser
from app.core.auth import get_current_user

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
    """Robustly extracts a stream ID (string) or message ID (int) from a chunk,
    falling back to a dynamic timestamp if needed."""
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
    
    assistant_message_id = str(uuid4())
    run_configs[thread_id] = {
        "type": "resume",
        "review_action": request.review_action,
        "human_comment": request.human_comment,
        "assistant_message_id": assistant_message_id,
        "user_id": user_id  # Store user_id for streaming
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
    
    text_block_id = run_data.get("text_block_id")
    if not text_block_id:
        text_block_id = f"text_run--{uuid4()}"
        run_data["text_block_id"] = text_block_id
    
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
            visualizations=[]
        )
        input_state = initial_state
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
        buffer = ""
        
        # Log config details before streaming starts
        config_user_id = config.get('configurable', {}).get('user_id', 'NOT SET')
        logger.info(f"Starting stream event_generator - thread_id: {thread_id}, user_id in config: {config_user_id}")
        
        pending_tool_calls = {}
        tool_calls_content_blocks = {}
        
        initial_data = json.dumps({"thread_id": thread_id})
        yield {"event": event_type, "data": initial_data}
        
        try:
            last_started_tool_id = None
            last_started_tool_name = None
            tool_call_sequence = 0  # Track order of tool calls
            
            # No need to track block IDs - just use stream_id directly as block_id
            
            for msg, metadata in agent.graph.stream(input_state, config, stream_mode="messages"):
                if await request.is_disconnected():
                    break
                
                node_name = metadata.get('langgraph_node', 'unknown')
                checkpoint_ns = metadata.get('langgraph_checkpoint_ns')
                if isinstance(checkpoint_ns, str):
                    normalized_checkpoint_ns = checkpoint_ns.replace(" ", "_")
                    if normalized_checkpoint_ns.startswith("assistant"):
                        logger.debug(f"Skipping chunk from assistant_keep_agent namespace: {checkpoint_ns}")
                        continue
         
                
                if hasattr(msg, 'tool_call_chunks') and msg.tool_call_chunks:
                    if node_name in ['agent']:
                        chunk = msg.tool_call_chunks[0]
                        chunk_dict = chunk if isinstance(chunk, dict) else chunk.dict() if hasattr(chunk, 'dict') else {}
                        chunk_id = chunk_dict.get('id')
                        chunk_index = chunk_dict.get('index', 0)
                        chunk_name = chunk_dict.get('name')
                        chunk_args_str = chunk_dict.get('args', '')
                        
                        if chunk_name == 'transfer_to_data_exploration':
                            continue
                        
                        tool_key = chunk_id if chunk_id else f"index_{chunk_index}"
                        
                        if chunk_id and chunk_name and tool_key not in pending_tool_calls:
                            tool_call_sequence += 1  # Increment for each new tool call
                            pending_tool_calls[tool_key] = {
                                'tool_name': chunk_name,
                                'node': node_name,
                                'tool_call_id': chunk_id,
                                'index': chunk_index,
                                'sequence': tool_call_sequence,  # Track order
                                'args': '',  # Accumulated args string
                                'output': None,  # Tool result content
                                'content': None,  # Tool explanation content
                                'saved': False
                            }
                            
                            tool_start_data = json.dumps({
                                "block_type": "tool_calls",
                                "block_id": f"tool_{chunk_id}",
                                "tool_call_id": chunk_id,
                                "tool_name": chunk_name,
                                "args": "",
                                "node": node_name,
                                "action": "start_tool_call"
                            })
                            yield {"event": "content_block", "data": tool_start_data}
                            
                            tool_add_block = json.dumps({
                                "block_type": "tool_calls",
                                "block_id": f"tool_{chunk_id}",
                                "tool_call_id": chunk_id,
                                "tool_name": chunk_name,
                                "node": node_name,
                                "action": "add_tool_call"
                            })
                            yield {"event": "content_block", "data": tool_add_block}
                            
                            last_started_tool_id = chunk_id
                            last_started_tool_name = chunk_name
                            
                            continue
                    
                        if chunk_args_str and last_started_tool_id in pending_tool_calls:
                            tool_info = pending_tool_calls.get(last_started_tool_id, {})
                            
                            pending_tool_calls[last_started_tool_id].setdefault('args', '')
                            pending_tool_calls[last_started_tool_id]['args'] += chunk_args_str
                            
                            tool_args_data = json.dumps({
                                "block_type": "tool_calls",
                                "block_id": f"tool_{tool_info['tool_call_id']}",
                                "tool_call_id": tool_info['tool_call_id'],
                                "tool_name": tool_info['tool_name'],
                                "args_chunk": chunk_args_str,
                                "node": node_name,
                                "action": "stream_args"
                            })
                            yield {"event": "content_block", "data": tool_args_data}
                
                elif hasattr(msg, 'tool_call_id') and hasattr(msg, 'content'):
                    tool_call_id = msg.tool_call_id
                    
                    tool_info = pending_tool_calls.get(tool_call_id)
                    if not tool_info:
                        for key, info in pending_tool_calls.items():
                            if info.get('tool_call_id') == tool_call_id:
                                tool_info = info
                                break
                    
                    if not tool_info:
                        tool_info = {'tool_name': 'unknown'}
                    
                    tool_name = tool_info.get('tool_name', 'unknown')
                    
                    if tool_name == 'transfer_to_data_exploration':
                        for key in list(pending_tool_calls.keys()):
                            if pending_tool_calls[key].get('tool_call_id') == tool_call_id:
                                del pending_tool_calls[key]
                                break
                        continue
                    
                    tool_key_for_output = None
                    if tool_call_id in pending_tool_calls:
                        tool_key_for_output = tool_call_id
                    else:
                        for key, info in pending_tool_calls.items():
                            if info.get('tool_call_id') == tool_call_id:
                                tool_key_for_output = key
                                break
                    
                    if tool_key_for_output:
                        pending_tool_calls[tool_key_for_output]['output'] = msg.content
                    
                    args_str = tool_info.get('args', '')
                    parsed_args = {}
                    if args_str:
                        try:
                            parsed_args = json.loads(args_str)
                        except json.JSONDecodeError:
                            parsed_args = {}
                    
                    tool_call_object = {
                        "name": tool_name,
                        "input": parsed_args,
                        "output": msg.content,
                        "status": "approved"
                    }
                    
                    if tool_call_id not in tool_calls_content_blocks:
                        tool_calls_content_blocks[tool_call_id] = {
                            "id": f"tool_{tool_call_id}",
                            "type": "tool_calls",
                            "sequence": tool_info.get('sequence', 0),  # Store sequence for sorting
                            "needsApproval": False,
                            "data": {
                                "toolCalls": [tool_call_object],
                                "content": tool_info.get('content') or None
                            }
                        }
                    else:
                        tool_calls_content_blocks[tool_call_id]["data"]["toolCalls"].append(tool_call_object)
                    
                    if tool_key_for_output:
                        pending_tool_calls[tool_key_for_output]['saved'] = True
                    
                    tool_result_data = json.dumps({
                        "block_type": "tool_calls",
                        "block_id": f"tool_{tool_call_id}",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "node": node_name,
                        "input": parsed_args, 
                        "output": msg.content,
                        "action": "update_tool_result"
                    })
                    yield {"event": "content_block", "data": tool_result_data}
                    
                    # Tool finished - clean up tracking entry
                    if tool_key_for_output and tool_key_for_output in pending_tool_calls:
                        del pending_tool_calls[tool_key_for_output]
                        if last_started_tool_id == tool_key_for_output:
                            last_started_tool_id = None
                            last_started_tool_name = None
                
                elif hasattr(msg, 'content') and msg.content:
                    if type(msg).__name__ in ['AIMessageChunk']:
                        active_tool_id = None
                        if last_started_tool_id and last_started_tool_id in pending_tool_calls:
                            active_tool_id = last_started_tool_id
                        
                        if active_tool_id:
                            if active_tool_id in pending_tool_calls:
                                if pending_tool_calls[active_tool_id].get('content') is None:
                                    pending_tool_calls[active_tool_id]['content'] = ''
                                pending_tool_calls[active_tool_id]['content'] += msg.content
                            
                            if active_tool_id in tool_calls_content_blocks:
                                if tool_calls_content_blocks[active_tool_id]["data"].get("content") is None:
                                    tool_calls_content_blocks[active_tool_id]["data"]["content"] = ''
                                tool_calls_content_blocks[active_tool_id]["data"]["content"] += msg.content
                            
                            tool_expl_chunk = json.dumps({
                                "block_type": "tool_calls",
                                "block_id": f"tool_{active_tool_id}",
                                "tool_call_id": active_tool_id,
                                "tool_name": last_started_tool_name,
                                "content": msg.content,
                                "node": node_name,
                                "action": "update_tool_calls_explanation"
                            })
                            yield {"event": "content_block", "data": tool_expl_chunk}
                            continue
                        
                        if node_name not in ['planner', 'agent']:
                            continue
                        
                        chunk_text = msg.content
                        msg_id = _extract_stream_or_message_id(msg, preferred_key='message_id')
                        if chunk_text.startswith("{") or buffer:
                            buffer += chunk_text
                            try:
                                parsed = json.loads(buffer)
                                yield {
                                    "event": "message",
                                    "data": json.dumps({
                                        "content": parsed.get("content", ""),
                                        "node": node_name,
                                        "type": "feedback_answer",
                                        "stream_id": msg_id
                                    })
                                }
                                buffer = ""
                                
                            except json.JSONDecodeError:
                                continue
                        else:
                            # Use text_block_id to ensure consistency with DB
                            token_data = json.dumps({
                                "block_type": "text",
                                "block_id": text_block_id, # Use consistent ID
                                "content": msg.content,
                                "node": node_name,
                                "stream_id": msg_id,
                                "message_id": assistant_message_id,
                                "action": "append_text"
                            })
                            yield {"event": "content_block", "data": token_data}

                    elif type(msg).__name__ in ['AIMessage']:
                        msg_id_final = _extract_stream_or_message_id(msg, preferred_key='stream_id')
                        
                        if node_name == 'tool_explanation' and last_started_tool_id:
                            if last_started_tool_id in pending_tool_calls:
                                if pending_tool_calls[last_started_tool_id].get('content') is None:
                                    pending_tool_calls[last_started_tool_id]['content'] = ''
                                pending_tool_calls[last_started_tool_id]['content'] += msg.content
                            
                            if last_started_tool_id in tool_calls_content_blocks:
                                if tool_calls_content_blocks[last_started_tool_id]["data"].get("content") is None:
                                    tool_calls_content_blocks[last_started_tool_id]["data"]["content"] = ''
                                tool_calls_content_blocks[last_started_tool_id]["data"]["content"] += msg.content
                            
                            tool_expl_final = json.dumps({
                                "block_type": "tool_calls",
                                "block_id": f"tool_{last_started_tool_id}",
                                "tool_id": last_started_tool_id,
                                "tool_name": last_started_tool_name,
                                "content": msg.content,
                                "node": node_name,
                                "action": "update_tool_calls_explanation"
                            })
                            yield {"event": "content_block", "data": tool_expl_final}
                            continue
                        
                        # Use text_block_id to ensure consistency with DB
                        yield {"event": "content_block", "data": json.dumps({
                            "block_type": "text",
                            "block_id": text_block_id, # Use consistent ID
                            "content": msg.content,
                            "node": node_name,
                            "message_id": assistant_message_id,
                            "action": "finalize_text"
                        })}
            
            # After streaming completes, emit final payloads
            state = agent.graph.get_state(config)
            values = getattr(state, 'values', {}) or {}
            messages = values.get("messages", [])
            steps = values.get("steps", [])
            plan = values.get("plan", "")
            query = values.get("query", "")
            # Determine assistant final response and its message_id
            assistant_response = ""
            assistant_message_id_from_state: int | None = None
            for m in reversed(messages):
                if (hasattr(m, 'content') and m.content and type(m).__name__ == 'AIMessage' and (not hasattr(m, 'tool_calls') or not m.tool_calls)):
                    assistant_response = m.content
                    # Extract a numeric message id if present
                    try:
                        extracted = _extract_stream_or_message_id(m, preferred_key='message_id')
                        assistant_message_id_from_state = int(extracted) if isinstance(extracted, (int, str)) and str(extracted).isdigit() else None
                    except Exception:
                        assistant_message_id_from_state = None
                    break
            
            if assistant_message_id is None:
                assistant_message_id = assistant_message_id_from_state or run_data.get("assistant_message_id")
            run_data["assistant_message_id"] = assistant_message_id

            # Compute checkpoint_id if present
            checkpoint_id = None
            try:
                if hasattr(state, 'config') and state.config and 'configurable' in state.config:
                    configurable = state.config['configurable']
                    if 'checkpoint_id' in configurable:
                        checkpoint_id = str(configurable['checkpoint_id'])
            except Exception:
                checkpoint_id = None

            # Overall confidence
            overall_confidence = None
            if steps:
                confidences = [s.get("confidence", 0.8) for s in steps if isinstance(s, dict) and "confidence" in s]
                overall_confidence = (sum(confidences) / len(confidences)) if confidences else 0.8

            # Build final_result summary
            try:
                from src.models.schemas import FinalResult
                final_result_summary = FinalResult(
                    summary=assistant_response,
                    details=f"Executed {len(steps)} steps successfully",
                    source="Database query execution",
                    inference="Based on database analysis and tool execution",
                    extra_explanation=f"Plan: {plan}"
                )
                final_result_dict = final_result_summary.model_dump()
            except Exception:
                final_result_dict = {
                    "summary": (assistant_response[:200] + "...") if isinstance(assistant_response, str) and len(assistant_response) > 200 else assistant_response,
                    "details": f"Executed {len(steps)} steps successfully",
                    "source": "Database query execution",
                    "inference": "Based on database analysis and tool execution",
                    "extra_explanation": f"Plan: {plan}"
                }

            if state.next and 'human_feedback' in state.next:
                response_type = values.get("response_type")
                if assistant_response and message_service:
                    try:
                        if response_type == "replan":
                            logger.info(f"Replan detected in streaming - clearing needs_approval from previous messages in thread {thread_id}")
                            await message_service.clear_previous_approvals(thread_id)
                        
                        content_blocks = []

                        # Sort by sequence to preserve tool call order
                        sorted_tool_calls = sorted(
                            tool_calls_content_blocks.items(), 
                            key=lambda x: x[1].get('sequence', 0)
                        )
                        for tool_call_id, content_block in sorted_tool_calls:
                            if len(content_block["data"]["toolCalls"]) > 0:
                                content_blocks.append(content_block)

                        if assistant_response:
                            content_blocks.append({
                                "id": text_block_id or f"text_{assistant_message_id or str(uuid4())}",
                                "type": "text",
                                "needsApproval": True,
                                "data": {"text": assistant_response}
                            })
                        
                        if steps and len(steps) > 0 and checkpoint_id:
                            content_blocks.append({
                                "id": f"explorer_{checkpoint_id}",
                                "type": "explorer",
                                "needsApproval": True,
                                "data": {"checkpointId": checkpoint_id}
                            })
                        
                        logger.info(f"Calling save_assistant_message for approval with thread_id: {thread_id}, user_id: {user_id}, message_id: {assistant_message_id}, checkpoint_id: {checkpoint_id}, content_blocks count: {len(content_blocks)}")
                        saved_message = await message_service.save_assistant_message(
                            thread_id=thread_id,
                            content=content_blocks,
                            message_type="structured",
                            checkpoint_id=checkpoint_id,
                            needs_approval=True,
                            message_id=assistant_message_id,
                            user_id=user_id
                        )
                        logger.info(f"Successfully saved assistant message {saved_message.id if saved_message else 'None'} (UUID: {saved_message.message_id if saved_message else 'None'}) for approval in thread {thread_id}")
                    except Exception as e:
                        logger.error(f"Failed to save assistant message for approval in thread {thread_id}: {e}")
                
                status_data = json.dumps({"status": "user_feedback"})
                yield {"event": "status", "data": status_data}
            else:
                status_data = json.dumps({"status": "finished"})
                yield {"event": "status", "data": status_data}

                try:
                    content_blocks = []
                    
                    # Sort by sequence to preserve tool call order
                    sorted_tool_calls = sorted(
                        tool_calls_content_blocks.items(), 
                        key=lambda x: x[1].get('sequence', 0)
                    )
                    for tool_call_id, content_block in sorted_tool_calls:
                        if len(content_block["data"]["toolCalls"]) > 0:
                            content_blocks.append(content_block)

                    if assistant_response:
                            content_blocks.append({
                                "id": text_block_id or f"text_{assistant_message_id or str(uuid4())}",
                                "type": "text",
                                "needsApproval": False,
                                "data": {"text": assistant_response}
                        })
                    
                    if steps and len(steps) > 0 and checkpoint_id:
                        content_blocks.append({
                            "id": f"explorer_{checkpoint_id}",
                            "type": "explorer", 
                            "needsApproval": False,
                                "data": {"checkpointId": checkpoint_id}
                        })
                    
                    visualizations = values.get("visualizations", [])
                    if visualizations and len(visualizations) > 0 and checkpoint_id:
                        content_blocks.append({
                            "id": f"viz_{checkpoint_id}",
                            "type": "visualizations",
                            "needsApproval": False,
                                "data": {"checkpointId": checkpoint_id}
                        })
                    
                    logger.info(f"Calling save_assistant_message for completion with thread_id: {thread_id}, user_id: {user_id}, message_id: {assistant_message_id}, checkpoint_id: {checkpoint_id}, content_blocks count: {len(content_blocks)}")
                    saved_completion_message = await message_service.save_assistant_message(
                        thread_id=thread_id,
                        content=content_blocks,
                        message_type="structured",
                        checkpoint_id=checkpoint_id,
                        needs_approval=False,
                        message_id=assistant_message_id,
                        user_id=user_id
                    )
                    logger.info(f"Successfully saved assistant completion message {saved_completion_message.id if saved_completion_message else 'None'} (UUID: {saved_completion_message.message_id if saved_completion_message else 'None'}) in thread {thread_id}")
                        
                except Exception as e:
                    logger.error(f"Failed to save completion messages for thread {thread_id}: {e}", exc_info=True)

                # Emit enriched completed payload
                completed_payload = {
                    "success": True,
                    "data": {
                        "thread_id": thread_id,
                        "checkpoint_id": checkpoint_id,
                        "run_status": "finished",
                        "assistant_response": assistant_response,
                        "query": query,
                        "plan": plan,
                        "error": None,
                        "steps": steps,
                        "final_result": final_result_dict,
                        "total_time": None,
                        "overall_confidence": overall_confidence
                    },
                    "message": f"Explorer data retrieved successfully for checkpoint {checkpoint_id}" if checkpoint_id else "Explorer data retrieved successfully"
                }
                yield {"event": "completed", "data": json.dumps(completed_payload)}

                # Visualizations follow-up
                try:
                    from .graph import _normalize_visualizations  # reuse normalization helper
                except Exception:
                    _normalize_visualizations = lambda v: v if isinstance(v, list) else []
                visualizations = _normalize_visualizations(values.get("visualizations", []))
                
                # Emit visualization content block if visualizations exist
                if visualizations and len(visualizations) > 0 and checkpoint_id:
                    viz_block_data = json.dumps({
                        "block_type": "visualizations",
                        "block_id": f"viz_{checkpoint_id}",
                        "checkpoint_id": checkpoint_id,
                        "visualizations": visualizations,
                        "count": len(visualizations),
                        "types": list({v.get("type") for v in visualizations if isinstance(v, dict) and v.get("type")}),
                        "action": "add_visualizations"
                    })
                    yield {"event": "content_block", "data": viz_block_data}
                
                try:
                    visualization_types = list({v.get("type") for v in visualizations if isinstance(v, dict) and v.get("type")})
                    visualizations_payload = {
                        "success": True,
                        "data": {
                            "thread_id": thread_id,
                            "checkpoint_id": checkpoint_id,
                            "visualizations": visualizations,
                            "count": len(visualizations),
                            "types": visualization_types
                        },
                        "message": f"Visualization data retrieved successfully for checkpoint {checkpoint_id}" if checkpoint_id else "Visualization data retrieved successfully"
                    }
                    yield {"event": "visualizations_ready", "data": json.dumps(visualizations_payload)}
                except Exception:
                    pass
                
            pending_tool_calls.clear()
            tool_calls_content_blocks.clear()
                
            if thread_id in run_configs:
                del run_configs[thread_id]
                
        except Exception as e:
            error_message = str(e) if e else "Unknown error occurred"
            logger.error(f"Streaming graph error for thread {thread_id}: {error_message}", exc_info=True)
            
            # Ensure assistant_message_id exists for error tracking
            if not assistant_message_id:
                assistant_message_id = str(uuid4())
                run_data["assistant_message_id"] = assistant_message_id
            
            # Flush any pending tool calls with error state
            def _parse_args(args_str: str) -> Dict[str, Any]:
                if not args_str:
                    return {}
                try:
                    return json.loads(args_str)
                except json.JSONDecodeError:
                    return {}
            
            for pending_id, tool_info in list(pending_tool_calls.items()):
                tool_call_id = tool_info.get('tool_call_id') or pending_id
                tool_name = tool_info.get('tool_name', 'unknown')
                parsed_args = _parse_args(tool_info.get('args', ''))
                
                if tool_call_id not in tool_calls_content_blocks:
                    tool_calls_content_blocks[tool_call_id] = {
                        "id": f"tool_{tool_call_id}",
                        "type": "tool_calls",
                        "sequence": tool_info.get('sequence', 0),
                        "needsApproval": False,
                        "data": {
                            "toolCalls": [],
                            "content": tool_info.get('content') or None
                        }
                    }
                
                tool_calls_content_blocks[tool_call_id]["data"]["toolCalls"].append({
                    "name": tool_name,
                    "input": parsed_args,
                    "output": f"Error: {error_message}",
                    "status": "error",
                    "error": error_message
                })
                
                tool_error_event = json.dumps({
                    "block_type": "tool_calls",
                    "block_id": f"tool_{tool_call_id}",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "node": "agent",
                    "input": parsed_args,
                    "error": error_message,
                    "action": "update_tool_error"
                })
                yield {"event": "content_block", "data": tool_error_event}
            
            pending_tool_calls.clear()
            last_started_tool_id = None
            last_started_tool_name = None
            
            # Emit error text block for frontend visibility
            error_block_id = f"error_{assistant_message_id or str(uuid4())}"
            error_block_event = json.dumps({
                "block_type": "text",
                "block_id": error_block_id,
                "content": f"Error: {error_message}",
                "node": "agent",
                "message_id": assistant_message_id,
                "action": "append_error"
            })
            yield {"event": "content_block", "data": error_block_event}
            
            # Gather current graph state for context (best-effort)
            steps = []
            plan = ""
            query = run_data.get("human_request", "")
            checkpoint_id = None
            try:
                state = agent.graph.get_state(config)
                if state:
                    values = getattr(state, "values", {}) or {}
                    steps = values.get("steps", []) or []
                    plan = values.get("plan", "") or ""
                    query = values.get("query", query)
                    
                    if hasattr(state, 'config') and state.config and 'configurable' in state.config:
                        configurable = state.config['configurable']
                        if 'checkpoint_id' in configurable:
                            checkpoint_id = str(configurable['checkpoint_id'])
            except Exception:
                pass
            
            # Persist error message for backend history
            if message_service:
                try:
                    content_blocks = []
                    
                    sorted_tool_calls = sorted(
                        tool_calls_content_blocks.items(),
                        key=lambda x: x[1].get('sequence', 0)
                    )
                    for _, content_block in sorted_tool_calls:
                        if len(content_block["data"]["toolCalls"]) > 0:
                            content_blocks.append(content_block)
                    
                    content_blocks.append({
                        "id": error_block_id,
                        "type": "text",
                        "needsApproval": False,
                        "data": {"text": f"Error: {error_message}"}
                    })
                    
                    logger.info(f"Calling save_assistant_message for error with thread_id: {thread_id}, user_id: {user_id}, message_id: {assistant_message_id}, checkpoint_id: {checkpoint_id}, content_blocks count: {len(content_blocks)}")
                    saved_error_message = await message_service.save_assistant_message(
                        thread_id=thread_id,
                        content=content_blocks,
                        message_type="structured",
                        checkpoint_id=checkpoint_id,
                        needs_approval=False,
                        message_id=assistant_message_id,
                        user_id=user_id
                    )
                    logger.info(f"Successfully saved assistant error message {saved_error_message.id if saved_error_message else 'None'} (UUID: {saved_error_message.message_id if saved_error_message else 'None'}) in thread {thread_id}")
                    
                    await message_service.update_message_status(
                        thread_id=thread_id,
                        message_id=saved_error_message.id if saved_error_message else None,
                        message_status="error"
                    )
                except Exception as save_error:
                    logger.error(f"Failed to persist error message for thread {thread_id}: {save_error}")
            
            # Notify frontend about error status
            status_data = json.dumps({
                "status": "error",
                "error": error_message
            })
            yield {"event": "status", "data": status_data}
            
            error_payload = {
                "success": False,
                "data": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                    "run_status": "error",
                    "assistant_response": None,
                    "query": query,
                    "plan": plan,
                    "error": error_message,
                    "steps": steps,
                    "final_result": None,
                    "total_time": None,
                    "overall_confidence": None
                },
                "message": f"Execution failed: {error_message}"
            }
            yield {"event": "completed", "data": json.dumps(error_payload)}
            
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