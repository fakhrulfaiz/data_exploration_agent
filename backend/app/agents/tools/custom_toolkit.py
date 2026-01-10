"""
Custom toolkit for the explainable agent project.
Automatically passes LLM instance and database engine to custom tools.
"""

from langchain_core.tools import BaseTool
from pydantic import BaseModel
from typing import List, Any, Optional
from pydantic import Field
from .visualization_tools import SmartTransformForVizTool, LargePlottingTool
from .data_analysis_tools import SecurePythonREPLTool, DataFrameInfoTool
from .data_exploration_agent_tool import DataExplorationAgentTool
from .image_QA_tools import ImageBatchQATool


class CustomToolkit(BaseModel):
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
            ImageBatchQATool(),
        ]
        
        if self.db_engine is not None:
            tools.append(LargePlottingTool(llm=self.llm))
            
            if self.db_path is not None:
                tools.append(DataExplorationAgentTool(
                    llm=self.llm,
                    db_engine=self.db_engine,
                    db_path=self.db_path
                ))
        
        return tools
    