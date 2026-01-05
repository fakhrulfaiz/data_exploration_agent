import json
import os
from pathlib import Path
from pprint import pformat
from typing import Annotated, Any, Dict, Iterable, List, Literal

from dotenv import load_dotenv
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

import sys
import re
sys.path.append("/home/afiq/fyp/fafa-repo/backend/app/agents/dev/agent")

# Import the data exploration agent
from data_exploration_subagent import build_agent as build_data_exploration_agent
from state.data_exploration_state import DataExplorationState, ToolResult
from pydantic.json_schema import SkipJsonSchema

# Load environment variables
load_dotenv()

# Initialize the model
model = init_chat_model("gpt-4o-mini")

# Build the data exploration agent
data_exploration_agent = build_data_exploration_agent()

# helper
def _format_any_result(result: Any) -> str:
    """
    Safely format structured or unstructured results.
    """
    if isinstance(result, (dict, list, tuple)):
        return pformat(result, width=100, sort_dicts=False)
    return str(result)

def _format_data_exploration_results(tool_results: Annotated[List[Any], SkipJsonSchema()]) -> str:
    """
    Convert a list of ToolResult objects into one formatted string.
    """
    sections = []

    for idx, tr in enumerate(tool_results, start=1):
        section = (
            f"Tool Result #{idx}\n"
            f"Tool Name : {tr.name}\n"
            f"Query     : {tr.query}\n"
            f"Result:\n{_format_any_result(tr.result)}\n"
            f"{'=' * 60}"
        )
        sections.append(section)

    return "\n\n".join(sections)


# Wrap data_exploration_agent as a tool
@tool("database_exploration_agent", description="Use this agent to explore and query the art database. Provide a natural language question about the art data. REMEMBER TO ALWAYS specify total number of rows you want to return and ask for img_path.")
def call_data_exploration_agent(
    query: str, 
) -> Command:
    """
    Call the database exploration agent to answer questions about the art database.
    REMEMBER TO ALWAYS specify total number of rows you want to return and ask for img_path.

    Args:
        query: A natural language question about the art data
        
    Returns:
        The response from the data exploration agent. 
    """
    result = data_exploration_agent.invoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    reply = result["messages"][-1].content + "\n\n```json" + result["messages"][-2].content + "```"
    json_str = result["messages"][-2].content
    # validated_data = DataExplorationState.model_validate_json(json_str)

    # # Create Tool Message for Command 
    # tool_message = ToolMessage(
    #     content=reply,
    #     tool_call_id=tool_call_id,
    # )
    return reply

    # return Command(
    #     update={
    #             "messages": [tool_message],
    #             "tool_results": json.loads(json_str),
    #         }
    # )


# Import image QNA tool
# from image_qna_tool import build_image_qna_tool
# image_qna_tool = build_image_qna_tool()
from agent.image_qna_subagent import build_image_qna_agent
image_qna_agent = build_image_qna_agent()

# Wrap data_exploration_agent as a tool
@tool("image_qna_agent", description="Use this expert agent to answer questions related to the visual aspects of images in the database. You can query multiple images at once and the agent will answer it in parallel. Use this tool when you want to answer questions that needs visual information from an image. This tool only works with image path. Example path = `images/img_0.jpg`")
def call_image_qna_agent(query: str, img_path: List[str]) -> str:
    """
    Call the image QNA agent to answer questions related to the images in the database. You can query multiple images at once and the agent will answer it in parallel.
    Use this tool when you want to answer questions that needs visual information from an image. This tool only works with image path. Example path = `images/img_0.jpg`

    Args:
        query: A natural language question about the images in the database. Provide details goals of the query. The query can be done on multiple images at once.
        img_path: A list of image path for the related images to be accessed. Example path = [images/img_0.jpg] or [images/img_1.jpg, images/img_2.jpg, ...]
        
    Returns:
        The response from the image QNA agent. 
    """
    img_path_json_str = json.dumps(img_path)
    result = image_qna_agent.invoke(
        {"messages": [{"role": "user", "content": f"{query}\n\nimg_path={img_path_json_str}"}]}
    )

    reply = result["messages"][-1].content + "\n\n```json" + result["messages"][-2].content + "```"
    return reply

# Define tools list
tools = [
    # image_qna_tool,
    call_image_qna_agent,
    call_data_exploration_agent,
]

tools_by_name = {tool.name: tool for tool in tools}

# Reducer 
def merge_tool_results(a: dict, b: dict) -> dict:
    return {**a, **b}

from state.main_agent_state import MainAgentState

# Helper functions
def format_tools_for_prompt(tools):
    lines = []
    for i, tool in enumerate(tools, start=1):
        lines.append(f"{i}. {tool.name}: {tool.description}")
    return "\n".join(lines)


def parse_plan(plan_text: str) -> list[str]:
    """
    Converts a numbered plan string into a list of steps.
    """
    # Split on line breaks and remove empty lines
    lines = [line.strip() for line in plan_text.split("\n") if line.strip()]
    
    steps = []
    for line in lines:
        # Remove the number + dot prefix (e.g., "1. ", "2. ")
        step = re.sub(r"^\d+\.\s*", "", line)
        steps.append(step)
    
    return steps


