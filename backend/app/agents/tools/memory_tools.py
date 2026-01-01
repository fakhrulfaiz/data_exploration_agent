"""
Memory management tools for LangGraph agents.

These tools allow agents to:
1. Store conversation-scoped memories in LangGraph Store
2. Retrieve relevant memories from vector DB
3. Get user profile preferences
"""

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from typing import Annotated, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@tool
def save_conversation_memory(
    memory_content: str,
    store: Annotated[Any, InjectedStore()],
    namespace: tuple = ("conversation", "temp")
) -> str:
    """
    Save a temporary memory for this conversation.
    
    Use this to remember important facts mentioned during the conversation
    that might be useful later in the same thread.
    
    Args:
        memory_content: What to remember (e.g., "User prefers bar charts over pie charts")
        store: Injected LangGraph store
        namespace: Memory namespace (default: conversation/temp)
    
    Returns:
        Confirmation message
    """
    try:
        import uuid
        memory_id = str(uuid.uuid4())
        
        store.put(
            namespace,
            memory_id,
            {"content": memory_content, "type": "conversation_memory"}
        )
        
        logger.info(f"Saved conversation memory: {memory_content[:50]}...")
        return f"Remembered: {memory_content}"
        
    except Exception as e:
        logger.error(f"Failed to save conversation memory: {str(e)}")
        return f"Failed to save memory: {str(e)}"


@tool
def get_conversation_memories(
    store: Annotated[Any, InjectedStore()],
    namespace: tuple = ("conversation", "temp")
) -> List[str]:
    """
    Retrieve all memories from this conversation.
    
    Use this to recall what was discussed earlier in the conversation.
    
    Args:
        store: Injected LangGraph store
        namespace: Memory namespace (default: conversation/temp)
    
    Returns:
        List of memory contents
    """
    try:
        items = store.search(namespace)
        memories = [item.value.get("content", "") for item in items if item.value]
        
        logger.info(f"Retrieved {len(memories)} conversation memories")
        return memories
        
    except Exception as e:
        logger.error(f"Failed to retrieve conversation memories: {str(e)}")
        return []


def create_memory_tools():
    """
    Create memory management tools for agents.
    
    Returns:
        List of memory tools
    """
    return [
        save_conversation_memory,
        get_conversation_memories
    ]
