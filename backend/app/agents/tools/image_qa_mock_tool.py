"""Image QA Tool - Answer questions about images using vision-language models."""

from langchain_core.tools import tool
from typing import Optional


@tool
def image_qa_mock(
    image_url: str,
    question: str,
    context: Optional[str] = None,
    max_tokens: Optional[int] = 100
) -> str:
    """
    Answer questions about images using advanced vision-language models.
    
    This tool analyzes images and answers natural language questions about their content.
    It can identify objects, read text, describe scenes, count items, and understand
    visual relationships. Useful for extracting information from image.
    
    Use this when you need to:
    - Analyze image content or extract visual information
    - Answer questions about what's shown in an image
    - Read text or numbers from images (OCR)
    - Identify objects, people, or scenes in photos
    - Understand charts, graphs, or diagrams
    
    Args:
        image_url: URL or file path to the image to analyze
        question: The question to ask about the image (e.g., "What objects are in this image?")
        context: Optional additional context to help answer the question
        max_tokens: Maximum length of the response (default: 100)
    
    Returns:
        A detailed answer to the question based on the image content
    """
    return f"""TEST SUCCESS - Image QA Mock Tool

Image URL: {image_url}
Question: {question}
Context: {context or 'None provided'}
Max Tokens: {max_tokens}

This is a mock response. In a real implementation, this would analyze the image and answer the question.
"""
