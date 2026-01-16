# XpAgent.py - Main supervisor agent with configurable LLM model

"""
Main Agent / Supervisor implementation that orchestrates:
1. data_exploration_sub.py - Database queries and exploration
2. image_qna_sub.py - GPU-accelerated image analysis
3. data_plotting_sub.py - Data visualization

Key Features:
- Configurable LLM model for both main agent and subagents
- Structured planning with validation
- Step-by-step execution with context accumulation
- Final answer aggregation
- Testable and composable design

Usage:
    from agent.XpAgent import build_xp_agent, run_task
    
    # Build with default model (gpt-4o-mini)
    agent = build_xp_agent()
    
    # Build with specific model
    agent = build_xp_agent(model_name="gpt-4o")
    
    # Quick task execution
    result = run_task("Find the oldest painting in the database", model_name="gpt-4o-mini")
"""

import os
import re
import json
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import MemorySaver

# Load environment variables
load_dotenv()

# Import enhanced state
from .state.main_agent_state_v2 import (
    MainAgentState,
    PlanStep,
    StepResult,
    ExecutionPlan,
    StepExecutionDecision,
    FinalAnswer,
    TOOL_CAPABILITIES
)


# ============================================================================
# SUBAGENT IMPORTS - NEW CONFIGURABLE VERSIONS
# ============================================================================

# Import the enhanced subagents
from .data_exploration_sub import build_data_exploration_agent
from .image_qna_sub import build_image_qna_agent
from .data_plotting_sub import build_plotting_agent


# ============================================================================
# CONFIGURATION
# ============================================================================

# Default model for all agents
DEFAULT_MODEL = "gpt-4o-mini"

# Default database path
DEFAULT_DB_PATH = "/home/afiq/fyp/fafa-repo/backend/app/resource/art.db"

# Workspace directories
WORKSPACE_PATH = Path("/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace")
OUTPUT_PATH = WORKSPACE_PATH / "outputs"
PLOT_PATH = WORKSPACE_PATH / "plot"


# ============================================================================
# DATABASE SCHEMA CONTEXT
# ============================================================================

DATABASE_SCHEMA = """
## Table: paintings

### Columns
| Column Name | Data Type | Description |
|------------|-----------|-------------|
| title | TEXT | Name of the painting |
| inception | INTEGER | Year the painting was created (e.g., 1503, 1642) |
| movement | TEXT | Art movement (e.g., Renaissance, Baroque) |
| genre | TEXT | Artistic genre (e.g., portrait, landscape) |
| image_url | TEXT | Public URL to the painting image (DO NOT USE for image analysis) |
| img_path | TEXT | Local file path to the image (e.g., 'images/img_0.jpg') - USE THIS for image_qna_agent |

### CRITICAL: Image Analysis Workflow
1. ALWAYS use `img_path` column (NOT image_url) when you need visual analysis
2. First query the database to get img_path values
3. Then pass those img_path values to image_qna_agent
4. img_path format is like: 'images/img_0.jpg', 'images/img_1.jpg', etc.

### Query Tips
- The database CANNOT tell you about visual content (colors, subjects, people, etc.)
- Always include img_path in SELECT when visual analysis will follow
- For date filtering: use inception column (it's a year integer, e.g., WHERE inception BETWEEN 1600 AND 1700)
- Always specify row limits (e.g., LIMIT 10) to avoid overwhelming the system
"""


# ============================================================================
# SUBAGENT FACTORY - CREATES CONFIGURED SUBAGENTS
# ============================================================================

class SubagentFactory:
    """
    Factory for creating and caching subagents with consistent configuration.
    Allows for lazy initialization and configuration reuse.
    """
    
    def __init__(self, model_name: str = DEFAULT_MODEL, db_path: str = None, use_gpu: Optional[bool] = None):
        """
        Initialize the factory with configuration.
        
        Args:
            model_name: LLM model to use for all subagents
            db_path: Path to the database for data exploration
            use_gpu: GPU configuration for image analysis (None=auto, True=require, False=force CPU)
        """
        self.model_name = model_name
        self.db_path = db_path or DEFAULT_DB_PATH
        self.use_gpu = use_gpu
        
        # Cached agents
        self._data_exploration_agent = None
        self._image_qna_agent = None
        self._plotting_agent = None
    
    def get_data_exploration_agent(self):
        """Get or create the data exploration agent."""
        if self._data_exploration_agent is None:
            print(f"📊 Creating data exploration agent with model: {self.model_name}")
            self._data_exploration_agent = build_data_exploration_agent(
                model_name=self.model_name,
                db_path=self.db_path
            )
        return self._data_exploration_agent
    
    def get_image_qna_agent(self):
        """Get or create the image QnA agent."""
        if self._image_qna_agent is None:
            print(f"🖼️  Creating image QnA agent with model: {self.model_name}")
            self._image_qna_agent = build_image_qna_agent(
                model_name=self.model_name,
                use_gpu=self.use_gpu
            )
        return self._image_qna_agent
    
    def get_plotting_agent(self):
        """Get or create the plotting agent."""
        if self._plotting_agent is None:
            print(f"📈 Creating plotting agent with model: {self.model_name}")
            self._plotting_agent = build_plotting_agent(
                model_name=self.model_name
            )
        return self._plotting_agent
    
    def reset(self):
        """Reset all cached agents (useful for testing)."""
        self._data_exploration_agent = None
        self._image_qna_agent = None
        self._plotting_agent = None


