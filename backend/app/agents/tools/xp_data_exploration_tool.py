"""
XpAgent Data Exploration Tool.
Wraps the data_exploration_sub agent as a LangChain tool for XpAgent.
"""

import logging
import json
import re
import os
from typing import Any, Optional, List
from pathlib import Path
from pydantic import Field
from langchain.tools import BaseTool
from langchain_core.messages import HumanMessage, AIMessage
import pandas as pd

from app.services.dependencies import get_redis_dataframe_service
from app.schemas.chat import DataContext

logger = logging.getLogger(__name__)

# Workspace configuration - keep using dev workspace
WORKSPACE_PATH = Path("/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace")
OUTPUT_PATH = WORKSPACE_PATH / "outputs"


class XpDataExplorationTool(BaseTool):
    """Tool wrapper for data exploration subagent."""
    
    name: str = "database_exploration_agent"
    description: str = """Execute database queries to explore and retrieve artwork data.
    
    CAPABILITIES:
    - SQL query generation from natural language
    - Filtering, sorting, aggregation (COUNT, SUM, AVG)
    - Finding specific records (oldest, newest, top N)
    - Grouping and complex queries
    - Automatic CSV export of results
    
    Parameters:
    - query (str): Natural language description of what data to retrieve
    
    Returns: Query results with data preview and CSV file path.
    
    IMPORTANT: When visual analysis is needed later, always include img_path column!
    """
    
    model_name: str = Field(default="gpt-4o-mini", description="LLM model to use")
    db_path: str = Field(default="/home/afiq/fyp/fafa-repo/backend/app/resource/art.db", description="Path to SQLite database")
    _agent: Any = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, model_name: str = "gpt-4o-mini", db_path: Optional[str] = None, **kwargs):
        # Set defaults
        if db_path is None:
            db_path = "/home/afiq/fyp/fafa-repo/backend/app/resource/art.db"
        
        super().__init__(model_name=model_name, db_path=db_path, **kwargs)
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Lazy initialize the subagent."""
        try:
            from app.agents.dev.agent.data_exploration_sub import build_data_exploration_agent
            self._agent = build_data_exploration_agent(
                model_name=self.model_name,
                db_path=self.db_path
            )
            logger.info(f"XpDataExplorationTool initialized with model {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize data exploration agent: {e}")
            raise
    
    def _run(self, query: str) -> str:
        """Execute data exploration query."""
        try:
            logger.info(f"XpDataExplorationTool executing: {query[:100]}...")
            
            # Invoke the subagent with complete initial state
            # The subagent expects these fields to be present
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "original_task": query,
                "query_history": [],
                "tables_queried": [],
                "exploration_complete": False,
                "ready_for_export": False,
                "result_summary": ""
            }
            
            result_state = self._agent.invoke(
                initial_state,
                {"configurable": {"thread_id": f"xp_data_exploration_{id(self)}"}}
            )
            
            # Extract result from messages
            result_content = ""
            for msg in reversed(result_state.get("messages", [])):
                if isinstance(msg, AIMessage):
                    content = msg.content
                    if isinstance(content, str):
                        result_content = content
                    elif isinstance(content, list):
                        result_content = " ".join(str(c) for c in content)
                    else:
                        result_content = str(content)
                    break
            
            # Check for CSV output in result
            csv_path = None
            if "saved to" in result_content.lower() or ".csv" in result_content:
                csv_match = re.search(r'([\S]+\.csv)', result_content)
                if csv_match:
                    csv_path = csv_match.group(1)
            
            # Store CSV DataFrame in Redis if file exists
            data_context = None
            if csv_path:
                # Resolve full path if relative
                if not os.path.isabs(csv_path):
                    full_csv_path = OUTPUT_PATH / os.path.basename(csv_path)
                else:
                    full_csv_path = Path(csv_path)
                
                if full_csv_path.exists():
                    try:
                        df = pd.read_csv(full_csv_path)
                        redis_service = get_redis_dataframe_service()
                        context_data = redis_service.store_dataframe(
                            df=df,
                            sql_query=None,  # XpAgent doesn't expose SQL directly
                            metadata={
                                "description": query,
                                "source": "xp_data_exploration_tool",
                                "csv_file": str(full_csv_path)
                            }
                        )
                        
                        # Create DataContext for consistency with main agent
                        data_context = DataContext(
                            df_id=context_data["df_id"],
                            sql_query=context_data.get("sql_query"),
                            columns=context_data["columns"],
                            shape=context_data["shape"],
                            created_at=context_data["created_at"],
                            expires_at=context_data["expires_at"]
                        )
                        
                        logger.info(f"Stored CSV in Redis: {context_data['df_id']} with shape {context_data['shape']}")
                    except Exception as e:
                        logger.warning(f"Failed to store CSV in Redis: {e}")
            
            # Format response
            response = {
                "success": True,
                "result": result_content,
                "csv_file": csv_path
            }
            
            # Add data context if stored in Redis
            if data_context:
                response["data_context"] = data_context.model_dump(mode="json")
                response["df_id"] = data_context.df_id
            
            logger.info(f"XpDataExplorationTool completed. CSV: {csv_path}, df_id: {data_context.df_id if data_context else None}")
            return json.dumps(response, indent=2, default=str)
            
        except Exception as e:
            logger.error(f"XpDataExplorationTool error: {e}", exc_info=True)
            return json.dumps({
                "success": False,
                "error": str(e)
            })
    
    async def _arun(self, query: str) -> str:
        """Async version - falls back to sync."""
        return self._run(query)
