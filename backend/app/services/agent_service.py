"""Agent service with comprehensive checkpoint management capabilities."""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph

# Lazy import to avoid circular dependency
# from ..agents import DataExplorationAgent
from ..agents.state import ExplainableAgentState
from ..utils.logger import get_logger

logger = get_logger(__name__)


class AgentService:  
    def __init__(self):
        self._agent: Optional[Any] = None 
        self._llm: Optional[ChatOpenAI] = None
        
    def initialize_agent(
        self, 
        llm: ChatOpenAI, 
        db_path: str, 
        use_postgres_checkpointer: bool = True
    ) -> None:
        # Lazy import to avoid circular dependency
        from ..agents.data_exploration_agent import DataExplorationAgent
        # from ..agents import DataExplorationAgent
        # from ..agents.workflows import DataExplorationAgentWF as DataExplorationAgent  # Lazy assignment cause WHY NOT!!!!
        from ..agents import DataExplorationAgent
        
        try:
            self._llm = llm
            self._agent = DataExplorationAgent(
                llm=llm, 
                db_path=db_path, 
                use_postgres_checkpointer=use_postgres_checkpointer,
                require_tool_approval=True 
            )
            logger.info("Agent service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize agent service: {e}")
            raise
     
    def get_agent(self) -> Any:  # DataExplorationAgent - lazy import
        if self._agent is None:
            raise RuntimeError("Agent service not initialized. Call initialize_agent() first.")
        return self._agent
    
    def get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            raise RuntimeError("LLM not initialized. Call initialize_agent() first.")
        return self._llm
    
    def is_initialized(self) -> bool:
        return self._agent is not None and self._llm is not None
    
    async def shutdown(self) -> None:
        try:
            if self._agent and hasattr(self._agent.graph, 'checkpointer'):
                checkpointer = self._agent.graph.checkpointer
                if hasattr(checkpointer, 'aclose'):
                    await checkpointer.aclose()
                elif hasattr(checkpointer, 'close'):
                    checkpointer.close()
            
            # Reset internal state
            self._agent = None
            self._llm = None
            
            logger.info("Agent service shutdown completed")
        except Exception as e:
            logger.error(f"Error during agent service shutdown: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            health_status = {
                "service_initialized": self.is_initialized(),
                "agent_available": self._agent is not None,
                "llm_available": self._llm is not None,
                "checkpointer_available": False,
                "timestamp": datetime.now().isoformat()
            }
            
            if self._agent and hasattr(self._agent.graph, 'checkpointer'):
                checkpointer = self._agent.graph.checkpointer
                health_status["checkpointer_available"] = checkpointer is not None
                
                # Test basic checkpointer functionality
                if checkpointer:
                    try:
                        # Try to list checkpoints to verify connection
                        test_config = {"configurable": {"thread_id": "health_check_test"}}
                        if hasattr(checkpointer, 'alist'):
                            # For async checkpointer, just check if method exists
                            health_status["checkpointer_functional"] = True
                        else:
                            # For sync checkpointer, try a quick operation
                            list(checkpointer.list({}))
                            health_status["checkpointer_functional"] = True
                    except Exception as e:
                        health_status["checkpointer_functional"] = False
                        health_status["checkpointer_error"] = str(e)
            
            health_status["overall_status"] = "healthy" if all([
                health_status["service_initialized"],
                health_status["agent_available"],
                health_status["llm_available"],
                health_status["checkpointer_available"]
            ]) else "unhealthy"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "overall_status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def reset_agent(self) -> None:
        try:
            self._agent = None
            self._llm = None
            logger.info("Agent service reset completed")
        except Exception as e:
            logger.error(f"Error during agent service reset: {e}")
    
    @property
    def agent(self) -> Any:  # DataExplorationAgent - lazy import
        return self.get_agent()
    
    async def run_agent(
        self, 
        message: str, 
        thread_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run the agent with a message and optional thread context.
        
        Args:
            message: User message to process
            thread_id: Optional thread identifier for conversation continuity
            initial_state: Optional initial state override
            
        Returns:
            Dict containing agent response and metadata
        """
        try:
            # Prepare initial state with defaults
            if initial_state is None:
                initial_state = {
                    "messages": [HumanMessage(content=message)],
                    "use_planning": False,  # Disable planning by default
                    "use_explainer": False,  # Disable explainer by default
                    "status": "approved"
                }
            else:
                # Ensure messages are included
                if "messages" not in initial_state:
                    initial_state["messages"] = [HumanMessage(content=message)]
                # Set defaults if not provided
                if "use_planning" not in initial_state:
                    initial_state["use_planning"] = False
                if "use_explainer" not in initial_state:
                    initial_state["use_explainer"] = False
                if "status" not in initial_state:
                    initial_state["status"] = "approved"
            
            # Prepare config
            config = {"configurable": {"thread_id": thread_id or "default"}}
            
            # Execute agent
            result = self._agent.graph.invoke(initial_state, config=config)
            
            # Extract only the last AI message for cleaner response
            last_ai_message = None
            for msg in reversed(result.get("messages", [])):
                if hasattr(msg, 'type') and msg.type == 'ai':
                    last_ai_message = getattr(msg, "content", "")
                    break
            
            # Fallback to all messages if no AI message found
            if last_ai_message is None:
                responses = []
                for msg in result.get("messages", []):
                    content = getattr(msg, "content", None)
                    if isinstance(content, str) and content.strip():
                        responses.append(content)
                last_ai_message = responses[-1] if responses else "No response generated"
            
            logger.info(f"Agent executed successfully for thread {thread_id}")
            
            return {
                "messages": [last_ai_message],  # Return only the final response
                "thread_id": thread_id,
                "state": result,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return {
                "messages": [],
                "thread_id": thread_id,
                "error": str(e),
                "success": False
            }

    async def delete_thread(self, thread_id: str) -> bool:
   
        try:
            checkpointer = self._agent.graph.checkpointer
            if not checkpointer:
                logger.warning("No checkpointer available in the graph")
                return False
            
            # LangGraph checkpoints are always sync, use delete_thread method
            if not hasattr(checkpointer, 'delete_thread'):
                logger.error("Checkpointer does not have delete_thread method")
                return False
            
            # PostgresSaver.delete_thread takes thread_id as string parameter
            # Run in thread pool since it's a sync blocking operation
            delete_method = getattr(checkpointer, 'delete_thread')
            await asyncio.to_thread(delete_method, thread_id)
            
            logger.info(f"Successfully deleted thread {thread_id}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}", exc_info=True)
            return False
    
    
    async def get_current_state(
        self, 
        thread_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the current state for a thread.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            Current state dictionary or None if not found
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            # Use get_state for synchronous operation on the graph
            state = self._agent.graph.get_state(config)
            
            if state:
                return {
                    "thread_id": thread_id,
                    "state": state.values,
                    "next": state.next,
                    "config": state.config,
                    "metadata": state.metadata,
                    "created_at": state.created_at if hasattr(state, 'created_at') else None
                }
            return None
                
        except Exception as e:
            logger.error(f"Failed to get current state for {thread_id}: {e}")
            return None
    
    
    # ==================== State Management Operations ====================
    
    async def initialize_thread_state(
        self, 
        thread_id: str,
        initial_state: Dict[str, Any]
    ) -> bool:
        """
        Initialize state for a new thread.
        
        Args:
            thread_id: Thread identifier
            initial_state: Initial state to set
            
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Use the agent's graph to create initial checkpoint
            config = {"configurable": {"thread_id": thread_id}}
            
            # Invoke with initial state to create first checkpoint
            result = self._agent.graph.invoke(initial_state, config=config)
            
            logger.info(f"Successfully initialized state for thread {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize state for thread {thread_id}: {e}")
            return False
    
    async def update_thread_state(
        self, 
        thread_id: str,
        state_updates: Dict[str, Any]
    ) -> bool:
        """
        Update state for an existing thread.
        
        Args:
            thread_id: Thread identifier
            state_updates: State updates to apply
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            
            # Get current state to verify thread exists
            current_state = self._agent.graph.get_state(config)
            if not current_state:
                logger.warning(f"No existing state found for thread {thread_id}")
                return False
            
            # Update the graph's state - this method is sync
            self._agent.graph.update_state(config, state_updates)
            
            logger.info(f"Successfully updated state for thread {thread_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update state for thread {thread_id}: {e}")
            return False
  
    async def delete_multiple_threads(self, thread_ids: List[str]) -> Dict[str, bool]:
        """
        Delete multiple threads in bulk.
        
        Args:
            thread_ids: List of thread identifiers to delete
            
        Returns:
            Dictionary mapping thread_id to deletion success status
        """
        results = {}
        
        for thread_id in thread_ids:
            results[thread_id] = await self.delete_thread(thread_id)
        
        successful = sum(1 for success in results.values() if success)
        logger.info(f"Bulk deletion completed: {successful}/{len(thread_ids)} threads deleted")
        
        return results
    
    async def cleanup_old_checkpoints(
        self, 
        older_than_days: int = 30
    ) -> Dict[str, int]:
        """
        Clean up old checkpoints.
        
        Note: This method is primarily for checkpoint cleanup at the LangGraph level.
        For thread management, use ChatThreadService instead.
        
        Args:
            older_than_days: Age threshold in days
            
        Returns:
            Dictionary with cleanup results
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            
            # TODO: Implement actual checkpoint cleanup logic
            # This should clean up LangGraph checkpoints, not chat threads
            # Chat thread management should be done via ChatThreadService
            
            logger.info(f"Checkpoint cleanup requested for items older than {older_than_days} days")
            
            return {
                "deleted_count": 0,
                "older_than_days": older_than_days,
                "cutoff_date": cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to cleanup old checkpoints: {e}")
            raise
    
    # ==================== Explorer & Visualization Operations ====================
    
    async def get_explorer_data(
        self, 
        thread_id: str, 
        checkpoint_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get exploration data from a specific checkpoint.
        
        Args:
            thread_id: Thread identifier
            checkpoint_id: Checkpoint identifier
            
        Returns:
            Dictionary with explorer data including steps, plan, and results
        """
        try:
            logger.info(f"Getting explorer data for thread_id: {thread_id}, checkpoint_id: {checkpoint_id}")
            
            # Create config to get the state at specific checkpoint
            config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
            logger.debug(f"Using config: {config}")
            
            # Get the state from the agent (using sync method since PostgresSaver is synchronous)
            state = self._agent.graph.get_state(config)
            logger.debug(f"Retrieved state: {state is not None}, has values: {hasattr(state, 'values') if state else False}")
            
            if not state or not hasattr(state, 'values') or not state.values:
                logger.warning(f"No state found for thread_id: {thread_id}, checkpoint_id: {checkpoint_id}")
                return None
            
            values = state.values
            
            # Extract steps data
            steps_data = values.get("steps", [])
            steps = []
            
            for step_data in steps_data:
                if isinstance(step_data, dict):
                    step = {
                        "id": step_data.get("id", 0),
                        "type": step_data.get("type", "unknown"),
                        "decision": step_data.get("decision", ""),
                        "reasoning": step_data.get("reasoning", ""),
                        "input": step_data.get("input", ""),
                        "output": step_data.get("output", ""),
                        "tool_justification": step_data.get("tool_justification"),
                        "contrastive_explanation": step_data.get("contrastive_explanation"),
                        "data_evidence": step_data.get("data_evidence"),
                        "timestamp": step_data.get("timestamp", "")
                    }
                    steps.append(step)
            
            # Set default overall confidence (no longer calculated from individual steps)
            overall_confidence = 0.8 if steps else None
            
            # Extract last AI message
            last_message = None
            if values.get("messages", []):
                messages = values.get("messages", [])
                for msg in reversed(messages):
                    if (hasattr(msg, 'content') and msg.content and 
                        type(msg).__name__ == 'AIMessage' and
                        (not hasattr(msg, 'tool_calls') or not msg.tool_calls)):
                        last_message = msg.content
                        break
            
            # Create final result if we have steps
            final_result = None
            if steps:
                final_result = {
                    "summary": last_message,
                    "details": f"Executed {len(steps)} steps successfully",
                    "source": "Database query execution",
                    "inference": "Based on database analysis and tool execution",
                    "extra_explanation": f"Plan: {values.get('plan', '')}"
                }
            
            # Build the ExplorerResult format
            explorer_result = {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "run_status": "finished",
                "assistant_response": last_message,
                "query": values.get("query", ""),
                "plan": values.get("plan", ""),
                "error": None,
                "steps": steps if steps else None,
                "final_result": final_result,
                "total_time": None,
                "overall_confidence": overall_confidence
            }
            
            logger.info(f"Successfully built explorer data with {len(steps)} steps")
            return explorer_result
            
        except Exception as e:
            logger.error(f"Error getting explorer data for checkpoint {checkpoint_id}: {str(e)}", exc_info=True)
            return None
    
    async def get_visualization_data(
        self, 
        thread_id: str, 
        checkpoint_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get visualization data from a specific checkpoint.
        
        Args:
            thread_id: Thread identifier
            checkpoint_id: Checkpoint identifier
            
        Returns:
            Dictionary with visualization data or None if not found
        """
        try:
            logger.info(f"Getting visualization data for thread_id: {thread_id}, checkpoint_id: {checkpoint_id}")
            
            # Create config to get the state at specific checkpoint
            config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
            
            # Get the state from the agent
            state = self._agent.graph.get_state(config)
            
            if not state or not hasattr(state, 'values') or not state.values:
                logger.warning(f"No state found for thread_id: {thread_id}")
                return None
            
            values = state.values
            
            # Extract visualizations from the state
            visualizations = values.get("visualizations", [])
            
            if not visualizations:
                logger.info(f"No visualizations found in checkpoint {checkpoint_id}")
                return None
            
            # Normalize visualizations
            from ..utils.visualization_utils import normalize_visualizations
            normalized_visualizations = normalize_visualizations(visualizations)
            
            if not normalized_visualizations:
                logger.info(f"No valid visualizations found in checkpoint {checkpoint_id}")
                return None
            
            # Build visualization data response
            visualization_data = {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "visualizations": normalized_visualizations,
                "count": len(normalized_visualizations),
                "types": [viz.get("type", "unknown") for viz in normalized_visualizations]
            }
            
            logger.info(f"Successfully retrieved {len(normalized_visualizations)} visualizations from checkpoint {checkpoint_id}")
            return visualization_data
            
        except Exception as e:
            logger.error(f"Error getting visualization data for checkpoint {checkpoint_id}: {str(e)}")
            return None