# Global factory instance (can be replaced for testing)
_factory: Optional[SubagentFactory] = None


def get_factory() -> SubagentFactory:
    """Get the global factory instance."""
    global _factory
    if _factory is None:
        _factory = SubagentFactory()
    return _factory


def set_factory(factory: SubagentFactory):
    """Set the global factory instance."""
    global _factory
    _factory = factory


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _extract_img_paths_from_content(content: str) -> List[str]:
    """Extract image paths from result content."""
    img_paths = []
    # Match patterns like images/img_0.jpg, images/img_123.jpg
    matches = re.findall(r'images/img_\d+\.jpg', content)
    img_paths.extend(matches)
    # Also try to match from JSON arrays in content
    try:
        json_matches = re.findall(r'\[[\s\S]*?"images/img_\d+\.jpg"[\s\S]*?\]', content)
        for match in json_matches:
            parsed = json.loads(match)
            img_paths.extend([p for p in parsed if isinstance(p, str) and 'images/img_' in p])
    except:
        pass
    return list(set(img_paths))


def _extract_csv_paths_from_content(content: str) -> List[str]:
    """Extract CSV file paths from result content."""
    csv_paths = []
    
    # Match various patterns for CSV paths
    # Pattern 1: "saved to: /path/to/file.csv" or "saved to: file.csv"
    saved_matches = re.findall(r'saved to:?\s*([\S]+\.csv)', content, re.IGNORECASE)
    csv_paths.extend(saved_matches)
    
    # Pattern 2: Full absolute paths
    abs_matches = re.findall(r'(/[\w/.-]+\.csv)', content)
    csv_paths.extend(abs_matches)
    
    # Pattern 3: workspace/outputs paths
    workspace_matches = re.findall(r'(workspace/outputs/[\w.-]+\.csv)', content)
    csv_paths.extend(workspace_matches)
    
    # Pattern 4: Just filename.csv in Output File context
    output_file_matches = re.findall(r'\*\*Output File\*\*:?\s*([\S]+\.csv)', content)
    csv_paths.extend(output_file_matches)
    
    # Deduplicate and return
    return list(set(csv_paths))


# ============================================================================
# TOOL EXECUTION FUNCTIONS
# ============================================================================

def execute_data_exploration(query: str, factory: SubagentFactory) -> tuple[StepResult, str]:
    """Execute data exploration agent and return result with context summary."""
    try:
        agent = factory.get_data_exploration_agent()
        result = agent.invoke({
            "messages": [HumanMessage(content=query)],
            "original_task": query,
            "query_history": [],
            "tables_queried": [],
            "exploration_complete": False,
            "ready_for_export": False,
            "result_summary": ""
        })
        
        # Extract result
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        content = last_message.content if last_message and hasattr(last_message, 'content') else str(result)
        
        # Get the result_summary from subagent state
        result_summary = result.get("result_summary", "")
        
        # Check for output file - search in content and result_summary
        output_file = None
        search_content = f"{content}\n{result_summary}"
        csv_paths = _extract_csv_paths_from_content(search_content)
        
        if csv_paths:
            # Prefer absolute paths, then the first found
            for path in csv_paths:
                if os.path.isabs(path):
                    output_file = path
                    break
            if not output_file:
                # Try to resolve to absolute path
                for path in csv_paths:
                    if os.path.exists(path):
                        output_file = os.path.abspath(path)
                        break
                    # Check in outputs directory
                    full_path = OUTPUT_PATH / os.path.basename(path)
                    if full_path.exists():
                        output_file = str(full_path)
                        break
            if not output_file:
                output_file = csv_paths[0]
        
        # Build context string with explicit CSV file info for downstream agents
        context = f"## Database Query Result\n\n"
        context += f"**Query**: {query}\n\n"
        
        if result_summary:
            context += f"**Summary**:\n{result_summary}\n\n"
        
        context += f"**Full Response**:\n{content}\n"
        
        # Add explicit CSV file information for plotting agent
        if output_file:
            context += f"\n**Output CSV File**: {output_file}\n"
            context += f"\n### CSV File Available for Plotting\n"
            context += f"- **File Path**: `{output_file}`\n"
            # Try to get CSV preview
            try:
                if os.path.exists(output_file):
                    import pandas as pd
                    df = pd.read_csv(output_file)
                    context += f"- **Columns**: {list(df.columns)}\n"
                    context += f"- **Row Count**: {len(df)}\n"
                    context += f"- **Preview**:\n```\n{df.head().to_string()}\n```\n"
            except Exception as preview_err:
                context += f"- (Could not load preview: {preview_err})\n"
        
        step_result = StepResult(
            step_number=0,
            success=True,
            result_content=content,
            output_file=output_file
        )
        
        return step_result, context
        
    except Exception as e:
        step_result = StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        )
        return step_result, f"Error in data exploration: {str(e)}"


