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
    
    @tool("image_qna_tool", description="Use this tool when you want to answer questions that needs visual information from an image. This tool only works with image path. Example path = `images/img_0.jpg`")
    def image_qna_tool(img_url: str, question: str, runtime: ToolRuntime, tool_call_id: Annotated[str, InjectedToolCallId]):
        """
        Use this tool when you want to answer questions about an image. The image should be a local file path. Example path = `images/img_0.jpg`
        
        Args:
            img_url: The path of the image. Example path = `images/img_0.jpg`
            question: The question to answer about the image
            
        Returns:
            The answer to the question.
        """
        image = _load_image(str(img_url))  # error handling for image loading error in `urlparse()` in load_image()

        inputs = processor(image, question, return_tensors="pt")

        with torch.no_grad():
            output_ids = model.generate(**inputs)

        answer = processor.decode(output_ids[0], skip_special_tokens=True)

        # Get tool call id
        tool_call_id = runtime.tool_call_id


        # Create Tool Message for Command 
        tool_message = ToolMessage(
            content=f"Answered question ({question}) about image {img_url}: {answer}",
            tool_call_id=tool_call_id,
        )

        # return answer
        return Command(
            update={
                "messages": [tool_message],
                "image_analysis_history": [f"Image: {img_url} | Q: {question} | A: {answer}"]
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
    image_analysis_history: Annotated[list[str], operator.add]

# Custom Output state for data exploration
class ImageAnalysisOutput(BaseModel):
    """Output state for data exploration"""
    task: str = Field(..., description="The overall tasks to accomplish.")
    total_run_needed: int = Field(..., description="The total number of unique tool runs needed to accomplish the task.")
    completed_run: int = Field(..., description="The number of unique tool runs that has been completed.")
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
        tool_run_history = json.dumps(state["image_analysis_history"])
        final_message = AIMessage(content=f"Run history: {tool_run_history}")
        
        return {"messages": [final_message]}

# make custom tool_condition
def image_qna_tool_condition(state: ImageAnalysisState) -> Literal["tools", "evaluator"]:
    last_message = state["messages"][-1]
    # check for tool_calls from agent
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "evaluator"

def build_image_qna_agent():
    
    # 2. Define the agent node properly
    def agent_node(state: ImageAnalysisState):
        system_prompt = (
            "You are an image analysis agent. Your job is to answer questions about images. "
            "You have a tool called `image_qna_tool`. Use it for visual questions. "
            "Aggregate history to provide a final answer."
        )
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

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        image_qna_tool_condition,
        ["tools", "evaluator"],
        )
    builder.add_edge("tools", "agent")
    builder.add_edge("evaluator", END)

    return builder.compile()


