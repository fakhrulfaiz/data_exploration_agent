# data_plotting_sub.py - Enhanced version with configurable LLM model

"""
Improvements over data_plotting_subagent.py:
1. Configurable LLM model name - pass any supported model via init_chat_model
2. Better testability with separate functions
3. Flexible model initialization throughout the graph

Key Features:
- ReAct-style agent for data visualization
- LLM-based code generation for plots
- Supports bar, line, scatter, pie, histogram
- Configurable LLM backbone
- Proper state management with plot records
"""

import os
import re
import json
import pandas as pd
from typing import List, Literal, Optional, Dict, Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_experimental.tools import PythonAstREPLTool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .state.data_plotting_state import (
    DataPlottingState,
    PlotRecord,
    FileInfo,
    PlottingEvaluatorOutput,
)
from pathlib import Path

# Load environment
load_dotenv()

# Use relative paths that work in both Docker and local environments
_CURRENT_DIR = Path(__file__).resolve().parent  # data_plotting_sub.py location

# Default workspace directory (can be overridden via set_plotting_workspace)
DEFAULT_WORKSPACE_DIR = str(_CURRENT_DIR.parent / "workspace")  # backend/app/agents/dev/workspace
DEFAULT_PLOT_OUTPUT_DIR = os.path.join(DEFAULT_WORKSPACE_DIR, "plot")

print(f"📊 data_plotting_sub.py paths:")
print(f"   _CURRENT_DIR: {_CURRENT_DIR}")
print(f"   DEFAULT_WORKSPACE_DIR: {DEFAULT_WORKSPACE_DIR}")
print(f"   DEFAULT_PLOT_OUTPUT_DIR: {DEFAULT_PLOT_OUTPUT_DIR}")
DEFAULT_PLOT_OUTPUT_DIR = os.path.join(DEFAULT_WORKSPACE_DIR, "plot")

# Runtime workspace paths (set via set_plotting_workspace)
_workspace_dir = DEFAULT_WORKSPACE_DIR
_plot_output_dir = DEFAULT_PLOT_OUTPUT_DIR


def set_plotting_workspace(workspace_dir: str, plot_output_dir: str = None):
    """
    Set the workspace directories for plotting.
    
    Args:
        workspace_dir: Path to the workspace directory
        plot_output_dir: Path to plot output directory (defaults to workspace_dir/plot)
    """
    global _workspace_dir, _plot_output_dir
    _workspace_dir = workspace_dir
    _plot_output_dir = plot_output_dir or os.path.join(workspace_dir, "plot")
    # Ensure directories exist
    os.makedirs(_workspace_dir, exist_ok=True)
    os.makedirs(_plot_output_dir, exist_ok=True)


def get_plotting_workspace() -> tuple[str, str]:
    """Get current workspace and plot output directories."""
    return _workspace_dir, _plot_output_dir


# Ensure default plot directory exists
os.makedirs(DEFAULT_PLOT_OUTPUT_DIR, exist_ok=True)


# ============================================================================
# PYTHON REPL HELPER
# ============================================================================

def _extract_code_from_block(response: str) -> str:
    """Extract code from markdown code blocks."""
    if '```' not in response:
        return response
    if '```python' in response:
        code_regex = r'```python(.+?)```'
    else:
        code_regex = r'```(.+?)```'
    code_matches = re.findall(code_regex, response, re.DOTALL)
    return "\n".join(code_matches) if code_matches else response


class PythonREPL:
    """Python REPL for executing plotting code."""
    
    def __init__(self):
        self.python_tool = PythonAstREPLTool()
    
    def run(self, code: str) -> str:
        """Execute Python code and return result."""
        code = _extract_code_from_block(code)
        try:
            result = self.python_tool.run(code)
            return result if result else "Code executed successfully."
        except Exception as e:
            return f"Error: {repr(e)}"


python_repl = PythonREPL()


# ============================================================================
# LLM-BASED CODE GENERATION
# ============================================================================

class PlotCodeOutput(BaseModel):
    """Structured output from LLM for plot code generation."""
    reasoning: str = Field(
        ...,
        description="Explanation of what plot is being created and why this approach was chosen"
    )
    code: str = Field(
        ...,
        description="Complete Python code to generate the plot. Must use matplotlib with Agg backend, read CSV, create plot, and save to specified output path."
    )


