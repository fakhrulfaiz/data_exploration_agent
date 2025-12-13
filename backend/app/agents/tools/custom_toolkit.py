"""
Custom toolkit for the explainable agent project.
Automatically passes LLM instance and database engine to custom tools.
"""

from langchain.agents.agent_toolkits.base import BaseToolkit
from langchain.tools import BaseTool
from typing import List, Any, Optional
from pydantic import Field
from .visualization_tools import SmartTransformForVizTool, LargePlottingTool
from .data_analysis_tools import SqlToDataFrameTool, SecurePythonREPLTool, DataFrameInfoTool
from .text2sql_tool import Text2SQLTool


class CustomToolkit(BaseToolkit):
    llm: Any = Field(description="Language model instance")
    db_engine: Optional[Any] = Field(default=None, description="Database engine for SQL execution")
    db_path: Optional[str] = Field(default=None, description="Path to SQLite database")
    
    def __init__(self, llm: Any, db_engine: Any = None, db_path: str = None, **kwargs):
        super().__init__(llm=llm, db_engine=db_engine, db_path=db_path, **kwargs)
    
    def get_tools(self) -> List[BaseTool]:
        tools = [
            SmartTransformForVizTool(llm=self.llm),
            SecurePythonREPLTool(),
            DataFrameInfoTool(),
        ]
        
        if self.db_engine is not None:
            tools.extend([
                SqlToDataFrameTool(db_engine=self.db_engine),
                LargePlottingTool(llm=self.llm),
            ])
        
        if self.db_path is not None:
            tools.append(Text2SQLTool(llm=self.llm, db_path=self.db_path))
        
        return tools