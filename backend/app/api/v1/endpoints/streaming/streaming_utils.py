from typing import Dict, List, Optional, Any, AsyncGenerator
import json
import logging
from uuid import uuid4

from app.api.v1.endpoints.streaming.handlers import (
    ToolCallHandler,
    TextContentHandler,
    PlanContentHandler,
    StreamContext
)
from app.api.v1.endpoints.streaming.streaming_persistence import StreamingMessagePersistence

logger = logging.getLogger(__name__)


def _extract_checkpoint_id(state: Any) -> Optional[str]:
    try:
        if hasattr(state, 'config') and state.config and 'configurable' in state.config:
            configurable = state.config['configurable']
            if 'checkpoint_id' in configurable:
                return str(configurable['checkpoint_id'])
    except Exception:
        pass
    return None


def _serialize_interrupt(interrupt_data: Any) -> Dict:
    try:
        if hasattr(interrupt_data, 'value'):
            return interrupt_data.value
        elif hasattr(interrupt_data, '__dict__'):
            return interrupt_data.__dict__
        elif isinstance(interrupt_data, dict):
            return interrupt_data
        else:
            return {"raw": str(interrupt_data)}
    except Exception as e:
        logger.error(f"Failed to serialize interrupt: {e}")
        return {"error": "Failed to serialize interrupt"}


def _build_additional_blocks(
    values: Dict,
    checkpoint_id: Optional[str],
    context: StreamContext
) -> List[Dict]:
    blocks = []
    
    steps = values.get("steps", [])
    if steps and len(steps) > 0 and checkpoint_id:
        blocks.append({
            "id": f"explorer_{checkpoint_id}",
            "type": "explorer",
            "needsApproval": False,
            "data": {"checkpointId": checkpoint_id}
        })
    
    visualizations = values.get("visualizations", [])
    if visualizations and len(visualizations) > 0 and checkpoint_id:
        blocks.append({
            "id": f"viz_{checkpoint_id}",
            "type": "visualizations",
            "needsApproval": False,
            "data": {"checkpointId": checkpoint_id}
        })
    
    error_explanation = values.get("error_explanation")
    if error_explanation:
        error_block_id = f"error_{context.assistant_message_id or str(uuid4())}"
        blocks.append({
            "id": error_block_id,
            "type": "error",
            "needsApproval": False,
            "data": error_explanation
        })
        logger.info(f"Added error explanation block: {error_block_id}")
    
    return blocks


