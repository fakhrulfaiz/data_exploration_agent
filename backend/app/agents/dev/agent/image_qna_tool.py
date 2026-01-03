# Need to handle http error from the requests.get() 

## current error is from the page rejecting the request as we dont have a user agent or authorization

import os
import torch
import requests
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
from langchain.tools import tool
from langgraph.types import Command


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
    def image_qna_tool(img_url: str, question: str):
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
        # return answer
        return Command(
            update={
                "messages": [f"Analysis for {img_url}: {answer}"],
                "image_analysis_history": [f"Image: {img_url} | Q: {question} | A: {answer}"]
            }
        )
    
    return image_qna_tool


# import os
# from langchain.chat_models import init_chat_model
# from dotenv import load_dotenv

# # Load from env
# load_dotenv()

# model = init_chat_model("gpt-4o-mini")

# image_qna_tool = build_image_qna_tool()
# tools = [image_qna_tool]

# from langchain_core.messages import ToolMessage
# from langgraph.graph import StateGraph, START, END, MessagesState
# from langgraph.prebuilt import ToolNode, tools_condition
# from typing_extensions import TypedDict, Annotated
# from langgraph.graph.message import add_messages
# import operator

# # Define state right here
# class ImageAnalysisState(MessagesState):
#     analysis_history: Annotated[list[str], operator.add]

# def build_image_analysis_agent():
#     """
#     Build and initialize the image analysis agent for the tools pipeline.
    
#     Returns:
#         The image_analysis_agent LangChain agent ready for use in an agent.
#     """
#     # Nodes

#     system_prompt = "You are an image analysis agent. Your job is to answer questions about images. You have a tool called `image_qna_tool` that you can use to answer questions about images. You can only use this tool if the user asks a question that requires visual information from an image."

#     def agent_node(state: ImageAnalysisState):
#         return {"messages": [model.bind_tools(tools).invoke(state["messages"])]}

#     builder = StateGraph(ImageAnalysisState)
#     builder.add_node("agent", agent_node)
#     builder.add_node("tools", ToolNode(tools))  # Handles parallel automatically!

#     builder.add_edge(START, "agent")
#     builder.add_conditional_edges("agent", tools_condition)  # Parallel if tool_calls
#     builder.add_edge("tools", "agent")

#     return builder.compile()


