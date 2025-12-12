"""Agent Executor State - Simplified state for agent executor sub-graph"""
from typing import List, Dict, Any, Optional, Set
from langgraph.graph.message import MessagesState
from langchain_core.messages import BaseMessage


class AgentExecutorState(MessagesState):
    """State for agent executor sub-graph
    
    This is a simplified state that only contains fields needed for tool execution.
    The parent ExplainableAgentState will receive updates via return values.
    """
    # Original query and plan for context
    query: str
    plan: str
    
    # Current group info
    group_index: int
    group_tools: List[str]
    
    # Tool execution tracking
    current_tool_call: Optional[Dict[str, Any]] = None
    tool_results: List[BaseMessage] = []  # Accumulated tool messages
    tools_used: Set[str] = set()  # Track which tools have been used
    
    # Control flags
    has_errors: bool = False
    should_retry: bool = False
