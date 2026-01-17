"""
XpAgent V2 - Simplified experimental agent.

This is a minimal agent implementation following the XpAgent architecture
but using the same integration pattern as MainAgent for streaming compatibility.

Key design principles:
- Uses ExplainableAgentState for streaming compatibility
- Has its own workspace: backend/app/agents/workspace
- Used in experiment_mode

v2.2 Changes:
- Added SubagentFactory for tool management (matches dev blueprint)
- Added executor node for step execution
- Added StepResult model for tracking execution results
- Graph flow: START -> planner -> executor -> finalizer -> END
- Tools: data_exploration_agent (Phase 1)
"""

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional, Literal
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

from app.agents.state import ExplainableAgentState

logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================

class PlanStep(BaseModel):
    """A single step in the execution plan - matches XpAgent dev blueprint."""
    step_number: int = Field(description="Step number (1-indexed)")
    description: str = Field(description="What this step accomplishes")
    tool_name: Literal["database_exploration_agent", "image_qna_agent", "data_plotting_agent"] = Field(
        description="Which tool to use for this step"
    )
    tool_args_json: str = Field(
        default="{}",
        description="JSON string of arguments to pass to the tool. E.g. '{\"query\": \"Find all paintings\"}'"
    )
    depends_on: List[int] = Field(
        default_factory=list,
        description="Step numbers this step depends on"
    )
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = Field(
        default="pending",
        description="Current status of this step"
    )


class ExecutionPlan(BaseModel):
    """Structured execution plan - matches XpAgent dev blueprint."""
    understanding: str = Field(
        description="Your understanding of what the user wants to achieve"
    )
    minimal_approach: str = Field(
        description="Explain why this is the MINIMUM number of steps needed"
    )
    steps: List[PlanStep] = Field(
        description="MINIMAL list of steps - only include steps that are absolutely necessary",
        default_factory=list
    )
    reasoning: str = Field(
        description="Why this minimal plan will accomplish the user's goal efficiently"
    )


# Database schema context for planning
DATABASE_SCHEMA = """
## Table: paintings

### Columns
| Column Name | Data Type | Description |
|------------|-----------|-------------|
| title | TEXT | Name of the painting |
| inception | INTEGER | Year the painting was created |
| movement | TEXT | Art movement (e.g., Renaissance, Baroque) |
| genre | TEXT | Artistic genre (e.g., portrait, landscape) |
| image_url | TEXT | Public URL to the painting image (DO NOT USE for image analysis) |
| img_path | TEXT | Local file path to the image - USE THIS for image_qna_agent |

### Image Analysis Workflow
1. ALWAYS use `img_path` column (NOT image_url) for visual analysis
2. First query database to get img_path values
3. Then pass those img_path values to image_qna_agent
"""


# Tool capabilities for planning
TOOL_CAPABILITIES = {
    "database_exploration_agent": {
        "description": "Queries SQL database for artwork metadata. Can access: title, inception, movement, genre, image_url, img_path.",
        "can_produce_csv": True,
        "requires_csv_input": False
    },
    "image_qna_agent": {
        "description": "Analyzes visual content of images using AI. REQUIRES img_path from database.",
        "can_produce_csv": True,
        "requires_csv_input": False
    },
    "data_plotting_agent": {
        "description": "Creates visualizations from CSV data. Supports: bar, line, scatter, pie charts.",
        "can_produce_csv": False,
        "requires_csv_input": True
    }
}


# ============================================================================
# CONFIGURATION (must be before SubagentFactory)
# ============================================================================

DEFAULT_MODEL = "gpt-4o-mini"

# Use relative paths that work in both Docker and local environments
# __file__ is the path to this script, so we go up to find the backend root
_CURRENT_DIR = Path(__file__).resolve().parent  # /app/app/agents in Docker, or local path
_BACKEND_ROOT = _CURRENT_DIR.parent.parent  # /app in Docker, or backend/ locally

DEFAULT_DB_PATH = str(_BACKEND_ROOT / "app" / "resource" / "art.db")

# XpAgentV2 has its own workspace (relative to agents directory)
WORKSPACE_PATH = _CURRENT_DIR / "workspace"
OUTPUT_PATH = WORKSPACE_PATH / "outputs"
PLOT_PATH = WORKSPACE_PATH / "plot"

# Debug: Print resolved paths
print(f"🔧 XpAgentV2 Path Configuration:")
print(f"   _CURRENT_DIR: {_CURRENT_DIR}")
print(f"   _BACKEND_ROOT: {_BACKEND_ROOT}")
print(f"   WORKSPACE_PATH: {WORKSPACE_PATH}")
print(f"   OUTPUT_PATH: {OUTPUT_PATH}")
print(f"   DEFAULT_DB_PATH: {DEFAULT_DB_PATH}")

# Ensure workspace directories exist
os.makedirs(OUTPUT_PATH, exist_ok=True)
os.makedirs(PLOT_PATH, exist_ok=True)


# ============================================================================
# STEP RESULT MODEL (from dev blueprint)
# ============================================================================

class StepResult(BaseModel):
    """Result from executing a step - matches dev blueprint."""
    step_number: int = Field(..., description="Which step this result is for")
    success: bool = Field(..., description="Whether the step succeeded")
    result_content: str = Field(default="", description="The actual result content")
    output_file: Optional[str] = Field(default=None, description="Output file path if any")
    error_message: str = Field(default="", description="Error message if failed")


# ============================================================================
# SUBAGENT FACTORY (from dev blueprint)
# ============================================================================

