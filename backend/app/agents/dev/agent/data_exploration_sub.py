# data_exploration_sub.py - Enhanced version with configurable LLM model

"""
Improvements over data_exploration_subagent_v2.py:
1. Configurable LLM model name - pass any supported model via init_chat_model
2. Better testability with separate functions
3. Flexible model initialization throughout the graph

Key Features:
- State tracks: original_task, schema_info, query_history (structured)
- Tool properly updates state with structured QueryRecord
- Evaluator has full context of what was queried and results
- Agent can synthesize from accumulated query history
- Proper CSV export implementation
- Configurable LLM backbone
"""

import os
import csv
import ast
import json
from pathlib import Path
from typing import Literal, List, Optional, Any
from datetime import datetime

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

# Load environment variables
load_dotenv()

# Import enhanced state
from .state.data_exploration_state_v2 import (
    DataExplorationState,
    DataExplorationOutput,
    QueryRecord,
    SchemaInfo,
    QueryArgs
)


# ============================================================================
# DATABASE SETUP
# ============================================================================

# Use relative paths that work in both Docker and local environments
_CURRENT_DIR = Path(__file__).resolve().parent  # data_exploration_sub.py location
_BACKEND_ROOT = _CURRENT_DIR.parent.parent.parent.parent  # Go up to backend/

# Default database path - can be overridden
DEFAULT_DB_PATH = str(_BACKEND_ROOT / "app" / "resource" / "art.db")


def setup_database(db_path: str = None):
    """
    Setup database connection.
    
    Args:
        db_path: Path to the SQLite database. Uses default if not provided.
    
    Returns:
        SQLDatabase instance
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    
    sql_url = f"sqlite:///{db_path}"
    db = SQLDatabase.from_uri(sql_url)
    return db


def setup_toolkit(db: SQLDatabase, llm):
    """Setup SQL toolkit with all necessary tools."""
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    return toolkit.get_tools()


def get_database_info(db_path: str = None) -> dict:
    """
    Get basic database information for testing.
    
    Args:
        db_path: Path to the database
    
    Returns:
        Dictionary with database info
    """
    db = setup_database(db_path)
    return {
        "dialect": db.dialect,
        "tables": db.get_usable_table_names(),
        "db_path": db_path or DEFAULT_DB_PATH
    }


# ============================================================================
# WORKSPACE CONFIGURATION
# ============================================================================

# Default workspace paths - can be overridden via build_data_exploration_agent
# Uses relative path from current file location
DEFAULT_WORKSPACE_PATH = _CURRENT_DIR.parent / "workspace"  # backend/app/agents/dev/workspace
DEFAULT_OUTPUT_PATH = DEFAULT_WORKSPACE_PATH / "outputs"

print(f"📁 data_exploration_sub.py paths:")
print(f"   _CURRENT_DIR: {_CURRENT_DIR}")
print(f"   DEFAULT_DB_PATH: {DEFAULT_DB_PATH}")
print(f"   DEFAULT_WORKSPACE_PATH: {DEFAULT_WORKSPACE_PATH}")
print(f"   DEFAULT_OUTPUT_PATH: {DEFAULT_OUTPUT_PATH}")


# ============================================================================
# WRAPPED QUERY TOOL WITH COLUMN TRACKING
# ============================================================================

def create_query_tool(base_tool):
    """Create a wrapped query tool that includes column tracking."""
    
    def run_query_with_columns(query: str, columns: List[str]) -> str:
        """
        Execute a SQL query and return results.
        
        Args:
            query: The SQL query to execute
            columns: Expected column names in the result (for downstream processing)
        
        Returns:
            Query results as string
        """
        return base_tool.invoke({"query": query})
    
    return StructuredTool.from_function(
        name="sql_db_query",
        description="Execute a SQL query against the database. Always specify expected columns for result tracking.",
        func=run_query_with_columns,
        args_schema=QueryArgs,
    )


# ============================================================================
# NODE: LIST TABLES (Workflow Step 1)
# ============================================================================

def list_tables_node(state: DataExplorationState, tools: list):
    """List available tables in the database."""
    list_tables_tool = next(t for t in tools if t.name == "sql_db_list_tables")
    
    # Create tool call
    tool_call = {
        "name": "sql_db_list_tables",
        "args": {},
        "id": "list_tables_001",
        "type": "tool_call",
    }
    tool_call_message = AIMessage(content="", tool_calls=[tool_call])
    
    # Execute tool
    tool_message = list_tables_tool.invoke(tool_call)
    tables = [t.strip() for t in tool_message.content.split(",")]
    
    # Create response
    response = AIMessage(content=f"Available tables in database: {', '.join(tables)}")
    
    # Initialize schema info
    schema_info = SchemaInfo(tables=tables)
    
    return {
        "messages": [tool_call_message, tool_message, response],
        "schema_info": schema_info
    }


# ============================================================================
# NODE: GET SCHEMA (Workflow Step 2)
# ============================================================================

def call_get_schema_node(state: DataExplorationState, llm, get_schema_tool):
    """Request schema for relevant tables."""
    llm_with_tools = llm.bind_tools([get_schema_tool], tool_choice="any")
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def process_schema_node(state: DataExplorationState):
    """Process schema response and update state."""
    # Find the last tool message with schema info
    schema_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            schema_text = msg.content
            break
    
    # Update schema info
    current_schema = state.get("schema_info") or SchemaInfo()
    updated_schema = SchemaInfo(
        tables=current_schema.tables,
        schema_text=schema_text
    )
    
    return {"schema_info": updated_schema}


# ============================================================================
# NODE: GENERATE QUERY (ReAct Agent Core)
# ============================================================================

def create_generate_query_node(llm, query_tool, db):
    """Create the query generation node with context awareness."""
    
    def generate_query(state: DataExplorationState):
        """Generate SQL queries based on task and accumulated context."""
        
        # Build context-aware system prompt
        system_prompt = f"""## Role