def create_plot_code_generator(llm):
    """Create an LLM chain for generating plot code."""
    
    code_gen_prompt = """You are a Python data visualization expert. Generate matplotlib code to create a plot.

## Instructions
- Use `matplotlib.use('Agg')` BEFORE importing pyplot (required for non-GUI)
- Read the CSV file using pandas
- Create the appropriate plot based on the task
- Save the plot to the specified output path
- Use `plt.tight_layout()` and `plt.close()` after saving
- Print a success message with the output path

## CSV File Information
{csv_info}

## Plot Task
{task}

## Output Path
Save to: {output_path}

## Code Requirements
1. Start with: `import matplotlib; matplotlib.use('Agg')`
2. Import pyplot and pandas
3. Read CSV from the exact path provided
4. Create a clear, readable visualization
5. Add appropriate title, labels, and formatting
6. Save with dpi=150 and bbox_inches='tight'
7. Close the figure after saving

Generate the complete Python code:"""
    
    return llm.with_structured_output(PlotCodeOutput), code_gen_prompt


def parse_and_format_code(code_output: PlotCodeOutput) -> str:
    """
    Extract and format Python code from LLM output.
    
    Args:
        code_output: Structured output containing code and reasoning
    
    Returns:
        Clean Python code ready for execution
    """
    code = code_output.code
    
    # Extract from markdown code blocks if present
    code = _extract_code_from_block(code)
    
    # Clean up common issues
    lines = code.strip().split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip empty lines at start
        if not cleaned_lines and not line.strip():
            continue
        cleaned_lines.append(line)
    
    # Remove trailing empty lines
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
    
    return '\n'.join(cleaned_lines)


def generate_plot_with_llm(
    llm,
    csv_path: str,
    csv_info: str,
    task: str,
    output_path: str
) -> tuple[bool, str, str]:
    """
    Generate and execute plot code using LLM.
    
    Args:
        llm: Language model instance
        csv_path: Full path to CSV file
        csv_info: Preview/info about the CSV content
        task: What plot to create
        output_path: Where to save the plot
    
    Returns:
        Tuple of (success: bool, result_message: str, reasoning: str)
    """
    code_generator, prompt_template = create_plot_code_generator(llm)
    
    try:
        # Generate code using LLM
        prompt = prompt_template.format(
            csv_info=csv_info,
            task=task,
            output_path=output_path
        )
        
        code_output: PlotCodeOutput = code_generator.invoke([
            SystemMessage(content="You are a Python data visualization expert."),
            HumanMessage(content=prompt)
        ])
        
        # Parse and clean the code
        clean_code = parse_and_format_code(code_output)
        
        # Execute the code
        result = python_repl.run(clean_code)
        
        # Check for errors
        if "Error" in result or "error" in result.lower():
            return False, f"Code execution failed: {result}", code_output.reasoning
        
        # Check if file was created
        if os.path.exists(output_path):
            return True, f"✅ Plot saved to: {output_path}", code_output.reasoning
        else:
            return False, f"Code executed but file not created at {output_path}. Output: {result}", code_output.reasoning
            
    except Exception as e:
        return False, f"Plot generation failed: {str(e)}", ""


# ============================================================================
# TOOLS - WITH CONFIGURABLE LLM
# ============================================================================

# Store LLM reference for tool use (set during agent creation)
_plotting_llm = None

def set_plotting_llm(llm):
    """Set the LLM to use for plot code generation."""
    global _plotting_llm
    _plotting_llm = llm


def get_plotting_llm():
    """Get the current plotting LLM."""
    return _plotting_llm