class SubagentFactory:
    """
    Factory for creating and caching subagents with consistent configuration.
    Follows the dev blueprint pattern for lazy initialization.
    """
    
    def __init__(self, model_name: str = DEFAULT_MODEL, db_path: Optional[str] = None):
        """
        Initialize the factory with configuration.
        
        Args:
            model_name: LLM model to use for all subagents
            db_path: Path to the database for data exploration
        """
        self.model_name = model_name
        self.db_path = db_path or DEFAULT_DB_PATH
        self.output_path = OUTPUT_PATH  # Use XpAgentV2's workspace path
        
        # Cached agents (compiled LangGraph subagents)
        self._data_exploration_graph = None
        self._image_qna_agent = None
        self._plotting_agent = None
    
    def get_data_exploration_graph(self):
        """
        Get or create the data exploration subagent graph.
        
        Uses the dev blueprint pattern: builds a LangGraph subagent that executes
        SQL queries with full context tracking (list tables -> get schema -> 
        generate query -> run query -> evaluate -> export).
        """
        if self._data_exploration_graph is None:
            logger.info(f"📊 Building data exploration graph with model: {self.model_name}")
            logger.info(f"   Output path: {self.output_path}")
            # Import from dev blueprint
            from app.agents.dev.agent.data_exploration_sub import build_data_exploration_agent
            
            self._data_exploration_graph = build_data_exploration_agent(
                model_name=self.model_name,
                db_path=self.db_path,
                output_path=self.output_path  # Pass XpAgentV2's output path
            )
            logger.info(f"✅ Data exploration graph built successfully")
        return self._data_exploration_graph
    
    def get_image_qna_agent(self):
        """
        Get or create the image QnA agent.
        
        Uses the dev blueprint pattern: builds a LangGraph subagent that analyzes
        images using BLIP model for visual question answering.
        """
        if self._image_qna_agent is None:
            logger.info(f"🖼️ Building image QnA agent with model: {self.model_name}")
            logger.info(f"   Output path: {self.output_path}")
            # Import from dev blueprint
            from app.agents.dev.agent.image_qna_sub import build_image_qna_agent
            
            self._image_qna_agent = build_image_qna_agent(
                model_name=self.model_name,
                use_gpu=True,
                output_path=self.output_path  # Pass XpAgentV2's output path
            )
            logger.info(f"✅ Image QnA agent built successfully")
        return self._image_qna_agent
    
    def get_plotting_agent(self):
        """
        Get or create the plotting agent.
        
        Uses the dev blueprint pattern: builds a LangGraph subagent that creates
        visualizations from CSV data using LLM-based code generation.
        """
        if self._plotting_agent is None:
            logger.info(f"📈 Building plotting agent with model: {self.model_name}")
            logger.info(f"   Workspace path: {WORKSPACE_PATH}")
            logger.info(f"   Plot path: {PLOT_PATH}")
            # Import from dev blueprint
            from app.agents.dev.agent.data_plotting_sub import build_plotting_agent
            
            self._plotting_agent = build_plotting_agent(
                model_name=self.model_name,
                workspace_dir=str(WORKSPACE_PATH),
                plot_output_dir=str(PLOT_PATH)
            )
            logger.info(f"✅ Plotting agent built successfully")
        return self._plotting_agent
    
    def reset(self):
        """Reset all cached agents (useful for testing)."""
        self._data_exploration_graph = None
        self._image_qna_agent = None
        self._plotting_agent = None


# ============================================================================
# TOOL EXECUTION FUNCTIONS (from dev blueprint)
# ============================================================================

def _extract_csv_paths_from_content(content: str) -> List[str]:
    """Extract CSV file paths from result content."""
    csv_paths = []
    
    # Pattern 1: "saved to: /path/to/file.csv"
    saved_matches = re.findall(r'saved to:?\s*([\S]+\.csv)', content, re.IGNORECASE)
    csv_paths.extend(saved_matches)
    
    # Pattern 2: Full absolute paths
    abs_matches = re.findall(r'(/[\w/.-]+\.csv)', content)
    csv_paths.extend(abs_matches)
    
    # Pattern 3: df_id patterns
    df_id_matches = re.findall(r'df:[\w]+', content)
    csv_paths.extend(df_id_matches)
    
    return list(set(csv_paths))


def _extract_img_paths_from_context(context: str) -> List[str]:
    """Extract image paths from tool context (previous step results)."""
    import re
    
    img_paths = []
    
    # Pattern 1: "img_path": "images/img_X.jpg" (from JSON-like content)
    json_matches = re.findall(r'"img_path"\s*:\s*"([^"]+)"', context)
    img_paths.extend(json_matches)
    
    # Pattern 2: images/img_X.jpg pattern (common artwork path format)
    direct_matches = re.findall(r'images/img_\d+\.jpg', context)
    img_paths.extend(direct_matches)
    
    # Pattern 3: img_path column in table format (e.g., "| images/img_0.jpg |")
    table_matches = re.findall(r'\|\s*(images/img_\d+\.jpg)\s*\|', context)
    img_paths.extend(table_matches)
    
    # Pattern 4: "Images to analyze: [...]" format
    json_array_match = re.search(r'Images to analyze:\s*(\[.*?\])', context, re.DOTALL)
    if json_array_match:
        try:
            import json
            parsed = json.loads(json_array_match.group(1))
            if isinstance(parsed, list):
                img_paths.extend([p for p in parsed if isinstance(p, str)])
        except json.JSONDecodeError:
            pass
    
    return list(set(img_paths))


