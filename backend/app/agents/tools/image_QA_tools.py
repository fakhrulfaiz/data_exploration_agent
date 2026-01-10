"""
Image Question Answering tools for the explainable agents.
Refactored to process images directly from the Redis DataFrame.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Annotated

from langchain.tools import BaseTool
from pydantic import Field
from langgraph.prebuilt import InjectedState
from langchain_core.tools import InjectedToolCallId
import torch
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
from app.services.redis_dataframe_service import get_redis_dataframe_service

logger = logging.getLogger(__name__)

# Resource path handling
def _get_resource_path(img_path: str) -> Path:
    """Resolve local image path relative to backend resources."""
    # Assuming img_path is like "images/img_0.jpg"
    # And resources are at backend/app/resource/
    
    current_dir = Path(__file__).resolve().parent # backend/app/agents/tools
    resource_dir = current_dir.parent.parent / "resource" # backend/app/resource
    
    return resource_dir / img_path

class VisualQA:
    """BLIP VQA model - loads immediately at module import."""
    _instance = None
    _model = None
    _processor = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VisualQA, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Model is already loaded at module import, just assign references
        self.processor = VisualQA._processor
        self.model = VisualQA._model
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def answer_question(self, img_path: str, question: str) -> str:
        try:
            full_path = _get_resource_path(img_path)
            if not full_path.exists():
                return "Image not found"
                
            raw_image = Image.open(full_path).convert('RGB')
            
            inputs = self.processor(raw_image, question, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                out = self.model.generate(**inputs, max_length=50)
                
            return self.processor.decode(out[0], skip_special_tokens=True)
        except Exception as e:
            logger.error(f"Error processing image {img_path}: {e}")
            return f"Error: {str(e)}"

class ImageBatchQATool(BaseTool):
    """
    Tool that runs Visual QA on all images in the current DataFrame and adds the results as a new column.
    """
    
    name: str = "image_batch_qa_tool"
    description: str = """Use this tool to extract visual information from images listed in the current DataFrame.
    
    Prerequisites:
    - A DataFrame must be available (from previous SQL tool).
    - The DataFrame MUST contain an 'img_path' column (e.g. 'images/img_0.jpg').
    
    What it does:
    1. Iterates through every row in the DataFrame.
    2. Opens the image found at 'img_path'.
    3. Asks the 'question' to the vision model (BLIP).
    4. Stores the answer in a new column specified by 'output_column'.
    5. Updates the DataFrame in memory (Redis) so subsequent tools can use this new data.
    
    Parameters:
    - question (str): The visual question to ask (e.g. "What is the main subject?", "Is there a river?").
    - output_column (str): The name of the new column to store results (e.g. "main_subject", "has_river").
    
    Returns:
    - Summary of the operation (success count, column name added).
    
    IMPORTANT for Visualization:
    - For visualizing the results (e.g. YES/NO counts, categorical distributions), ALWAYS use 'large_plotting_tool'.
    - Do NOT use 'smart_transform_for_viz' for Image QA results as it handles categorical data poorly.
    """
    
    def _run(
        self,
        question: str,
        output_column: str,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        
        logger.info(f"ImageBatchQATool called with question: '{question}', output_column: '{output_column}'")
        
        if state is None:
            state = {}
            
        # 1. GET DATAFRAME FROM REDIS
        data_context = state.get("data_context")
        if not data_context or not data_context.df_id:
            logger.error("No DataFrame available in state")
            return json.dumps({
                "error": "No DataFrame available. Please run a SQL query first.",
                "error_type": "resource_not_found",
                "recoverable": False
            })
            
        logger.info(f"Retrieved data_context with df_id: {data_context.df_id}")
        
        redis_service = get_redis_dataframe_service()
        df = redis_service.get_dataframe(data_context.df_id)
        
        if df is None:
            logger.error(f"DataFrame {data_context.df_id} not found in Redis")
            return json.dumps({
                "error": "DataFrame not found or expired.",
                "error_type": "resource_not_found",
                "recoverable": True
            })
            
        logger.info(f"Loaded DataFrame with shape: {df.shape}, columns: {list(df.columns)}")
        
        # 2. VALIDATE IMG_PATH
        if "img_path" not in df.columns:
            logger.error(f"DataFrame missing 'img_path' column. Available columns: {list(df.columns)}")
            return json.dumps({
                "error": "DataFrame does not contain 'img_path' column. Query must include image paths.",
                "error_type": "validation_error",
                "recoverable": False
            })

        # 3. INITIALIZE VQA (Lazy)
        try:
            logger.info("Initializing BLIP VQA model...")
            vqa = VisualQA()
            logger.info("BLIP VQA model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to load BLIP VQA model: {e}", exc_info=True)
            return json.dumps({
                "error": f"Failed to load Vision Model: {e}",
                "error_type": "system_error",
                "recoverable": False
            })

        # 4. PROCESS IMAGES
        logger.info(f"Processing {len(df)} images for question: '{question}'...")
        
        results = []
        success_count = 0
        error_count = 0
        
        for index, row in df.iterrows():
            img_path = row.get("img_path")
            if not img_path:
                logger.warning(f"Row {index}: Missing img_path")
                results.append(None)
                continue
                
            logger.debug(f"Processing image {index + 1}/{len(df)}: {img_path}")
            answer = vqa.answer_question(str(img_path), question)
            results.append(answer)
            
            if "Error" not in answer and "Image not found" not in answer:
                success_count += 1
                logger.debug(f"Row {index}: Success - {answer}")
            else:
                error_count += 1
                logger.warning(f"Row {index}: Failed - {answer}")
                
        logger.info(f"Image processing complete. Success: {success_count}, Errors: {error_count}")
                
        # 5. UPDATE DATAFRAME IN REDIS
        df[output_column] = results
        logger.info(f"Added new column '{output_column}' to DataFrame")
        
        # Update the DataFrame in Redis (preserves the same df_id)
        if not redis_service.update_dataframe(df, data_context.df_id):
            return json.dumps({
                "error": "Failed to update DataFrame in Redis",
                "error_type": "storage_error",
                "recoverable": True
            })
        
        redis_service.extend_ttl(data_context.df_id)
        logger.info(f"Updated DataFrame saved to Redis with ID: {data_context.df_id}")
        
        
        
        result_message = f"""Image Analysis Complete.
