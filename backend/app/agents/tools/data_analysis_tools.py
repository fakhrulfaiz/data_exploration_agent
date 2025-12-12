"""
Data Analysis Tools for the explainable agent project.
Includes SQL to DataFrame conversion and secure Python REPL execution.
"""

import re
import json
import uuid
import logging
import subprocess
import tempfile
import os
import signal
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional, Annotated
from pydantic import Field
from langchain.tools import BaseTool
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
import pandas as pd

from app.services.redis_dataframe_service import get_redis_dataframe_service
from app.schemas.chat import DataContext

logger = logging.getLogger(__name__)

def sanitize_input(query: str) -> str:
    """Sanitize input to the python REPL.
    
    Remove whitespace, backtick & python (if llm mistakes python console as terminal)
    
    Args:
        query: The query to sanitize
        
    Returns:
        str: The sanitized query
    """
    # Removes `, whitespace & python from start
    query = re.sub(r"^(\s|`)*(?i:python)?\s*", "", query)
    # Removes whitespace & ` from end
    query = re.sub(r"(\s|`)*$", "", query)
    return query


class SqlToDataFrameTool(BaseTool):
    """
    Tool that executes SQL queries and stores results as DataFrames in Redis.
    Replaces direct SQL execution in visualization tools.
    """
    
    name: str = "sql_db_to_df"
    description: str = """Execute SQL queries and store results as DataFrames in Redis for analysis.
    
    Use this tool to:
    - Execute SQL queries against the database
    - Convert results to pandas DataFrame
    - Store DataFrame in Redis with automatic expiration
    - Update agent state with DataFrame context
    
    Parameters:
    - sql_query (str): The SQL query to execute
    - description (optional str): Description of what this query does
    
    Returns: Success message with DataFrame info and Redis storage details.
    The DataFrame will be available for Python analysis and visualization tools."""
    
    db_engine: Any = Field(description="Database engine for SQL execution")
    
    def _run(
        self,
        sql_query: str,
        description: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute SQL query and store DataFrame in Redis"""
        
        try:
            
        
            logger.info(f"Executing SQL query: {sql_query}")
            
            # Execute SQL query using pandas
            df = pd.read_sql_query(sql_query, self.db_engine)
            
            if df.empty:
                return "Query executed successfully but returned no data. No DataFrame was created."
            
            # Store DataFrame in Redis
            redis_service = get_redis_dataframe_service()
            context_data = redis_service.store_dataframe(
                df=df,
                sql_query=sql_query,
                metadata={
                    "description": description,
                    "tool_call_id": tool_call_id,
                    "created_by": "sql_db_to_df"
                }
            )
            
            # Create DataContext for state
            data_context = DataContext(
                df_id=context_data["df_id"],
                sql_query=context_data["sql_query"],
                columns=context_data["columns"],
                shape=context_data["shape"],
                created_at=context_data["created_at"],
                expires_at=context_data["expires_at"]
            )
            
            # Description for LLM context (kept out of data_context payload)
            description_text = (
                f"SQL query executed successfully and DataFrame stored in Redis with ID {context_data['df_id']} "
                f"({context_data['shape'][0]} rows × {context_data['shape'][1]} columns). "
                f"Expires at {context_data['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}."
            )
            
            logger.info(f"Successfully stored DataFrame {context_data['df_id']} with shape {context_data['shape']}")
            payload = {
                "data_context": data_context.model_dump(mode="json"),
                "description": description_text,
            }
            return json.dumps(payload)
            
        except Exception as e:
            error_payload = {
                "error": f"Error executing SQL query: {str(e)}"
            }
            logger.error(error_payload["error"])
            return json.dumps(error_payload)
    
    async def _arun(
        self,
        sql_query: str,
        description: Optional[str] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(sql_query, description, tool_call_id)


class SecurePythonREPLTool(BaseTool):
    """
    Secure Python REPL tool that executes code in isolated subprocess within the container.
    Loads DataFrames from Redis for analysis.
    """
    
    name: str = "python_repl"
    description: str = """Execute Python code securely in an isolated subprocess with pandas DataFrame access.
    
    The DataFrame from the last SQL query is automatically loaded as 'df' variable.
    
    Use this tool for:
    - Data analysis and manipulation with pandas
    - Statistical calculations and aggregations
    - Data cleaning and transformation
    - Complex computations on the DataFrame
    
    Security features:
    - Isolated subprocess execution
    - Restricted environment variables
    - Limited execution time (30 seconds)
    - Automatic cleanup after execution
    - Safe error handling
    
    Parameters:
    - code (str): Python code to execute (must use print() to see output)
    
    Example: print(df.describe()) or print(df['column'].mean())
    
    Returns: Output from the executed Python code."""
    
    sanitize_input: bool = True
    
    def _run(
        self,
        code: str,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute Python code in secure Docker container"""
        
        try:
            if state is None:
                state = {}
            
            # Sanitize input
            if self.sanitize_input:
                code = sanitize_input(code)
            
            # Get DataFrame from state
            data_context = state.get("data_context")
            if not data_context or not data_context.df_id:
                return "Error: No DataFrame available. Please run a SQL query first using sql_db_to_df tool."
            
            # Load DataFrame from Redis
            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            
            if df is None:
                return f"Error: DataFrame {data_context.df_id} not found or expired. Please run the SQL query again."
            
            # Extend TTL since we're using the DataFrame
            redis_service.extend_ttl(data_context.df_id)
            
            logger.info(f"Executing Python code in subprocess for DataFrame {data_context.df_id}")
            
            # Execute code in secure subprocess
            result = self._execute_in_subprocess(code, df)
            
            logger.info(f"Python code executed successfully for DataFrame {data_context.df_id}")
            return result
            
        except Exception as e:
            error_msg = f"Error executing Python code: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _execute_in_subprocess(self, code: str, df: pd.DataFrame) -> str:
        """Execute Python code in a secure subprocess within the container"""
        
        try:
            # Prepare the Python script with DataFrame and user code
            python_script = f'''
import pandas as pd
import numpy as np
import sys
import signal
import pickle
import base64
from io import StringIO

# Timeout handler
def timeout_handler(signum, frame):
    raise TimeoutError("Code execution timeout (30 seconds)")

# Set up timeout (only on Unix systems)
try:
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)
except AttributeError:
    # Windows doesn't have SIGALRM, skip timeout setup
    pass

try:
    # Decode and load DataFrame
    df_data = base64.b64decode('{self._encode_dataframe(df)}')
    df = pickle.loads(df_data)
    
    # Capture output
    output_buffer = StringIO()
    original_stdout = sys.stdout
    sys.stdout = output_buffer
    
    try:
        # Execute user code
{self._indent_code(code, 8)}
        
        # Get captured output
        output = output_buffer.getvalue()
        
    except Exception as e:
        output = f"Error: {{type(e).__name__}}: {{str(e)}}"
    
    finally:
        sys.stdout = original_stdout
        try:
            signal.alarm(0)  # Cancel timeout
        except AttributeError:
            pass  # Windows doesn't have alarm
    
    # Print result (this goes to subprocess stdout)
    if output.strip():
        print(output.strip())
    else:
        print("Code executed successfully, but no output was printed.")
        
except TimeoutError:
    print("Error: Code execution timeout (30 seconds)")
except Exception as e:
    print(f"Error: {{type(e).__name__}}: {{str(e)}}")
'''
            
            # Create restricted environment
            restricted_env = {
                'PATH': '/usr/local/bin:/usr/bin:/bin',
                'PYTHONPATH': '',
                'HOME': '/tmp',
                'USER': 'nobody',
                'SHELL': '/bin/sh'
            }
            
            # Execute in subprocess with restrictions
            try:
                result = subprocess.run(
                    ['python', '-c', python_script],
                    capture_output=True,
                    text=True,
                    timeout=35,  # Slightly longer than internal timeout
                    env=restricted_env,
                    cwd='/tmp'  # Run in temporary directory
                )
                
                if result.returncode == 0:
                    return result.stdout.strip() or "Code executed successfully, but no output was generated."
                else:
                    error_output = result.stderr.strip() or result.stdout.strip()
                    return f"Execution failed: {error_output}"
                    
            except subprocess.TimeoutExpired:
                return "Error: Code execution timeout (35 seconds)"
            except subprocess.CalledProcessError as e:
                return f"Execution error: {e.stderr or e.stdout or str(e)}"
                
        except Exception as e:
            return f"Unexpected error during code execution: {str(e)}"
    
    def _encode_dataframe(self, df: pd.DataFrame) -> str:
        """Encode DataFrame as base64 pickle for passing to container"""
        import pickle
        import base64
        
        df_bytes = pickle.dumps(df)
        return base64.b64encode(df_bytes).decode('utf-8')
    
    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code for embedding in Python script"""
        lines = code.split('\n')
        indent = ' ' * spaces
        return '\n'.join(indent + line for line in lines)
    
    async def _arun(
        self,
        code: str,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(code, state, tool_call_id)


class DataFrameInfoTool(BaseTool):
    """
    Tool to get information about the current DataFrame in Redis.
    """
    
    name: str = "dataframe_info"
    description: str = """Get information about the current DataFrame stored in Redis.
    
    Use this tool to:
    - Check if a DataFrame is available
    - Get DataFrame metadata (shape, columns, creation time, etc.)
    - View sample data
    - Check expiration time
    
    No parameters required.
    
    Returns: Information about the current DataFrame or error if none available."""
    
    def _run(
        self,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Get DataFrame information from Redis"""
        
        try:
            if state is None:
                state = {}
            # Get DataFrame context from state
            data_context = state.get("data_context")
            if not data_context or not data_context.df_id:
                return "No DataFrame available. Please run a SQL query first using sql_db_to_df tool."
            
            # Get DataFrame and metadata from Redis
            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            metadata = redis_service.get_metadata(data_context.df_id)
            
            if df is None:
                return f"DataFrame {data_context.df_id} not found or expired. Please run the SQL query again."
            
            # Format information
            info = f"""**Current DataFrame Information:**

**Basic Info:**
- **ID:** {data_context.df_id}
- **Shape:** {data_context.shape[0]:,} rows × {data_context.shape[1]} columns
- **Created:** {data_context.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if data_context.created_at else 'Unknown'}
- **Expires:** {data_context.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC') if data_context.expires_at else 'Unknown'}

**Columns:** {', '.join(data_context.columns)}

**SQL Query:**
```sql
{data_context.sql_query or 'Not available'}
```

**Sample Data:**
{df.head(5).to_string(index=False)}

**Data Types:**
{df.dtypes.to_string()}

The DataFrame is ready for Python analysis using the python_repl tool."""
            
            return info
            
        except Exception as e:
            error_msg = f"Error getting DataFrame info: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    async def _arun(
        self,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool"""
        return self._run(state, tool_call_id)