def _extract_img_paths_from_csv(csv_path: str) -> List[str]:
    """Extract image paths from a CSV file's img_path column."""
    import pandas as pd
    import os
    
    if not os.path.exists(csv_path):
        return []
    
    try:
        df = pd.read_csv(csv_path)
        
        # Check for img_path column (case-insensitive)
        img_col = None
        for col in df.columns:
            if col.lower() in ['img_path', 'image_path', 'img_url', 'image_url', 'path']:
                img_col = col
                break
        
        if img_col and img_col in df.columns:
            # Get unique non-null values
            paths = df[img_col].dropna().unique().tolist()
            return [str(p) for p in paths if p]
        
        return []
    except Exception as e:
        logger.warning(f"Failed to extract img_paths from CSV {csv_path}: {e}")
        return []


def execute_data_exploration(query: str, factory: SubagentFactory) -> tuple:
    """
    Execute data exploration using the LangGraph subagent.
    
    This follows the dev blueprint pattern: the subagent handles
    list tables -> get schema -> generate query -> run query -> evaluate -> CSV export.
    
    Args:
        query: Natural language query for data exploration
        factory: SubagentFactory with cached graph
        
    Returns:
        Tuple of (StepResult, context_string)
    """
    from langchain_core.messages import HumanMessage
    
    try:
        logger.info(f"🔍 Executing data exploration: {query[:100]}...")
        
        # Get the compiled graph from factory
        graph = factory.get_data_exploration_graph()
        
        # Initialize state following blueprint pattern
        initial_state = {
            "messages": [HumanMessage(content=query)],
            "original_task": query,
            "query_history": [],
            "tables_queried": [],
            "exploration_complete": False,
            "ready_for_export": False
        }
        
        # Run the graph
        result = graph.invoke(initial_state)
        
        # DEBUG: Check if files exist after subagent completes
        import os as os_module
        print(f"🔍 DEBUG: After graph.invoke() in execute_data_exploration")
        print(f"   Checking workspace outputs directory:")
        outputs_dir = str(WORKSPACE_PATH / "outputs")
        if os_module.path.exists(outputs_dir):
            files = os_module.listdir(outputs_dir)
            print(f"   Files in {outputs_dir}: {files}")
            for f in files:
                fpath = os_module.path.join(outputs_dir, f)
                print(f"      - {f}: {os_module.path.getsize(fpath)} bytes")
        else:
            print(f"   Directory does not exist: {outputs_dir}")
        
        # Extract results from state
        messages = result.get("messages", [])
        result_summary = result.get("result_summary", "")
        query_history = result.get("query_history", [])
        
        # Get the final message content
        final_content = ""
        output_file = None
        
        if messages:
            last_msg = messages[-1]
            final_content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
            
            # Extract CSV path if present
            csv_paths = _extract_csv_paths_from_content(final_content)
            if csv_paths:
                output_file = csv_paths[0]
        
        # Build context string for downstream tools
        context = f"## Database Query Result\n\n"
        context += f"**Query**: {query}\n\n"
        
        if result_summary:
            context += f"**Summary**:\n{result_summary}\n\n"
        
        if query_history:
            context += f"**Queries Executed**: {len(query_history)}\n"
            # Show last query details
            last_query = query_history[-1]
            if hasattr(last_query, 'query'):
                context += f"**Last SQL**: `{last_query.query}`\n"
                context += f"**Row Count**: {last_query.row_count}\n"
        
        if output_file:
            context += f"\n**Output File**: `{output_file}`\n"
        
        # Check if exploration was successful
        success = result.get("exploration_complete", False) or "✅" in final_content or output_file is not None
        
        step_result = StepResult(
            step_number=0,
            success=success,
            result_content=final_content,
            output_file=output_file
        )
        
        logger.info(f"✅ Data exploration completed. Success: {success}, Output: {output_file}")
        return step_result, context
        
    except Exception as e:
        logger.error(f"Data exploration error: {e}")
        return StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        ), f"Error in data exploration: {str(e)}"


def execute_image_qna(
    task: str,
    image_urls: List[str],
    factory: SubagentFactory
) -> tuple:
    """
    Execute image QnA analysis using the LangGraph subagent.
    
    This follows the dev blueprint pattern: the subagent handles
    image loading -> BLIP analysis -> LLM synthesis -> CSV export.
    
    Args:
        task: Natural language task for image analysis
        image_urls: List of image URLs/paths to analyze
        factory: SubagentFactory with cached graph
        
    Returns:
        Tuple of (StepResult, context_string)
    """
    from langchain_core.messages import HumanMessage
    
    try:
        logger.info(f"🖼️ Executing image QnA: {task[:100]}...")
        logger.info(f"   Images: {len(image_urls)} images to process")
        
        # Validate image paths
        if not image_urls:
            return StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message="No image paths available for analysis. Please run a database query first to get images with img_path column."
            ), "Error: No image paths provided for image QnA. Please ensure a data exploration step runs first that retrieves img_path values."
        
        # Get the compiled graph from factory
        graph = factory.get_image_qna_agent()
        
        # Build message with images included for agent to extract
        message_content = f"{task}\n\nImages to analyze: {json.dumps(image_urls)}"
        
        # Initialize state following blueprint pattern
        initial_state = {
            "messages": [HumanMessage(content=message_content)],
            "original_task": task,
            "images_to_process": image_urls,
            "images_processed": [],
            "analysis_records": [],
            "tools_complete": False
        }
        
        logger.info(f"   Initial state images_to_process: {image_urls}")
        
        # Run the graph
        result = graph.invoke(initial_state)
        
        # Extract results from state
        messages = result.get("messages", [])
        result_summary = result.get("result_summary", "")
        analysis_records = result.get("analysis_records", [])
        
        # Get the final message content
        final_content = ""
        output_file = None
        
        if messages:
            last_msg = messages[-1]
            final_content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
            
            # Extract CSV path if present
            csv_paths = _extract_csv_paths_from_content(final_content)
            if csv_paths:
                output_file = csv_paths[0]
        
        # Build context string for downstream tools
        context = f"## Image Analysis Result\n\n"
        context += f"**Task**: {task}\n\n"
        context += f"**Images Analyzed**: {len(analysis_records)}\n\n"
        
        if result_summary:
            context += f"**Summary**:\n{result_summary}\n\n"
        
        if output_file:
            context += f"\n**Output File**: `{output_file}`\n"
        
        # Check if analysis was successful
        success = result.get("tools_complete", False) or "✅" in final_content or output_file is not None
        
        step_result = StepResult(
            step_number=0,
            success=success,
            result_content=final_content,
            output_file=output_file
        )
        
        logger.info(f"✅ Image QnA completed. Success: {success}, Output: {output_file}")
        return step_result, context
        
    except Exception as e:
        logger.error(f"Image QnA error: {e}")
        return StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        ), f"Error in image QnA: {str(e)}"


