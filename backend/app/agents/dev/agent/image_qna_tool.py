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
    
    @tool("image_qna_tool", description="Use this tool when you want to answer questions that needs visual information from an image. The image should be a URL or a local file path.")
    def image_qna_tool(img_url: str, question: str) -> str:
        """
        Use this tool when you want to answer questions about an image. The image should be a URL or a local file path.
        
        Args:
            img_url: The URL/URI or path of the image
            question: The question to answer about the image
            
        Returns:
            The answer to the question.
        """
        image = _load_image(str(img_url))  # error handling for image loading error in `urlparse()` in load_image()

        inputs = processor(image, question, return_tensors="pt")

        with torch.no_grad():
            output_ids = model.generate(**inputs)

        answer = processor.decode(output_ids[0], skip_special_tokens=True)
        return answer
    
    return image_qna_tool