@tool("read_csv_file")
def read_csv_file(file_path: str) -> str:
    """
    Read a CSV file and return its content preview with column info.
    
    Args:
        file_path: Path to the CSV file (relative to workspace/data or absolute)
    
    Returns:
        String with file info: columns, row count, and first few rows
    """
    workspace_dir, _ = get_plotting_workspace()
    
    # Handle relative paths
    if not os.path.isabs(file_path):
        # Try workspace/data first
        full_path = os.path.join(workspace_dir, "data", file_path)
        if not os.path.exists(full_path):
            # Try workspace directly
            full_path = os.path.join(workspace_dir, file_path)
        if not os.path.exists(full_path):
            # Try workspace/outputs
            full_path = os.path.join(workspace_dir, "outputs", file_path)
        if not os.path.exists(full_path):
            # Use as-is
            full_path = file_path
    else:
        full_path = file_path
    
    if not os.path.exists(full_path):
        return f"Error: File not found at {full_path}"
    
    try:
        df = pd.read_csv(full_path)
        info = f"## File: {os.path.basename(full_path)}\n\n"
        info += f"**Full Path**: {full_path}\n"
        info += f"**Columns**: {list(df.columns)}\n"
        info += f"**Row Count**: {len(df)}\n"
        info += f"**Data Types**:\n{df.dtypes.to_string()}\n\n"
        info += f"**First 5 Rows**:\n```\n{df.head().to_string()}\n```\n"
        
        # Basic statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            info += f"\n**Numeric Summary**:\n```\n{df[numeric_cols].describe().to_string()}\n```"
        
        return info
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool("generate_plot")
def generate_plot(
    file_path: str,
    plot_instruction: str,
    output_filename: str = ""
) -> str:
    """
    Generate a plot from CSV data using LLM-based code generation.
    
    Args:
        file_path: Path to the CSV file
        plot_instruction: Specific instruction for what plot to create 
                         (e.g., "bar chart of genre vs count", "line plot showing trend over time")
        output_filename: Filename for saving the plot (optional, will be auto-generated)
    
    Returns:
        Success/error message with output path and reasoning
    """
    global _plotting_llm
    
    if _plotting_llm is None:
        return "Error: LLM not initialized. Call set_plotting_llm() first."
    
    workspace_dir, plot_output_dir = get_plotting_workspace()
    
    # Resolve file path
    if not os.path.isabs(file_path):
        full_path = os.path.join(workspace_dir, "data", file_path)
        if not os.path.exists(full_path):
            full_path = os.path.join(workspace_dir, file_path)
        if not os.path.exists(full_path):
            full_path = os.path.join(workspace_dir, "outputs", file_path)
        if not os.path.exists(full_path):
            full_path = file_path
    else:
        full_path = file_path
    
    if not os.path.exists(full_path):
        return f"Error: File not found at {full_path}"
    
    # Read CSV info for context
    try:
        df = pd.read_csv(full_path)
        csv_info = f"**File**: {full_path}\n"
        csv_info += f"**Columns**: {list(df.columns)}\n"
        csv_info += f"**Row Count**: {len(df)}\n"
        csv_info += f"**Data Types**:\n{df.dtypes.to_string()}\n\n"
        csv_info += f"**Sample Data (first 5 rows)**:\n{df.head().to_string()}\n"
        
        # Add numeric summary if applicable
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            csv_info += f"\n**Numeric Summary**:\n{df[numeric_cols].describe().to_string()}"
    except Exception as e:
        return f"Error reading CSV: {str(e)}"
    
    # Generate output filename if not provided
    if not output_filename:
        base_name = os.path.splitext(os.path.basename(full_path))[0]
        # Create descriptive filename from instruction
        safe_instruction = re.sub(r'[^\w\s]', '', plot_instruction.lower())[:30]
        safe_instruction = safe_instruction.replace(' ', '_')
        output_filename = f"{base_name}_{safe_instruction}.png"
    
    if not output_filename.endswith('.png'):
        output_filename += '.png'
    
    output_path = os.path.join(plot_output_dir, output_filename)
    
    # Generate and execute plot code using LLM
    success, result_message, reasoning = generate_plot_with_llm(
        llm=_plotting_llm,
        csv_path=full_path,
        csv_info=csv_info,
        task=plot_instruction,
        output_path=output_path
    )
    
    # Format response
    response = result_message
    if reasoning:
        response += f"\n\n**Reasoning**: {reasoning}"
    
    return response


# Tool list - focused on basic plotting
plotting_tools = [read_csv_file, generate_plot]


