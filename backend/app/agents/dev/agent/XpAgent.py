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
# XP AGENT IDENTITY & CAPABILITIES
# ============================================================================

XP_AGENT_IDENTITY = """
## XP Agent - Intelligent Art Database Analysis Supervisor

### Who I Am
I am XP Agent, a sophisticated multi-agent orchestrator specialized in artwork database analysis.
I coordinate intelligent subagents to accomplish complex research, analysis, and visualization tasks.

### My Core Capabilities
1. **Database Exploration**: Query and analyze artwork metadata (title, date, movement, genre)
2. **Visual Analysis**: Analyze artwork images for colors, subjects, composition, style
3. **Data Visualization**: Create charts and plots from analysis results

### What Makes Me Powerful
- I break down complex requests into logical steps
- I coordinate multiple intelligent subagents that can each handle complex subtasks
- I accumulate context across steps to build comprehensive answers
- I can handle multi-turn conversations with memory

### Task Complexity I Handle
- Simple: "How many paintings are in the database?" (1 step)
- Medium: "Show me Renaissance paintings with people in them" (2-3 steps: query → analyze images)
- Complex: "Compare visual characteristics of Baroque vs Renaissance art and visualize the findings" (5+ steps)
"""

# ============================================================================
# SUBAGENT CAPABILITIES DOCUMENTATION
# ============================================================================

SUBAGENT_CAPABILITIES = """
## My Intelligent Subagents

### 1. Database Exploration Agent (`database_exploration_agent`)
**Type**: Intelligent LLM-powered SQL Agent

**What It Can Do**:
- Understand natural language queries about artwork data
- Execute multiple SQL queries autonomously to fully explore the data
- Handle consecutive tasks in a single invocation

**Query Format for Consecutive Tasks**:
```markdown
Please complete the following tasks:
- Find all paintings from the Renaissance era
- Count how many there are per genre
- Include img_path for any images that need visual analysis
- Export the results to CSV
```

**Query Format for Simple Tasks**:
```markdown
Find the 5 oldest paintings in the database with their title, inception date, and img_path.
```

**Database Schema**:
- Table: `paintings`
- Columns: title (TEXT), inception (DATE), movement (TEXT), genre (TEXT), image_url (TEXT), img_path (TEXT)

**CRITICAL**: Always request `img_path` when downstream visual analysis is needed!

---

### 2. Image QnA Agent (`image_qna_agent`)
**Type**: Intelligent GPU-accelerated Visual Analysis Agent (BLIP VQA)

**What It Can Do**:
- Analyze visual content of artwork images
- Process multiple images in batch
- Answer specific questions about each image
- Handle consecutive analysis tasks

**Query Format for Consecutive Tasks**:
```markdown
For each image, analyze and report:
- The main subjects depicted
- Number of people visible
- Dominant colors
- Overall mood/atmosphere
```

**Query Format for Simple Tasks**:
```markdown
Describe what is depicted in each painting.
```

**REQUIRES**: img_path values from database_exploration_agent (format: 'images/img_N.jpg')

---

### 3. Data Plotting Agent (`data_plotting_agent`)
**Type**: Intelligent Visualization Agent

**What It Can Do**:
- Read and understand CSV data structure
- Generate appropriate visualizations
- Create multiple charts in one invocation

**Query Format for Consecutive Tasks**:
```markdown
Create the following visualizations:
- Bar chart showing distribution by genre
- Pie chart showing movement proportions
- Line chart if temporal data is available
```

**Query Format for Simple Tasks**:
```markdown
Create a bar chart showing the count of paintings per art movement.
```

**IMPORTANT**: CSV file path is automatically resolved from previous steps.
"""

# ============================================================================
# DYNAMIC ARG RESOLVER PROMPT
# ============================================================================