def plan_and_list_tasks(state: MainAgentState):
    """Plan and list tasks."""
    planning_system_prompt = """
    You are an efficient task planner. Your job is to only plan and list tasks or subtasks in the most efficient and resourceful way.
    You are given a user query/task and a list of tools.

    
    list the tasks in the following format:
    1. task 1, use tool A, to get information X
    2. task 2, use tool B, to process Y
    3. task 3, use tool C, to make Z
    ...

    plan and list the tasks in a way that each task can be solved by one of these tools.

    tools:
    1. image_qna_agent: This tool equipped with an expert agent with visual question answering tool that can answer questions related to the images in the database. If the question are simmilar, you can populate multiply image path to query multiple images at once.
    2. database_exploration_agent: This tool can answer questions related to the database but limited to the scope of the schema. Always be explicit on the total number of rows you want to return for most accurate result.

    Remember that you need to use image_qna_tool to solve tasks that needs to understand the visuals in the images.

    MAIN_TASK(True Goal): {query}

    tools_description:
    {tools}    

    IMPORTANT:
    1. image_qna_agent need  list of IMAGE PATH (["images/img_0.jpg"] or ["images/img_1.jpg", "images/img_2.jpg", ...]) to works. ALWAYS use multiple image in one call when possible. 
    2. Dont query on non-existant database column. You can use image_qna_agent to synthesis the information from the image.
    {feedback}

    database_schema:
    ## Table: paintings

### Description
Stores metadata about paintings, including historical, artistic, and image-related information.

### Columns
| Column Name | Data Type | Description |
|------------|-----------|-------------|
| title | TEXT | Name of the painting |
| inception | DATETIME | Date the painting was created |
| movement | TEXT | Art movement (e.g., Renaissance) |
| genre | TEXT | Artistic genre |
| image_url | TEXT | Public URL to the painting image |
| img_path | TEXT | Local file path to the image |

### Sample Rows
| title | inception | movement | genre | image_url | img_path |
|------|-----------|----------|-------|-----------|----------|
| Predella of the Barbadori altarpiece | 1438-01-01 | Renaissance | religious art | http://commons.wikimedia.org/wiki/Special:FilePath/Predella%20Pala%20Barbadori-%20Uffizi.JPG | images/img_0.jpg |
| Judith | 1525-01-01 | Renaissance | religious art | http://commons.wikimedia.org/wiki/Special:FilePath/Palma%20il%20Vecchio%20-%20Judith%20-%20WGA16936. | images/img_1.jpg |
| Judith | 1528-01-01 | Renaissance | religious art | http://commons.wikimedia.org/wiki/Special:FilePath/Palma%20il%20Vecchio%20-%20Judith%20-%20WGA16936. | images/img_2.jpg |

    """
    if state.get("query") is None: # Ensure query is not None
        state["query"] = state["messages"][0].content
    
    if state.get("feedback") is not None: # replan
        replanning_system_prompt = planning_system_prompt.format(
            query=state["query"],
            feedback= f"The last plan failed: {state['feedback']}",
            tools=format_tools_for_prompt(tools)
        )
        response = model.invoke(
                [
                    {"role": "system", "content": replanning_system_prompt},
                    {"role": "user", "content": state["messages"][-1].content},
                ]
            )
        state_update = {
                "base_plan": parse_plan(response.content),
                "current_step": 0,
                "replan_count": state["replan_count"] + 1,
                "feedback": None
            }

        # Return updated state
        return state_update
    
    response = model.invoke(
            [
                {"role": "system", "content": planning_system_prompt.format(
                    query=state["query"],
                    tools=format_tools_for_prompt(tools),
                    feedback=""
                )},
                {"role": "user", "content": state["messages"][-1].content},
            ]
        )

    state_update = {
            "base_plan": parse_plan(response.content),
            "current_step": 0,
            "replan_count": 0
        }

    # Return updated state
    return state_update



# Node: Process user query with main agent
main_agent_system_prompt = """
You are a helpful assistant designed to solve tasks/ question about the art database.
You have access to a specialized data exploration agent that can query the art database.
You also have access to a tool that can answer questions related to the images in the database.

Your limitation in data exploration agent is that it can only query the database and tasks that demands context outside the database schema are beyond its scope.

When users ask questions about the art database, use the data_exploration_agent tool to find the answers, if the schema and context relates.
When users ask questions in regard to the visuals in the images, use the image_qna_agent to solve the tasks.

You can ask the agent multi-step questions and use the results to provide comprehensive responses.
"""