# ============================================================================
# NODE: AGENT (ReAct reasoning)
# ============================================================================

def create_agent_node(llm):
    """Create the main agent node with ReAct reasoning."""
    
    # Set the LLM for the generate_plot tool to use
    set_plotting_llm(llm)
    
    def agent_node(state: DataPlottingState):
        """Agent reasons about what plots to create and takes actions."""
        
        # Build context
        original_task = state.get("original_task", "")
        file_info = state.get("file_info")
        plot_records = state.get("plot_records", [])
        plots_generated = state.get("plots_generated", [])
        
        # Format plot history
        plot_history = ""
        if plot_records:
            for record in plot_records:
                status = "✅" if record.success else "❌"
                plot_history += f"- {status} {record.plot_type}: {record.description}"
                if record.output_path:
                    plot_history += f" -> {record.output_path}"
                if record.error_message:
                    plot_history += f" (Error: {record.error_message})"
                plot_history += "\n"
        
        # File info
        file_context = ""
        if file_info:
            file_context = f"""
## Source File
- Path: {file_info.file_path}
- Columns: {file_info.columns}
- Row Count: {file_info.row_count}
- Preview: {file_info.file_content_preview[:500]}...
"""
        
        system_prompt = f"""You are a data visualization assistant. Create plots that satisfy the user's request.

## Original Task
{original_task}

{file_context}

## Plot History
{plot_history if plot_history else "No plots generated yet."}

## Generated Plots
{json.dumps(plots_generated) if plots_generated else "None yet"}

## Your Tools
1. **read_csv_file(file_path)**: Read and preview CSV file contents to understand the data
2. **generate_plot(file_path, plot_instruction, output_filename)**: Create a plot using LLM-generated code
   - file_path: Path to the CSV file
   - plot_instruction: Describe what plot you want (e.g., "bar chart showing genre distribution", "line plot of count over time")
   - output_filename: (optional) Name for the output file

## Instructions
1. FIRST: Use read_csv_file to understand the data structure and available columns
2. THEN: Use generate_plot with a clear plot_instruction describing what visualization you need
3. Be specific in your plot_instruction - mention column names, chart type, and what you want to show

## Example plot_instruction values:
- "Create a bar chart with genre on x-axis and count on y-axis"
- "Make a pie chart showing the distribution of categories"
- "Plot a line graph showing the trend of values over time"
- "Create a scatter plot of price vs quantity to show correlation"
- "Generate a histogram of the age distribution"
"""
        
        messages = [SystemMessage(content=system_prompt)] + list(state.get("messages", []))
        
        # Bind tools and invoke
        response = llm.bind_tools(plotting_tools).invoke(messages)
        
        return {"messages": [response]}
    
    return agent_node


# ============================================================================
# NODE: PROCESS TOOL RESULTS
# ============================================================================

def process_results_node(state: DataPlottingState):
    """Process tool results and update state with plot records."""
    
    messages = state.get("messages", [])
    if not messages:
        return {}
    
    updates = {}
    new_records = []
    new_plots = []
    file_info = state.get("file_info")
    
    # Find the last AI message with tool calls and corresponding tool messages
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            content = msg.content
            
            # Check if this is a file read result
            if "## File:" in content and "Columns" in content:
                # Parse file info
                try:
                    # Extract columns
                    col_match = re.search(r'\*\*Columns\*\*: \[(.*?)\]', content)
                    columns = []
                    if col_match:
                        columns = [c.strip().strip("'\"") for c in col_match.group(1).split(",")]
                    
                    # Extract row count
                    row_match = re.search(r'\*\*Row Count\*\*: (\d+)', content)
                    row_count = int(row_match.group(1)) if row_match else 0
                    
                    # Extract path
                    path_match = re.search(r'\*\*Full Path\*\*: (.+)', content)
                    file_path = path_match.group(1).strip() if path_match else ""
                    
                    file_info = FileInfo(
                        file_path=file_path,
                        file_content_preview=content[:1000],
                        columns=columns,
                        row_count=row_count
                    )
                    updates["file_info"] = file_info
                except:
                    pass
            
            # Check if this is a successful plot result
            elif "✅" in content and "saved to:" in content.lower():
                # Extract output path
                path_match = re.search(r'saved to[:\s]+([^\s\n]+)', content, re.IGNORECASE)
                output_path = path_match.group(1) if path_match else ""
                
                # Determine plot type from content
                plot_type = "unknown"
                for pt in ["bar", "line", "scatter", "pie", "histogram"]:
                    if pt in content.lower():
                        plot_type = pt
                        break
                
                record = PlotRecord(
                    plot_type=plot_type,
                    file_path=file_info.file_path if file_info else "",
                    output_path=output_path,
                    description=f"Generated {plot_type} plot",
                    success=True
                )
                new_records.append(record)
                if output_path:
                    new_plots.append(output_path)
            
            # Check for errors
            elif "Error" in content or "failed" in content.lower():
                record = PlotRecord(
                    plot_type="unknown",
                    file_path=file_info.file_path if file_info else "",
                    success=False,
                    error_message=content[:200]
                )
                new_records.append(record)
    
    if new_records:
        updates["plot_records"] = new_records
    if new_plots:
        updates["plots_generated"] = new_plots
    
    return updates