def execute_image_qna(query: str, img_paths: List[str], tool_context: str, factory: SubagentFactory) -> tuple[StepResult, str]:
    """Execute image QnA agent and return result with context summary."""
    try:
        agent = factory.get_image_qna_agent()
        
        # Format the query with image paths and context
        full_query = f"{query}\n\nImages to analyze: {json.dumps(img_paths)}"
        if tool_context:
            full_query += f"\n\nContext from previous tools:\n{tool_context}"
        
        result = agent.invoke({
            "messages": [HumanMessage(content=full_query)],
            "original_task": query,
            "images_to_process": img_paths,
            "images_processed": [],
            "analysis_records": [],
            "tools_complete": False
        })
        
        # Extract result
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        content = last_message.content if last_message and hasattr(last_message, 'content') else str(result)
        
        # Get analysis records
        analysis_records = result.get("analysis_records", [])
        
        # Check for output file - search in content
        output_file = None
        csv_paths = _extract_csv_paths_from_content(content)
        
        if csv_paths:
            # Prefer absolute paths
            for path in csv_paths:
                if os.path.isabs(path) and os.path.exists(path):
                    output_file = path
                    break
            if not output_file:
                for path in csv_paths:
                    full_path = OUTPUT_PATH / os.path.basename(path)
                    if full_path.exists():
                        output_file = str(full_path)
                        break
            if not output_file:
                output_file = csv_paths[0]
        
        # Build context string
        context = f"## Image Analysis Result\n\n"
        context += f"**Query**: {query}\n"
        context += f"**Images Analyzed**: {len(img_paths)}\n\n"
        
        if analysis_records:
            context += "**Analysis Results**:\n"
            for record in analysis_records:
                if hasattr(record, 'to_string'):
                    context += f"- {record.to_string()}\n"
                else:
                    context += f"- {str(record)}\n"
            context += "\n"
        
        context += f"**Full Response**:\n{content}\n"
        
        # Add explicit CSV file information for plotting agent
        if output_file:
            context += f"\n**Output CSV File**: {output_file}\n"
            context += f"\n### CSV File Available for Plotting\n"
            context += f"- **File Path**: `{output_file}`\n"
            # Try to get CSV preview
            try:
                if os.path.exists(output_file):
                    import pandas as pd
                    df = pd.read_csv(output_file)
                    context += f"- **Columns**: {list(df.columns)}\n"
                    context += f"- **Row Count**: {len(df)}\n"
                    context += f"- **Preview**:\n```\n{df.head().to_string()}\n```\n"
            except Exception as preview_err:
                context += f"- (Could not load preview: {preview_err})\n"
        
        step_result = StepResult(
            step_number=0,
            success=True,
            result_content=content,
            output_file=output_file
        )
        
        return step_result, context
        
    except Exception as e:
        step_result = StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        )
        return step_result, f"Error in image analysis: {str(e)}"


