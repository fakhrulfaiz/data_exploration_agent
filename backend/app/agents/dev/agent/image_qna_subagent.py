# Need to handle http error from the requests.get() 

## current error is from the page rejecting the request as we dont have a user agent or authorization

import json
import os
from typing import Literal
from pydantic import BaseModel, Field
import torch
import requests
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import ToolRuntime
from langchain_core.tools import InjectedToolCallId
from langchain.tools import tool
from langgraph.types import Command
from typing_extensions import Annotated


def _load_image(img_url: str) -> Image.Image:
    """
    Load an image from:
    - http/https URL
    - local file path
    - file:// URI
    """
    # As we are in a static development environment, hard code the path
    base_path = "/home/afiq/fyp/fafa-repo/backend/app/resource/"
    img_url = base_path + img_url
    parsed = urlparse(img_url)

    # Remote URL
    if parsed.scheme in ("http", "https"):
        response = requests.get(img_url, stream=True)
        response.raise_for_status()
        return Image.open(response.raw).convert("RGB")

    # file:// URI
    if parsed.scheme == "file":
        path = parsed.path
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        return Image.open(path).convert("RGB")

    # Local path (no scheme)
    if os.path.exists(img_url):
        return Image.open(img_url).convert("RGB")

    raise ValueError(f"Unsupported image URL or path: {img_url}")


def build_image_qna_tool():
    """
    Build and initialize the image QnA tool for the tools pipeline.
    
    Returns:
        The image_qna_tool LangChain tool ready for use in an agent.
    """
    # Initialize model
    processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
    model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
    
    @tool("image_qna_tool")
    def image_qna_tool(img_url: str, query: str, runtime: ToolRuntime, tool_call_id: Annotated[str, InjectedToolCallId]):
        """
        Directly extracts visual data from an image for database entry.
        
        Args:
            img_url: Path or URL to the image. Example path = `images/img_0.jpg`
            query: A non-conversational, imperative string describing 
                            the data to extract. 
                            BAD: "Can you tell me what is in this?"
                            GOOD: "detailed list of objects, color palette, and scene composition"
            
        Returns:
            The result.
        """
        image = _load_image(str(img_url))  # error handling for image loading error in `urlparse()` in load_image()

        inputs = processor(image, query, return_tensors="pt")

        with torch.no_grad():
            output_ids = model.generate(**inputs)

        answer = processor.decode(output_ids[0], skip_special_tokens=True)

        # Get tool call id
        tool_call_id = runtime.tool_call_id


        # Create Tool Message for Command 
        tool_message = ToolMessage(
            content=f"Answered question ({query}) about image {img_url}: {answer}",
            tool_call_id=tool_call_id,
        )

        # return answer
        return Command(
            update={
                "messages": [tool_message],
                "image_analysis_history": [f"Image: {img_url} | Q: {query} | A: {answer}"]
            }
        )
    
    return image_qna_tool

import os
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

# Load from env
load_dotenv()

model = init_chat_model("gpt-4o-mini")

image_qna_tool = build_image_qna_tool()
tools = [image_qna_tool]

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages
import operator
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import ToolMessage, AIMessage

# Define state right here
class ImageAnalysisState(MessagesState):
#     image_analysis_history: Annotated[list[str], operator.add]
    tools_complete: bool = Field(default=False, description="Whether all tool runs is accomplished as a whole with utmost completion.")

# Custom Output state for data exploration
class ImageAnalysisOutput(BaseModel):
    """Output state for data exploration"""
    task: str = Field(..., description="The overall tasks to accomplish.")
    task_complete: bool = Field(..., description="Whether the overall task and all tool runs is accomplished as a whole with utmost completion.")
    storing_instruction: str = Field(..., description="A detailed instruction to store the final answer in a csv file in a way that are extractable and easy to plot into a graph. The instruction should include the table name and column name to store the answer. The instruction should include the final answer in the value to be stored.")
    error: bool = Field(..., description="Whether there is an error. Incomplete tool runs are not considered errors.")
    error_message: str = Field(..., description="useful message that helps to request more context to overcome the error.")

# make an evaluator node
def evaluator_node(state: ImageAnalysisState):

    last_message = state["messages"][-1]

    # if last message is tool message, skip
    if isinstance(last_message, ToolMessage):
        return {}
    
    # evaluator llm
    evaluator = model.with_structured_output(ImageAnalysisOutput)
    system_message = SystemMessage(content="You are an evaluator. Your job is to evaluate the task and determine if the task is accomplished. If not, return the error message.")
    
    evaluation: ImageAnalysisOutput | None = None
    # if last message is AIMessage, evaluate
    if isinstance(last_message, AIMessage):
        # first_message = state["messages"][1] # not system message
        # messages_for_llm = [system_message] + [first_message, last_message]
        evaluation : ImageAnalysisOutput = evaluator.invoke([system_message] + state["messages"])

    if evaluation.error :
        return Command(goto=END, graph=Command.PARENT, update={"current_step": 0, "feedback": f"final tool execution result: {evaluation.error_message}"})
    
    else:
        # tool_run_history = json.dumps(state["image_analysis_history"])
        aim = evaluation.task
        workspace_dir = "/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace"
        prompt_to_store = f"Main Task: {aim}. Based on the conversation history, extract and congest all the answer into a final answer. Store the final answer in a csv file in these path{workspace_dir}. Example: `{workspace_dir}/data/total_animals_per_genre.csv`. HINT:{evaluation.storing_instruction} "
        storing_message = AIMessage(content=prompt_to_store)

        return Command(goto="update_workspace", update={"messages": [storing_message], "tools_complete": evaluation.task_complete})
        # return {"messages": [storing_message]}