- Question: "{question}"
- Target Column: "{output_column}"
- Processed Rows: {len(df)}
- Successful Analyses: {success_count}
- Failed Analyses: {error_count}

The DataFrame has been updated. You can now use tools like data_plotting_tool or smart_transform_for_viz on the new column '{output_column}'."""
        
        logger.info(f"ImageBatchQATool completed successfully")
        
        # Return structured output with data preview for frontend table display
        import json
        return json.dumps({
            "status": "success", 
            "description": result_message,
            "data_preview": df.head(5).to_dict(orient='records'),
            "row_count": len(df),
            # Include data_context to align with SQL tool if needed, but main_agent handles context from state usually. 
            # We'll just provide the preview.
        }, default=str)

    async def _arun(self, question: str, output_column: str, state: Annotated[Dict[str, Any], InjectedState] = None, tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None) -> str:
        """Run the tool asynchronously by offloading to a thread pool."""
        import asyncio
        import functools
        
        loop = asyncio.get_running_loop()

        func = functools.partial(self._run, question, output_column, state, tool_call_id)
        return await loop.run_in_executor(None, func)


# ============================================================================
# EAGER MODEL LOADING - Load BLIP model immediately at module import
# ============================================================================

logger.info("Loading BLIP VQA model at startup (this may take 10-30 seconds on first run)...")
try:
    VisualQA._processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
    VisualQA._model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
    
    if torch.cuda.is_available():
        VisualQA._model.to("cuda")
        logger.info("BLIP VQA model loaded on CUDA and ready to use")
    else:
        logger.info("BLIP VQA model loaded on CPU and ready to use")
except Exception as e:
    logger.error(f"Failed to load BLIP VQA model: {e}")
    logger.warning("Image QA tool will not be available")
