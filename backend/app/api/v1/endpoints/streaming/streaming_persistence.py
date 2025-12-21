"""
Message persistence service for streaming graph responses.

Handles saving and loading assistant messages during streaming.
"""

from typing import Dict, List, Optional, Tuple, Any
import json
import logging

from app.services.message_management_service import MessageManagementService

logger = logging.getLogger(__name__)


class StreamingMessagePersistence:
    """Handles message persistence during streaming"""
    
    def __init__(self, message_service: MessageManagementService):
        self.message_service = message_service
    
    async def save_with_content_blocks(
        self,
        thread_id: str,
        user_id: str,
        assistant_message_id: str,
        content_blocks: List[Dict],
        checkpoint_id: Optional[str] = None,
        needs_approval: bool = False
    ) -> Optional[Any]:
        """Save assistant message with content blocks"""
        try:
            logger.info(
                f"Saving assistant message - thread: {thread_id}, "
                f"message_id: {assistant_message_id}, "
                f"blocks: {len(content_blocks)}, "
                f"needs_approval: {needs_approval}"
            )
            
            saved_message = await self.message_service.save_assistant_message(
                thread_id=thread_id,
                content=content_blocks,
                checkpoint_id=checkpoint_id,
                needs_approval=needs_approval,
                message_id=assistant_message_id,
                user_id=user_id
            )
            
            logger.info(
                f"Successfully saved message {saved_message.id if saved_message else 'None'} "
                f"(UUID: {saved_message.message_id if saved_message else 'None'})"
            )
            return saved_message
            
        except Exception as e:
            logger.error(f"Failed to save message: {e}", exc_info=True)
            return None
    
    async def load_existing_blocks(
        self,
        thread_id: str,
        assistant_message_id: str
    ) -> Tuple[Dict[str, Dict], Dict[str, Dict], List[Dict]]:
        """Load existing blocks from database. Returns (completed_tools, pending_tools, other_blocks)"""
        completed_tools = {}
        pending_tools = {}
        other_blocks = []  # Plan, text, and other non-tool blocks
        
        try:
            logger.info(f"Loading existing blocks for message {assistant_message_id}")
            existing_message = await self.message_service._get_message_by_id(
                thread_id, assistant_message_id
            )
            
            if not existing_message or not existing_message.content:
                logger.warning("No existing message found or message has no content")
                return completed_tools, pending_tools, other_blocks
            
            logger.info(f"Found existing message with {len(existing_message.content)} content blocks")
            
            for idx, block in enumerate(existing_message.content):
                block_type = block.get('type')
                block_id = block.get('id', '')
                needs_approval = block.get('needsApproval', False)
                
                logger.info(
                    f"  Block {idx}: type={block_type}, id={block_id}, "
                    f"needsApproval={needs_approval}"
                )
                
                if block_type == 'tool_calls':
                    tool_call_id = block_id.replace('tool_', '')
                    tool_calls_data = block.get('data', {}).get('toolCalls', [])
                    has_output = any(tc.get('output') is not None for tc in tool_calls_data)
                    
                    logger.info(
                        f"    Tool calls count: {len(tool_calls_data)}, "
                        f"has_output: {has_output}"
                    )
                    
                    if has_output:
                        # Completed tool - preserve it
                        completed_tools[tool_call_id] = block
                        logger.info(f"    ✓ Loaded completed tool block: {tool_call_id}")
                    elif needs_approval:
                        # Pending tool awaiting approval
                        if tool_call_id and tool_calls_data:
                            for tc in tool_calls_data:
                                tool_name = tc.get('name')
                                tool_input = tc.get('input', {})
                                args_str = json.dumps(tool_input) if tool_input else ''
                                pending_tools[tool_call_id] = {
                                    'tool_call_id': tool_call_id,
                                    'tool_name': tool_name,
                                    'args': args_str,
                                    'sequence': block.get('sequence', 0)
                                }
                                logger.info(f"    ✓ Loaded pending tool: {tool_call_id} ({tool_name})")
                    else:
                        logger.info("    ✗ Skipping tool block without output")
                else:
                    # Preserve plan, text, and other block types
                    other_blocks.append(block)
                    logger.info(f"    ✓ Loaded {block_type} block: {block_id}")
            
            logger.info(
                f"Loaded {len(completed_tools)} completed tools, "
                f"{len(pending_tools)} pending tools, "
                f"{len(other_blocks)} other blocks"
            )
            
        except Exception as e:
            logger.error(f"Failed to load existing blocks: {e}", exc_info=True)
        
        return completed_tools, pending_tools, other_blocks
    

    
    async def clear_previous_approvals(self, thread_id: str):
        """Clear previous approval flags (for replans)"""
        try:
            await self.message_service.clear_previous_approvals(thread_id)
        except Exception as e:
            logger.error(f"Failed to clear previous approvals: {e}", exc_info=True)