def execute_plotting(task: str, file_path: str, factory: SubagentFactory) -> tuple[StepResult, str]:
    """Execute plotting agent and return result with context summary."""
    try:
        agent = factory.get_plotting_agent()
        
        # Resolve file path to absolute path
        resolved_file_path = None
        
        if os.path.isabs(file_path) and os.path.exists(file_path):
            resolved_file_path = file_path
        else:
            # Try multiple locations
            search_paths = [
                Path(file_path),  # As-is
                OUTPUT_PATH / file_path,  # In outputs
                OUTPUT_PATH / os.path.basename(file_path),  # Basename in outputs
                WORKSPACE_PATH / file_path,  # In workspace
                WORKSPACE_PATH / "data" / file_path,  # In data
            ]
            
            for potential in search_paths:
                if potential.exists():
                    resolved_file_path = str(potential.absolute())
                    break
        
        if not resolved_file_path or not os.path.exists(resolved_file_path):
            return StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message=f"CSV file not found: {file_path}. Searched in: {OUTPUT_PATH}, {WORKSPACE_PATH}"
            ), f"Error: CSV file not found: {file_path}"
        
        # Read file info to provide to agent
        file_info = ""
        try:
            import pandas as pd
            df = pd.read_csv(resolved_file_path)
            file_info = f"\n\nFile Info:\n- Path: {resolved_file_path}\n- Columns: {list(df.columns)}\n- Rows: {len(df)}\n- Preview:\n{df.head().to_string()}\n"
        except Exception as e:
            file_info = f"\n(Could not read file preview: {e})"
        
        # Build comprehensive message for plotting agent
        agent_message = f"""Create plots for: {task}

Data file: {resolved_file_path}
{file_info}

IMPORTANT: Use the exact file path above when calling the generate_plot tool."""
        
        result = agent.invoke({
            "messages": [HumanMessage(content=agent_message)],
            "original_task": task,
            "files_to_plot": [resolved_file_path],
            "plot_records": [],
            "plots_generated": [],
            "tools_complete": False,
            "result_summary": ""
        })
        
        # Extract result
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        content = last_message.content if last_message and hasattr(last_message, 'content') else str(result)
        
        # Get result summary
        result_summary = result.get("result_summary", "")
        plots_generated = result.get("plots_generated", [])
        
        # Build context string
        context = f"## Plotting Result\n\n"
        context += f"**Task**: {task}\n"
        context += f"**Input File**: {file_path}\n\n"
        
        if plots_generated:
            context += f"**Plots Generated**: {len(plots_generated)}\n"
            for plot in plots_generated:
                context += f"- {plot}\n"
            context += "\n"
        
        if result_summary:
            context += f"**Summary**:\n{result_summary}\n\n"
        
        context += f"**Full Response**:\n{content}\n"
        
        step_result = StepResult(
            step_number=0,
            success=True,
            result_content=content,
            output_file=plots_generated[0] if plots_generated else None
        )
        
        return step_result, context
        
    except Exception as e:
        step_result = StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        )
        return step_result, f"Error in plotting: {str(e)}"


def _execute_tool(
    tool_name: str, 
    args: Dict[str, Any], 
    tool_context: str, 
    factory: SubagentFactory,
    generated_files: List[str] = None,
    step_results: List[StepResult] = None
) -> tuple[StepResult, str]:
    """Execute a tool and return the result with context string.
    
    Args:
        tool_name: Name of the tool to execute
        args: Arguments from the plan (may contain hallucinated file paths)
        tool_context: Accumulated context from previous steps
        factory: SubagentFactory for creating agents
        generated_files: List of actual files generated by previous steps
        step_results: Results from previous steps (contains actual output_file paths)
    """
    generated_files = generated_files or []
    step_results = step_results or []
    
    if tool_name == "database_exploration_agent":
        query = args.get("query", "")
        return execute_data_exploration(query, factory)
    
    elif tool_name == "image_qna_agent":
        query = args.get("query", "")
        img_paths = args.get("img_path", args.get("img_paths", []))
        if isinstance(img_paths, str):
            img_paths = [img_paths]
        return execute_image_qna(query, img_paths, tool_context, factory)
    
    elif tool_name == "data_plotting_agent":
        task = args.get("task", "")
        
        # IMPORTANT: Don't trust file_path from args - it's often hallucinated by the planner
        # Instead, find the actual CSV file from previous step outputs
        file_path = None
        
        # Strategy 1: Get from previous step results (most reliable)
        for result in reversed(step_results):
            if result.success and result.output_file:
                if result.output_file.endswith('.csv') and os.path.exists(result.output_file):
                    file_path = result.output_file
                    print(f"   📄 Using CSV from step {result.step_number}: {file_path}")
                    break
        
        # Strategy 2: Check generated_files list
        if not file_path:
            for f in reversed(generated_files):
                if f.endswith('.csv') and os.path.exists(f):
                    file_path = f
                    print(f"   📄 Using generated file: {file_path}")
                    break
        
        # Strategy 3: Extract from tool_context as last resort
        if not file_path and tool_context:
            csv_paths = _extract_csv_paths_from_content(tool_context)
            for path in reversed(csv_paths):
                if os.path.isabs(path) and os.path.exists(path):
                    file_path = path
                    print(f"   📄 Found CSV in context: {file_path}")
                    break
                # Try outputs directory
                full_path = OUTPUT_PATH / os.path.basename(path)
                if full_path.exists():
                    file_path = str(full_path)
                    print(f"   📄 Found CSV in outputs: {file_path}")
                    break
        
        if not file_path:
            return StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message="No CSV file found from previous steps. Data exploration must run first to generate a CSV."
            ), "Error: No CSV file available for plotting"
        
        return execute_plotting(task, file_path, factory)
    
    else:
        return StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=f"Unknown tool: {tool_name}"
        ), f"Error: Unknown tool {tool_name}"


