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
import pandas as pd
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
from app.services.redis_dataframe_service import get_redis_dataframe_service

Image.MAX_IMAGE_PIXELS = 300000000

logger = logging.getLogger(__name__)

# Error sentinel constants for clean error reporting
ERROR_NOT_FOUND = "ERROR_NOT_FOUND"
ERROR_TOO_LARGE = "ERROR_TOO_LARGE"
ERROR_PROCESSING = "ERROR_PROCESSING"
ERROR_SENTINELS = {ERROR_NOT_FOUND, ERROR_TOO_LARGE, ERROR_PROCESSING}

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
                logger.warning(f"Image not found: {img_path}")
                return ERROR_NOT_FOUND
                
            raw_image = Image.open(full_path).convert('RGB')
            
            inputs = self.processor(raw_image, question, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                out = self.model.generate(**inputs, max_length=50)
                
            return self.processor.decode(out[0], skip_special_tokens=True)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing image {img_path}: {error_msg}")
            
            # Categorize errors for cleaner output
            if "decompression bomb" in error_msg.lower() or "image size" in error_msg.lower():
                return ERROR_TOO_LARGE
            else:
                return ERROR_PROCESSING

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
    
    Error Codes (stored in output column when processing fails):
    - ERROR_NOT_FOUND: Image file does not exist
    - ERROR_TOO_LARGE: Image exceeds size limits (decompression bomb protection)
    - ERROR_PROCESSING: Other processing errors (corrupted file, unsupported format, etc.)
    
    Returns:
    - Summary of the operation (success count, error breakdown, column name added).
    
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
                "tool_name": "image_batch_qa_tool",
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
                "tool_name": "image_batch_qa_tool",
                "recoverable": True
            })
            
        logger.info(f"Loaded DataFrame with shape: {df.shape}, columns: {list(df.columns)}")
        
        # 2. VALIDATE IMG_PATH
        if "img_path" not in df.columns:
            logger.error(f"DataFrame missing 'img_path' column. Available columns: {list(df.columns)}")
            return json.dumps({
                "error": "DataFrame does not contain 'img_path' column. Query must include image paths.",
                "error_type": "validation_error",
                "tool_name": "image_batch_qa_tool",
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
                "tool_name": "image_batch_qa_tool",
                "recoverable": False
            })

        # 4. CHECK IF COLUMN EXISTS 
        column_exists = output_column in df.columns
        if column_exists:
            # Initialize results with existing values
            results = df[output_column].tolist()
            # Count existing successes
            existing_success = sum(1 for val in results if val not in ERROR_SENTINELS and pd.notna(val))
        else:
            results = [None] * len(df) 
        
        # 5. PROCESS IMAGES (only errors if column exists, otherwise all)
        success_count = 0
        error_count = 0
        processed_count = 0
        skipped_count = 0
        
        for index, row in df.iterrows():
            if column_exists:
                existing_value = results[index]
                if existing_value not in ERROR_SENTINELS and pd.notna(existing_value):
                    success_count += 1
                    skipped_count += 1
                    continue
            
            img_path = row.get("img_path")
            if not img_path:
                results[index] = ERROR_PROCESSING
                error_count += 1
                continue
                
            answer = vqa.answer_question(str(img_path), question)
            results[index] = answer
            processed_count += 1
            
            if answer not in ERROR_SENTINELS:
                success_count += 1
                logger.debug(f"Row {index}: Success - {answer}")
            else:
                error_count += 1
                logger.warning(f"Row {index}: {answer} - {img_path}")
        
        if column_exists:
            logger.info(f"Retry complete. Processed: {processed_count}, Skipped: {skipped_count}, Success: {success_count}, Errors: {error_count}")
        else:
            logger.info(f"Image processing complete. Success: {success_count}, Errors: {error_count}")
                
        # 6. UPDATE DATAFRAME IN REDIS
        # CRITICAL FIX for Parallel Execution:
        # Re-fetch the latest DataFrame from Redis to ensure we don't overwrite changes made by other parallel tools.
        latest_df = redis_service.get_dataframe(data_context.df_id)
        
        df_to_save = df
        if latest_df is not None and len(latest_df) == len(df):
            # Safe to merge
            logger.info("Merging new column into latest DataFrame version to prevent race conditions")
            # We assume row order hasn't changed since tools generally don't sort in-place and save
            latest_df[output_column] = results
            df_to_save = latest_df
        else:
            # Fallback if latest is gone or size/index mismatch
            logger.warning("Latest DataFrame not found or size mismatch during merge. Overwriting with local version.")
            df[output_column] = results
            
        if column_exists:
            logger.info(f"Updated column '{output_column}' in DataFrame (reprocessed errors only)")
        else:
            logger.info(f"Added new column '{output_column}' to DataFrame")
        
        # Update the DataFrame in Redis (preserves the same df_id)
        if not redis_service.update_dataframe(df_to_save, data_context.df_id):
            return json.dumps({
                "error": "Failed to update DataFrame in Redis",
                "error_type": "storage_error",
                "tool_name": "image_batch_qa_tool",
                "recoverable": True
            })
        
        redis_service.extend_ttl(data_context.df_id)
        logger.info(f"Updated DataFrame saved to Redis with ID: {data_context.df_id}")
        
        
        
        # Build error breakdown if there are failures
        error_breakdown = ""
        if error_count > 0:
            error_counts = df[output_column].value_counts()
            error_items = [f"  - {err}: {error_counts.get(err, 0)}" for err in ERROR_SENTINELS if err in error_counts]
            if error_items:
                error_breakdown = "\n\nError breakdown:\n" + "\n".join(error_items)
        
        # Build result message
        if column_exists and skipped_count > 0:
            result_message = f"""Image Analysis Complete (Retry).
- Question: "{question}"
- Target Column: "{output_column}"
- Total Rows: {len(df)}
- Reprocessed: {processed_count} (errors only)
- Skipped: {skipped_count} (already successful)
- Successful Analyses: {success_count}
- Failed Analyses: {error_count}{error_breakdown}

The DataFrame has been updated. Only rows with errors were reprocessed.
Note: Rows with errors are marked as {', '.join(ERROR_SENTINELS)}."""
        else:
            result_message = f"""Image Analysis Complete.
- Question: "{question}"
- Target Column: "{output_column}"
- Processed Rows: {len(df)}
- Successful Analyses: {success_count}
- Failed Analyses: {error_count}{error_breakdown}

The DataFrame has been updated. You can now use tools like large_plotting_tool on the new column '{output_column}'.
Note: Rows with errors are marked as {', '.join(ERROR_SENTINELS)}."""
        
        logger.info(f"ImageBatchQATool completed successfully")
        
        # Return structured output with data preview for frontend table display
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