def execute_plotting(
    task: str,
    file_path: str,
    factory: SubagentFactory
) -> tuple:
    """
    Execute data plotting using the LangGraph subagent.
    
    This follows the dev blueprint pattern: the subagent handles
    CSV reading -> LLM code generation -> matplotlib execution -> save plot.
    
    Args:
        task: Natural language task for plotting
        file_path: Path to the CSV file to visualize
        factory: SubagentFactory with cached graph
        
    Returns:
        Tuple of (StepResult, context_string)
    """
    from langchain_core.messages import HumanMessage
    
    try:
        logger.info(f"📈 Executing plotting: {task[:100]}...")
        logger.info(f"   File: {file_path}")
        
        # Validate file path
        if not file_path:
            return StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message="No CSV file available for plotting. Please run a database query first to generate data."
            ), "Error: No CSV file provided for plotting. Please ensure a data exploration step runs first."
        
        # Get the compiled graph from factory
        graph = factory.get_plotting_agent()
        
        # Initialize state following blueprint pattern
        initial_state = {
            "messages": [HumanMessage(content=f"Create plots for: {task}\nData file: {file_path}")],
            "original_task": task,
            "files_to_plot": [file_path],
            "plot_records": [],
            "plots_generated": [],
            "tools_complete": False,
            "result_summary": ""
        }
        
        # Run the graph
        result = graph.invoke(initial_state)
        
        # Extract results from state
        messages = result.get("messages", [])
        result_summary = result.get("result_summary", "")
        plots_generated = result.get("plots_generated", [])
        
        # Get the final message content
        final_content = ""
        output_files = []
        
        if messages:
            last_msg = messages[-1]
            final_content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        # Add generated plots to output files
        if plots_generated:
            output_files.extend(plots_generated)
        
        # Build context string for downstream tools
        context = f"## Plotting Result\n\n"
        context += f"**Task**: {task}\n\n"
        context += f"**Input File**: `{file_path}`\n\n"
        
        if result_summary:
            context += f"**Summary**:\n{result_summary}\n\n"
        
        if plots_generated:
            context += f"**Generated Plots**:\n"
            for plot_path in plots_generated:
                context += f"- `{plot_path}`\n"
        
        # Check if plotting was successful
        success = result.get("tools_complete", False) or len(plots_generated) > 0 or "✅" in final_content
        
        step_result = StepResult(
            step_number=0,
            success=success,
            result_content=final_content,
            output_file=plots_generated[0] if plots_generated else None
        )
        
        logger.info(f"✅ Plotting completed. Success: {success}, Plots: {len(plots_generated)}")
        return step_result, context
        
    except Exception as e:
        logger.error(f"Plotting error: {e}")
        return StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        ), f"Error in plotting: {str(e)}"


def _execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    tool_context: str,
    factory: SubagentFactory,
    generated_files: Optional[List[str]] = None,
    step_results: Optional[List[StepResult]] = None
) -> tuple:
    """
    Execute a tool and return the result with context string.
    Follows dev blueprint pattern.
    """
    generated_files = generated_files or []
    step_results = step_results or []
    
    if tool_name == "database_exploration_agent":
        query = args.get("query", "")
        return execute_data_exploration(query, factory)
    
    elif tool_name == "image_qna_agent":
        task = args.get("task", args.get("query", ""))
        image_urls = args.get("image_urls", args.get("images", []))
        
        # If no image_urls provided, try to find them from previous steps
        if not image_urls:
            # First, try to extract from tool_context (contains previous step results)
            image_urls = _extract_img_paths_from_context(tool_context)
            if image_urls:
                logger.info(f"🖼️ Auto-detected {len(image_urls)} images from tool_context")
            
            # If still no images, check step_results for CSV files with img_path column
            if not image_urls and step_results:
                for step in reversed(step_results):
                    if step.output_file and step.output_file.endswith('.csv'):
                        extracted = _extract_img_paths_from_csv(step.output_file)
                        if extracted:
                            image_urls = extracted
                            logger.info(f"🖼️ Auto-detected {len(image_urls)} images from CSV: {step.output_file}")
                            break
            
            # Last resort: check generated_files for CSVs
            if not image_urls:
                csv_files = [f for f in generated_files if f.endswith('.csv')]
                for csv_file in reversed(csv_files):
                    extracted = _extract_img_paths_from_csv(csv_file)
                    if extracted:
                        image_urls = extracted
                        logger.info(f"🖼️ Auto-detected {len(image_urls)} images from generated CSV: {csv_file}")
                        break
        
        if not image_urls:
            logger.warning("⚠️ No image paths found for image QnA. Agent will attempt to proceed without images.")
        
        return execute_image_qna(task, image_urls, factory)
    
    elif tool_name == "data_plotting_agent":
        task = args.get("task", args.get("query", ""))
        file_path = args.get("file_path", args.get("csv_path", ""))
        
        # If no file_path provided, try to find one from previous steps
        if not file_path:
            # First, check generated_files for CSV files (most recent first)
            csv_files = [f for f in reversed(generated_files) if f.endswith('.csv')]
            if csv_files:
                file_path = csv_files[0]
                logger.info(f"📈 Auto-detected CSV from generated_files: {file_path}")
            
            # If still no file, check step_results for output files
            if not file_path and step_results:
                for step in reversed(step_results):
                    if step.output_file and step.output_file.endswith('.csv'):
                        file_path = step.output_file
                        logger.info(f"📈 Auto-detected CSV from step_results: {file_path}")
                        break
            
            # Last resort: find the most recent CSV in the outputs directory
            if not file_path:
                try:
                    csv_candidates = list(OUTPUT_PATH.glob("*.csv"))
                    if csv_candidates:
                        # Sort by modification time, newest first
                        csv_candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        file_path = str(csv_candidates[0])
                        logger.info(f"📈 Auto-detected latest CSV from outputs: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to scan outputs directory: {e}")
        
        if not file_path:
            logger.warning("⚠️ No CSV file found for plotting. Agent will attempt to proceed without data.")
        
        return execute_plotting(task, file_path, factory)
    
    else:
        return StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=f"Unknown tool: {tool_name}"
        ), f"Error: Unknown tool {tool_name}"


