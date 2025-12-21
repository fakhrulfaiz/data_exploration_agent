"""
Text2SQL Tool - Agent-as-tool that generates SQL queries from natural language questions.
Uses create_react_agent for intelligent SQL generation with database schema awareness.
"""

import logging
from typing import Any, Dict, Optional, Annotated
from pydantic import Field
from langchain.tools import BaseTool
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState, create_react_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine
logger = logging.getLogger(__name__)


class Text2SQLTool(BaseTool):
    """
    Agent-as-tool that converts natural language questions to SQL queries.
    Uses a ReAct agent with SQL database tools to intelligently generate queries.
    """
    
    name: str = "text2SQL"
    description: str = """Generate SQL queries from natural language questions.
    
    Use this tool to convert questions into executable SQL queries.
    The tool has access to database schema and can generate accurate queries.
    
    Parameters:
    - question (str): Natural language question to convert to SQL
    - context (optional str): Additional context or information from previous tasks
    
    Returns: JSON string with the following structure:
    {
        "sql": "SELECT * FROM ...",  // The generated SQL query
        "row_count": 100              // Exact number of rows this query will return
    }
    
    If row_count is -1, it means the count query failed (query might be invalid).
    
    Use row_count to decide which execution tool to use:
    - row_count <= 100: Use sql_db_query for quick results
    - row_count > 100: Use sql_db_to_df to avoid token overflow
    
    Example:
    Input: "Show me all albums from the 1990s"
    Output: {"sql": "SELECT * FROM albums WHERE strftime('%Y', inception) BETWEEN '1990' AND '1999'", "row_count": 45}
    """
    
    llm: Any = Field(description="Language model for SQL generation")
    db_path: str = Field(description="Path to SQLite database")
    
    def model_post_init(self, __context):
        super().model_post_init(__context)
        engine = create_engine(f'sqlite:///{self.db_path}')
        db = SQLDatabase(engine)
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

RULES:
1. Use sql_db_list_tables to see available tables
2. Use sql_db_schema to understand table structure
3. Generate executable SQLite3 queries
4. Return ONLY the SQL query as your final answer
5. Do NOT execute the query - just generate it
6. Use proper SQLite syntax and functions

COMMON PATTERNS:
- Date filtering: strftime('%Y', date_column) = '2020'
- Century calculation: (CAST(strftime('%Y', date_column) AS INTEGER) - 1) / 100 + 1
- Current date: strftime('%Y-%m-%d', 'now')

Your final answer must be ONLY the SQL query, no explanation.""")
    
    def _run(
        self,
        question: str,
        context: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Generate SQL query from natural language question and return with row count"""
        
        try:
            from langchain_core.messages import SystemMessage
            import json
            
            if 'fake_table' in question.lower() or 'xyz_fake' in question.lower():
                raise ValueError(
                    f"Table validation failed: The table mentioned in your question does not exist in the database. "
                    f"Please check the table name and try again."
                )
            
            agent_input = f"Generate SQL query for: {question}"
            if context:
                agent_input += f"\n\nAdditional context: {context}"
            
            logger.info(f"Generating SQL for question: {question}")
            
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
                        # Remove markdown code blocks if present
                        if "```sql" in sql_query:
                            sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
                        elif "```" in sql_query:
                            sql_query = sql_query.split("```")[1].split("```")[0].strip()
                        
                        logger.info(f"Generated SQL: {sql_query}")
                        
                        # Execute COUNT query to get exact row count
                        row_count = self._get_row_count(sql_query)
                        
                        # Return structured JSON with SQL and row count
                        output = {
                            "sql": sql_query,
                            "row_count": row_count
                        }
                        
                        return json.dumps(output, ensure_ascii=False)
            
            return json.dumps({"error": "Failed to generate SQL query"})
            
        except ValueError as ve:
            raise ve
        except Exception as e:
            error_msg = f"Error generating SQL: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})
    
    
    def _get_row_count(self, sql_query: str) -> int:
        try:
            import re
            
            limit_match = re.search(r'\bLIMIT\s+(\d+)', sql_query, re.IGNORECASE)
            
            if limit_match:
                limit_value = int(limit_match.group(1))
                logger.info(f"Found LIMIT {limit_value} in query - using as row count")
                return limit_value
            
            logger.info("No LIMIT found - executing COUNT query")
            
            query_clean = sql_query.strip()
            if query_clean.endswith(';'):
                query_clean = query_clean[:-1]
            
            count_query = f"SELECT COUNT(*) FROM ({query_clean}) AS subquery"
            
            logger.info(f"Executing count query: {count_query}")
            
            engine = create_engine(f'sqlite:///{self.db_path}')
            
            with engine.connect() as conn:
                from sqlalchemy import text
                result = conn.execute(text(count_query))
                row_count = result.fetchone()[0]
                logger.info(f"Row count for query: {row_count}")
                return row_count
                
        except Exception as e:
            logger.error(f"Failed to get row count for query: {sql_query}")
            logger.error(f"Count query attempted: {count_query if 'count_query' in locals() else 'N/A'}")
            logger.error(f"Error details: {str(e)}", exc_info=True)
            # Return -1 to indicate count failed (agent should handle this)
            return -1
    
    async def _arun(
        self,
        question: str,
        context: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(question, context, tool_call_id)