# ============================================================================
# NODE: CONTEXT BUILDER - Handles multi-turn memory
# ============================================================================

def create_context_builder_node():
    """Create the context builder node that accumulates conversation history."""
    
    def context_builder_node(state: MainAgentState):
        """
        Build conversation context from previous turns.
        This node runs at the start of each new query to accumulate context.
        """
        # Get previous conversation context
        previous_context = state.get("conversation_context", "")
        previous_final_answer = state.get("final_answer", "")
        previous_query = state.get("original_query", "")
        
        # Get the new query from the latest message
        new_query = ""
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                new_query = msg.content
                break
            elif isinstance(msg, dict) and msg.get("role") == "user":
                new_query = msg.get("content", "")
                break
        
        if not new_query:
            return {}  # No new query, nothing to do
        
        # Check if this is a continuation (previous answer exists)
        if previous_final_answer and previous_query:
            # Extract a one-line summary from the final answer
            summary_line = ""
            answer_lines = [l.strip() for l in previous_final_answer.split('\n') 
                          if l.strip() and not l.strip().startswith("#")]
            if answer_lines:
                summary_line = answer_lines[0]
                if len(summary_line) > 200:
                    summary_line = summary_line[:200] + "..."
            
            # Build accumulated context
            if previous_context:
                # Append to existing context
                new_context = f"{previous_context}\n→ Answer: {summary_line}\n\nFollow-up: {new_query}"
            else:
                # First follow-up after initial query
                new_context = f"Query: {previous_query}\n→ Answer: {summary_line}\n\nFollow-up: {new_query}"
            
            print(f"📚 Built conversation context ({len(new_context)} chars)")
            print(f"   Previous query: {previous_query[:50]}...")
            print(f"   Answer summary: {summary_line[:50]}...")
            print(f"   New query: {new_query[:50]}...")
            
            return {
                "conversation_context": new_context,
                "original_query": new_query,  # Set current query
                # Reset execution state for new query
                "plan_steps": [],
                "step_results": [],
                "tool_context": "",
                "current_step_index": 0,
                "total_steps": 0,
                "completed_steps": 0,
                "execution_complete": False,
                "final_answer": None,
                "feedback": None,
                "pending_interrupt": False,
                "generated_files": []
            }
        else:
            # First query in conversation - no context to build
            print(f"📝 New conversation started: {new_query[:50]}...")
            return {
                "conversation_context": "",
                "original_query": new_query,
                # Reset execution state
                "plan_steps": [],
                "step_results": [],
                "tool_context": "",
                "current_step_index": 0,
                "total_steps": 0,
                "completed_steps": 0,
                "execution_complete": False,
                "final_answer": None,
                "feedback": None,
                "pending_interrupt": False,
                "generated_files": []
            }
    
    return context_builder_node


# ============================================================================
# NODE: PLANNER
# ============================================================================

def create_planner_node(llm):
    """Create the planning node with structured output."""
    
    def planner_node(state: MainAgentState):
        """Plan how to accomplish the user's task."""
        
        query = state.get("original_query", "")
        conversation_context = state.get("conversation_context", "")
        
        if not query:
            # Extract from messages if not set
            for msg in state.get("messages", []):
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
        
        # Check for feedback from previous attempts
        feedback = state.get("feedback")
        previous_results = state.get("step_results", [])
        
        # Build the planning prompt with conversation context
        context_section = ""
        if conversation_context:
            context_section = f"""
## Conversation History (IMPORTANT - Use this context!)
The user is continuing a conversation. Here's what happened before:

{conversation_context}

**IMPORTANT**: The current query may reference previous results. Use the context above to understand references like "it", "that", "the painting", etc.
"""
        
        system_prompt = f"""## Role
You are a Strategic AI Planner for an artwork database analysis system.
{context_section}
## Available Tools
{json.dumps({k: v.model_dump() for k, v in TOOL_CAPABILITIES.items()}, indent=2)}

## Database Schema
{DATABASE_SCHEMA}

## Critical Planning Rules

1. **MINIMUM STEPS PRINCIPLE**: Create the SHORTEST possible plan.
   - If only database info is needed → 1 step (database_exploration_agent)
   - If visual analysis is needed → 2 steps (database to get img_path, then image_qna_agent)
   - Add plotting ONLY if user explicitly asks for visualizations
   - **If the answer is already in conversation context, you may not need any database query!**

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
   - **Use information from conversation context when available**
   - Don't create data exploration steps if data is already available from previous results
   - Skip plotting unless explicitly requested

5. **CRITICAL - File Path Rules**:
   - For data_plotting_agent: DO NOT specify file_path in tool_args_json
   - The system will AUTOMATICALLY use the CSV file from the previous step
   - Just specify the "task" (what plot to create), leave file_path empty: {{"task": "create bar chart of counts"}}
   - Example: {{"task": "bar chart showing distribution"}} - NO file_path needed!

## Your Task
Create a minimal, efficient plan to answer the user's query. Use conversation context when relevant.
"""

        # Build user message with context
        user_content = f"**Current Query**: {query}\n\n"
        
        if feedback:
            user_content += f"**Previous Attempt Feedback**: {feedback}\n\n"
        
        if previous_results:
            user_content += "**Previous Step Results**:\n"
            for r in previous_results:
                status = "✅" if r.success else "❌"
                user_content += f"- Step {r.step_number}: {status} {r.result_content[:200]}...\n"
            user_content += "\n"
        
        user_content += "Create the MINIMUM number of steps needed to answer this query."
        
        # Get structured plan from LLM
        planner_llm = llm.with_structured_output(ExecutionPlan)
        
        try:
            plan: ExecutionPlan = planner_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            
            # Update state with plan (keep conversation_context intact)
            return {
                "plan_steps": plan.steps,
                "total_steps": len(plan.steps),
                "current_step_index": 0,
                "completed_steps": 0,
                "feedback": None,
                "pending_interrupt": False
            }
            
        except Exception as e:
            print(f"❌ Planning error: {e}")
            return {
                "original_query": query,
                "feedback": f"Planning failed: {str(e)}",
                "pending_interrupt": True
            }
    
    return planner_node