# ============================================================================
# XP AGENT V2 CLASS
# ============================================================================

class XpAgentV2:
    """
    Simplified experimental agent following XpAgent architecture.
    
    This version starts with no tools and will be extended incrementally.
    Uses ExplainableAgentState for streaming compatibility.
    """
    
    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        db_path: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        checkpointer: Optional[Any] = None,
        use_postgres_checkpointer: bool = True,
        logs_dir: Optional[str] = None
    ):
        self.model_name = model_name
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Initialize LLM
        if llm is not None:
            self.llm = llm
        else:
            self.llm = init_chat_model(model_name)
        
        # Initialize SubagentFactory for tool execution (from dev blueprint)
        self.factory = SubagentFactory(model_name=model_name, db_path=self.db_path)
        
        # Setup logs directory
        if logs_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logs_dir = os.path.join(backend_dir, "logs")
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Setup checkpointer
        if checkpointer is not None:
            self.checkpointer = checkpointer
        elif use_postgres_checkpointer:
            try:
                from app.core.checkpointer import checkpointer_manager
                from app.core.database import db_manager
                from langgraph.checkpoint.postgres import PostgresSaver
                import psycopg
                
                if checkpointer_manager.is_initialized():
                    db_uri = db_manager.get_db_uri()
                    conn = psycopg.connect(db_uri, autocommit=True)
                    self.checkpointer = PostgresSaver(conn)
                    logger.info("XpAgentV2 using PostgresSaver checkpointer")
                else:
                    logger.warning("Checkpointer not initialized, falling back to MemorySaver")
                    self.checkpointer = MemorySaver()
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL checkpointer for XpAgentV2: {e}")
                self.checkpointer = MemorySaver()
        else:
            self.checkpointer = MemorySaver()
        
        # Build the graph
        self.graph = self._create_graph()
        self._save_graph_visualization()
        logger.info("XpAgentV2 initialized successfully")
    
    def _save_graph_visualization(self):
        """Save graph visualization for debugging."""
        try:
            graph_image = self.graph.get_graph().draw_mermaid_png()
            graph_path = os.path.join(self.logs_dir, "xp_agent_v2_graph.png")
            with open(graph_path, "wb") as f:
                f.write(graph_image)
            logger.info(f"XpAgentV2 graph visualization saved to: {graph_path}")
        except Exception as e:
            logger.warning(f"Failed to generate XpAgentV2 graph visualization: {e}")
    
    # ========================================================================
    # GRAPH NODES
    # ========================================================================
    
    def _planner_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Planning node that analyzes the user query and creates an execution plan.
        
        This node follows the XpAgent dev blueprint:
        1. Analyzes the user's query
        2. Generates a structured plan with minimal steps
        3. Sets the plan in state for approval
        """
        query = state.get("query", "")
        messages = state.get("messages", [])
        
        # Extract query from messages if not set
        if not query:
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
        
        logger.info(f"XpAgentV2 planner processing query: {query[:100]}...")
        
        # Build planning prompt following XpAgent dev blueprint
        system_prompt = f"""## Role
You are a Strategic AI Planner for an artwork database analysis system.

## Available Tools
{json.dumps(TOOL_CAPABILITIES, indent=2)}

## Database Schema
{DATABASE_SCHEMA}

## Critical Planning Rules

1. **MINIMUM STEPS PRINCIPLE**: Create the SHORTEST possible plan.
   - If only database info is needed → 1 step (database_exploration_agent)
   - If visual analysis is needed → 2 steps (database to get img_path, then image_qna_agent)
   - Add plotting ONLY if user explicitly asks for visualizations

2. **Tool Selection Rules**:
   - database_exploration_agent: Use for ANY database query (counts, lists, filtering, etc.)
   - image_qna_agent: Use ONLY when you need to analyze visual content of images
   - data_plotting_agent: Use ONLY when user explicitly asks for charts/graphs/plots

