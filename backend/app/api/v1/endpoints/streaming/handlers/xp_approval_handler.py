"""
XpAgent Approval Handler.
Handles simple boolean approval flow for XpAgent's plan execution.
"""

from typing import Dict, Any, AsyncGenerator, List, Optional
import json
import logging

from .base_handler import ContentHandler, StreamContext

logger = logging.getLogger(__name__)


class XpApprovalHandler(ContentHandler):
    """
    Handler for XpAgent's simple boolean approval flow.
    
    Unlike MainAgent's complex approval flow, XpAgent uses a simple
    approve/reject mechanism without retry or replan options.
    """
    
    def __init__(self, context: StreamContext, agent):
        super().__init__(context)
        self.agent = agent
        self.plan_content = ""
        self.steps = []
        self.needs_approval = False
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        """Check if this message is from XpAgent's planner node."""
        node_name = metadata.get('langgraph_node', 'unknown')
        return (
            node_name == 'planner' and
            hasattr(msg, 'content') and 
            msg.content and
            type(msg).__name__ == 'AIMessage'
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle XpAgent's plan output."""
        self.plan_content = msg.content
        
        # Get current state
        state = self.agent.graph.get_state(self.context.config)
        values = getattr(state, 'values', {}) or {}
        
        status = values.get("status", "")
        use_planning = values.get("use_planning", True)
        plan_data = values.get("plan", "")
        
        # Check if this plan needs approval
        self.needs_approval = (status == "user_feedback" and use_planning)
        
        # Extract steps if available
        self.steps = values.get("steps", [])
        
        # Generate block ID - use "plan_" prefix for frontend compatibility
        block_id = f"plan_{self.context.assistant_message_id}"
        
        # Build plan block data
        plan_block_data = {
            "plan": self.plan_content,
            "steps": self.steps,
            "query": values.get("query", "")
        }
        
        # Use block_type "plan" and action "add_planner" for frontend compatibility
        # The frontend handleContentBlockEvent only handles "plan" block type
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "plan",
                "block_id": block_id,
                "content": self.plan_content,
                "node": "planner",
                "message_id": self.context.assistant_message_id,
                "needsApproval": self.needs_approval,
                "steps": self.steps,
                "action": "add_planner"
            })
        }
        
        # Save plan block with type "plan" for frontend compatibility
        plan_block = {
            "id": block_id,
            "type": "plan",
            "needsApproval": self.needs_approval,
            "data": plan_block_data
        }
        await self.context.save_block(plan_block)
        logger.info(f"✅ XpAgent plan block {block_id} saved (needsApproval={self.needs_approval})")
        
        # If approval needed, emit approval request event
        if self.needs_approval:
            checkpoint_id = self._extract_checkpoint_id(state)
            
            yield {
                "event": "xp_approval_required",
                "data": json.dumps({
                    "type": "plan_approval",
                    "message": "XpAgent plan ready for execution",
                    "plan": self.plan_content,
                    "steps": self.steps,
                    "checkpoint_id": checkpoint_id,
                    "options": ["approve", "reject"]
                })
            }
    
    def _extract_checkpoint_id(self, state: Any) -> Optional[str]:
        """Extract checkpoint ID from state."""
        try:
            if hasattr(state, 'config') and state.config and 'configurable' in state.config:
                configurable = state.config['configurable']
                if 'checkpoint_id' in configurable:
                    return str(configurable['checkpoint_id'])
        except Exception:
            pass
        return None
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        """Get content blocks for persistence."""
        if not self.plan_content:
            return []
        
        return [{
            "id": f"xp_plan_{self.context.assistant_message_id}",
            "type": "xp_plan",
            "needsApproval": self.needs_approval,
            "data": {
                "plan": self.plan_content,
                "steps": self.steps
            }
        }]


