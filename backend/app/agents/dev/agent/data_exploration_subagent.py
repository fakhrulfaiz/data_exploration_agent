import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

# Load environment variables
load_dotenv()

# Initialize the model
model = init_chat_model("gpt-4o-mini")

# Setup database connection
base_path = Path.cwd().parent.parent
db_path = base_path / "resource" / "art.db"

# Override the database path cause error in notebook
db_path = "/home/afiq/fyp/fafa-repo/backend/app/resource/art.db"

sql_url = f"sqlite:///{db_path}"
db = SQLDatabase.from_uri(sql_url)

# Initialize toolkit and tools
toolkit = SQLDatabaseToolkit(db=db, llm=model)
tools = toolkit.get_tools()

# Setup tool nodes
get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
get_schema_node = ToolNode([get_schema_tool], name="get_schema")

run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
run_query_node = ToolNode([run_query_tool], name="run_query")


# Node: List available tables
def list_tables(state: MessagesState):
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
def call_get_schema(state: MessagesState):
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
""".format(
    dialect=db.dialect,
    top_k=5,
)


def generate_query(state: MessagesState):
    system_message = {
        "role": "system",
        "content": generate_query_system_prompt,
    }
    llm_with_tools = model.bind_tools([run_query_tool])
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


def check_query(state: MessagesState):
    system_message = {
        "role": "system",
        "content": check_query_system_prompt,
    }

    # Generate an artificial user message to check
    tool_call = state["messages"][-1].tool_calls[0]
    user_message = {"role": "user", "content": tool_call["args"]["query"]}
    llm_with_tools = model.bind_tools([run_query_tool], tool_choice="any")
    response = llm_with_tools.invoke([system_message, user_message])
    response.id = state["messages"][-1].id

    return {"messages": [response]}


# Conditional edge function
def should_continue(state: MessagesState) -> Literal[END, "check_query"]:
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return END
    else:
        return "check_query"


# Build the agent graph
def build_agent():
    builder = StateGraph(MessagesState)
    builder.add_node(list_tables)
    builder.add_node(call_get_schema)
    builder.add_node(get_schema_node, "get_schema")
    builder.add_node(generate_query)
    builder.add_node(check_query)
    builder.add_node(run_query_node, "run_query")

    builder.add_edge(START, "list_tables")
    builder.add_edge("list_tables", "call_get_schema")
    builder.add_edge("call_get_schema", "get_schema")
    builder.add_edge("get_schema", "generate_query")
    builder.add_conditional_edges(
        "generate_query",
        should_continue,
    )
    builder.add_edge("check_query", "run_query")
    builder.add_edge("run_query", "generate_query")

    return builder.compile()


# Initialize the agent
agent = build_agent()


if __name__ == "__main__":
    # Example usage
    question = "Which genre has the oldest painting?"

    for step in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()