3. **Image Analysis Protocol**:
   - ALWAYS get img_path from database FIRST
   - NEVER use image_url for visual analysis
   - Pass img_path list to image_qna_agent

4. **Efficiency**:
   - Don't add steps "just in case"
   - Skip plotting unless explicitly requested

5. **CRITICAL - File Path Rules**:
   - For data_plotting_agent: DO NOT specify file_path in tool_args_json
   - The system will AUTOMATICALLY use the CSV file from the previous step
   - Just specify the "task" (what plot to create)

## Your Task
Create a minimal, efficient plan to answer the user's query.
"""

        user_content = f"**Current Query**: {query}\n\nCreate the MINIMUM number of steps needed to answer this query."
        
        # Get structured plan from LLM
        try:
            planner_llm = self.llm.with_structured_output(ExecutionPlan)
            plan_result = planner_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            plan: ExecutionPlan = plan_result  # type: ignore
            
            logger.info(f"XpAgentV2 generated plan: {plan.understanding}")
            logger.info(f"  Steps: {len(plan.steps)}, Approach: {plan.minimal_approach[:50]}...")
            
            # ===== DEV BLUEPRINT: Build plan_steps (List[PlanStep] as dicts) =====
            # This matches the dev blueprint's MainAgentState.plan_steps
            plan_steps = []
            for step in plan.steps:
                plan_steps.append({
                    "step_number": step.step_number,
                    "description": step.description,
                    "tool_name": step.tool_name,
                    "tool_args_json": step.tool_args_json,
                    "depends_on": step.depends_on,
                    "status": step.status,
                    "result_summary": "",
                    "output_file": None
                })
            
            # ===== DISPLAY FORMAT: Build plan_text for frontend PlanMessage =====
            # PlanMessage expects: **Strategy**: ..., **Step N**: ..., Tool Options: (numbered list)
            plan_text = f"**Strategy**: {plan.understanding} {plan.minimal_approach}\n\n"
            
            for step in plan.steps:
                # Step header (PlanMessage parses **Step N**: title)
                plan_text += f"**Step {step.step_number}**: {step.description}\n"
                
                # Tool Options section (PlanMessage parses "Tool Options:" followed by numbered list)
                plan_text += "Tool Options:\n"
                # Parse tool_args_json for description
                try:
                    args = json.loads(step.tool_args_json) if step.tool_args_json != "{}" else {}
                    args_desc = ", ".join(f"{k}={v}" for k, v in args.items()) if args else "default parameters"
                except:
                    args_desc = step.tool_args_json
                plan_text += f"  1. {step.tool_name}: {args_desc}\n"
                
                # Add dependency info as Requires (PlanMessage parses "Requires:")
                if step.depends_on:
                    deps_str = ", ".join(f"Step {d}" for d in step.depends_on)
                    plan_text += f"Requires: {deps_str}\n"
                
                plan_text += "\n"
            
            # ===== RETURN STATE UPDATE (matches dev blueprint + streaming) =====
            return {
                # === Streaming layer fields ===
                "query": query,
                "plan": plan_text.strip(),  # Display format for PlanMessage
                "steps": plan_steps,  # Legacy field - same as plan_steps for compatibility
                "step_counter": 0,
                "status": "user_feedback",  # Triggers routing to human_feedback node
                "agent_type": "xp_agent_v2",
                
                # === Dev blueprint MainAgentState fields ===
                "original_query": query,
                "plan_steps": plan_steps,  # Structured plan steps (dev blueprint)
                "total_steps": len(plan_steps),
                "current_step_index": 0,
                "completed_steps": 0,
                "step_results": [],
                "tool_context": "",
                "feedback": None,
                "pending_interrupt": False,
                "execution_complete": False,
                "final_answer": None,
                "generated_files": []
            }
            
        except Exception as e:
            logger.error(f"XpAgentV2 planning error: {e}")
            # Fallback: create a simple plan with dev blueprint fields
            return {
                # Streaming layer fields
                "query": query,
                "plan": f"**Strategy**: Answer the query directly.\n\n_Planning error occurred: {str(e)}_",
                "steps": [],
                "step_counter": 0,
                "status": "user_feedback",
                "agent_type": "xp_agent_v2",
                # Dev blueprint fields
                "original_query": query,
                "plan_steps": [],
                "total_steps": 0,
                "current_step_index": 0,
                "completed_steps": 0,
                "step_results": [],
                "tool_context": "",
                "feedback": f"Planning failed: {str(e)}",
                "pending_interrupt": True,
                "execution_complete": False,
                "final_answer": None,
                "generated_files": []
            }
    
    def _interrupt_for_approval_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Interrupt node that pauses execution and waits for user approval.
        
        This node:
        1. Displays the plan to the user
        2. Waits for a simple boolean approval (approve/reject)
        3. Updates state based on user decision
        
        Uses langgraph's interrupt() for human-in-the-loop functionality.
        """
        plan = state.get("plan", "No plan available")
        query = state.get("query", "")
        # Use plan_steps (dev blueprint) if available, fallback to steps
        plan_steps = state.get("plan_steps") or state.get("steps", [])
        
        logger.info("XpAgentV2 interrupt_for_approval: Waiting for user approval...")
        
        # Create interrupt data for the frontend - use xp_plan_approval type
        # This matches XpAgent's pattern and is recognized by handle_xp_approval
        interrupt_data = {
            "type": "xp_plan_approval",
            "message": "Plan created - please approve to execute",
            "plan": plan,
            "query": query,
            "steps": plan_steps,  # Send structured plan_steps
            "options": ["approve", "reject"]
        }
        
        # This will pause execution and wait for user input
        # The user's response will be returned when they resume the graph
        user_response = interrupt(interrupt_data)
        
        logger.info(f"XpAgentV2 received approval response: {user_response}")
        
        # Process user response
        # Handle different response formats (string, bool, dict)
        is_approved = False
        
        if isinstance(user_response, bool):
            is_approved = user_response
        elif isinstance(user_response, str):
            is_approved = user_response.lower() in ("approve", "approved", "yes", "true", "ok")
        elif isinstance(user_response, dict):
            action = user_response.get("action", "")
            is_approved = action.lower() in ("approve", "approved", "yes")
        
        if is_approved:
            logger.info("XpAgentV2 plan approved - proceeding to execution")
            return {
                "status": "approved",
                "human_comment": None,
                "pending_interrupt": False,
                "feedback": None
            }
        else:
            logger.info("XpAgentV2 plan rejected - cancelling execution")
            # Provide a rejection message as the response
            rejection_reason = ""
            if isinstance(user_response, dict):
                rejection_reason = user_response.get("reason", user_response.get("comment", ""))
            elif isinstance(user_response, str) and user_response.lower() not in ("reject", "rejected", "no", "false", "cancel"):
                rejection_reason = user_response
            
            return {
                "status": "cancelled",
                "human_comment": rejection_reason if rejection_reason else "Plan was rejected by user.",
                "assistant_response": f"Plan was rejected. {rejection_reason}".strip(),
                "execution_complete": True,
                "final_answer": f"Plan was rejected by user. {rejection_reason}".strip()
            }
    
    def _executor_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Executor node that executes the current step in the plan.
        Follows the dev blueprint pattern.
        
        This node:
        1. Gets the current step from plan_steps
        2. Executes the appropriate tool via factory
        3. Updates state with results
        4. Increments step counter
        """
        current_idx = state.get("current_step_index", 0)
        plan_steps = state.get("plan_steps") or []
        tool_context = state.get("tool_context", "") or ""
        
        if current_idx >= len(plan_steps):
            # No more steps - execution complete
            logger.info("XpAgentV2 executor: No more steps, execution complete")
            return {
                "execution_complete": True
            }
        
        # Get current step (it's a dict, not a PlanStep object)
        current_step = plan_steps[current_idx]
        step_number = current_step.get("step_number", current_idx + 1)
        description = current_step.get("description", "")
        tool_name = current_step.get("tool_name", "")
        tool_args_json = current_step.get("tool_args_json", "{}")
        
        logger.info(f"XpAgentV2 executor: Step {step_number}: {description}")
        logger.info(f"  Tool: {tool_name}")
        
        # Parse tool arguments
        try:
            tool_args = json.loads(tool_args_json) if tool_args_json else {}
        except json.JSONDecodeError:
            tool_args = {}
        
        # For database_exploration_agent, use description as query if no query arg
        if tool_name == "database_exploration_agent" and not tool_args.get("query"):
            tool_args["query"] = description
        
        # Get previous results and generated files for context
        step_results_raw = state.get("step_results") or []
        step_results = [StepResult(**r) if isinstance(r, dict) else r for r in step_results_raw]
        generated_files = state.get("generated_files") or []
        
        # Execute the tool
        step_result, new_context = _execute_tool(
            tool_name=tool_name,
            args=tool_args,
            tool_context=tool_context,
            factory=self.factory,
            generated_files=generated_files,
            step_results=step_results
        )
        step_result.step_number = step_number
        
        # Update step status in plan_steps
        plan_steps[current_idx]["status"] = "completed" if step_result.success else "failed"
        if step_result.success:
            plan_steps[current_idx]["result_summary"] = step_result.result_content[:500]
        else:
            plan_steps[current_idx]["result_summary"] = step_result.error_message
        
        if step_result.output_file:
            plan_steps[current_idx]["output_file"] = step_result.output_file
        
        # Build state updates
        updates: Dict[str, Any] = {
            "current_step_index": current_idx + 1,
            "step_results": [step_result.model_dump()],  # Will be appended via reducer
            "tool_context": tool_context + "\n\n" + new_context if tool_context else new_context,
            "plan_steps": plan_steps,
            "completed_steps": state.get("completed_steps", 0) + (1 if step_result.success else 0)
        }
        
        # Update generated files
        if step_result.output_file:
            current_files = list(generated_files)
            if step_result.output_file not in current_files:
                current_files.append(step_result.output_file)
                updates["generated_files"] = current_files
        
        # Check if we're done
        if current_idx + 1 >= len(plan_steps):
            updates["execution_complete"] = True
            logger.info("XpAgentV2 executor: All steps completed")
        
        # Handle errors
        if not step_result.success:
            updates["feedback"] = f"Step {step_number} failed: {step_result.error_message}"
            updates["pending_interrupt"] = True
            logger.warning(f"XpAgentV2 executor: Step {step_number} failed: {step_result.error_message}")
        
        return updates
    
    def _aggregator_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Aggregator node that synthesizes results from all executed steps.
        Creates the final answer from tool outputs.
        """
        original_query = state.get("original_query") or state.get("query", "")
        step_results = state.get("step_results") or []
        tool_context = state.get("tool_context", "") or ""
        generated_files = state.get("generated_files") or []
        messages = state.get("messages", [])
        
        logger.info("XpAgentV2 aggregator: Synthesizing final answer...")
        
        # Build aggregation prompt
        system_prompt = """You are a helpful assistant that synthesizes information to answer user queries.

Based on the execution results provided, create a clear, comprehensive answer.

Rules:
1. Answer the user's original question directly
2. Include relevant data and findings from the results
3. Mention any generated files or visualizations
4. Be concise but complete
5. If there were errors, acknowledge limitations
6. Format data nicely (use tables, lists, etc. as appropriate)"""

        # Build context for LLM
        user_content = f"**Original Question**: {original_query}\n\n"
        user_content += "**Execution Results**:\n"
        user_content += tool_context if tool_context else "No tool results available."
        
        if generated_files:
            user_content += f"\n\n**Generated Files**: {generated_files}"
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            final_answer = response.content
        except Exception as e:
            logger.error(f"XpAgentV2 aggregator error: {e}")
            final_answer = f"I found some results but had trouble summarizing them. Here's what I know:\n\n{tool_context[:1000]}"
        
        # Build response message
        response_message = AIMessage(content=final_answer)
        new_messages = list(messages) + [response_message]
        
        return {
            "messages": new_messages,
            "assistant_response": final_answer,
            "final_answer": final_answer,
            "execution_complete": True,
            "status": "approved",
            "response_type": "answer"
        }
    
    def _responder_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Simple responder node that processes user query and generates a response.
        
        This is a minimal implementation that will be extended with planning
        and tool execution in future versions.
        """
        query = state.get("query", "")
        messages = state.get("messages", [])
        
        logger.info(f"XpAgentV2 responder processing query: {query[:100]}...")
        
        # Build system prompt
        system_prompt = """You are a helpful AI assistant specialized in data exploration and analysis.

