# data_exploration_subagent_v2.py - Redesigned with proper state management and evaluator context

"""
Key Fixes:
1. State tracks: original_task, schema_info, query_history (structured)
2. Tool properly updates state with structured QueryRecord
3. Evaluator has full context of what was queried and results
4. Agent can synthesize from accumulated query history
5. Fixed conditional edges routing
6. Proper CSV export implementation
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

def setup_database():
    """Setup database connection and tools."""
    db_path = "/home/afiq/fyp/fafa-repo/backend/app/resource/art.db"
    sql_url = f"sqlite:///{db_path}"
    db = SQLDatabase.from_uri(sql_url)
    return db


def setup_toolkit(db: SQLDatabase, llm):
    """Setup SQL toolkit with all necessary tools."""
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    return toolkit.get_tools()


# ============================================================================
# WORKSPACE CONFIGURATION
# ============================================================================

WORKSPACE_PATH = Path("/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace")
OUTPUT_PATH = WORKSPACE_PATH / "outputs"


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
            
            # return {"messages": [feedback_msg]}
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

def create_update_workspace_node(llm):
    """Create workspace update node for CSV saving."""
    
    def update_workspace(state: DataExplorationState):
        """Extract data from agent response and save to CSV."""
        
        # Find the agent's final response with data
        final_data = None
        csv_filename = "query_result.csv"
        columns = state.get("final_columns", [])
        
        # Look for FINAL_CSV_DATA block or structured data in messages
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage):
                content = msg.content
                
                # Try to parse export instruction message
                try:
                    export_info = json.loads(content)
                    if export_info.get("status") == "ready_for_export":
                        csv_filename = export_info.get("filename", csv_filename)
                        columns = export_info.get("columns", columns)
                        continue
                except json.JSONDecodeError:
                    pass
                
                # Look for FINAL_CSV_DATA block
                if "### FINAL_CSV_DATA ###" in content:
                    # Extract data between markers
                    start = content.find("### FINAL_CSV_DATA ###")
                    # Find code block after marker
                    code_start = content.find("```", start)
                    if code_start != -1:
                        code_end = content.find("```", code_start + 3)
                        if code_end != -1:
                            raw_data = content[code_start + 3:code_end].strip()
                            # Remove language identifier if present
                            if raw_data.startswith("csv"):
                                raw_data = raw_data[3:].strip()
                            final_data = raw_data
                            break
                
                # Look for markdown tables
                if "|" in content and "---" in content:
                    # Try to extract table data
                    lines = content.split("\n")
                    table_lines = [l for l in lines if "|" in l]
                    if len(table_lines) >= 2:  # Header + separator + data
                        # Extract headers
                        header_line = table_lines[0]
                        if not columns:
                            columns = [c.strip() for c in header_line.split("|") if c.strip()]
                        
                        # Extract data rows (skip separator line)
                        data_lines = [l for l in table_lines[2:] if "---" not in l]
                        rows = []
                        for line in data_lines:
                            cells = [c.strip() for c in line.split("|") if c.strip()]
                            if cells:
                                rows.append(cells)
                        
                        if rows:
                            # Convert to CSV format
                            csv_lines = [",".join(columns)]
                            for row in rows:
                                csv_lines.append(",".join(str(c) for c in row))
                            final_data = "\n".join(csv_lines)
                            break
        
        if not final_data:
            # Try to get from last query result
            query_history = state.get("query_history", [])
            if query_history:
                last_query = query_history[-1]
                if isinstance(last_query, QueryRecord) and last_query.success:
                    try:
                        parsed = ast.literal_eval(last_query.result)
                        if isinstance(parsed, list) and parsed:
                            columns = last_query.columns or [f"col_{i}" for i in range(len(parsed[0]))]
                            csv_lines = [",".join(columns)]
                            for row in parsed:
                                if isinstance(row, (list, tuple)):
                                    csv_lines.append(",".join(str(c) for c in row))
                            final_data = "\n".join(csv_lines)
                    except:
                        pass
        
        if not final_data:
            output_message = AIMessage(
                content="Failed to extract data for CSV export. No structured data found in agent response."
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
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename if needed
        if not csv_filename.endswith(".csv"):
            csv_filename += ".csv"
        
        csv_path = OUTPUT_PATH / csv_filename
        
        # Handle duplicate filenames
        if csv_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"{csv_path.stem}_{timestamp}.csv"
            csv_path = OUTPUT_PATH / csv_filename
        
        try:
            # Write CSV file
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                f.write(final_data)
            
            # Build result summary with file path info
            result_summary = state.get("result_summary", "")
            if result_summary:
                result_summary += f"\n\n**Output File**: {csv_path}"
            
            output_message = AIMessage(
                content=f"✅ Data exploration complete. Results saved to: {csv_path}\n\nColumns: {columns}"
            )
            
            return Command(
                goto=END,
                # graph=Command.PARENT,
                update={
                    "messages": [output_message],
                    "result_summary": result_summary,  # Pass summary for other agents
                }
            )
            
        except Exception as e:
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
# BUILD THE GRAPH
# ============================================================================

def build_data_exploration_agent():
    """Build the complete data exploration agent graph."""
    
    # Initialize components
    llm = init_chat_model("gpt-4o")
    db = setup_database()
    tools = setup_toolkit(db, llm)
    
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
    update_workspace = create_update_workspace_node(llm)
    
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

def create_data_exploration_tool_for_supervisor():
    """
    Wrap the data exploration agent as a tool that can be called by a supervisor.
    """
    graph = build_data_exploration_agent()
    
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

# Initialize the agent for direct use
agent = build_data_exploration_agent()

if __name__ == "__main__":
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
    
    print("Starting data exploration agent test...")
    print(f"Task: {question}\n")
    
    for step in agent.stream(initial_state, stream_mode="values"):
        if step.get("messages"):
            step["messages"][-1].pretty_print()
