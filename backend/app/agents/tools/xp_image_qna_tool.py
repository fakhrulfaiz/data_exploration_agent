"""
XpAgent Image QnA Tool.
Wraps the image_qna_sub agent as a LangChain tool for XpAgent.
"""

import logging
import json
import re
import os
from typing import Any, Optional, List
from pathlib import Path
from pydantic import Field
from langchain.tools import BaseTool
from langchain_core.messages import HumanMessage, AIMessage
import pandas as pd

from app.services.dependencies import get_redis_dataframe_service
from app.schemas.chat import DataContext

logger = logging.getLogger(__name__)

# Workspace configuration - keep using dev workspace
WORKSPACE_PATH = Path("/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace")
OUTPUT_PATH = WORKSPACE_PATH / "outputs"


class XpImageQnATool(BaseTool):
    """Tool wrapper for image QnA subagent."""
    
    name: str = "image_qna_agent"
    description: str = """Analyze visual content of images using BLIP VQA model.
    
    CAPABILITIES:
    - Describe colors, subjects, objects, people, style, composition
    - Count items in images
    - Answer questions about image content
    - Batch processing of multiple images
    - GPU acceleration when available
    
    Parameters:
    - query (str): Question about the image(s)
    - img_path (list): List of local image paths (e.g., ['images/img_0.jpg'])
    
    IMPORTANT: 
    - Use img_path from database (NOT image_url)
    - First query database to get img_path values, then use this tool
    
    Returns: Analysis results for each image.
    """
    
    model_name: str = Field(default="gpt-4o-mini", description="LLM model to use")
    use_gpu: Optional[bool] = Field(default=None, description="GPU configuration")
    _agent: Any = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, model_name: str = "gpt-4o-mini", use_gpu: Optional[bool] = None, **kwargs):
        super().__init__(model_name=model_name, use_gpu=use_gpu, **kwargs)
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Lazy initialize the subagent."""
        try:
            from app.agents.dev.agent.image_qna_sub import build_image_qna_agent
            self._agent = build_image_qna_agent(
                model_name=self.model_name,
                use_gpu=self.use_gpu
            )
            logger.info(f"XpImageQnATool initialized with model {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize image QnA agent: {e}")
            raise
    
    def _extract_img_paths(self, query: str) -> List[str]:
        """Extract image paths from query string."""
        img_paths = []
        
        # Match patterns like images/img_0.jpg
        matches = re.findall(r'images/img_\d+\.jpg', query)
        img_paths.extend(matches)
        
        # Try to parse JSON arrays in query
        try:
            json_matches = re.findall(r'\[[\s\S]*?"images/img_\d+\.jpg"[\s\S]*?\]', query)
            for match in json_matches:
                parsed = json.loads(match)
                img_paths.extend([p for p in parsed if isinstance(p, str) and 'images/img_' in p])
        except:
            pass
        
        return list(set(img_paths))
    
    def _run(self, query: str, img_path: Optional[List[str]] = None) -> str:
        """Execute image QnA analysis."""
        try:
            logger.info(f"XpImageQnATool executing: {query[:100]}...")
            
            # Extract image paths if not provided
            if not img_path:
                img_path = self._extract_img_paths(query)
            
            if not img_path:
                return json.dumps({
                    "success": False,
                    "error": "No image paths provided. Please include img_path from database."
                })
            
            # Build full query with images
            full_query = f"{query}\n\nImages to analyze: {json.dumps(img_path)}"
            
            # Build proper initial state - must include all ImageAnalysisState fields
            initial_state = {
                "messages": [HumanMessage(content=full_query)],
                "original_task": query,
                "images_to_process": img_path,
                "images_processed": [],
                "analysis_records": [],
                "tools_complete": False,
                "error_occurred": False,
                "error_message": ""
            }
            
            # Invoke the subagent with complete initial state
            result_state = self._agent.invoke(
                initial_state,
                {"configurable": {"thread_id": f"xp_image_qna_{id(self)}"}}
            )
            
            # Extract result from messages
            result_content = ""
            for msg in reversed(result_state.get("messages", [])):
                if isinstance(msg, AIMessage):
                    content = msg.content
                    if isinstance(content, str):
                        result_content = content
                    elif isinstance(content, list):
                        result_content = " ".join(str(c) for c in content)
                    else:
                        result_content = str(content)
                    break
            
            # Check for CSV output
            csv_path = None
            if ".csv" in result_content:
                csv_match = re.search(r'([\S]+\.csv)', result_content)
                if csv_match:
                    csv_path = csv_match.group(1)
            
            # Store CSV DataFrame in Redis if file exists
            data_context = None
            if csv_path:
                # Resolve full path if relative
                if not os.path.isabs(csv_path):
                    full_csv_path = OUTPUT_PATH / os.path.basename(csv_path)
                else:
                    full_csv_path = Path(csv_path)
                
                if full_csv_path.exists():
                    try:
                        df = pd.read_csv(full_csv_path)
                        redis_service = get_redis_dataframe_service()
                        context_data = redis_service.store_dataframe(
                            df=df,
                            sql_query=None,
                            metadata={
                                "description": query,
                                "source": "xp_image_qna_tool",
                                "csv_file": str(full_csv_path),
                                "images_analyzed": img_path
                            }
                        )
                        
                        data_context = DataContext(
                            df_id=context_data["df_id"],
                            sql_query=context_data.get("sql_query"),
                            columns=context_data["columns"],
                            shape=context_data["shape"],
                            created_at=context_data["created_at"],
                            expires_at=context_data["expires_at"]
                        )
                        
                        logger.info(f"Stored image analysis CSV in Redis: {context_data['df_id']}")
                    except Exception as e:
                        logger.warning(f"Failed to store CSV in Redis: {e}")
            
            response = {
                "success": True,
                "result": result_content,
                "images_analyzed": img_path,
                "csv_file": csv_path
            }
            
            # Add data context if stored in Redis
            if data_context:
                response["data_context"] = data_context.model_dump(mode="json")
                response["df_id"] = data_context.df_id
            
            logger.info(f"XpImageQnATool completed. Analyzed {len(img_path)} images, df_id: {data_context.df_id if data_context else None}")
            return json.dumps(response, indent=2, default=str)
            
        except Exception as e:
            logger.error(f"XpImageQnATool error: {e}", exc_info=True)
            return json.dumps({
                "success": False,
                "error": str(e)
            })
    
    async def _arun(self, query: str, img_path: Optional[List[str]] = None) -> str:
        """Async version - falls back to sync."""
        return self._run(query, img_path)