Currently, you have no tools available. You can:
1. Answer questions about data analysis concepts
2. Explain how you would approach a data exploration task
3. Provide guidance on what tools would be needed

When tools become available, you will be able to:
- Query databases
- Analyze images
- Create visualizations

For now, respond helpfully to the user's query and explain what you would do if you had the tools.

Be concise and helpful."""

        # Build conversation for LLM
        llm_messages: list = [SystemMessage(content=system_prompt)]
        
        # Add message history (last 10 messages for context)
        for msg in messages[-10:]:
            if isinstance(msg, HumanMessage):
                llm_messages.append(msg)
            elif isinstance(msg, AIMessage):
                llm_messages.append(msg)
        
        # If query is not in messages, add it
        if query and (not messages or messages[-1].content != query):
            llm_messages.append(HumanMessage(content=query))
        
        # Generate response
        try:
            response = self.llm.invoke(llm_messages)
            response_content = response.content
        except Exception as e:
            logger.error(f"XpAgentV2 LLM error: {e}")
            response_content = f"I encountered an error processing your request: {str(e)}"
        
        # Build response message
        response_message = AIMessage(content=response_content)
        
        # Update state with dev blueprint fields
        new_messages = list(messages) + [response_message]
        
        # Mark all steps as completed (mock execution for now)
        plan_steps = state.get("plan_steps") or []
        for step in plan_steps:
            step["status"] = "completed"
        
        return {
            "messages": new_messages,
            "assistant_response": response_content,
            "status": "approved",
            "agent_type": "xp_agent_v2",
            # Dev blueprint fields
            "plan_steps": plan_steps,
            "completed_steps": len(plan_steps),
            "execution_complete": True,
            "final_answer": response_content
        }
    
    def _finalizer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Finalizer node to complete the response.
        
        For now, this just ensures the response is properly formatted.
        """
        assistant_response = state.get("assistant_response", "")
        final_answer = state.get("final_answer") or assistant_response
        
        logger.info("XpAgentV2 finalizer completing response...")
        
        return {
            "status": "approved",
            "response_type": "answer",
            "execution_complete": True,
            "final_answer": final_answer
        }
    
    # ========================================================================
    # ROUTING FUNCTIONS
    # ========================================================================
    
    def _route_after_executor(self, state: ExplainableAgentState) -> Literal["executor", "aggregator"]:
        """
        Route after executor: continue executing steps or aggregate results.
        
        If execution_complete or all steps done -> go to aggregator
        Otherwise -> loop back to executor for next step
        """
        execution_complete = state.get("execution_complete", False)
        current_idx = state.get("current_step_index", 0)
        plan_steps = state.get("plan_steps") or []
        
        if execution_complete or current_idx >= len(plan_steps):
            logger.info("XpAgentV2 routing: Execution complete, going to aggregator")
            return "aggregator"
        else:
            logger.info(f"XpAgentV2 routing: Step {current_idx + 1}/{len(plan_steps)}, continuing execution")
            return "executor"
    
    # ========================================================================
    # GRAPH CONSTRUCTION
    # ========================================================================
    
    def _create_graph(self):
        """
        Create the XpAgentV2 graph with planning and execution flow.
        
        Flow (v2.2 - with executor):
            START -> planner -> executor -> [loop until complete] -> aggregator -> finalizer -> END
        
        Note: Interrupt is disabled for initial testing of executor flow.
        """
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        graph.add_node("planner", self._planner_node)
        graph.add_node("executor", self._executor_node)
        graph.add_node("aggregator", self._aggregator_node)
        graph.add_node("finalizer", self._finalizer_node)
        
        # Set entry point
        graph.set_entry_point("planner")
        
        # Flow: planner -> executor (skip interrupt for testing)
        graph.add_edge("planner", "executor")
        
        # Conditional edge after executor: loop or proceed to aggregator
        graph.add_conditional_edges(
            "executor",
            self._route_after_executor,
            {
                "executor": "executor",
                "aggregator": "aggregator"
            }
        )
        
        # Flow: aggregator -> finalizer -> END
        graph.add_edge("aggregator", "finalizer")
        graph.add_edge("finalizer", END)
        
        # Compile with checkpointer
        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        else:
            return graph.compile(checkpointer=MemorySaver())