STEP_RESOLVER_PROMPT = """## Role
You are a Step Argument Resolver. Your job is to determine the ACTUAL arguments for a tool call based on accumulated execution context.

## Current Step to Execute
- **Step {step_number}**: {step_description}
- **Tool**: {tool_name}
- **Intent**: {step_intent}
- **Expected Output**: {expected_output}

## Accumulated Context from Previous Steps
{accumulated_context}

## Your Task
Based on the accumulated context above, determine the ACTUAL arguments needed to execute this step.

### CRITICAL: Query Format
The subagents are INTELLIGENT LLM-powered agents. Pass the intent directly as natural language.

**For database_exploration_agent**:
- Pass the intent AS-IS if it's well-formed
- Do NOT convert to SQL - the subagent handles SQL internally
- If intent has markdown list format, preserve it

**For image_qna_agent**:
- Pass the intent describing what to analyze
- Extract img_path values from accumulated context (format: images/img_N.jpg)
- If intent has markdown list format, preserve it

**For data_plotting_agent**:
- Pass the intent describing what charts to create
- Find the CSV file path from accumulated context
- If intent has markdown list format, preserve it

### Rules:
1. **Preserve intent format**: If intent uses markdown lists, keep them in resolved_query
2. **Extract real values from context**: Only use paths that appear in the accumulated context
3. **DO NOT hallucinate paths**: Never make up file paths or image paths
4. **For image_qna_agent**: Extract ALL img_path values mentioned in previous results
5. **For data_plotting_agent**: Find the ACTUAL CSV file path from previous step outputs
6. **If required data is missing**: Set action to "replan" with a clear reason

### Image Path Extraction:
- Look for patterns like: images/img_0.jpg, images/img_123.jpg
- These appear in database query results when img_path column is selected
- Collect ALL relevant image paths, not just a subset

### CSV Path Extraction:
- Look for "Output CSV File:", "saved to:", or file paths ending in .csv
- Use the FULL absolute path when available
- The path is usually in format: /home/.../workspace/outputs/something.csv
"""


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
                "replan_feedback": None,
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
                "replan_feedback": None,
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
        
        # Check for replan feedback (set when user approves replan)
        # This is separate from 'feedback' which triggers interrupts
        replan_feedback = state.get("replan_feedback")
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
        
        system_prompt = f"""## Your Identity
{XP_AGENT_IDENTITY}

{context_section}

## Your Intelligent Subagents
{SUBAGENT_CAPABILITIES}

## Database Schema Reference
{DATABASE_SCHEMA}

---

## CRITICAL: Planning Rules for Executable Plans

### Rule 1: Subagents Are INTELLIGENT Agents
Your subagents are NOT simple functions - they are intelligent LLM-powered agents that can:
- Handle complex, multi-part requests in a SINGLE invocation
- Make their own decisions about how to accomplish tasks
- Execute multiple operations autonomously

**WRONG APPROACH** ❌ (Too many micro-steps):
- Step 1: Query paintings from 1500-1550
- Step 2: Query paintings from 1550-1600
- Step 3: Query paintings from 1600-1650
- Step 4: Combine results

**CORRECT APPROACH** ✅ (Let the subagent handle it):
- Step 1: database_exploration_agent → "Find all paintings from 1500-1650, group by era, and include img_path for visual analysis"

### Rule 2: Use Markdown Lists for Consecutive Tasks
When a subagent needs to perform multiple related operations, use markdown list format:

**For database_exploration_agent**:
```
Please complete the following tasks:
- Query all paintings from the Renaissance movement
- Count how many paintings exist per genre
- Include img_path column for any paintings that need visual analysis
- Order results by inception date
```

**For image_qna_agent**:
```
For each image, analyze and determine:
- Main subjects depicted in the artwork
- Number of people visible (if any)
- Dominant color palette
- Art style characteristics
```

**For data_plotting_agent**:
```
Create the following visualizations from the data:
- Bar chart showing count per genre
- Pie chart showing distribution by movement
```

### Rule 3: Intent Field Format
The `intent` field describes WHAT to accomplish in natural language.
- For simple tasks: Single sentence describing the goal
- For consecutive tasks: Markdown list of sub-tasks

**NEVER include**:
- Specific file paths like "images/img_1.jpg" 
- Hardcoded CSV paths
- SQL syntax (let the subagent handle SQL)

### Rule 4: Dependency Chain
- image_qna_agent ALWAYS requires database_exploration_agent first (to get img_path)
- data_plotting_agent requires data from previous steps (CSV automatically resolved)

### Rule 5: Plan Validation Checklist
Before finalizing your plan, verify:
✅ Each step uses exactly one of: database_exploration_agent, image_qna_agent, data_plotting_agent
✅ Intent describes WHAT to do, not HOW (no file paths, no SQL)
✅ If visual analysis needed: database step comes FIRST with img_path requested
✅ If charts needed: data source step comes BEFORE plotting step
✅ Consecutive tasks in a step use markdown list format

---

## Your Task
Create an EXECUTABLE plan that can be directly run by the subagents.
Address ALL aspects of the user's query with as many steps as genuinely needed.
"""

        # Build user message with context
        user_content = f"**Current Query**: {query}\n\n"
        
        # Include replan feedback if this is a replan attempt
        if replan_feedback:
            user_content += f"**⚠️ Previous Attempt Failed - Reason**: {replan_feedback}\n\n"
            user_content += "Please create a NEW plan that addresses this issue.\n\n"
        
        if previous_results:
            user_content += "**Previous Step Results**:\n"
            for r in previous_results:
                status = "✅" if r.success else "❌"
                user_content += f"- Step {r.step_number}: {status} {r.result_content[:200]}...\n"
            user_content += "\n"
        
        user_content += "Create a complete, executable plan. Remember:\n"
        user_content += "- Subagents are intelligent and can handle complex multi-part requests\n"
        user_content += "- Use markdown list format for consecutive tasks within a step\n"
        user_content += "- Intent should describe WHAT to do, not specific paths or SQL"
        
        # Get structured plan from LLM
        planner_llm = llm.with_structured_output(ExecutionPlan)
        
        try:
            plan: ExecutionPlan = planner_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content)
            ])
            
            # Log the plan
            print(f"\n📋 Plan created with {len(plan.steps)} steps:")
            for step in plan.steps:
                print(f"   Step {step.step_number}: [{step.tool_name}] {step.description}")
                print(f"      Intent: {step.intent[:100]}...")
            
            # Update state with plan - clear replan_feedback after use
            return {
                "plan_steps": plan.steps,
                "total_steps": len(plan.steps),
                "current_step_index": 0,
                "completed_steps": 0,
                "feedback": None,  # Ensure feedback is cleared
                "replan_feedback": None,  # Clear replan_feedback after planner uses it
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
# NODE: STEP RESOLVER - Dynamically resolves tool arguments from context
# ============================================================================

def create_step_resolver_node(llm):
    """Create the step resolver node that determines actual tool arguments at runtime."""
    
    def step_resolver_node(state: MainAgentState):
        """
        Resolve actual tool arguments based on accumulated context.
        This is the KEY to fixing the hallucinated args problem.
        """
        current_idx = state.get("current_step_index", 0)
        plan_steps = state.get("plan_steps", [])
        tool_context = state.get("tool_context", "")
        step_results = state.get("step_results", [])
        generated_files = state.get("generated_files", [])
        
        if current_idx >= len(plan_steps):
            return {"execution_complete": True}
        
        current_step = plan_steps[current_idx]
        
        print(f"\n🔍 Resolving args for Step {current_step.step_number}: {current_step.description}")
        print(f"   Tool: {current_step.tool_name}")
        print(f"   Intent: {current_step.intent}")
        
        # Build context for the resolver
        accumulated_context = f"## Previous Step Results and Files\n\n"
        
        # Add step results with their outputs
        for result in step_results:
            accumulated_context += f"### Step {result.step_number} Result\n"
            accumulated_context += f"- Success: {result.success}\n"
            if result.output_file:
                accumulated_context += f"- Output File: {result.output_file}\n"
            accumulated_context += f"- Content:\n{result.result_content[:2000]}\n\n"
        
        # Add generated files list
        if generated_files:
            accumulated_context += f"### Generated Files\n"
            for f in generated_files:
                accumulated_context += f"- {f}\n"
            accumulated_context += "\n"
        
        # Add tool context (contains detailed results)
        if tool_context:
            accumulated_context += f"### Detailed Tool Context\n{tool_context}\n"
        
        # Create the resolver prompt
        resolver_prompt = STEP_RESOLVER_PROMPT.format(
            step_number=current_step.step_number,
            step_description=current_step.description,
            tool_name=current_step.tool_name,
            step_intent=current_step.intent,
            expected_output=current_step.expected_output,
            accumulated_context=accumulated_context
        )
        
        # Get structured decision from LLM
        resolver_llm = llm.with_structured_output(StepExecutionDecision)
        
        try:
            decision: StepExecutionDecision = resolver_llm.invoke([
                SystemMessage(content=resolver_prompt),
                HumanMessage(content=f"Resolve the actual arguments for tool: {current_step.tool_name}")
            ])
            
            print(f"   📋 Decision: {decision.action}")
            if decision.resolved_query:
                print(f"   Query: {decision.resolved_query[:100]}...")
            if decision.resolved_img_paths:
                print(f"   Images: {len(decision.resolved_img_paths)} paths resolved")
            if decision.resolved_csv_path:
                print(f"   CSV: {decision.resolved_csv_path}")
            
            # Store the decision in state for the executor
            return {
                "current_step_decision": decision
            }
            
        except Exception as e:
            print(f"❌ Resolver error: {e}")
            # Create a fallback decision using heuristics
            fallback_decision = _create_fallback_decision(
                current_step, tool_context, step_results, generated_files
            )
            return {
                "current_step_decision": fallback_decision
            }
    
    return step_resolver_node


def _create_fallback_decision(
    step: PlanStep, 
    tool_context: str, 
    step_results: List[StepResult],
    generated_files: List[str]
) -> StepExecutionDecision:
    """Create a fallback decision using heuristic extraction."""
    
    if step.tool_name == "database_exploration_agent":
        # Use the intent as the query
        return StepExecutionDecision(
            action="execute",
            resolved_query=step.intent or step.description,
            reasoning="Fallback: Using step intent as query"
        )
    
    elif step.tool_name == "image_qna_agent":
        # Extract image paths from context
        img_paths = _extract_img_paths_from_content(tool_context)
        if not img_paths:
            return StepExecutionDecision(
                action="replan",
                replan_reason="No image paths found in previous step results",
                reasoning="Cannot execute image analysis without image paths"
            )
        return StepExecutionDecision(
            action="execute",
            resolved_query=step.intent or step.description,
            resolved_img_paths=img_paths,
            reasoning=f"Fallback: Extracted {len(img_paths)} image paths from context"
        )
    
    elif step.tool_name == "data_plotting_agent":
        # Find CSV file from generated files or step results
        csv_path = None
        for f in reversed(generated_files):
            if f.endswith('.csv') and os.path.exists(f):
                csv_path = f
                break
        if not csv_path:
            for result in reversed(step_results):
                if result.output_file and result.output_file.endswith('.csv'):
                    if os.path.exists(result.output_file):
                        csv_path = result.output_file
                        break
        
        if not csv_path:
            return StepExecutionDecision(
                action="replan",
                replan_reason="No CSV file found from previous steps",
                reasoning="Cannot create plot without data file"
            )
        
        return StepExecutionDecision(
            action="execute",
            resolved_query=step.intent or step.description,
            resolved_csv_path=csv_path,
            reasoning=f"Fallback: Using CSV file {csv_path}"
        )
    
    return StepExecutionDecision(
        action="replan",
        replan_reason=f"Unknown tool: {step.tool_name}",
        reasoning="Cannot handle unknown tool"
    )


# ============================================================================
# NODE: STEP EXECUTOR
# ============================================================================

def create_executor_node(llm, factory: SubagentFactory):
    """Create the step execution node."""
    
    def executor_node(state: MainAgentState):
        """Execute the current step using resolved arguments."""
        
        current_idx = state.get("current_step_index", 0)
        plan_steps = state.get("plan_steps", [])
        tool_context = state.get("tool_context", "")
        decision = state.get("current_step_decision")
        
        if current_idx >= len(plan_steps):
            return {"execution_complete": True}
        
        current_step = plan_steps[current_idx]
        
        # Check if we need to replan based on resolver decision
        if decision and decision.action == "replan":
            print(f"⚠️ Step {current_step.step_number} needs replanning: {decision.replan_reason}")
            return {
                "feedback": decision.replan_reason,
                "pending_interrupt": True
            }
        
        if decision and decision.action == "skip":
            print(f"⏭️ Skipping Step {current_step.step_number}: {decision.skip_reason}")
            current_step.status = "skipped"
            return {
                "current_step_index": current_idx + 1,
                "step_results": [StepResult(
                    step_number=current_step.step_number,
                    success=True,
                    result_content=f"Skipped: {decision.skip_reason}"
                )]
            }
        
        print(f"\n🔄 Executing Step {current_step.step_number}: {current_step.description}")
        print(f"   Tool: {current_step.tool_name}")
        
        # Execute with resolved arguments
        step_result, new_context = _execute_tool_with_decision(
            current_step,
            decision,
            tool_context,
            factory,
            state.get("generated_files", []),
            state.get("step_results", [])
        )
        step_result.step_number = current_step.step_number
        
        # Update step status
        current_step.status = "completed" if step_result.success else "failed"
        current_step.result_summary = step_result.result_content[:500] if step_result.success else step_result.error_message
        current_step.output_file = step_result.output_file
        
        # Build updates
        updates = {
            "current_step_index": current_idx + 1,
            "step_results": [step_result],
            "tool_context": new_context,
            "completed_steps": state.get("completed_steps", 0) + (1 if step_result.success else 0),
            "current_step_decision": None  # Clear the decision
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


def _execute_tool_with_decision(
    step: PlanStep,
    decision: Optional[StepExecutionDecision],
    tool_context: str,
    factory: SubagentFactory,
    generated_files: List[str],
    step_results: List[StepResult]
) -> tuple[StepResult, str]:
    """Execute a tool using the resolved decision."""
    
    tool_name = step.tool_name
    
    if tool_name == "database_exploration_agent":
        query = (decision.resolved_query if decision and decision.resolved_query else None) or step.intent or step.description
        return execute_data_exploration(query, factory)
    
    elif tool_name == "image_qna_agent":
        query = (decision.resolved_query if decision and decision.resolved_query else None) or step.intent or step.description
        img_paths = decision.resolved_img_paths if decision and decision.resolved_img_paths else []
        
        # Fallback: extract from context if decision didn't provide paths
        if not img_paths:
            img_paths = _extract_img_paths_from_content(tool_context)
        
        if not img_paths:
            return StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message="No image paths available for analysis"
            ), "Error: No image paths found"
        
        return execute_image_qna(query, img_paths, tool_context, factory)
    
    elif tool_name == "data_plotting_agent":
        task = (decision.resolved_query if decision and decision.resolved_query else None) or step.intent or step.description
        csv_path = decision.resolved_csv_path if decision else None
        
        # Fallback: find CSV from previous steps
        if not csv_path:
            for result in reversed(step_results):
                if result.success and result.output_file and result.output_file.endswith('.csv'):
                    if os.path.exists(result.output_file):
                        csv_path = result.output_file
                        break
        
        if not csv_path:
            for f in reversed(generated_files):
                if f.endswith('.csv') and os.path.exists(f):
                    csv_path = f
                    break
        
        if not csv_path:
            return StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message="No CSV file found from previous steps"
            ), "Error: No CSV file available for plotting"
        
        return execute_plotting(task, csv_path, factory)
    
    else:
        return StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=f"Unknown tool: {tool_name}"
        ), f"Error: Unknown tool {tool_name}"


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
    
    # Get the feedback that triggered this interrupt
    current_feedback = state.get("feedback", "Unknown issue")
    
    # Check replan limit
    if state.get("replan_count", 0) >= state.get("max_replans", 3):
        print("⚠️ Maximum replans reached, showing partial results")
        return Command(
            goto="aggregator",
            update={
                "pending_interrupt": False,
                "feedback": None,  # Clear feedback
                "replan_feedback": None,
                "execution_complete": True
            }
        )
    
    # Ask user for approval
    is_approved = interrupt({
        "question": f"Plan needs revision. Feedback: {current_feedback}\n\nDo you want to replan?",
        "options": ["Yes, replan", "No, show partial results"]
    })
    
    if is_approved == "Yes, replan" or is_approved is True:
        print(f"✅ User approved replan. Transferring feedback to replan_feedback.")
        return Command(
            goto="planner",
            update={
                "replan_count": state.get("replan_count", 0) + 1,
                "pending_interrupt": False,
                "current_step_index": 0,
                "plan_steps": [],
                # Transfer feedback to replan_feedback for planner to use
                "replan_feedback": current_feedback,
                # Clear feedback to prevent re-triggering interrupt
                "feedback": None
            }
        )
    else:
        print(f"❌ User rejected replan. Going to aggregator.")
        return Command(
            goto="aggregator",
            update={
                "pending_interrupt": False,
                "feedback": None,  # Clear feedback
                "replan_feedback": None,
                "execution_complete": True
            }
        )


# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_after_executor(state: MainAgentState) -> Literal["step_resolver", "aggregator", "interrupt_for_replan"]:
    """Route based on executor result."""
    
    if state.get("pending_interrupt"):
        return "interrupt_for_replan"
    
    if state.get("execution_complete"):
        return "aggregator"
    
    current_idx = state.get("current_step_index", 0)
    total_steps = state.get("total_steps", 0)
    
    if current_idx >= total_steps:
        return "aggregator"
    
    # Go to step resolver for next step
    return "step_resolver"


def route_after_planner(state: MainAgentState) -> Literal["step_resolver", "interrupt_for_replan"]:
    """Route based on planner result."""
    
    if state.get("pending_interrupt"):
        return "interrupt_for_replan"
    
    if state.get("plan_steps"):
        # Go to step resolver first, not directly to executor
        return "step_resolver"
    
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
    step_resolver = create_step_resolver_node(llm)  # NEW: Resolves args dynamically
    executor = create_executor_node(llm, factory)
    aggregator = create_aggregator_node(llm)
    
    # Build graph
    builder = StateGraph(MainAgentState)
    
    # Add nodes
    builder.add_node("context_builder", context_builder)  # Handles multi-turn memory
    builder.add_node("planner", planner)
    builder.add_node("step_resolver", step_resolver)  # NEW: Dynamic arg resolution
    builder.add_node("executor", executor)
    builder.add_node("aggregator", aggregator)
    builder.add_node("interrupt_for_replan", interrupt_for_replan_node)
    
    # Add edges
    builder.add_edge(START, "context_builder")  # START -> context_builder
    builder.add_edge("context_builder", "planner")  # context_builder -> planner
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        ["step_resolver", "interrupt_for_replan"]  # planner -> step_resolver (not executor)
    )
    builder.add_edge("step_resolver", "executor")  # step_resolver -> executor
    builder.add_conditional_edges(
        "executor",
        route_after_executor,
        ["step_resolver", "aggregator", "interrupt_for_replan"]  # executor -> step_resolver for next step
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