You are a Lead Data Analyst working with a {db.dialect} database.

## Your Task
{state.get('original_task', 'Analyze the database and extract relevant data.')}

## Database Schema
{state.get('schema_info', SchemaInfo()).schema_text if state.get('schema_info') else 'Schema not yet loaded.'}

## Strict Rules
1. **Literal Matches Only**: Use ONLY table/column names exactly as shown in schema
2. **No Guessing**: If a column doesn't exist, report it - don't invent alternatives
3. **Case Sensitivity**: Match identifiers exactly as provided
4. **No DML**: Never use INSERT, UPDATE, DELETE, DROP

## SQLite Date/Time Handling (CRITICAL)
- SQLite stores dates as TEXT (e.g., "1650-01-15" or "+1650-01-15T00:00:00Z")
- **NEVER** compare date columns directly with integers like `WHERE inception BETWEEN 1600 AND 1700`
- **ALWAYS** use `strftime()` to extract date components:
  - Extract year: `CAST(strftime('%Y', inception) AS INTEGER)` 
  - Extract month: `strftime('%m', inception)`
  - Extract day: `strftime('%d', inception)`
- Example for year filtering: `WHERE CAST(strftime('%Y', inception) AS INTEGER) BETWEEN 1600 AND 1700`
- **Check the schema** to understand column types before writing date comparisons

## Tool Usage
Use `sql_db_query` tool with:
- `query`: Your SQL query
- `columns`: List of column names your query will return (REQUIRED for tracking)

## Query History Context
"""
        
        # Add query history for context
        query_history = state.get("query_history", [])
        if query_history:
            system_prompt += f"\n**Previous Queries ({len(query_history)})**:\n"
            for i, record in enumerate(query_history[-5:], 1):  # Last 5 queries
                if isinstance(record, QueryRecord):
                    system_prompt += f"  {i}. {record.to_summary()}\n"
                elif isinstance(record, dict):
                    system_prompt += f"  {i}. Query: {record.get('query', 'N/A')[:80]}...\n"
        
        system_prompt += """

## Output Behavior
- If you need more data: Call the sql_db_query tool
- If you have enough data to answer: Provide a final response with:
  1. **Summary**: Which tables/columns were used
  2. **Result Table**: Data in Markdown table format
  3. **CSV Data**: Raw data in a code block marked `### FINAL_CSV_DATA ###`