# ============================================================================
# NODE: STEP EXECUTOR
# ============================================================================

def create_executor_node(llm, factory: SubagentFactory):
    """Create the step execution node."""
    
    def executor_node(state: MainAgentState):
        """Execute the current step in the plan."""
        
        current_idx = state.get("current_step_index", 0)
        plan_steps = state.get("plan_steps", [])
        tool_context = state.get("tool_context", "")
        
        if current_idx >= len(plan_steps):
            # No more steps
            return {
                "execution_complete": True
            }
        
        current_step = plan_steps[current_idx]
        print(f"\n🔄 Executing Step {current_step.step_number}: {current_step.description}")
        print(f"   Tool: {current_step.tool_name}")
        
        # Get tool arguments
        tool_args = current_step.get_tool_args()
        
        # Get previous results and generated files for context
        previous_results = state.get("step_results", [])
        generated_files = state.get("generated_files", [])
        
        # Execute the tool with full context
        step_result, new_context = _execute_tool(
            current_step.tool_name,
            tool_args,
            tool_context,
            factory,
            generated_files=generated_files,
            step_results=previous_results
        )
        step_result.step_number = current_step.step_number
        
        # Update step status
        current_step.status = "completed" if step_result.success else "failed"
        current_step.result_summary = step_result.result_content[:500] if step_result.success else step_result.error_message
        current_step.output_file = step_result.output_file
        
        # Extract image paths for potential downstream use
        if step_result.success:
            img_paths = _extract_img_paths_from_content(step_result.result_content)
            if img_paths:
                new_context += f"\n**Extracted Image Paths**: {json.dumps(img_paths)}\n"
        
        # Build updates
        updates = {
            "current_step_index": current_idx + 1,
            "step_results": [step_result],
            "tool_context": new_context,
            "completed_steps": state.get("completed_steps", 0) + (1 if step_result.success else 0)
        }
        
        # Update generated files list
        if step_result.output_file:
            current_files = state.get("generated_files", [])
            if step_result.output_file not in current_files:
                updates["generated_files"] = current_files + [step_result.output_file]
        
        # Check if we're done
        if current_idx + 1 >= len(plan_steps):
            updates["execution_complete"] = True
        
        # Handle errors
        if not step_result.success:
            updates["feedback"] = f"Step {current_step.step_number} failed: {step_result.error_message}"
            updates["pending_interrupt"] = True
        
        return updates
    
    return executor_node


# ============================================================================
# NODE: AGGREGATOR
# ============================================================================