# ============================================================================
# NODE: EVALUATOR
# ============================================================================

def create_evaluator_node(llm):
    """Create evaluator node that assesses task completion."""
    
    def evaluator_node(state: DataPlottingState):
        """Evaluate if all required plots have been generated."""
        
        original_task = state.get("original_task", "")
        plot_records = state.get("plot_records", [])
        plots_generated = state.get("plots_generated", [])
        file_info = state.get("file_info")
        messages = state.get("messages", [])
        
        # Build evaluation context
        successful_plots = [r for r in plot_records if r.success]
        failed_plots = [r for r in plot_records if not r.success]
        
        eval_context = {
            "original_task": original_task,
            "file_analyzed": file_info.file_path if file_info else "None",
            "columns_available": file_info.columns if file_info else [],
            "total_plot_attempts": len(plot_records),
            "successful_plots": len(successful_plots),
            "failed_plots": len(failed_plots),
            "generated_files": plots_generated,
            "plot_summaries": [
                {"type": r.plot_type, "description": r.description, "output": r.output_path}
                for r in successful_plots
            ]
        }
        
        # Get last message for context
        last_message_content = ""
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                last_message_content = str(last_msg.content)[:500]
        
        eval_prompt = f"""Evaluate if the plotting task is complete.

## Original Task
{original_task}

## Evaluation Context
{json.dumps(eval_context, indent=2)}

## Last Agent Response
{last_message_content}

## Your Assessment
1. Does the generated plot(s) satisfy the original task?
2. Are there any missing visualizations?
3. What is the quality of the work?

Provide your assessment as structured output.
"""
        
        evaluator = llm.with_structured_output(PlottingEvaluatorOutput)
        
        try:
            evaluation: PlottingEvaluatorOutput = evaluator.invoke([
                SystemMessage(content="You are evaluating if a plotting task is complete."),
                HumanMessage(content=eval_prompt)
            ])
            
            # Build result summary for main agent
            result_summary = f"## Plotting Results\n\n"
            result_summary += f"**Task**: {original_task}\n\n"
            
            if successful_plots:
                result_summary += "**Generated Plots**:\n"
                for plot in successful_plots:
                    result_summary += f"- {plot.plot_type}: {plot.description} -> `{plot.output_path}`\n"
            
            if plots_generated:
                result_summary += f"\n**Output Files**: {json.dumps(plots_generated)}\n"
            
            result_summary += f"\n**Quality Score**: {evaluation.quality_score}/5\n"
            result_summary += f"**Summary**: {evaluation.plots_summary}\n"
            
            return {
                "tools_complete": evaluation.task_complete,
                "error_occurred": evaluation.error,
                "error_message": evaluation.error_message,
                "result_summary": result_summary
            }
            
        except Exception as e:
            return {
                "error_occurred": True,
                "error_message": f"Evaluation failed: {str(e)}"
            }
    
    return evaluator_node


# ============================================================================
# NODE: UPDATE WORKSPACE
# ============================================================================