from data_plotting_tool import PythonREPL, CodeGeneratorOutput
def update_workspace(state: ImageAnalysisState):
    """Save the latest query result to CSV file."""
    
    last_message = state["messages"][-1]
    workspace_helper = model.with_structured_output(CodeGeneratorOutput)
    workspace_details: CodeGeneratorOutput = workspace_helper.invoke(state["messages"])

    python_repl = PythonREPL()
    
    if workspace_details.code == "":
        output_message = AIMessage(
            content=f"Code generation for data storing from image_qna_agent failed. Reason: {workspace_details.reasoning}",
        )
        return Command(
            goto="interrupt_for_replan", 
            graph=Command.PARENT, 
            update={"messages": [output_message], "feedback": workspace_details.reasoning}
        )

    else:
        # execute the code
        result = python_repl.run(workspace_details.code)
        # check for error
        if "Error" in result:
            output_message = AIMessage(
                content=f"Code generation for data storing from image_qna_agent failed. Reason: {workspace_details.reasoning}",
            )
            return Command(
                goto="interrupt_for_replan", 
                graph=Command.PARENT, 
                update={"messages": [output_message], "feedback": workspace_details.reasoning}
            )
        
        output_message = AIMessage(
            content=f"Code execution successful. Data succesfully stored in {workspace_details.file_name}",
            )
        return Command(
            update={
                "messages": [output_message],
            }
        )


# make custom tool_condition
def image_qna_tool_condition(state: ImageAnalysisState) -> Literal["tools", "evaluator", "agent"]:
    last_message = state["messages"][-1]
    # check for tool_calls from agent
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    # check if all tasks complete
    if state.get("tools_complete") == True:
        return "agent"
    
    return "evaluator"

def build_image_qna_agent():
    
    # 2. Define the agent node properly
    def agent_node(state: ImageAnalysisState):
        # system_prompt = (
        #     "You are an image analysis agent. Your job is to answer questions about images. Only answer questions that was asked and make sure to limit tool calls when possible. "
        #     "You have a tool called `image_qna_tool`. Use it for visual questions. "
        #     "Aggregate history of answers (only when you need to run multiple tool calls) to provide a final answer." 
        #     "All of your answer or aggregated answer(s) should be in table format."
        #     "You will also store the final answer in a csv file for plotting purpose automatically."
        #     "When you finish executing all tool needed for the main task and succesfully receive a message for succeful data storing, you should stop and give the final response to user."
        # )
        system_prompt = """
Role: Expert Visual Data Analyst & Aggregator

Objective: You are a specialized agent designed to transform raw images into structured data. You use the image_qna_tool as a feature extractor—not a chatbot—to populate a tabular dataset for CSV export.

1. Tool Execution Protocol (Critical)
When using image_qna_tool, you must adhere to the Extraction-Query format to avoid one-word or conversational failures:

Forbidden: "Can you see...", "Is there...", "Please describe...", "What is...?"

Mandatory: Use direct, imperative nouns and descriptors.

Examples of Correct Queries:

Subject Identification: "main subjects and primary focus of the image"

Attribute Extraction: "colors, textures, and artistic style of the painting"

Detailed Scan: "comprehensive list of background elements and environmental context"

2. Task Workflow
Plan: Identify all images in the sequence. Determine the specific attributes needed for the final table.

Extract: For each image, call image_qna_tool. If a general query returns insufficient data, perform a follow-up call with a more specific descriptor (e.g., "specific text or branding visible").

Synthesize: Maintain an internal state of all tool outputs. If a tool returns "no" or "unknown," label it as Data Not Found in your table.

3. Output & CSV Formatting
Your final response must be a Markdown Table. Once the table is rendered, ensure it is ready for CSV conversion by following these rules:

Column Headers: Image_ID, Primary_Objects, Detailed_Description, Confidence_Notes.

Data Integrity: Use semicolons (;) instead of commas within cells to prevent CSV parsing errors.

Final Step: After displaying the table, confirm if the user wants the raw string saved to the workspace via your save tool.
"""
        messages_for_llm = [SystemMessage(content=system_prompt)] + state["messages"]
        
        # Bind tools and invoke
        response = model.bind_tools(tools).invoke(messages_for_llm)
        
        # Return the response to be added to the state
        return {"messages": [response]}

    # 3. Build Graph
    builder = StateGraph(ImageAnalysisState)
    
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("evaluator", evaluator_node)
    builder.add_node("update_workspace", update_workspace)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        image_qna_tool_condition,
        ["tools", "evaluator"],
        )
    builder.add_edge("tools", "agent")
    builder.add_edge("evaluator", "update_workspace")

    return builder.compile()


