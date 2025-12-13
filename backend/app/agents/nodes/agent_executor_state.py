"""Agent Executor State - Simplified state for agent executor sub-graph"""
from typing import List, Dict, Any, Optional, Set
from langgraph.graph.message import MessagesState
from langchain_core.messages import BaseMessage


class AgentExecutorState(MessagesState):
  
    query: str
    plan: str
    
    group_index: int
    group_tools: List[str]
    
    current_tool_call: Optional[Dict[str, Any]] = None
    tool_results: List[BaseMessage] = [] 
    tools_used: Set[str] = set()  
    
    has_errors: bool = False
    should_retry: bool = False