def process_query(state: MainAgentState):
    """Process user query with the main agent."""

    # if has feedback go straight to replan, will implement later
    if state.get("feedback") is not None:
        return state

    # Safety check: do we have any steps left?
    if state["current_step"] >= len(state["base_plan"]):
        print(f"All steps completed. Current step: {state['current_step']}, Total steps: {len(state['base_plan'])}")
        return {"messages": state["messages"]}  # return current messages unchanged

    # Get the current plan step
    current_step_text = state["base_plan"][state["current_step"]]
    
    # # Check for previous step
    # previous_step = ""
    # if state["current_step"] > 0:
    #     previous_step = f"Just executed: {state["base_plan"][state["current_step"] - 1]}. Next "
    # Pass the whole step (with json.dumps), so the agent can understand the context
    base_plan_string = json.dumps(state["base_plan"])

    # data_exploration_result = state['data_exploration_history']
    # data_exploration_result_str = _format_data_exploration_results(data_exploration_result)


    # System + user messages
    system_message = {"role": "system", "content": main_agent_system_prompt}
    # plan_message = {"role": "user", "content": f"Now you are working on this step: {current_step_text}\nThis is the overall plan: {base_plan_string} and this is what we find from the previous result: {json.dumps(data_exploration_result_str)}\n\n"}#add image analysis result here later
    plan_message = {"role": "user", "content": f"Now you are working on this step: {current_step_text}\nThis is the overall plan: {base_plan_string}\n\n"}

    # Bind tools the agent can use
    llm_with_tools = model.bind_tools([call_image_qna_agent, call_data_exploration_agent])

    # Include previous messages for context
    response = llm_with_tools.invoke([system_message] + state["messages"] + [plan_message])

    # Track the step in history
    new_step_history = state["step_history"].copy() if state.get("step_history") else {}
    new_step_history[state["current_step"]] = current_step_text

    # Increment the current_step after producing the tool call
    new_current_step = state["current_step"] + 1
    
    # Append response to messages (not replace)
    new_messages = state["messages"] + [response]

    return {
        "messages": new_messages,
        "current_step": new_current_step,
        "step_history": new_step_history
    }


def tool_node(state: MainAgentState):
    """Performs the tool call."""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        try:
            observation = tool.invoke(tool_call["args"])

        except Exception as e:
            observation = f"Error: {e}"
            feedback = f"Error on Tool {tool_call['name']}, Error: {e}"
            result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
            return {"messages": result, "feedback": feedback}

        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


def interrupt_for_replan(state: MainAgentState) -> Command[Literal["plan_and_list_tasks", "cleanup"]]:

    # is_approved = interrupt({
    #     "question": "Do you want to proceed with replanning?",
    # }) 
    is_approved = True

    if is_approved:
        print("Replanning...")
        # reset counter
        return Command(goto="plan_and_list_tasks", update={"current_step": 0,})
    else:
        return Command(goto="cleanup")


# Conditional edge function
def should_continue(state: MainAgentState) -> Literal["cleanup", "tool_execution", "interrupt_for_replan"]:
    """Determine if we should call the agent or end."""
    # Check for replan
    if state.get("feedback") is not None:
        return "interrupt_for_replan"

    messages = state["messages"]
    last_message = messages[-1]

    # Check if we have reached the end of the plan
    # if state["current_step"] >= len(state["base_plan"]):
    #     return "cleanup"
    if not getattr(last_message, "tool_calls", None):
        return "cleanup"
    else:
        return "tool_execution"
    

# cleanup Node
def cleanup_state(state: MainAgentState) -> MainAgentState:
    return {
        **state,
        "base_plan": None,
        "current_step": 0,
        "step_history": None,
        "replan_count": 0,
        "feedback": None,
        "query": None
    }


# Build the main agent graph
def build_main_agent(checkpointer):
    """Build the main agent graph with data exploration agent as subagent."""
    builder = StateGraph(MainAgentState)
    builder.add_node("plan_and_list_tasks", plan_and_list_tasks)
    builder.add_node("process_query", process_query)
    builder.add_node("tool_execution", tool_node)
    builder.add_node("cleanup", cleanup_state)
    builder.add_node("interrupt_for_replan", interrupt_for_replan)
    
    builder.add_edge(START, "plan_and_list_tasks")
    builder.add_edge("plan_and_list_tasks", "process_query")
    builder.add_conditional_edges(
        "process_query",
        should_continue,
    )
    builder.add_edge("tool_execution", "process_query")
    builder.add_edge("cleanup", END)
    
    return builder.compile(checkpointer=checkpointer)

from langgraph.checkpoint.memory import MemorySaver
# Initialize the main agent
main_agent = build_main_agent(MemorySaver())


if __name__ == "__main__":
    # Example usage
    questions = [
        "What is the oldest painting?",
        # "Which genre has the oldest painting?",
        # "Does the oldest painting has one person in it?",
        # "Get the number of paintings that shows Fruit for each century.",
    ]
    

    config = {"configurable": {"thread_id": "dev-fyp"}}

    for question in questions:
        print(f"\nQuestion: {question}")
        print("-" * 50)
        
        for step in main_agent.stream(
            {"messages": [{"role": "user", "content": question}]},
            stream_mode="values",
            config=config,
        ):
            step["messages"][-1].pretty_print()
