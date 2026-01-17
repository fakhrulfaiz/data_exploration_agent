"""
XpAgent Data Plotting Tool.
Wraps the data_plotting_sub agent as a LangChain tool for XpAgent.
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

logger = logging.getLogger(__name__)

# Workspace configuration - keep using dev workspace
WORKSPACE_PATH = Path("/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace")
PLOT_PATH = WORKSPACE_PATH / "plot"
OUTPUT_PATH = WORKSPACE_PATH / "outputs"

# Ensure directories exist
os.makedirs(PLOT_PATH, exist_ok=True)
os.makedirs(OUTPUT_PATH, exist_ok=True)


class XpDataPlottingTool(BaseTool):
    """Tool wrapper for data plotting subagent."""
    
    name: str = "data_plotting_agent"
    description: str = """Create data visualizations from CSV data.
    
    CAPABILITIES:
    - Bar charts, line charts, scatter plots, pie charts, histograms
    - LLM-powered code generation for custom plots
    - Automatic file path handling
    - Saves plots to workspace/plot directory
    
    Parameters:
    - task (str): Description of the visualization to create
    - file_path (optional str): Path to CSV file. If not provided, uses latest from previous step.
    
    IMPORTANT:
    - Do NOT specify file_path - system automatically uses CSV from previous step
    - Just describe what plot you want: "Create a bar chart showing distribution"
    
    Returns: Plot file path and execution result.
    """
    
    model_name: str = Field(default="gpt-4o-mini", description="LLM model to use")
    _agent: Any = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, model_name: str = "gpt-4o-mini", **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Lazy initialize the subagent."""
        try:
            from app.agents.dev.agent.data_plotting_sub import build_plotting_agent
            self._agent = build_plotting_agent(
                model_name=self.model_name
            )
            logger.info(f"XpDataPlottingTool initialized with model {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize plotting agent: {e}")
            raise
    
    def _find_latest_csv(self) -> Optional[str]:
        """Find the most recent CSV file in outputs directory."""
        try:
            csv_files = list(OUTPUT_PATH.glob("*.csv"))
            if csv_files:
                # Sort by modification time, newest first
                csv_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                return str(csv_files[0])
        except Exception as e:
            logger.warning(f"Error finding CSV files: {e}")
        return None
    
    def _run(self, task: str, file_path: Optional[str] = None) -> str:
        """Execute data plotting task."""
        try:
            logger.info(f"XpDataPlottingTool executing: {task[:100]}...")
            
            # Find CSV if not provided
            if not file_path:
                file_path = self._find_latest_csv()
                if file_path:
                    logger.info(f"Auto-detected CSV file: {file_path}")
            
            # Build full task with file path
            if file_path:
                full_task = f"""Create plots for: {task}

Data file: {file_path}

IMPORTANT: Use the exact file path above when calling the generate_plot tool."""
            else:
                full_task = task
                logger.warning("No CSV file found. Agent will attempt to proceed without data file.")
            
            # Build proper initial state - must include all DataPlottingState fields
            initial_state = {
                "messages": [HumanMessage(content=full_task)],
                "original_task": task,
                "files_to_plot": [file_path] if file_path else [],
                "files_plotted": [],
                "plot_records": [],
                "plots_generated": [],
                "tools_complete": False,
                "result_summary": ""
            }
            
            # Invoke the subagent with complete initial state
            result_state = self._agent.invoke(
                initial_state,
                {"configurable": {"thread_id": f"xp_plotting_{id(self)}"}}
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
            
            # Check for plot output
            plot_path = None
            if ".png" in result_content:
                png_match = re.search(r'([\S]+\.png)', result_content)
                if png_match:
                    plot_path = png_match.group(1)
            
            # Also check plot records in state
            plot_records = result_state.get("plot_records", [])
            if plot_records and not plot_path:
                for record in plot_records:
                    if hasattr(record, 'output_path') and record.output_path:
                        plot_path = record.output_path
                        break
            
            response = {
                "success": True,
                "result": result_content,
                "plot_file": plot_path,
                "data_file": file_path
            }
            
            logger.info(f"XpDataPlottingTool completed. Plot: {plot_path}")
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"XpDataPlottingTool error: {e}", exc_info=True)
            return json.dumps({
                "success": False,
                "error": str(e)
            })
    
    async def _arun(self, task: str, file_path: Optional[str] = None) -> str:
        """Async version - falls back to sync."""
        return self._run(task, file_path)