def create_aggregator_node(llm):
    """Create the final answer aggregation node."""
    
    def aggregator_node(state: MainAgentState):
        """Aggregate results and create final answer."""
        
        original_query = state.get("original_query", "")
        step_results = state.get("step_results", [])
        tool_context = state.get("tool_context", "")
        generated_files = state.get("generated_files", [])
        
        # Build aggregation prompt
        system_prompt = """You are a helpful assistant that synthesizes information to answer user queries.

Based on the execution results provided, create a clear, comprehensive answer.

Rules:
1. Answer the user's original question directly
2. Include relevant data and findings from the results
3. Mention any generated files or visualizations
4. Be concise but complete
5. If there were errors, acknowledge limitations
"""
        
        user_content = f"""## Original Query
{original_query}

## Execution Results
{tool_context}

## Generated Files
{json.dumps(generated_files) if generated_files else "None"}

## Successful Steps
{len([r for r in step_results if r.success])} of {len(step_results)}

Please synthesize these results into a clear, helpful answer for the user.
"""
        
        # Get structured answer
        answer_llm = llm.with_structured_output(FinalAnswer)
        
        try:
            answer: FinalAnswer = answer_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            
            # Format final answer
            final_text = f"{answer.summary}\n\n{answer.detailed_answer}"
            
            if generated_files:
                final_text += f"\n\n**Generated Files**: {', '.join(generated_files)}"
            
            if answer.limitations:
                final_text += f"\n\n**Note**: {answer.limitations}"
            
            return {
                "final_answer": final_text,
                "messages": [AIMessage(content=final_text)],
                "generated_files": answer.generated_files or generated_files
            }
            
        except Exception as e:
            # Fallback to simple aggregation
            fallback_answer = f"Results for: {original_query}\n\n"
            for r in step_results:
                if r.success:
                    fallback_answer += f"- {r.result_content[:500]}\n"
            
            return {
                "final_answer": fallback_answer,
                "messages": [AIMessage(content=fallback_answer)],
                "generated_files": generated_files
            }
    
    return aggregator_node


# ============================================================================
# NODE: INTERRUPT HANDLER
# ============================================================================

def interrupt_for_replan_node(state: MainAgentState) -> Command[Literal["planner", "aggregator"]]:
    """Handle interrupts and decide whether to replan."""
    
    # Check replan limit
    if state.get("replan_count", 0) >= state.get("max_replans", 3):
        print("⚠️ Maximum replans reached, showing partial results")
        return Command(
            goto="aggregator",
            update={
                "pending_interrupt": False,
                "execution_complete": True
            }
        )
    
    # Ask user for approval
    is_approved = interrupt({
        "question": f"Plan needs revision. Feedback: {state.get('feedback', 'Unknown issue')}\n\nDo you want to replan?",
        "options": ["Yes, replan", "No, show partial results"]
    })
    
    if is_approved == "Yes, replan" or is_approved is True:
        return Command(
            goto="planner",
            update={
                "replan_count": state.get("replan_count", 0) + 1,
                "pending_interrupt": False,
                "current_step_index": 0,
                "plan_steps": []
            }
        )
    else:
        return Command(
            goto="aggregator",
            update={
                "pending_interrupt": False,
                "execution_complete": True
            }
        )


# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_after_executor(state: MainAgentState) -> Literal["executor", "aggregator", "interrupt_for_replan"]:
    """Route based on executor result."""
    
    if state.get("pending_interrupt"):
        return "interrupt_for_replan"
    
    if state.get("execution_complete"):
        return "aggregator"
    
    current_idx = state.get("current_step_index", 0)
    total_steps = state.get("total_steps", 0)
    
    if current_idx >= total_steps:
        return "aggregator"
    
    return "executor"


def route_after_planner(state: MainAgentState) -> Literal["executor", "interrupt_for_replan"]:
    """Route based on planner result."""
    
    if state.get("pending_interrupt"):
        return "interrupt_for_replan"
    
    if state.get("plan_steps"):
        return "executor"
    
    return "interrupt_for_replan"


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_xp_agent(
    model_name: str = DEFAULT_MODEL,
    db_path: str = None,
    use_gpu: Optional[bool] = None,
    checkpointer=None
):
    """
    Build the main XP agent graph with configurable LLM.
    
    Args:
        model_name: LLM model to use for main agent AND all subagents.
                   Examples: "gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet", "gemini-2.0-flash"
                   Defaults to "gpt-4o-mini".
        db_path: Path to the SQLite database. Uses default if not provided.
        use_gpu: GPU configuration for image analysis.
                - None: Auto-detect and use GPU if available (default)
                - True: Require GPU, fail if unavailable
                - False: Force CPU even if GPU available
        checkpointer: LangGraph checkpointer for conversation persistence.
    
    Returns:
        Compiled LangGraph StateGraph for the main agent.
    """
    print("=" * 80)
    print(f"🚀 Building XP Agent")
    print(f"   Model: {model_name}")
    print(f"   Database: {db_path or DEFAULT_DB_PATH}")
    print(f"   GPU: {'auto-detect' if use_gpu is None else use_gpu}")
    print("=" * 80)
    
    # Initialize the main LLM
    llm = init_chat_model(model_name)
    
    # Create subagent factory with same model
    factory = SubagentFactory(
        model_name=model_name,
        db_path=db_path,
        use_gpu=use_gpu
    )
    
    # Set global factory (for compatibility with existing patterns)
    set_factory(factory)
    
    # Create nodes
    context_builder = create_context_builder_node()
    planner = create_planner_node(llm)
    executor = create_executor_node(llm, factory)
    aggregator = create_aggregator_node(llm)
    
    # Build graph
    builder = StateGraph(MainAgentState)
    
    # Add nodes
    builder.add_node("context_builder", context_builder)  # NEW: Handles multi-turn memory
    builder.add_node("planner", planner)
    builder.add_node("executor", executor)
    builder.add_node("aggregator", aggregator)
    builder.add_node("interrupt_for_replan", interrupt_for_replan_node)
    
    # Add edges
    builder.add_edge(START, "context_builder")  # START -> context_builder
    builder.add_edge("context_builder", "planner")  # context_builder -> planner
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        ["executor", "interrupt_for_replan"]
    )
    builder.add_conditional_edges(
        "executor",
        route_after_executor,
        ["executor", "aggregator", "interrupt_for_replan"]
    )
    builder.add_edge("aggregator", END)
    
    # Compile with checkpointer if provided
    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


