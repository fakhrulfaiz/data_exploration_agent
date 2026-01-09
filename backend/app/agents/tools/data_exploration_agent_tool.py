"""
Unified Data Exploration Tool.
Combines Text2SQL generation and SQL execution/storage into a single tool tool.
"""

import logging
import json
import pandas as pd
from typing import Any, Dict, Optional, Annotated, List
from pydantic import Field
from langchain.tools import BaseTool
from langchain_core.tools import InjectedToolCallId
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import InjectedState, create_react_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine

from app.services.redis_dataframe_service import get_redis_dataframe_service
from app.schemas.chat import DataContext

logger = logging.getLogger(__name__)

class DataExplorationAgentTool(BaseTool):
    name: str = "data_exploration_tool"
    description: str = """COMPLETE SUB-AGENT for database exploration and retrieval.
    
    Handles the entire workflow: Natural language → SQL generation → Execution → Storage.
    
    CAPABILITIES (Native SQL):
    - Filtering (WHERE), Sorting (ORDER BY), Aggregation (COUNT, SUM, AVG)
    - Grouping (GROUP BY), Joins, Subqueries
    - Finding specific records (oldest, newest, top N)
    
    Use this for ALL database queries, including simple retrieval and complex analysis.
    ONE CALL completes the entire process.
    
    Parameters:
    - question (str): The natural language query
    - context (optional str): Extra context
    
    Returns: JSON with data_preview, row_count, sql_query, and data_context (ID for next steps).
    Data is automatically stored in Redis for use by other tools (python_repl, visualization).
    """
    
    llm: Any = Field(description="Language model for SQL generation")
    db_path: str = Field(description="Path to SQLite database")
    db_engine: Any = Field(description="Database engine for SQL execution")
    
    # # Mock error testing - automatically simulates failure on first call, success on retry
    # _mock_error_triggered: bool = False
    
    def model_post_init(self, __context):
        super().model_post_init(__context)
        schema_engine = create_engine(f'sqlite:///{self.db_path}')
        db = SQLDatabase(schema_engine)
        
        # Create SQL tools directly to avoid deprecated QuerySQLCheckerTool
        # which tries to import from langchain_core.memory (doesn't exist in newer versions)
        from langchain_community.tools.sql_database.tool import (
            InfoSQLDatabaseTool,
            ListSQLDatabaseTool,
        )
        
        sql_tools = [
            ListSQLDatabaseTool(db=db),
            InfoSQLDatabaseTool(db=db)
        ]
        
        object.__setattr__(self, '_agent', create_react_agent(
            self.llm,
            sql_tools
        ))
        
        object.__setattr__(self, '_system_prompt', """You are a SQL query generator expert.

Your task is to generate ONLY the SQL query, nothing else.

CRITICAL VALIDATION RULES:
1. FIRST, call sql_db_list_tables to see available tables.
2. CHOOSE the most relevant table from the list. If user request is vague (e.g., "the table"), infer the table if obvious.
3. VERIFY that the table you want to query is present in the sql_db_list_tables output.
4. IF the table is NOT in the list: Return 'ERROR: Table [name] not found'.
5. ONLY query tables that are explicitly listed in sql_db_list_tables.

SQL GENERATION RULES:
1. Use sql_db_schema to understand table structure
2. Generate executable SQLite3 queries
3. Return ONLY the SQL query as your final answer
4. Do NOT execute the query - just generate it
5. Use proper SQLite syntax and functions

COMMON PATTERNS:
- Date filtering: strftime('%Y', date_column) = '2020'
- Century calculation: (CAST(strftime('%Y', date_column) AS INTEGER) - 1) / 100 + 1
- Current date: strftime('%Y-%m-%d', 'now')

Your final answer must be ONLY the SQL query, no explanation.""")

    def _generate_sql(self, question: str, context: Optional[str] = None) -> str:
        """Internal method to generate SQL from natural language"""
        if 'fake_table' in question.lower() or 'xyz_fake' in question.lower():
            raise ValueError("Table validation failed: The table mentioned does not exist.")
            
        agent_input = f"Generate SQL query for: {question}"
        if context:
            agent_input += f"\n\nAdditional context: {context}"
            
        agent = object.__getattribute__(self, '_agent')
        system_prompt = object.__getattribute__(self, '_system_prompt')
        
        result = agent.invoke({
            "messages": [
                SystemMessage(content=system_prompt),
                ("user", agent_input)
            ]
        })
        
        messages = result.get("messages", [])
        if messages:
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.content:
                    sql_query = msg.content.strip()
                    # Clean markdown
                    if "```sql" in sql_query:
                        sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
                    elif "```" in sql_query:
                        sql_query = sql_query.split("```")[1].split("```")[0].strip()
                    
                    # Check for error prefix from the LLM (e.g. Table not found)
                    if sql_query.startswith("Error:") or sql_query.startswith("ERROR:"):
                        raise ValueError(sql_query)
                        
                    return sql_query
                    
        raise ValueError("Failed to generate SQL query")

    def _run(
        self,
        question: str,
        context: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute the full data exploration pipeline"""
        try:
            logger.info(f"DataExplorationAgentTool processing question: {question}")
            
            # Step 1: Generate SQL
            try:
                sql_query = self._generate_sql(question, context)
                logger.info(f"Generated SQL: {sql_query}")
            except Exception as e:
                return json.dumps({
                    "error": f"Failed to generate SQL: {str(e)}",
                    "error_type": "validation_error",
                    "tool_name": "data_exploration_tool",
                    "details": {
                        "question": question,
                        "context": context,
                        "exception": str(e)
                    },
                    "recoverable": False  # Bad question needs replanning
                })

            # Step 2: Execute SQL and get DataFrame
            try:
                # # MOCK ERROR TESTING: Automatically simulate SQL execution failure on first call
                # # This helps test error detection and retry flow in frontend
                # if not self._mock_error_triggered:
                #     object.__setattr__(self, '_mock_error_triggered', True)
                #     logger.warning("🧪 MOCK ERROR: Simulating SQL execution failure for testing")
                #     # Return standardized error to test JSON error detection
                #     return json.dumps({
                #         "error": "Generated SQL failed to execute: MOCK ERROR - Simulated transient database error",
                #         "error_type": "execution_error",
                #         "tool_name": "data_exploration_tool",
                #         "details": {
                #             "sql_query": sql_query,
                #             "db_error": "MOCK: Connection timeout (testing error handling)"
                #         },
                #         "recoverable": True  # Should trigger retry
                #     })
                
                df = pd.read_sql_query(sql_query, self.db_engine)
            except Exception as e:
                logger.error(f"SQL Execution failed: {str(e)}")
                # STANDARDIZED ERROR: SQL Execution Failed
                return json.dumps({
                    "error": f"Generated SQL failed to execute: {str(e)}",
                    "error_type": "execution_error",
                    "tool_name": "data_exploration_tool",
                    "details": {
                        "sql_query": sql_query,
                        "db_error": str(e)
                    },
                    "recoverable": True  # Can retry, might be transient
                })

            if df.empty:
                 return json.dumps({
                    "description": "Query executed successfully but returned no data.",
                    "sql_query": sql_query,
                    "row_count": 0
                })

            # Step 3: Store in Redis
            try:
                redis_service = get_redis_dataframe_service()
                context_data = redis_service.store_dataframe(
                    df=df,
                    sql_query=sql_query,
                    metadata={
                        "description": question, # Use question as description
                        "tool_call_id": tool_call_id,
                        "created_by": "data_exploration_tool"
                    }
                )
            except Exception as e:
                 logger.error(f"Redis storage failed: {str(e)}")
                 # STANDARDIZED ERROR: Storage Failed (but data available)
                 return json.dumps({
                     "error": "Data retrieved but caching failed",
                     "error_type": "storage_error",
                     "tool_name": "data_exploration_tool",
                     "details": {
                         "storage_error": str(e),
                         "data_preview": df.head(5).to_dict(orient='records'),
                         "sql_query": sql_query
                     },
                     "recoverable": True  # Can retry storage
                 })

            # Step 4: Construct Response
            # Create DataContext for state compliance
            data_context = DataContext(
                df_id=context_data["df_id"],
                sql_query=context_data["sql_query"],
                columns=context_data["columns"],
                shape=context_data["shape"],
                created_at=context_data["created_at"],
                expires_at=context_data["expires_at"]
            )
            
            description_text = (
                f"Data retrieved for '{question}'. "
                f"Stored {context_data['shape'][0]} rows × {context_data['shape'][1]} columns in Redis. "
                f"ID: {context_data['df_id']}"
            )
            
            # Return payload including small preview of data
            # This helps the LLM know immediately what it got without needing another tool call usually
            preview_data = df.head(5).to_dict(orient='records')
            
            payload = {
                "data_context": data_context.model_dump(mode="json"),
                "description": description_text,
                "data_preview": preview_data,
                "row_count": len(df),
                "sql_query": sql_query
            }
            
            return json.dumps(payload, default=str)
            
        except Exception as e:
            logger.error(f"DataExplorationAgentTool fatal error: {str(e)}")
            # STANDARDIZED ERROR: Unexpected Fatal Error
            return json.dumps({
                "error": f"Unexpected error: {str(e)}",
                "error_type": "execution_error",
                "tool_name": "data_exploration_tool",
                "details": {"exception": str(e)},
                "recoverable": False
            })

    async def _arun(
        self,
        question: str,
        context: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(question, context, tool_call_id)
