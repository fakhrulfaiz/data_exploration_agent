import os
import csv
import ast
import json
from pathlib import Path
from typing import Literal, Annotated, Any, Dict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

# Load environment variables
load_dotenv()

# Initialize the model
model = init_chat_model("gpt-4o-mini")

# Setup database connection
base_path = Path.cwd().parent.parent
print(base_path)
db_path = base_path / "resource" / "art.db"

dev_path = base_path / "agents" / "dev"
workspace_path = dev_path / "workspace"

# sql_url = f"sqlite:///{db_path.resolve()}"
db_path = "/home/afiq/fyp/fafa-repo/backend/app/resource/art.db"
sql_url = f"sqlite:///{db_path}"
db = SQLDatabase.from_uri(sql_url)

toolkit = SQLDatabaseToolkit(db=db, llm=model)
tools = toolkit.get_tools()

# Setup tool nodes
get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
get_schema_node = ToolNode([get_schema_tool], name="get_schema")


from state.data_exploration_state import DataExplorationState, QueryArgs, DataExplorationOutput, ToolResult

from langchain_core.tools import StructuredTool


run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")

def run_query_tool_with_columns(query: str, columns: list[str]):
    # columns is for planning / downstream use
    # the actual DB tool only needs `query`
    return run_query_tool.invoke({"query": query})

wrapped_run_query_tool = StructuredTool.from_function(
    name="sql_db_query",  # SAME name (important)
    description=run_query_tool.description,
    func=run_query_tool_with_columns,
    args_schema=QueryArgs,
)
run_query_node = ToolNode([run_query_tool], name="run_query") # the action part of the agent system.

# Node: List available tables
def list_tables(state: DataExplorationState):
    tool_call = {
        "name": "sql_db_list_tables",
        "args": {},
        "id": "abc123",
        "type": "tool_call",
    }
    tool_call_message = AIMessage(content="", tool_calls=[tool_call])

    list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
    tool_message = list_tables_tool.invoke(tool_call)
    response = AIMessage(f"Available tables: {tool_message.content}")

    return {"messages": [tool_call_message, tool_message, response]}


# Node: Get schema
def call_get_schema(state: DataExplorationState):
    llm_with_tools = model.bind_tools([get_schema_tool], tool_choice="any")
    response = llm_with_tools.invoke(state["messages"])

    return {"messages": [response]}


# Node: Generate SQL query
generate_query_system_prompt = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {dialect} query to run,
then look at the results of the query and return the answer. Unless the user
specifies a specific number of examples they wish to obtain, always limit your
query to at most {top_k} results.

You can order the results by a relevant column to return the most interesting
examples in the database. Never query for all the columns from a specific table,
only ask for the relevant columns given the question.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.

If you have enough information to answer the user's question: DO NOT generate a tool call but instead answer the question.
There might be case where Table or Column name is not available. In this case, explain to user that the information is not available and end conversation.
""".format(
    dialect=db.dialect,
    top_k=5,
)


def generate_query(state: DataExplorationState):
    """The reasoning part of the agent."""
    system_message = {
        "role": "system",
        "content": generate_query_system_prompt,
    }
    llm_with_tools = model.bind_tools([wrapped_run_query_tool])
    response = llm_with_tools.invoke([system_message] + state["messages"])

    

    return {"messages": [response]}


# Node: Check query for common mistakes
check_query_system_prompt = """
You are a SQL expert with a strong attention to detail.
Double check the {dialect} query for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins

If there are any of the above mistakes, rewrite the query. If there are no mistakes,
just reproduce the original query.

