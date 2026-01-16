"""
Data Analysis Tools for the explainable agent project.
Includes SQL to DataFrame conversion and secure Python REPL execution.
"""

import re
import json
import uuid
import logging
import json
import uuid
import logging
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
    # Removes `, whitespace & python from start
    query = re.sub(r"^(\s|`)*(?i:python)?\s*", "", query)
    # Removes whitespace & ` from end
    query = re.sub(r"(\s|`)*$", "", query)
    return query



class SmartDataAnalysisTool(BaseTool):
    """
    Tool that uses LLM to write and execute Pandas code for data analysis.
    Replaces raw Python REPL with a safer, goal-oriented interface.
    """
    
    name: str = "smart_data_analysis"
    description: str = """Analyze data using natural language requests.
    
    Use this tool to:
    - Complex transformations (filtering, sorting, grouping, or aggregating data)
    - Calculating statistics (mean, sum, count, percentiles)
    - Answering specific questions about the dataset
    - Creating derived columns or complex calculations
    
    DO NOT use this tool for:
    - Simple counting before plotting (large_plotting_tool does this automatically)
    - Aggregating data just to visualize it (large_plotting_tool handles aggregation)
    
    Parameters:
    - analysis_request (str): A description of what you want to calculate or find out about the data.
    
    IMPORTANT: This tool works on EXISTING DataFrame columns. It CANNOT analyze images directly.
    For visual questions (e.g. "depicting"), use image_batch_qa_tool FIRST to create the data.
    
    Example: 
    - "Calculate the average inception year by movement"
    - "Count paintings where 'depicts_swords' is 'yes' (after image analysis)"
    
    Returns: The result of the analysis."""
    
    llm: Any = Field(description="Language model instance for code generation")
    
    def _run(
        self,
        analysis_request: str,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute the smart analysis tool"""
        from langchain_experimental.tools import PythonAstREPLTool
        from langchain_core.prompts import ChatPromptTemplate
        
        try:
            if state is None:
                state = {}
            
            # 1. GET DATAFRAME
            data_context = state.get("data_context")
            if not data_context or not data_context.df_id:
                return json.dumps({
                    "error": "No active DataFrame found. Please run a data retrieval query first.",
                    "error_type": "resource_not_found",
                    "tool_name": "smart_data_analysis",
                    "recoverable": False
                })
                
            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            
            if df is None:
                return json.dumps({
                    "error": f"DataFrame {data_context.df_id} not found or expired.",
                    "error_type": "resource_not_found",
                    "tool_name": "smart_data_analysis",
                    "details": {"df_id": data_context.df_id},
                    "recoverable": True
                })
                
            redis_service.extend_ttl(data_context.df_id)
            
            # 2. GENERATE CODE
            columns_info = str(list(df.columns))
            dtypes_info = str(df.dtypes)
            head_info = str(df.head(3).to_dict())
            
            system_prompt = """You are a Python Pandas expert. Write Python code to answer the user's data analysis request.
            
            DATA CONTEXT:
            - A pandas DataFrame 'df' is loaded.
            - Columns: {columns}
            - Types: {dtypes}
            - Sample: {head}
            
            RULES:
            1. Use 'df' variable.
            2. Write ONLY valid Python code. No markdown blocks.
            3. The LAST line must be an expression or print statement that outputs the result.
            4. Do not use plotting functions (plot, matplotlib).
            
            """
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{request}")
            ])
            
            chain = prompt | self.llm
            code_response = chain.invoke({
                "columns": columns_info,
                "dtypes": dtypes_info,
                "head": head_info,
                "request": analysis_request
            })
            
            code = code_response.content if hasattr(code_response, "content") else str(code_response)
            code = code.replace("```python", "").replace("```", "").strip()
            
            logger.info(f"Generated Analysis Code: {code}")
            
            # 3. EXECUTE CODE SAFE
            repl = PythonAstREPLTool(locals={"df": df})
            result = repl.run(code)
            
            return f"Analysis Result:\n{result}"
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return json.dumps({
                "error": f"Error performing analysis: {str(e)}",
                "error_type": "execution_error",
                "tool_name": "smart_data_analysis",
                "details": {"exception": str(e)},
                "recoverable": True
            })

    async def _arun(self, analysis_request: str, state: Annotated[Dict[str, Any], InjectedState] = None, tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None) -> str:
        return self._run(analysis_request, state, tool_call_id)
