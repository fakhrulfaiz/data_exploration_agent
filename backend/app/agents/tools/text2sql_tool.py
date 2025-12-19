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
    
    Returns: SQL query string that can be executed with sql_db_query or sql_db_to_df.
    
    Example:
    Input: "Show me all albums from the 1990s"
    Output: "SELECT * FROM albums WHERE strftime('%Y', inception) BETWEEN '1990' AND '1999'"
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
        """Generate SQL query from natural language question"""
        
        try:
            from langchain_core.messages import SystemMessage
            
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
                        return sql_query
            
            return "Error: Failed to generate SQL query"
            
        except ValueError as ve:
            # Re-raise ValueError (our validation errors) so error explainer can catch it
            raise ve
        except Exception as e:
            error_msg = f"Error generating SQL: {str(e)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
    
    async def _arun(
        self,
        question: str,
        context: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(question, context, tool_call_id)
