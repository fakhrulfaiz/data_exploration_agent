"""
Image Question Answering tools for the explainable agents.

"""

import ast
import logging
import re
from typing import Any, List, Union

from langchain.tools import BaseTool
from pydantic import Field



logger = logging.getLogger(__name__)

# PATH for docker
IMAGE_PATH = "/app/app/resource/"

class ImageQATool(BaseTool):
    """Image Question Answering tool."""
    
    # Need to specify specific name and description for each tool
    name : str= "image_analysis"
    description : str = """Analyze an image and answer a question based on its visual content.

Use this tool to:
- Analyze a single image and answer a question about what is depicted
- Detect the presence of objects, scenes, or attributes in an image
- Count objects or identify visual elements (foreground, background, etc.)
- Perform comparisons after each individual image analysis

Parameters:
- question (str): A question that targets exactly one image (e.g., “Is object <X> present?”, “How many <X> appear?”, “Does the image depict <Y>?”)
- context (str or List[str]): Context from previous agent actions to support image analysis.
    The context must include image paths in the following format:
    [{ 'img_path': 'xxxx' }, { 'img_path': 'yyyy' }, { 'img_path': 'zzzz' }, ...]
    For a single image:
    [{ 'img_path': 'images/img_0.jpg' }]
    If multiple contexts are required, they may be provided as a list of strings.

Returns: A textual answer derived from analyzing the image content

Notes:
- Minimize the number of image_analysis actions whenever possible
- The image_analysis action cannot access outputs of previous actions unless they are explicitly provided as context
- Outputs from other actions must be passed through context if they are required for image analysis
- Outputs from text2SQL actions must never be included in the question parameter
- Since text2SQL returns unstructured text, its output must be processed and passed via context so the required image_id can be extracted
"""

    vqa : Any = Field(description="Visual Question Answering model Instance to answer questions about images.")

    def _run(self, question: str, context: Union[str, List[str]]):

        ### Why does this take the str/ list and change it to dict. We will process the later tasks in list
        # if isinstance(context, str):
        #     context=correct_malformed_json(context)
            
        #     context = [ast.literal_eval(context)]
            
        #     # reshape for common LLM halucination
        #     if 'status' in context[0]:
        #         context=context[0]
        # else:
        #     context = ast.literal_eval(context[0])
        
        # # reshape for common LLM halucination
        # if 'data' in context:
        #     context = context['data'] # type: ignore

        # Ensure context is a list
        if not isinstance(context, list):
            context = [context]
        
        # Use VQA model to answer question
        try:
            # Initialize VQA model (This method is slow as we initialized the model everytime we are calling it, consider initializing it elsewhere and passing it in)
            # vqa = VisualQA() unused as we are passing it in

            vqa_answers = []
            image_paths = [f'{IMAGE_PATH}{ctx["img_path"]}' for ctx in context]# type: ignore # add later, append with base IMAGE_PATH

            # Looping the question for all images
            answers = self.vqa.answer_questions(image_paths, question)

            for ctx, ans in zip(context, answers):
                ctx['question_answer'] = ans # type: ignore
                vqa_answers.append(ctx) 

            return vqa_answers
        
        except Exception as e:
            logger.error(f"Error in image_analysis: {e}")
            return f"Error in image_analysis: {e}"


def correct_malformed_json(malformed_json_string: str) -> str:
    # Step 1: Replace escaped quotes with actual quotes
    corrected_json_string = malformed_json_string.replace('\\"', '"')
    
    # Step 2: Ensure all keys and values are properly quoted
    # This regular expression will find unquoted strings and put quotes around them
    # It skips already quoted values and datetime formats
    def quote_value(match):
        value = match.group(1)
        if not re.match(r'^".*"$', value) and not re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', value):
            value = f'"{value}"'
        return f':{value}'

    corrected_json_string = re.sub(r':(\w+)', quote_value, corrected_json_string)
    
    # Step 3: Handle duplicate keys by making them unique
    # Use a set to track seen keys and a counter for making keys unique
    seen_keys = set()
    def make_unique(match):
        key = match.group(1)
        if key in seen_keys:
            counter = 2
            new_key = f"{key}{counter}"
            while new_key in seen_keys:
                counter += 1
                new_key = f"{key}{counter}"
            key = new_key
        seen_keys.add(key)
        return f'"{key}"'
    
    corrected_json_string = re.sub(r'"(\w+)"(?=:)', make_unique, corrected_json_string)
    
    # Step 4: Add missing closing brace if needed
    if corrected_json_string.count('{') > corrected_json_string.count('}'):
        corrected_json_string += '}'
    
    return corrected_json_string



