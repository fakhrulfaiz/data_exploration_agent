"""
XpAgent Toolkit.
Provides tools for the XpAgent multi-agent system.
"""

from typing import List, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from .xp_data_exploration_tool import XpDataExplorationTool
from .xp_image_qna_tool import XpImageQnATool
from .xp_data_plotting_tool import XpDataPlottingTool


class XpToolkit(BaseModel):
    """Toolkit providing tools for XpAgent."""
    
    model_name: str = Field(default="gpt-4o-mini", description="LLM model for tools")
    db_path: Optional[str] = Field(default=None, description="Path to SQLite database")
    use_gpu: Optional[bool] = Field(default=None, description="GPU configuration for image analysis")
    
    # Cached tool instances
    _data_exploration_tool: Optional[XpDataExplorationTool] = None
    _image_qna_tool: Optional[XpImageQnATool] = None
    _plotting_tool: Optional[XpDataPlottingTool] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(
        self, 
        model_name: str = "gpt-4o-mini",
        db_path: Optional[str] = None,
        use_gpu: Optional[bool] = None,
        **kwargs
    ):
        super().__init__(
            model_name=model_name,
            db_path=db_path,
            use_gpu=use_gpu,
            **kwargs
        )
    
    def get_data_exploration_tool(self) -> XpDataExplorationTool:
        """Get or create data exploration tool."""
        if self._data_exploration_tool is None:
            self._data_exploration_tool = XpDataExplorationTool(
                model_name=self.model_name,
                db_path=self.db_path
            )
        return self._data_exploration_tool
    
    def get_image_qna_tool(self) -> XpImageQnATool:
        """Get or create image QnA tool."""
        if self._image_qna_tool is None:
            self._image_qna_tool = XpImageQnATool(
                model_name=self.model_name,
                use_gpu=self.use_gpu
            )
        return self._image_qna_tool
    
    def get_plotting_tool(self) -> XpDataPlottingTool:
        """Get or create plotting tool."""
        if self._plotting_tool is None:
            self._plotting_tool = XpDataPlottingTool(
                model_name=self.model_name
            )
        return self._plotting_tool
    
    def get_tools(self) -> List[BaseTool]:
        """Get all available tools."""
        return [
            self.get_data_exploration_tool(),
            self.get_image_qna_tool(),
            self.get_plotting_tool(),
        ]
    
    def get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        """Get a specific tool by name."""
        tool_map = {
            "database_exploration_agent": self.get_data_exploration_tool,
            "image_qna_agent": self.get_image_qna_tool,
            "data_plotting_agent": self.get_plotting_tool,
        }
        factory = tool_map.get(name)
        if factory:
            return factory()
        return None
    
    def reset(self):
        """Reset all cached tools."""
        self._data_exploration_tool = None
        self._image_qna_tool = None
        self._plotting_tool = None