## Important
When you're done exploring and have the final answer, DO NOT make another tool call.
Instead, provide your final synthesized response."""

        messages_for_llm = [SystemMessage(content=system_prompt)] + state["messages"]
        
        llm_with_tools = llm.bind_tools([query_tool])
        response = llm_with_tools.invoke(messages_for_llm)
        
        # If response has no tool calls, it's a final answer - append to result_summary
        update = {"messages": [response]}
        if isinstance(response, AIMessage) and not response.tool_calls:
            # This is a final answer, append to result_summary
            current_summary = state.get("result_summary", "")
            new_summary = response.content
            if current_summary:
                update["result_summary"] = f"{current_summary}\n\n---\n\n{new_summary}"
            else:
                update["result_summary"] = new_summary
        
        return update
    
    return generate_query


# ============================================================================
# NODE: PROCESS QUERY RESULTS
# ============================================================================

def create_process_results_node():
    """Create node to process tool results and update state."""
    
    def process_results(state: DataExplorationState):
        """Process tool messages and update query history."""
        last_message = state["messages"][-1]
        
        if not isinstance(last_message, ToolMessage):
            return {}
        
        # Find the corresponding tool call
        tool_call_id = last_message.tool_call_id
        tool_call = None
        
        for msg in reversed(state["messages"][:-1]):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for call in msg.tool_calls:
                    if call["id"] == tool_call_id:
                        tool_call = call
                        break
                if tool_call:
                    break
        
        if tool_call is None:
            return {}
        
        # Parse result
        result_content = last_message.content
        is_error = "Error" in result_content or "error" in result_content.lower()
        
        # Try to count rows
        row_count = 0
        try:
            parsed = ast.literal_eval(result_content)
            if isinstance(parsed, list):
                row_count = len(parsed)
        except:
            pass
        
        # Create QueryRecord
        record = QueryRecord(
            tool_call_id=tool_call_id,
            query=tool_call["args"].get("query", ""),
            columns=tool_call["args"].get("columns", []),
            result=result_content,
            row_count=row_count,
            success=not is_error,
            error_message=result_content if is_error else ""
        )
        
        # Extract tables queried (simple heuristic)
        tables_in_query = []
        schema_info = state.get("schema_info")
        if schema_info and schema_info.tables:
            query_upper = record.query.upper()
            for table in schema_info.tables:
                if table.upper() in query_upper:
                    tables_in_query.append(table)
        
        return {
            "query_history": [record],
            "tables_queried": tables_in_query
        }
    
    return process_results


# ============================================================================
# NODE: EVALUATOR WITH FULL CONTEXT
# ============================================================================

def create_evaluator_node(llm):
    """Create evaluator with full context awareness."""
    
    def evaluator_node(state: DataExplorationState):
        """Evaluate if the task is complete and data is ready for export."""
        last_message = state["messages"][-1]
        
        # Skip if last message is a tool message (agent hasn't processed it yet)
        if isinstance(last_message, ToolMessage):
            return {}
        
        # Build comprehensive context for evaluator
        eval_context = {
            "original_task": state.get("original_task", "Unknown"),
            "total_queries": len(state.get("query_history", [])),
            "tables_available": state.get("schema_info", SchemaInfo()).tables if state.get("schema_info") else [],
            "tables_queried": state.get("tables_queried", []),
            "query_summaries": []
        }
        
        for record in state.get("query_history", []):
            if isinstance(record, QueryRecord):
                eval_context["query_summaries"].append({
                    "query": record.query,
                    "columns": record.columns,
                    "row_count": record.row_count,
                    "success": record.success
                })
            elif isinstance(record, dict):
                eval_context["query_summaries"].append(record)
        
        system_message = SystemMessage(content=f"""You are a Task Completion Evaluator for a data exploration agent.

## Context
{json.dumps(eval_context, indent=2)}

## Last Agent Response
{last_message.content if hasattr(last_message, 'content') else str(last_message)}

## Your Job
1. Assess if the ORIGINAL TASK has been fully accomplished
2. Check if the agent has extracted the necessary data
3. Evaluate data quality and completeness
4. Provide CSV export instructions if task is complete

## Evaluation Criteria
- task_complete=True ONLY if:
  - The agent has provided a final response (not just made queries)
  - The response contains actual data that answers the original task
  - The data is in a format suitable for CSV export
  
- Look for indicators like:
  - Markdown tables with data
  - `### FINAL_CSV_DATA ###` blocks
  - Summary statements indicating completion

## CSV Preparation
If task_complete=True, provide:
- csv_columns: List of column headers
- csv_filename: Descriptive filename (e.g., "genre_painting_counts.csv")
- storing_instruction: How to parse and store the data