You will call the appropriate tool to execute the query after running this check.
""".format(dialect=db.dialect)

# Evaluate query result and make a structured output response
def evaluate_query(state: DataExplorationState):
    """
    Extract query results from ToolMessage and create structured ToolResult.
    Evaluation are made with an LLM.

    
    1. Extract details from ToolMessage
    2. Create ToolResult model with validation
    3. If error during validation → Command back to generate_query
    4. If success → return ToolResult to be appended to tool_results list
    """
    from langchain_core.messages import ToolMessage
    
    last_message = state["messages"][-1]
    evaluator = model.with_structured_output(DataExplorationOutput)
    system_message = {
        "role": "system",
        "content": "You need to evaluate if the following query make sense and run as intended. Be extra mindful and strict of weird query that does not make sense of the database schema (This is an error). If the model says it cant answer the question or cant run the query for whatever reason, return error and explain why.",
    }

    # Check if last message is AIMessage    
    if isinstance(last_message, AIMessage):
        output: DataExplorationOutput = evaluator.invoke(state["messages"])

        if output.error:
            if output.error_message == "":
                return Command(goto=END, graph=Command.PARENT, update={"current_step": 0, "feedback": f"final tool execution result: {output.final_tool_result}"})    
            return Command(goto=END, graph=Command.PARENT, update={"feedback": output.error_message, "current_step": 0})
        else:
            return END

    
    # Process results from ToolMessage
    # Find the corresponding tool call
    tool_call_id = last_message.tool_call_id
    tool_call = None
    
    for msg in reversed(state["messages"][:-1]):
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls:
                if call["id"] == tool_call_id:
                    tool_call = call
                    break
            if tool_call:
                break
    
    if tool_call is None:
        return {}
    
    # Create ToolResult model with validation
    tool_result = ToolResult(
        tool_call_id=tool_call_id,
        name=tool_call["name"],
        query=tool_call["args"]["query"],
        columns=tool_call["args"]["columns"],
        result=last_message.content
    )

    # Evaluation starts here
    result = tool_result.model_dump_json()
    message = AIMessage(content=result)
    
    output: DataExplorationOutput = evaluator.invoke(state["messages"] + [message] + [system_message]) # type: ignore
    output_message = AIMessage(content=output.model_dump_json())

    # check for error by the evaluator
    if not output.error and tool_result is not None:
        return {"tool_results": [tool_result], "messages": [message] + [output_message]} 
    else:
        return Command(goto="interrupt_for_replan", graph=Command.PARENT, update={"messages": [output_message], "feedback": output.error_message})
    
# Node to extract tool results into state
from langchain_core.messages import ToolMessage

def store_query_result(state: DataExplorationState):
    """
    Create structured output from the latest tool result and prepare for output.
    """
    if not state.get("tool_results") or len(state["tool_results"]) == 0:
        return {}
    
    last_result = state["tool_results"][-1]
    
    try:
        # Create structured output
        output = DataExplorationOutput(
            query=last_result.query,
            final_tool_result=str(last_result.result),
            error=False,
            error_message=None
        )
        
        # Return JSON as message for LLM context
        return {"messages": [AIMessage(content=json.dumps(output.model_dump()))]}
        
    except Exception as e:
        return {
            "messages": [AIMessage(
                content=json.dumps(
                    DataExplorationOutput(
                        query=last_result.query,
                        final_tool_result=str(last_result.result),
                        error=True,
                        error_message=str(e)
                    ).model_dump()
                )
            )]
        }


# Node to save query results to CSV workspace
def update_workspace(state: DataExplorationState):
    """Save the latest query result to CSV file."""
    if not state.get("tool_results") or len(state["tool_results"]) == 0:
        return {}
    
    # Get the most recent tool result
    last_result = state["tool_results"][-1]
    
    try:
        # Parse the result
        rows = ast.literal_eval(str(last_result.result))
        
        if not isinstance(rows, list):
            raise ValueError("Parsed result is not a list")
        
        # Create output directory
        output_dir = workspace_path / "data"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save to CSV with tool_call_id as filename
        csv_path = output_dir / f"{last_result.tool_call_id}.csv"
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(last_result.columns)
            writer.writerows(rows)
        
        return {}
        
    except Exception as e:
        # Log error but don't fail the workflow
        print(f"Warning: Failed to save CSV: {e}")
        return {}

# Conditional edge function
def should_continue(state: MessagesState) -> Literal["evaluate_query", "run_query"]:
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "evaluate_query"
    else:
        return "run_query"

# Build the agent graph
def build_agent():
    builder = StateGraph(DataExplorationState)
    builder.add_node(list_tables)
    builder.add_node(call_get_schema)
    builder.add_node(get_schema_node, "get_schema")
    builder.add_node(generate_query)
    builder.add_node(run_query_node, "run_query")
    builder.add_node(evaluate_query)
    builder.add_node(store_query_result)
    builder.add_node(update_workspace)

    builder.add_edge(START, "list_tables")
    builder.add_edge("list_tables", "call_get_schema")
    builder.add_edge("call_get_schema", "get_schema")
    builder.add_edge("get_schema", "generate_query")
    builder.add_conditional_edges(
        "generate_query",
        should_continue,
    )
    builder.add_edge("run_query", "evaluate_query")
    # builder.add_edge("evaluate_query", "store_query_result")
    builder.add_edge("store_query_result", "update_workspace")
    builder.add_edge("update_workspace", "generate_query")

    return builder.compile()


# Initialize the agent
agent = build_agent()

# Test
if __name__ == "__main__":
    # Example usage
    question = "Which genre has the oldest painting?"

    for step in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()
