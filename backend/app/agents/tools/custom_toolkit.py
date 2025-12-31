"""
Custom toolkit for the explainable agent project.
Automatically passes LLM instance and database engine to custom tools.
"""

from langchain.agents.agent_toolkits.base import BaseToolkit
from langchain.tools import BaseTool
from typing import List, Any, Optional
from pydantic import Field
from .visualization_tools import SmartTransformForVizTool, LargePlottingTool
from .data_analysis_tools import SecurePythonREPLTool, DataFrameInfoTool
from .image_QA_tools import ImageQATool
from .data_exploration_agent_tool import DataExplorationAgentTool


class CustomToolkit(BaseToolkit):
    llm: Any = Field(description="Language model instance")
    db_engine: Optional[Any] = Field(default=None, description="Database engine for SQL execution")
    db_path: Optional[str] = Field(default=None, description="Path to SQLite database")
    
    def __init__(self, llm: Any, db_engine: Any = None, db_path: str = None, **kwargs):
        super().__init__(llm=llm, db_engine=db_engine, db_path=db_path, **kwargs)
    
    def get_tools(self) -> List[BaseTool]:
        vqa = VisualQA()
        tools = [
            SmartTransformForVizTool(llm=self.llm),
            SecurePythonREPLTool(),
            DataFrameInfoTool(),
            ImageQATool(vqa=vqa) # consider initialize with LLM and pass as class attribute
        ]
        
        if self.db_engine is not None:
            tools.append(LargePlottingTool(llm=self.llm))
            
            if self.db_path is not None:
                tools.append(DataExplorationAgentTool(
                    llm=self.llm,
                    db_engine=self.db_engine,
                    db_path=self.db_path
                ))
        
        return tools
    
# Using Blip for VQA model
# Put this here to initialize one for now.
from contextlib import ExitStack
from PIL import Image

from transformers.models.blip import BlipForQuestionAnswering, BlipProcessor

class VisualQA():
    _instance = None
    _model = None
    _processor = None
    
    def __new__(cls, model_name: str = "Salesforce/blip-vqa-base"):
        if cls._instance is None:
            cls._instance = super(VisualQA, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, model_name: str = "Salesforce/blip-vqa-base"):
        # Only load model once (singleton pattern)
        if VisualQA._model is None:
            print("Loading VisualQA model (first time only)...")
            # `Salesforce/blip-vqa-capfilt-large` has better performance but i dont have enough storage/ resource 
            VisualQA._model = BlipForQuestionAnswering.from_pretrained(model_name)
            VisualQA._processor = BlipProcessor.from_pretrained(model_name)
            print("✅ VisualQA model loaded and cached")
        
        self.model = VisualQA._model
        self.processor = VisualQA._processor

    def answer_questions(self, image_paths: List[str], query: str, batch_size: int = 10):
        results = []
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i : i + batch_size]
            with ExitStack() as stack:
                images = [stack.enter_context(Image.open(image_path)) for image_path in batch_paths]
                queries = [query] * len(images)
                inputs = self.processor(
                    images=images, 
                    text=queries, 
                    return_tensors="pt",  # type: ignore
                    padding=True) # type: ignore
                outputs = self.model.generate(**inputs, max_length=20) # type: ignore

                # results.extend([self.processor.decode(o, skip_special_tokens=True) for o in outputs])
                decoded_outputs = self.processor.batch_decode(outputs, skip_special_tokens=True)
                results.extend(decoded_outputs) # type: ignore
        return results
