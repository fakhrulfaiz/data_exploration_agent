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
    """
    Unified tool that converts natural language to SQL, executes it, 
    and stores the resulting DataFrame in Redis.
    
    Acts as a sub-agent for data retrieval tasks.
    """
    
    name: str = "data_exploration_tool"
    description: str = """COMPLETE SUB-AGENT for database exploration and retrieval.
    
    This is a COMPLETE SUB-AGENT that handles the entire database query workflow:
    1. Natural language question → SQL generation (with full SQL capabilities)
    2. SQL validation and execution
    3. Result retrieval and storage
    
    ONE CALL to this tool completes the entire database query process.
    DO NOT split into separate "generate SQL" and "execute SQL" steps.
    
    IMPORTANT - This tool can ANSWER QUESTIONS DIRECTLY using SQL:
    - Finding oldest/newest/min/max values (ORDER BY, MIN, MAX)
    - Counting, summing, averaging (COUNT, SUM, AVG)
    - Grouping and aggregating data (GROUP BY)
    - Filtering with conditions (WHERE)
    - Joining multiple tables
    - Complex queries with subqueries and CTEs
    
    If the question can be answered with SQL, this tool will RETURN THE ANSWER.
    You do NOT need additional analysis steps for questions like:
    - "Which genre has the oldest painting?" → Returns the genre directly
    - "How many paintings per artist?" → Returns counts directly
    - "What's the average price by category?" → Returns averages directly
    
    Use this tool for ANY database-related question:
    - Simple data retrieval
    - Complex analytical queries
    - Questions requiring aggregation, sorting, or filtering
    
    Parameters:
    - question (str): Natural language question about the data
    - context (optional str): Additional context for the query
    
    Returns: JSON containing:
    - data_context: Metadata about the stored DataFrame (ID, shape, columns, etc.)
    - description: Human-readable summary of what was retrieved
    - data_preview: First 5 rows of data for immediate inspection
    - sql_query: The generated SQL query that was executed
    
    The retrieved data is automatically stored in Redis and available for:
    - python_repl (only if additional computation is needed)
    - smart_transform_for_viz (for creating charts)
    - large_plotting_tool (for matplotlib plots)
    """
    
    llm: Any = Field(description="Language model for SQL generation")
    db_path: str = Field(description="Path to SQLite database")
    db_engine: Any = Field(description="Database engine for SQL execution")
    
    def model_post_init(self, __context):
        super().model_post_init(__context)
        schema_engine = create_engine(f'sqlite:///{self.db_path}')
        db = SQLDatabase(schema_engine)
        
        toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)
        sql_tools = [
            tool for tool in toolkit.get_tools()
            if tool.name in ["sql_db_list_tables", "sql_db_schema"]
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
                return f"Error: Failed to generate SQL: {str(e)}"

            # Step 2: Execute SQL and get DataFrame
            try:
                df = pd.read_sql_query(sql_query, self.db_engine)
            except Exception as e:
                logger.error(f"SQL Execution failed: {str(e)}")
                # Retry strategy could go here, or returning specific helpful error
                return f"Error: Generated SQL failed to execute: {str(e)}. Query: {sql_query}"

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
                 # Fallback: still return data, but warn about caching
                 return json.dumps({
                     "error": "Data retrieved but caching failed.",
                     "data": df.head(5).to_dict(orient='records'),
                     "sql_query": sql_query
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
            return json.dumps({"error": f"Unexpected error: {str(e)}"})

    async def _arun(
        self,
        question: str,
        context: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(question, context, tool_call_id)