def _build_completion_payload(
    values: Dict,
    checkpoint_id: Optional[str],
    thread_id: str,
    assistant_response: str,
    query: str,
    plan: str,
    steps: List,
    overall_confidence: Optional[float]
) -> Dict:
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
    
    return {
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


async def _emit_visualization_events(
    values: Dict,
    checkpoint_id: Optional[str]
) -> AsyncGenerator[Dict, None]:
    try:
        from app.api.v1.endpoints.graph import _normalize_visualizations
    except Exception:
        _normalize_visualizations = lambda v: v if isinstance(v, list) else []
    
    visualizations = _normalize_visualizations(values.get("visualizations", []))
    
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
                "thread_id": values.get("thread_id"),
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


async def handle_tool_interrupt(
    interrupt_data: Any,
    tool_handler: ToolCallHandler,
    persistence: StreamingMessagePersistence,
    context: StreamContext,
    state: Any,
    config: Dict
) -> AsyncGenerator[Dict, None]:
    logger.info(f"Tool interrupt detected - thread_id: {context.thread_id}")
    
    interrupt_dict = _serialize_interrupt(interrupt_data)
    
    content_blocks = tool_handler.get_content_blocks(needs_approval=True)
    
    values = getattr(state, 'values', {}) or {}
    checkpoint_id = _extract_checkpoint_id(state)
    
    user_id = config.get('configurable', {}).get('user_id')
    await persistence.save_with_content_blocks(
        thread_id=context.thread_id,
        user_id=user_id,
        assistant_message_id=context.assistant_message_id,
        content_blocks=content_blocks,
        checkpoint_id=checkpoint_id,
        needs_approval=False
    )
    
    yield {
        "event": "status",
        "data": json.dumps({
            "status": "user_feedback",
            "thread_id": context.thread_id,
            "__interrupt__": [{"value": interrupt_dict}]
        })
    }


async def handle_plan_approval(
    tool_handler: ToolCallHandler,
    text_handler: TextContentHandler,
    plan_handler: PlanContentHandler,
    persistence: StreamingMessagePersistence,
    context: StreamContext,
    state: Any,
    config: Dict
) -> AsyncGenerator[Dict, None]:
    values = getattr(state, 'values', {}) or {}
    response_type = values.get("response_type")
    
    if response_type == "replan":
        logger.info(f"Replan detected - clearing previous approvals in thread {context.thread_id}")
        await persistence.clear_previous_approvals(context.thread_id)
    
    # Determine if approval is needed based on response type
    needs_approval = response_type in ["plan", "replan"]
    
    content_blocks = []
    content_blocks.extend(tool_handler.get_content_blocks())
    content_blocks.extend(plan_handler.get_content_blocks(needs_approval=needs_approval))
    content_blocks.extend(text_handler.get_content_blocks())
    
    checkpoint_id = _extract_checkpoint_id(state)
    if values.get("steps") and checkpoint_id:
        content_blocks.append({
            "id": f"explorer_{checkpoint_id}",
            "type": "explorer",
            "needsApproval": True,
            "data": {"checkpointId": checkpoint_id}
        })
    
    user_id = config.get('configurable', {}).get('user_id')
    await persistence.save_with_content_blocks(
        thread_id=context.thread_id,
        user_id=user_id,
        assistant_message_id=context.assistant_message_id,
        content_blocks=content_blocks,
        checkpoint_id=checkpoint_id,
        needs_approval=needs_approval
    )
    
    # Always emit user_feedback status since we're in human_feedback node waiting for user input
    yield {"event": "status", "data": json.dumps({"status": "user_feedback"})}


async def handle_completion(
    tool_handler: ToolCallHandler,
    text_handler: TextContentHandler,
    plan_handler: PlanContentHandler,
    persistence: StreamingMessagePersistence,
    context: StreamContext,
    state: Any,
    config: Dict
) -> AsyncGenerator[Dict, None]:
    values = getattr(state, 'values', {}) or {}
    
    content_blocks = []
    
    # Include existing blocks (plan, text) if they were loaded during resume
    if hasattr(context, 'existing_blocks') and context.existing_blocks:
        content_blocks.extend(context.existing_blocks)
        logger.info(f"Including {len(context.existing_blocks)} existing blocks from context")
    
    
    # Add blocks that were tracked during streaming (already in correct order)
    content_blocks.extend(context.completed_blocks)
    logger.info(f"Collected {len(context.completed_blocks)} blocks from stream in order")
    
    checkpoint_id = _extract_checkpoint_id(state)
    content_blocks.extend(_build_additional_blocks(values, checkpoint_id, context))
    
    # No need to sort - blocks are already in stream order!
    
    user_id = config.get('configurable', {}).get('user_id')
    await persistence.save_with_content_blocks(
        thread_id=context.thread_id,
        user_id=user_id,
        assistant_message_id=context.assistant_message_id,
        content_blocks=content_blocks,
        checkpoint_id=checkpoint_id,
        needs_approval=False
    )
    
    yield {"event": "status", "data": json.dumps({"status": "finished"})}
    
    messages = values.get("messages", [])
    assistant_response = ""
    for m in reversed(messages):
        if (hasattr(m, 'content') and m.content and type(m).__name__ == 'AIMessage' and 
            (not hasattr(m, 'tool_calls') or not m.tool_calls)):
            assistant_response = m.content
            break
    
    steps = values.get("steps", [])
    overall_confidence = None
    if steps:
        confidences = [s.get("confidence", 0.8) for s in steps if isinstance(s, dict) and "confidence" in s]
        overall_confidence = (sum(confidences) / len(confidences)) if confidences else 0.8
    
    completion_payload = _build_completion_payload(
        values=values,
        checkpoint_id=checkpoint_id,
        thread_id=context.thread_id,
        assistant_response=assistant_response,
        query=values.get("query", ""),
        plan=values.get("plan", ""),
        steps=steps,
        overall_confidence=overall_confidence
    )
    yield {"event": "completed", "data": json.dumps(completion_payload)}
    
    async for viz_event in _emit_visualization_events(values, checkpoint_id):
        yield viz_event


async def handle_error(
    error: Exception,
    tool_handler: ToolCallHandler,
    persistence: StreamingMessagePersistence,
    context: StreamContext,
    agent: Any,
    config: Dict,
    run_data: Dict
) -> AsyncGenerator[Dict, None]:
    error_message = str(error) if error else "Unknown error occurred"
    logger.error(f"Streaming error for thread {context.thread_id}: {error_message}", exc_info=True)
    
    if not context.assistant_message_id:
        context.assistant_message_id = str(uuid4())
        run_data["assistant_message_id"] = context.assistant_message_id
    
    # Flush pending tool calls with error state
    for tool_key, tool_state in list(tool_handler.pending_tools.items()):
        tool_call_id = tool_state.tool_call_id
        
        parsed_args = {}
        if tool_state.args:
            try:
                parsed_args = json.loads(tool_state.args)
            except json.JSONDecodeError:
                parsed_args = {}
        
        if tool_call_id not in tool_handler.completed_tools:
            tool_handler.completed_tools[tool_call_id] = {
                "id": f"tool_{tool_call_id}",
                "type": "tool_calls",
                "sequence": tool_state.sequence,
                "needsApproval": False,
                "data": {
                    "toolCalls": [],
                    "content": tool_state.content
                }
            }
        
        tool_handler.completed_tools[tool_call_id]["data"]["toolCalls"].append({
            "name": tool_state.tool_name,
            "input": parsed_args,
            "output": f"Error: {error_message}",
            "status": "error",
            "error": error_message
        })
        
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "tool_calls",
                "block_id": f"tool_{tool_call_id}",
                "tool_call_id": tool_call_id,
                "tool_name": tool_state.tool_name,
                "node": "agent",
                "input": parsed_args,
                "error": error_message,
                "action": "update_tool_error"
            })
        }
    
    tool_handler.pending_tools.clear()
    
    error_block_id = f"error_{context.assistant_message_id or str(uuid4())}"
    yield {
        "event": "content_block",
        "data": json.dumps({
            "block_type": "text",
            "block_id": error_block_id,
            "content": f"Error: {error_message}",
            "node": "agent",
            "message_id": context.assistant_message_id,
            "action": "append_error"
        })
    }
    
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
            checkpoint_id = _extract_checkpoint_id(state)
    except Exception:
        pass
    
    user_id = config.get('configurable', {}).get('user_id')
    content_blocks = []
    
    sorted_tool_calls = sorted(
        tool_handler.completed_tools.items(),
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
    
    saved_error_message = await persistence.save_with_content_blocks(
        thread_id=context.thread_id,
        user_id=user_id,
        assistant_message_id=context.assistant_message_id,
        content_blocks=content_blocks,
        checkpoint_id=checkpoint_id,
        needs_approval=False
    )
    
    yield {
        "event": "status",
        "data": json.dumps({
            "status": "error",
            "error": error_message
        })
    }
    
    error_payload = {
        "success": False,
        "data": {
            "thread_id": context.thread_id,
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


async def check_for_interrupts(state: Any) -> Optional[Any]:
    interrupt_data = None
    try:
        if hasattr(state, 'tasks') and state.tasks:
            logger.info(f"Checking {len(state.tasks)} tasks for interrupts")
            for idx, task in enumerate(state.tasks):
                logger.debug(f"Task {idx}: has interrupts attr = {hasattr(task, 'interrupts')}")
                if hasattr(task, 'interrupts') and task.interrupts:
                    interrupt_data = task.interrupts[0]
                    logger.info(f"Tool interrupt found in task {idx}: {type(interrupt_data)}")
                    break
        else:
            logger.debug(f"No tasks in state (hasattr={hasattr(state, 'tasks')}, tasks={getattr(state, 'tasks', None)})")
    except Exception as e:
        logger.error(f"Error checking for interrupts: {e}", exc_info=True)
    
    return interrupt_data