## Be Strict
If the agent is still asking questions or making queries without a final answer, mark task_complete=False.""")
        
        evaluator = llm.with_structured_output(DataExplorationOutput)
        evaluation: DataExplorationOutput = evaluator.invoke([system_message] + state["messages"])
        
        # Handle errors - return to parent for replan
        if evaluation.error:
            return Command(
                goto=END,
                graph=Command.PARENT,
                update={
                    "feedback": f"Data exploration failed: {evaluation.error_message}",
                    "error_occurred": True,
                    "error_message": evaluation.error_message
                }
            )
        
        # Handle incomplete task - agent needs to do more
        if not evaluation.task_complete:
            if evaluation.missing_data:
                feedback_msg = AIMessage(content=f"""Task incomplete.

**Missing Data**: {evaluation.missing_data}
**Evaluator Notes**: {evaluation.reasoning}

Please continue exploring to gather the required data.""")
            else:
                feedback_msg = AIMessage(content=f"""Task incomplete.

**Evaluator Notes**: {evaluation.reasoning}

Please provide a final synthesized response with the data in tabular format.""")
            
            # Command to the parent graph
            return Command(
                goto="interrupt_for_replan",
                graph=Command.PARENT,
                update={
                    "feedback": evaluation.reasoning
                }
            )
        
        # Task complete - prepare for CSV export
        return Command(
            goto="update_workspace",
            update={
                "exploration_complete": True,
                "ready_for_export": True,
                "final_columns": evaluation.csv_columns,
                "messages": [AIMessage(content=json.dumps({
                    "status": "ready_for_export",
                    "filename": evaluation.csv_filename,
                    "columns": evaluation.csv_columns,
                    "instruction": evaluation.storing_instruction,
                    "reasoning": evaluation.reasoning
                }))]
            }
        )
    
    return evaluator_node


# ============================================================================
# NODE: UPDATE WORKSPACE (CSV Export)
# ============================================================================

def create_update_workspace_node(llm, output_path: Path = None):
    """Create workspace update node for CSV saving.
    
    Args:
        llm: Language model for processing
        output_path: Path to save CSV outputs. Uses DEFAULT_OUTPUT_PATH if not provided.
    """
    # Use provided output_path or fall back to default
    csv_output_path = output_path or DEFAULT_OUTPUT_PATH
    print(f"📁 CSV output path configured: {csv_output_path}")
    
    def update_workspace(state: DataExplorationState):
        """Extract data from agent response and save to CSV."""
        import pandas as pd
        import io
        
        print(f"📝 update_workspace node called")
        print(f"   Output path: {csv_output_path}")
        
        # Get columns from evaluator output
        final_columns = state.get("final_columns", [])
        csv_filename = "query_result.csv"
        print(f"   Final columns from evaluator: {final_columns}")
        
        # Look for export instructions in messages
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage):
                content = msg.content
                try:
                    export_info = json.loads(content)
                    if export_info.get("status") == "ready_for_export":
                        csv_filename = export_info.get("filename", csv_filename)
                        if export_info.get("columns"):
                            final_columns = export_info.get("columns")
                        break
                except (json.JSONDecodeError, TypeError):
                    print(f"   ⚠️ Failed to parse export info: {content}")
                    pass
        
        # Primary approach: Get data from query_history (most reliable)
        df = None
        query_history = state.get("query_history", [])
        print(f"   Query history entries: {len(query_history)}")
        
        if query_history:
            # Find the last successful query with data
            for query_record in reversed(query_history):
                if isinstance(query_record, QueryRecord) and query_record.success:
                    print(f"   Found successful query: {query_record.query[:80]}...")
                    print(f"   Query result (first 200 chars): {str(query_record.result)[:200]}")
                    print(f"   Query columns: {query_record.columns}")
                    try:
                        # Parse the result (it's a string representation of list of tuples)
                        parsed = ast.literal_eval(query_record.result)
                        print(f"   Parsed {len(parsed)} rows from result")
                        if isinstance(parsed, list) and parsed:
                            first_row = parsed[0] if parsed else []
                            num_cols = len(first_row) if isinstance(first_row, (list, tuple)) else 1
                            
                            # Use columns from query record if available, else from evaluator, else generate
                            columns = query_record.columns if query_record.columns else final_columns
                            
                            # Adjust column count to match data
                            if not columns or len(columns) != num_cols:
                                if columns and len(columns) > num_cols:
                                    # Trim columns to match data
                                    columns = columns[:num_cols]
                                elif columns and len(columns) < num_cols:
                                    # Pad columns with generated names
                                    columns = list(columns) + [f"column_{i+1}" for i in range(len(columns), num_cols)]
                                else:
                                    # Generate all column names
                                    columns = [f"column_{i+1}" for i in range(num_cols)]
                            
                            print(f"   Using columns ({len(columns)}): {columns}")
                            
                            # Create DataFrame
                            df = pd.DataFrame(parsed, columns=columns)
                            print(f"   Created DataFrame with shape: {df.shape}")
                            break
                    except (SyntaxError, ValueError) as e:
                        # Try alternate parsing - result might be in different format
                        print(f"   ⚠️ Failed to parse query result: {e}")
                        continue
        
        # Fallback: Try to extract from markdown tables in messages
        if df is None:
            print("   ⚠️ No DataFrame from query_history, trying markdown tables...")
            for msg in reversed(state["messages"]):
                if isinstance(msg, AIMessage) and isinstance(msg.content, str):
                    content = msg.content
                    
                    # Look for FINAL_CSV_DATA block
                    if "### FINAL_CSV_DATA ###" in content:
                        start = content.find("### FINAL_CSV_DATA ###")
                        code_start = content.find("```", start)
                        if code_start != -1:
                            code_end = content.find("```", code_start + 3)
                            if code_end != -1:
                                raw_data = content[code_start + 3:code_end].strip()
                                if raw_data.startswith("csv"):
                                    raw_data = raw_data[3:].strip()
                                try:
                                    df = pd.read_csv(io.StringIO(raw_data))
                                    break
                                except:
                                    pass
                    
                    # Look for markdown tables
                    if "|" in content and "---" in content:
                        lines = content.split("\n")
                        table_lines = [l.strip() for l in lines if "|" in l and l.strip()]
                        if len(table_lines) >= 3:  # Header + separator + at least one data row
                            try:
                                # Parse header
                                header_cells = [c.strip() for c in table_lines[0].split("|") if c.strip()]
                                # Skip separator (table_lines[1])
                                # Parse data rows
                                rows = []
                                for line in table_lines[2:]:
                                    if "---" not in line:
                                        cells = [c.strip() for c in line.split("|") if c.strip()]
                                        if cells:
                                            rows.append(cells)
                                if rows:
                                    df = pd.DataFrame(rows, columns=header_cells[:len(rows[0])])
                                    break
                            except:
                                pass
        
        if df is None or df.empty:
            print("❌ DataFrame is None or empty - cannot save CSV")
            output_message = AIMessage(
                content="Failed to extract data for CSV export. No structured data found in query results."
            )
            return Command(
                goto=END,
                graph=Command.PARENT,
                update={
                    "messages": [output_message],
                    "feedback": "CSV export failed: No structured data found"
                }
            )
        
        # Ensure output directory exists
        print(f"📂 Checking output directory: {csv_output_path}")
        print(f"   Type of csv_output_path: {type(csv_output_path)}")
        print(f"   csv_output_path exists before mkdir: {csv_output_path.exists() if hasattr(csv_output_path, 'exists') else 'N/A'}")
        
        try:
            csv_output_path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ mkdir completed")
        except Exception as mkdir_err:
            print(f"   ❌ mkdir failed: {mkdir_err}")
        
        print(f"   csv_output_path exists after mkdir: {csv_output_path.exists() if hasattr(csv_output_path, 'exists') else 'N/A'}")
        print(f"   csv_output_path is_dir: {csv_output_path.is_dir() if hasattr(csv_output_path, 'is_dir') else 'N/A'}")
        
        # Generate unique filename if needed
        if not csv_filename.endswith(".csv"):
            csv_filename += ".csv"
        
        csv_path = csv_output_path / csv_filename
        print(f"   Initial csv_path: {csv_path}")
        print(f"   csv_path type: {type(csv_path)}")
        
        # Handle duplicate filenames
        if csv_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"{csv_path.stem}_{timestamp}.csv"
            csv_path = csv_output_path / csv_filename
            print(f"   File exists, using timestamped name: {csv_path}")
        
        try:
            # Write CSV file using pandas
            print(f"💾 ATTEMPTING TO SAVE CSV")
            print(f"   Full path: {csv_path}")
            print(f"   Absolute path: {csv_path.absolute() if hasattr(csv_path, 'absolute') else csv_path}")
            print(f"   DataFrame shape: {df.shape}")
            print(f"   DataFrame columns: {list(df.columns)}")
            print(f"   DataFrame head:\n{df.head()}")
            
            # Actually save
            df.to_csv(csv_path, index=False, encoding="utf-8")
            
            # IMMEDIATE verification using os.path.exists with string path
            import os
            csv_path_str = str(csv_path)
            print(f"   IMMEDIATE CHECK after to_csv():")
            print(f"   os.path.exists('{csv_path_str}'): {os.path.exists(csv_path_str)}")
            print(f"   csv_path.exists(): {csv_path.exists()}")
            
            # Flush to disk explicitly
            import subprocess
            subprocess.run(['sync'], check=False)
            print(f"   After sync command:")
            print(f"   os.path.exists('{csv_path_str}'): {os.path.exists(csv_path_str)}")
            
            # List directory
            print(f"   Directory listing of {csv_output_path}:")
            for item in os.listdir(csv_output_path):
                full_item_path = os.path.join(str(csv_output_path), item)
                print(f"      - {item} (size: {os.path.getsize(full_item_path)} bytes)")
            
            if os.path.exists(csv_path_str):
                file_size = os.path.getsize(csv_path_str)
                print(f"   ✅ FILE VERIFIED - Size: {file_size} bytes")
                
                # Read back to double-check
                with open(csv_path_str, 'r') as f:
                    first_100_chars = f.read(100)
                print(f"   First 100 chars of file: {first_100_chars}")
            else:
                print(f"   ❌ FILE NOT FOUND AFTER SAVE - Something went wrong!")
            
            # Build result summary with file path info
            result_summary = state.get("result_summary", "")
            if result_summary:
                result_summary += f"\n\n**Output File**: {csv_path}"
            
            output_message = AIMessage(
                content=f"✅ Data exploration complete. Results saved to: {csv_path}\n\nColumns: {list(df.columns)}\nRows: {len(df)}"
            )
            
            return Command(
                goto=END,
                update={
                    "messages": [output_message],
                    "result_summary": result_summary,
                }
            )
            
        except Exception as e:
            import traceback
            print(f"❌ EXCEPTION during CSV save:")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error message: {e}")
            print(f"   Traceback:\n{traceback.format_exc()}")
            output_message = AIMessage(
                content=f"Failed to save CSV: {str(e)}"
            )
            return Command(
                goto=END,
                graph=Command.PARENT,
                update={
                    "messages": [output_message],
                    "feedback": f"CSV export failed: {str(e)}"
                }
            )
    
    return update_workspace


# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_after_query_generation(state: DataExplorationState) -> Literal["run_query", "evaluator"]:
    """Route based on whether agent wants to run a query or is done."""
    last_message = state["messages"][-1]
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "run_query"
    
    return "evaluator"


def route_after_evaluator(state: DataExplorationState) -> Literal["generate_query", "update_workspace", END]:
    """Route based on evaluator's decision."""
    if state.get("ready_for_export"):
        return "update_workspace"
    
    # Check if we've hit a loop limit
    query_count = len(state.get("query_history", []))
    if query_count > 20:  # Safety limit
        return END
    
    return "generate_query"