def update_workspace_node(state: DataPlottingState):
    """Finalize and prepare results for return to main agent."""
    
    plots_generated = state.get("plots_generated", [])
    result_summary = state.get("result_summary", "")
    original_task = state.get("original_task", "")
    
    # Build final output message
    if plots_generated:
        output_content = f"✅ Plotting complete!\n\n"
        output_content += f"**Task**: {original_task}\n\n"
        output_content += "**Generated Plots**:\n"
        for plot_path in plots_generated:
            output_content += f"- {plot_path}\n"
    else:
        output_content = "⚠️ No plots were generated."
    
    output_message = AIMessage(content=output_content)
    
    return Command(
        goto=END,
        update={
            "messages": [output_message],
            "result_summary": result_summary
        }
    )


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================

def route_after_agent(state: DataPlottingState) -> str:
    """Route based on whether agent made tool calls."""
    messages = state.get("messages", [])
    if not messages:
        return "evaluator"
    
    last_message = messages[-1]
    
    # Check if it's an AI message with tool calls
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    
    return "evaluator"


def route_after_evaluator(state: DataPlottingState) -> str:
    """Route based on evaluation results."""
    
    tools_complete = state.get("tools_complete", False)
    error_occurred = state.get("error_occurred", False)
    plot_records = state.get("plot_records", [])
    
    # If error or complete, go to workspace update
    if error_occurred or tools_complete:
        return "update_workspace"
    
    # If we have some plots but not complete, let agent continue
    # Limit iterations to prevent infinite loops
    if len(plot_records) >= 10:
        return "update_workspace"
    
    return "agent"


# ============================================================================
# NODE: INITIALIZE FILE INFO
# ============================================================================

def initialize_file_info_node(state: DataPlottingState):
    """Pre-load file information at the start to give agent context."""
    
    files_to_plot = state.get("files_to_plot", [])
    
    if not files_to_plot:
        return {}
    
    # Get the first file to plot
    file_path = files_to_plot[0]
    
    workspace_dir, _ = get_plotting_workspace()
    
    # Resolve file path
    if not os.path.isabs(file_path):
        full_path = os.path.join(workspace_dir, "data", file_path)
        if not os.path.exists(full_path):
            full_path = os.path.join(workspace_dir, file_path)
        if not os.path.exists(full_path):
            full_path = os.path.join(workspace_dir, "outputs", file_path)
        if not os.path.exists(full_path):
            full_path = file_path
    else:
        full_path = file_path
    
    if not os.path.exists(full_path):
        return {
            "error_occurred": True,
            "error_message": f"File not found: {file_path} (tried: {full_path})"
        }
    
    try:
        df = pd.read_csv(full_path)
        file_info = FileInfo(
            file_path=full_path,
            file_content_preview=df.head(10).to_string(),
            columns=list(df.columns),
            row_count=len(df)
        )
        return {"file_info": file_info}
    except Exception as e:
        return {
            "error_occurred": True,
            "error_message": f"Error reading file: {str(e)}"
        }


# ============================================================================
# BUILD GRAPH - WITH CONFIGURABLE LLM
# ============================================================================

def build_plotting_agent(
    model_name: str = "gpt-4o",
    workspace_dir: str = None,
    plot_output_dir: str = None
):
    """
    Build the plotting subagent graph with configurable LLM and workspace.
    
    Args:
        model_name: LLM model to use with init_chat_model. Examples: "gpt-4o", "claude-3-5-sonnet",
                   "gemini-2.0-flash", etc. Defaults to "gpt-4o".
        workspace_dir: Path to workspace directory (defaults to DEFAULT_WORKSPACE_DIR)
        plot_output_dir: Path to plot output directory (defaults to workspace_dir/plot)
    
    Returns:
        Compiled LangGraph StateGraph for the plotting agent.
    """
    # Set workspace paths if provided
    if workspace_dir:
        set_plotting_workspace(workspace_dir, plot_output_dir)
    
    print(f"🤖 Initializing LLM: {model_name}")
    llm = init_chat_model(model_name)
    
    print(f"📊 Building plotting agent...")
    
    # Create nodes
    agent_node = create_agent_node(llm)
    evaluator_node = create_evaluator_node(llm)
    
    # Build graph
    builder = StateGraph(DataPlottingState)
    
    # Add nodes
    builder.add_node("initialize", initialize_file_info_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(plotting_tools))
    builder.add_node("process_results", process_results_node)
    builder.add_node("evaluator", evaluator_node)
    builder.add_node("update_workspace", update_workspace_node)
    
    # Add edges - start with initialization
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tools": "tools",
            "evaluator": "evaluator"
        }
    )
    builder.add_edge("tools", "process_results")
    builder.add_edge("process_results", "agent")
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "agent": "agent",
            "update_workspace": "update_workspace"
        }
    )
    builder.add_edge("update_workspace", END)
    
    return builder.compile()