# ============================================================================
# HELPER FUNCTIONS FOR EASY USE
# ============================================================================

def get_xp_agent(model_name: str = DEFAULT_MODEL, **kwargs):
    """Get or create an XP agent with specified model."""
    return build_xp_agent(model_name=model_name, **kwargs)


def run_task(
    task: str,
    model_name: str = DEFAULT_MODEL,
    db_path: str = None,
    use_gpu: Optional[bool] = None,
    stream: bool = False,
    config: dict = None
) -> dict:
    """
    Run a task through the XP agent and return results.
    
    Args:
        task: The task/query to execute
        model_name: LLM model to use
        db_path: Database path
        use_gpu: GPU configuration
        stream: If True, return a generator for streaming
        config: Optional config dict with thread_id etc.
    
    Returns:
        Final state dict from the agent
    """
    agent = build_xp_agent(
        model_name=model_name,
        db_path=db_path,
        use_gpu=use_gpu,
        checkpointer=MemorySaver() if config else None
    )
    
    initial_state = {
        "messages": [HumanMessage(content=task)],
        "original_query": task,
        "plan_steps": [],
        "step_results": [],
        "tool_context": "",
        "current_step_index": 0,
        "total_steps": 0,
        "completed_steps": 0,
        "replan_count": 0,
        "max_replans": 3,
        "execution_complete": False,
        "generated_files": []
    }
    
    run_config = config or {"configurable": {"thread_id": "default"}}
    
    if stream:
        return agent.stream(initial_state, run_config, stream_mode="values")
    else:
        return agent.invoke(initial_state, run_config)


def create_xp_tool_for_supervisor(model_name: str = DEFAULT_MODEL, **kwargs):
    """
    Wrap the XP agent as a tool for use by other supervisors.
    
    Args:
        model_name: LLM model to use
        **kwargs: Additional args for build_xp_agent
    
    Returns:
        A tool function that can be used by supervisor agents.
    """
    agent = build_xp_agent(model_name=model_name, **kwargs)
    
    @tool("xp_agent_tool")
    def xp_agent_tool(task: str) -> str:
        """
        Execute a complex multi-step task involving database exploration,
        image analysis, and/or data visualization.
        
        Args:
            task: The task to accomplish. Can involve database queries,
                  image analysis, or creating visualizations.
        
        Returns:
            Result summary with any generated files.
        """
        try:
            result = agent.invoke({
                "messages": [HumanMessage(content=task)],
                "original_query": task,
                "plan_steps": [],
                "step_results": [],
                "tool_context": "",
                "current_step_index": 0,
                "total_steps": 0,
                "execution_complete": False,
                "generated_files": []
            })
            
            final_answer = result.get("final_answer", "")
            generated_files = result.get("generated_files", [])
            
            output = final_answer
            if generated_files:
                output += f"\n\nGenerated files: {', '.join(generated_files)}"
            
            return output
            
        except Exception as e:
            return f"Error executing task: {str(e)}"
    
    return xp_agent_tool


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("XP Agent - Main Supervisor Test")
    print("=" * 80)
    
    # Example 1: Build with default settings
    print("\n📍 Example 1: Build with default settings (gpt-4o-mini)")
    agent = build_xp_agent()
    
    # Example 2: Build with different model
    print("\n📍 Example 2: Build with GPT-4o")
    # agent = build_xp_agent(model_name="gpt-4o")
    
    # Example 3: Quick task execution
    print("\n📍 Example 3: Quick task execution")
    # result = run_task("What is the oldest painting in the database?")
    # print(result.get("final_answer", "No answer"))
    
    # Test task
    test_tasks = [
        "What is the oldest painting in the database?",
        "How many paintings are there in each genre?",
        "Find 3 Renaissance paintings and describe their visual content",
    ]
    
    print("\n📋 Available test tasks:")
    for i, task in enumerate(test_tasks, 1):
        print(f"   {i}. {task}")
    
    print("\n✅ XP Agent ready!")
    print("   Use: result = run_task('your query here')")