# ============================================================================
# BUILD THE GRAPH - WITH CONFIGURABLE LLM
# ============================================================================

def build_data_exploration_agent(model_name: str = "gpt-4o", db_path: str = None, output_path: Path = None):
    """
    Build the complete data exploration agent graph with configurable LLM.
    
    Args:
        model_name: LLM model to use with init_chat_model. Examples: "gpt-4o", "claude-3-5-sonnet",
                   "gemini-2.0-flash", etc. Defaults to "gpt-4o".
        db_path: Path to the SQLite database. Uses default if not provided.
        output_path: Path to save CSV outputs. Uses DEFAULT_OUTPUT_PATH if not provided.
    
    Returns:
        Compiled LangGraph StateGraph for the data exploration agent.
    """
    print(f"🤖 Initializing LLM: {model_name}")
    llm = init_chat_model(model_name)
    
    print(f"🗄️  Connecting to database...")
    db = setup_database(db_path)
    tools = setup_toolkit(db, llm)
    
    print(f"   Database dialect: {db.dialect}")
    print(f"   Tables available: {db.get_usable_table_names()}")
    
    # Set output path for CSV exports
    csv_output_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH
    print(f"   Output path: {csv_output_path}")
    
    # Get specific tools
    get_schema_tool = next(t for t in tools if t.name == "sql_db_schema")
    run_query_base_tool = next(t for t in tools if t.name == "sql_db_query")
    
    # Create wrapped query tool with column tracking
    query_tool = create_query_tool(run_query_base_tool)
    
    # Create tool nodes
    get_schema_node = ToolNode([get_schema_tool], name="get_schema")
    run_query_node = ToolNode([query_tool], name="run_query")
    
    # Create function nodes with closures
    def list_tables(state):
        return list_tables_node(state, tools)
    
    def call_get_schema(state):
        return call_get_schema_node(state, llm, get_schema_tool)
    
    generate_query = create_generate_query_node(llm, query_tool, db)
    process_results = create_process_results_node()
    evaluator = create_evaluator_node(llm)
    update_workspace = create_update_workspace_node(llm, output_path=csv_output_path)
    
    # Combined node: process schema after get_schema tool
    def process_schema(state):
        return process_schema_node(state)
    
    # Build graph
    builder = StateGraph(DataExplorationState)
    
    # Add nodes
    builder.add_node("list_tables", list_tables)
    builder.add_node("call_get_schema", call_get_schema)
    builder.add_node("get_schema", get_schema_node)
    builder.add_node("process_schema", process_schema)
    builder.add_node("generate_query", generate_query)
    builder.add_node("run_query", run_query_node)
    builder.add_node("process_results", process_results)
    builder.add_node("evaluator", evaluator)
    builder.add_node("update_workspace", update_workspace)
    
    # Add edges - Workflow Phase
    builder.add_edge(START, "list_tables")
    builder.add_edge("list_tables", "call_get_schema")
    builder.add_edge("call_get_schema", "get_schema")
    builder.add_edge("get_schema", "process_schema")
    builder.add_edge("process_schema", "generate_query")
    
    # Add edges - ReAct Phase
    builder.add_conditional_edges(
        "generate_query",
        route_after_query_generation,
        ["run_query", "evaluator"]
    )
    builder.add_edge("run_query", "process_results")
    builder.add_edge("process_results", "generate_query")
    
    # Add edges - Evaluation Phase
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        ["generate_query", "update_workspace", END]
    )
    builder.add_edge("update_workspace", END)
    
    return builder.compile()