# ============================================================================
# HELPER FUNCTIONS FOR INTEGRATION
# ============================================================================

def get_plotting_agent(
    model_name: str = "gpt-4o",
    workspace_dir: str = None,
    plot_output_dir: str = None
):
    """Get or create the plotting agent with specified model and workspace."""
    return build_plotting_agent(
        model_name=model_name,
        workspace_dir=workspace_dir,
        plot_output_dir=plot_output_dir
    )


def execute_plotting_task(task: str, file_path: str, model_name: str = "gpt-4o") -> tuple[dict, str]:
    """
    Execute a plotting task and return results.
    
    Args:
        task: The plotting task description
        file_path: Path to the CSV file to plot
        model_name: LLM model to use
    
    Returns:
        Tuple of (result dict, result_summary string)
    """
    agent = get_plotting_agent(model_name=model_name)
    
    result = agent.invoke({
        "messages": [HumanMessage(content=f"Create plots for: {task}\nData file: {file_path}")],
        "original_task": task,
        "files_to_plot": [file_path],
        "plot_records": [],
        "plots_generated": [],
        "tools_complete": False,
        "result_summary": ""
    })
    
    return result, result.get("result_summary", "")


def create_plotting_tool_for_supervisor(model_name: str = "gpt-4o"):
    """
    Wrap the plotting agent as a tool that can be called by a supervisor.
    
    Args:
        model_name: LLM model to use. Examples: "gpt-4o", "claude-3-5-sonnet", etc.
    
    Returns:
        A tool function that can be used by supervisor agents.
    """
    graph = build_plotting_agent(model_name=model_name)
    
    @tool("plotting_tool")
    def plotting_tool(task: str, file_path: str) -> str:
        """
        Create plots from CSV data based on the task.
        
        Args:
            task: Description of what plot to create (e.g., "bar chart of genre distribution")
            file_path: Path to the CSV file to visualize
            
        Returns:
            Paths to generated plot files, or error message.
        """
        # Initialize state with task context
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
        
        # Extract final message
        if result.get("messages"):
            last_msg = result["messages"][-1]
            return last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        return "Plotting completed but no output message generated."
    
    return plotting_tool


# ============================================================================
# MAIN - Testing
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("Data Plotting Subagent Test (GPT-4o)")
    print("=" * 80)
    
    # Test with a sample task
    task = "Create a bar chart showing the distribution of painting genres"
    file_path = "painting_analysis.csv"
    
    print(f"Task: {task}")
    print(f"File: {file_path}")
    print("-" * 50)
    
    agent = build_plotting_agent()
    
    initial_state = {
        "messages": [HumanMessage(content=f"Create plots for: {task}\nData file: {file_path}")],
        "original_task": task,
        "files_to_plot": [file_path],
        "plot_records": [],
        "plots_generated": [],
        "tools_complete": False,
        "result_summary": ""
    }
    
    print("\n🚀 Starting plotting agent test...")
    # Uncomment to run:
    # for step in agent.stream(initial_state, stream_mode="values"):
    #     if "messages" in step and step["messages"]:
    #         last_msg = step["messages"][-1]
    #         print(f"[{type(last_msg).__name__}]")
    #         if hasattr(last_msg, 'content') and last_msg.content:
    #             print(last_msg.content[:500])
    #         print("-" * 30)
    # 
    # print("\n=== Final Result Summary ===")
    # print(step.get("result_summary", "No summary"))
