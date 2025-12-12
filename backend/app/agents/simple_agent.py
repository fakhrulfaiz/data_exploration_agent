"""Simple agent for testing database checkpointer with SQL DB toolkit."""

import os
from typing import List, Optional
import logging
from sqlalchemy import create_engine
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
       # Use sync PostgreSQL checkpointer with proper connection management
from langgraph.checkpoint.postgres import PostgresSaver
from ..core.database import db_manager
import psycopg
from .state import ExplainableAgentState
from ..core.checkpointer import get_sync_checkpointer
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SimpleAgent:
    """Simple agent for testing database checkpointer - uses only SQL DB toolkit."""

    def __init__(self, llm, db_path: str, use_postgres_checkpointer: bool = True):
        """
        Initialize the simple agent.
        
        Args:
            llm: Language model instance
            db_path: Path to SQLite database file
            use_postgres_checkpointer: Whether to use PostgreSQL checkpointer (default: True)
        """
        self.llm = llm
        self.db_path = db_path
        self.use_postgres_checkpointer = use_postgres_checkpointer
        
        # Create database engine and connection
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.db = SQLDatabase(self.engine)
        
        # Initialize SQL toolkit
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        
        # Get all SQL tools (excluding sql_db_query if needed)
        self.tools = [tool for tool in self.toolkit.get_tools() if tool.name != "sql_db_query"]
        
        # Create the graph (checkpointer will be set during compilation)
        self.graph = self.create_graph()
    
    def create_graph(self):
        """Create the LangGraph state graph."""
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        graph.add_node("agent", self.agent_node)
        graph.add_node("tools", self.tools_node)
        
        # Set entry point
        graph.set_entry_point("agent")
        
        # Add conditional edges
        graph.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "tools": "tools",
                "end": END
            }
        )
        
        # Tools always go back to agent
        graph.add_edge("tools", "agent")
        
        # Compile with appropriate checkpointer
        if self.use_postgres_checkpointer:
            try:
                from ..core.checkpointer import checkpointer_manager
                if checkpointer_manager.is_initialized():
                     
                    # Get the database URI and create a persistent connection
                    db_uri = db_manager.get_db_uri()
                    # Create a connection that will be managed by the checkpointer
                    conn = psycopg.connect(db_uri, autocommit=True)
                    checkpointer = PostgresSaver(conn)
                    return graph.compile(checkpointer=checkpointer)
                else:
                    logger.warning("Checkpointer not initialized, falling back to MemorySaver")
                    return graph.compile(checkpointer=MemorySaver())
            except Exception as e:
                logger.warning(f"Failed to use PostgreSQL checkpointer, falling back to MemorySaver: {e}")
                return graph.compile(checkpointer=MemorySaver())
        else:
            return graph.compile(checkpointer=MemorySaver())
    
    def should_continue(self, state: ExplainableAgentState):
        """Determine if we should continue to tools or end."""
        messages = state.get("messages", [])
        if not messages:
            return "end"
        
        last_message = messages[-1]
        
        # Check if last message has tool calls
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        else:
            return "end"
    
    def agent_node(self, state: ExplainableAgentState):
        """Agent node that processes messages and decides on tool usage."""
        messages = state.get("messages", [])
        
        # Build system message
        system_message = self._build_system_message()
        
        # Bind tools to LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Filter out system messages from conversation
        conversation_messages = [
            msg for msg in messages 
            if not isinstance(msg, SystemMessage)
        ]
        
        # Add system message at the beginning
        all_messages = [SystemMessage(content=system_message)] + conversation_messages
        
        # Get response from LLM
        response = llm_with_tools.invoke(all_messages)
        
        # Update state
        return {
            "messages": messages + [response],
            "query": state.get("query", ""),
            "plan": state.get("plan", ""),
            "steps": state.get("steps", []),
            "step_counter": state.get("step_counter", 0),
            "data_context": state.get("data_context"),
            "visualizations": state.get("visualizations", []),
        }
    
    def tools_node(self, state: ExplainableAgentState):
        """Execute tools and return results."""
        # Use ToolNode to execute tools
        tool_node = ToolNode(tools=self.tools)
        result = tool_node.invoke(state)
        
        logger.info("Tool node executed, returned %d messages", len(result.get("messages", [])))
        
        # Preserve state fields
        return {
            "messages": result.get("messages", []),
            "query": state.get("query", ""),
            "plan": state.get("plan", ""),
            "steps": state.get("steps", []),
            "step_counter": state.get("step_counter", 0),
            "data_context": state.get("data_context"),
            "visualizations": state.get("visualizations", []),
        }
    
    def _build_system_message(self):
        """Build system message for the agent."""
        return """You are a helpful SQL database assistant.

CORE RESPONSIBILITIES:
1. Answer user questions accurately using the available SQL tools.
2. Avoid making assumptions; verify with data.
3. Be efficient: Do not repeat successful tool calls.

DATABASE OPERATIONS:
1. **EXPLORATION FIRST**:
   - Always check `sql_db_list_tables` or `sql_db_schema` if you are unsure about table names or columns.
   - Do not guess column names.

2. **QUERY CONSTRUCTION**:
   - Write syntactically correct SQLite queries.
   - **LIMIT RESULTS**: Always use `LIMIT` when appropriate to avoid unnecessarily large datasets.
   - **SELECTIVE**: Select only necessary columns.
   - **READ-ONLY**: SELECT statements ONLY. No INSERT/UPDATE/DELETE.

3. **ERROR HANDLING**:
   - If a query fails, check the error message.
   - Common errors: Wrong column name, syntax error.
   - Fix the query and try ONCE more. If it fails again, ask the user for clarification.

RESPONSE STYLE:
- Be direct and concise - answer only what is asked
- Format data as markdown tables when showing query results
- Use code blocks with syntax highlighting for SQL

TOOL USAGE:
- Use sql_db_list_tables to see available tables
- Use sql_db_schema to see table structure
- Use sql_db_query_checker to validate SQL before execution
- Use sql_db_query to execute queries (but prefer sql_db_query_checker first)
"""