# ============================================================================
# HELPER: WRAP AS TOOL FOR SUPERVISOR
# ============================================================================

def create_data_exploration_tool_for_supervisor(model_name: str = "gpt-4o", db_path: str = None):
    """
    Wrap the data exploration agent as a tool that can be called by a supervisor.
    
    Args:
        model_name: LLM model to use. Examples: "gpt-4o", "claude-3-5-sonnet", etc.
        db_path: Path to the SQLite database.
    
    Returns:
        A tool function that can be used by supervisor agents.
    """
    graph = build_data_exploration_agent(model_name=model_name, db_path=db_path)
    
    @tool("data_exploration_tool")
    def data_exploration_tool(task: str) -> str:
        """
        Explore a database and extract structured data based on the task.
        
        Args:
            task: Description of what data to extract (e.g., "find all paintings grouped by genre with counts")
            
        Returns:
            Path to the generated CSV file with results, or error message.
        """
        # Initialize state with task context
        initial_state = {
            "messages": [HumanMessage(content=task)],
            "original_task": task,
            "query_history": [],
            "tables_queried": [],
            "exploration_complete": False,
            "ready_for_export": False
        }
        
        # Run the graph
        result = graph.invoke(initial_state)
        
        # Extract final message
        if result.get("messages"):
            last_msg = result["messages"][-1]
            return last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        return "Data exploration completed but no output message generated."
    
    return data_exploration_tool


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Example 1: Build with default settings (GPT-4o)
    print("=" * 80)
    print("Example 1: Default settings (GPT-4o)")
    print("=" * 80)
    agent = build_data_exploration_agent()
    
    # Example usage
    question = "Which genre has the most paintings? Show all genres with their painting counts."
    
    initial_state = {
        "messages": [HumanMessage(content=question)],
        "original_task": question,
        "query_history": [],
        "tables_queried": [],
        "exploration_complete": False,
        "ready_for_export": False
    }
    
    print(f"\n🚀 Starting data exploration agent test...")
    print(f"Task: {question}\n")
    
    # Uncomment to run:
    # for step in agent.stream(initial_state, stream_mode="values"):
    #     if step.get("messages"):
    #         step["messages"][-1].pretty_print()