class XpStepHandler(ContentHandler):
    """
    Handler for XpAgent's step execution results.
    
    Tracks individual step progress and results during execution.
    """
    
    def __init__(self, context: StreamContext, agent):
        super().__init__(context)
        self.agent = agent
        self.step_results = []
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        """Check if this message is from XpAgent's executor node."""
        node_name = metadata.get('langgraph_node', 'unknown')
        return (
            node_name == 'executor' and
            hasattr(msg, 'content') and 
            msg.content and
            type(msg).__name__ == 'AIMessage'
        )
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle XpAgent's step execution output."""
        content = msg.content
        
        # Get current state
        state = self.agent.graph.get_state(self.context.config)
        values = getattr(state, 'values', {}) or {}
        
        step_counter = values.get("step_counter", 0)
        steps = values.get("steps", [])
        status = values.get("status", "")
        
        # Generate step block
        block_id = f"xp_step_{self.context.assistant_message_id}_{step_counter}"
        
        step_data = {
            "step_number": step_counter,
            "content": content,
            "status": status,
            "total_steps": len(steps) if steps else 0
        }
        
        # Check if this is the latest step result
        if steps and step_counter > 0 and step_counter <= len(steps):
            latest_step = steps[step_counter - 1] if step_counter <= len(steps) else None
            if latest_step:
                step_data["step_info"] = latest_step
        
        self.step_results.append(step_data)
        
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "xp_step",
                "block_id": block_id,
                "content": content,
                "node": "executor",
                "message_id": self.context.assistant_message_id,
                "needsApproval": False,
                "step_number": step_counter,
                "status": status,
                "action": "add_xp_step"
            })
        }
        
        # Save step block
        step_block = {
            "id": block_id,
            "type": "xp_step",
            "needsApproval": False,
            "data": step_data
        }
        await self.context.save_block(step_block)
        logger.info(f"✅ XpAgent step block {block_id} saved (step {step_counter})")
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        """Get content blocks for persistence."""
        blocks = []
        for i, step_data in enumerate(self.step_results):
            blocks.append({
                "id": f"xp_step_{self.context.assistant_message_id}_{i + 1}",
                "type": "xp_step",
                "needsApproval": False,
                "data": step_data
            })
        return blocks


class XpErrorHandler(ContentHandler):
    """
    Handler for XpAgent error states that require user intervention.
    
    Provides simple boolean approval for error recovery.
    """
    
    def __init__(self, context: StreamContext, agent):
        super().__init__(context)
        self.agent = agent
        self.error_content = ""
        self.error_details = {}
    
    async def can_handle(self, msg: Any, metadata: Dict) -> bool:
        """Check if this is an error state requiring user action."""
        node_name = metadata.get('langgraph_node', 'unknown')
        
        if node_name != 'human_feedback':
            return False
        
        # Check agent state for error
        state = self.agent.graph.get_state(self.context.config)
        values = getattr(state, 'values', {}) or {}
        status = values.get("status", "")
        
        return status == "error"
    
    async def handle(self, msg: Any, metadata: Dict) -> AsyncGenerator[Dict, None]:
        """Handle XpAgent error state."""
        state = self.agent.graph.get_state(self.context.config)
        values = getattr(state, 'values', {}) or {}
        
        self.error_content = values.get("assistant_response", "An error occurred")
        self.error_details = {
            "step_counter": values.get("step_counter", 0),
            "status": values.get("status", "error"),
            "steps": values.get("steps", [])
        }
        
        block_id = f"xp_error_{self.context.assistant_message_id}"
        checkpoint_id = self._extract_checkpoint_id(state)
        
        yield {
            "event": "content_block",
            "data": json.dumps({
                "block_type": "xp_error",
                "block_id": block_id,
                "content": self.error_content,
                "node": "human_feedback",
                "message_id": self.context.assistant_message_id,
                "needsApproval": True,
                "action": "add_xp_error"
            })
        }
        
        # Emit error approval request
        yield {
            "event": "xp_approval_required",
            "data": json.dumps({
                "type": "error",
                "message": self.error_content,
                "error_details": self.error_details,
                "checkpoint_id": checkpoint_id,
                "options": ["approve", "reject"]  # approve = continue/retry, reject = cancel
            })
        }
        
        # Save error block
        error_block = {
            "id": block_id,
            "type": "xp_error",
            "needsApproval": True,
            "data": {
                "error": self.error_content,
                "details": self.error_details
            }
        }
        await self.context.save_block(error_block)
        logger.info(f"✅ XpAgent error block {block_id} saved")
    
    def _extract_checkpoint_id(self, state: Any) -> Optional[str]:
        """Extract checkpoint ID from state."""
        try:
            if hasattr(state, 'config') and state.config and 'configurable' in state.config:
                configurable = state.config['configurable']
                if 'checkpoint_id' in configurable:
                    return str(configurable['checkpoint_id'])
        except Exception:
            pass
        return None
    
    def get_content_blocks(self, needs_approval: bool = False) -> List[Dict]:
        """Get content blocks for persistence."""
        if not self.error_content:
            return []
        
        return [{
            "id": f"xp_error_{self.context.assistant_message_id}",
            "type": "xp_error",
            "needsApproval": True,
            "data": {
                "error": self.error_content,
                "details": self.error_details
            }
        }]
