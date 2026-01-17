# image_qna_sub.py - Enhanced version with configurable LLM and GPU support

"""
Improvements over image_qna_subagent_v2.py:
1. Configurable LLM model name - pass any supported model via init_chat_model
2. GPU-aware image analysis tool with automatic device detection
3. Efficient batch processing with device placement optimization
4. Flexible model initialization throughout the graph

Key Features:
- State tracks: original_task, images_processed, analysis_history (structured)
- Tool properly updates state with structured data
- Evaluator has full context of what was analyzed
- Agent can synthesize from accumulated history
- GPU acceleration for BLIP model when available
- Configurable LLM backbone
"""

import json
import os
from pathlib import Path
from typing import Literal, List, Optional
from pydantic import BaseModel, Field
import torch
import requests
from urllib.parse import urlparse
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.types import Command
from typing_extensions import Annotated
import operator
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode


# ============================================================================
# PATH CONFIGURATION (works in Docker and local)
# ============================================================================

_CURRENT_DIR = Path(__file__).resolve().parent  # image_qna_sub.py location
_BACKEND_ROOT = _CURRENT_DIR.parent.parent.parent.parent  # Go up to backend/
_RESOURCE_PATH = _BACKEND_ROOT / "app" / "resource"

print(f"🖼️ image_qna_sub.py paths:")
print(f"   _CURRENT_DIR: {_CURRENT_DIR}")
print(f"   _BACKEND_ROOT: {_BACKEND_ROOT}")
print(f"   _RESOURCE_PATH: {_RESOURCE_PATH}")


# ============================================================================
# DEVICE AND GPU UTILITIES
# ============================================================================

def get_device():
    """Detect and return the best available device (CUDA > MPS > CPU)."""
    if torch.cuda.is_available():
        device = "cuda"
        gpu_info = f"CUDA (GPU: {torch.cuda.get_device_name(0)})"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        gpu_info = "MPS (Apple Silicon)"
    else:
        device = "cpu"
        gpu_info = "CPU (No GPU available)"
    
    return device, gpu_info


def get_memory_info():
    """Get GPU memory information if available."""
    if torch.cuda.is_available():
        total_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        reserved = torch.cuda.memory_reserved(0) / (1024**3)
        allocated = torch.cuda.memory_allocated(0) / (1024**3)
        return {
            "total_gb": round(total_memory, 2),
            "reserved_gb": round(reserved, 2),
            "allocated_gb": round(allocated, 2)
        }
    return None


# ============================================================================
# STRUCTURED DATA MODELS FOR BETTER TRACKING
# ============================================================================

class ImageAnalysisRecord(BaseModel):
    """A single image analysis record for tracking."""
    image_url: str = Field(..., description="The image URL/path that was analyzed")
    query: str = Field(..., description="The query asked about the image")
    answer: str = Field(..., description="The answer from the BLIP model")
    
    def to_string(self) -> str:
        return f"Image: {self.image_url} | Query: {self.query} | Answer: {self.answer}"


def merge_analysis_records(left: List[ImageAnalysisRecord], right: List[ImageAnalysisRecord]) -> List[ImageAnalysisRecord]:
    """Custom reducer for analysis records - appends new records."""
    return left + right


# ============================================================================
# IMPROVED STATE DEFINITION
# ============================================================================

class ImageAnalysisState(MessagesState):
    """
    Enhanced state that properly tracks:
    - Original task for context
    - All images processed
    - Structured analysis history for evaluator
    - Completion status
    """
    # Core task tracking
    original_task: str = Field(default="", description="The original task/query this subagent was asked to accomplish")
    
    # Analysis tracking (structured for better context)
    analysis_records: Annotated[List[ImageAnalysisRecord], merge_analysis_records] = Field(
        default_factory=list,
        description="Structured history of all image analyses performed"
    )
    
    # Images tracking
    images_to_process: List[str] = Field(default_factory=list, description="List of image URLs to process")
    images_processed: List[str] = Field(default_factory=list, description="List of images that have been processed")
    
    # Status tracking
    tools_complete: bool = Field(default=False, description="Whether all tool runs are accomplished")
    
    # Error tracking
    error_occurred: bool = Field(default=False, description="Whether an error occurred")
    error_message: str = Field(default="", description="Error message if any")


# ============================================================================
# OUTPUT SCHEMA FOR EVALUATOR
# ============================================================================

class ImageAnalysisOutput(BaseModel):
    """Structured output for evaluator to assess task completion."""
    task: str = Field(..., description="The original task that was requested")
    task_complete: bool = Field(..., description="Whether ALL required analyses are complete and ready for CSV export")
    
    # Data quality assessment
    data_quality_score: int = Field(
        ..., 
        ge=1, le=5,
        description="Quality score 1-5: 1=unusable, 3=acceptable, 5=excellent. Based on answer completeness."
    )
    
    # CSV preparation guidance
    storing_instruction: str = Field(
        ..., 
        description="Detailed instruction for CSV storage: table structure, column names, and how to format the aggregated data"
    )
    
    # Missing data tracking
    missing_analyses: List[str] = Field(
        default_factory=list,
        description="List of images or queries that still need to be processed"
    )
    
    # Error handling
    error: bool = Field(default=False, description="Whether there's an unrecoverable error")
    error_message: str = Field(default="", description="Error details for feedback to parent agent")
    
    # Reasoning
    reasoning: str = Field(..., description="Explanation of the evaluation decision")


# ============================================================================
# IMAGE LOADING UTILITY
# ============================================================================

def _load_image(img_url: str) -> Image.Image:
    """Load an image from various sources with proper error handling."""
    # Use relative path that works in Docker and locally
    base_path = str(_RESOURCE_PATH) + "/"
    
    # If not an absolute path or URL, prepend base path
    if not img_url.startswith(('http://', 'https://', 'file://', '/')):
        img_url = base_path + img_url
    
    parsed = urlparse(img_url)

    # Remote URL
    # if parsed.scheme in ("http", "https"):
    #     headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    #     response = requests.get(img_url, stream=True, headers=headers, timeout=30)
    #     response.raise_for_status()

    #     img = Image.open(response.raw)
    #     img.draft('RGB', (1024, 1024))
    #     img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    #     return img.convert("RGB")
        # return Image.open(response.raw).convert("RGB")

    # file:// URI
    # if parsed.scheme == "file":
    #     path = parsed.path
    #     if not os.path.exists(path):
    #         raise FileNotFoundError(f"File not found: {path}")
    #     img = Image.open(img_url)
    #     img.draft('RGB', (1024, 1024))
    #     img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    #     return img.convert("RGB")

    # Local path (no scheme)
    # REMOVE LATER:::::::::::::::::::::::::::::::::::::
    Image.MAX_IMAGE_PIXELS = None
    # REMOVE LATER:::::::::::::::::::::::::::::::::::::
    if os.path.exists(img_url):
        img = Image.open(img_url)
        img.draft('RGB', (1024, 1024))
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        return img.convert("RGB")

    raise ValueError(f"Image not found or unsupported path: {img_url}")


# ============================================================================
# BUILD GPU-AWARE IMAGE QNA TOOL
# ============================================================================

def build_image_qna_tool(use_gpu: Optional[bool] = None):
    """
    Build the image QnA tool with GPU acceleration support.
    
    Args:
        use_gpu: Explicitly set GPU usage. If None, auto-detect.
                 If False, force CPU even if GPU available.
                 If True, prefer GPU but fallback to CPU if unavailable.
    
    Returns:
        The image_qna_tool function.
    """
    # Determine device
    device, device_info = get_device()
    
    # Handle explicit GPU preference (graceful fallback, no failure)
    if use_gpu is True and device == "cpu":
        print("⚠️  GPU requested but not available - falling back to CPU")
        # No exception - just continue with CPU
    if use_gpu is False:
        device = "cpu"
        device_info = "CPU (forced by configuration)"
    
    print(f"🔧 Image QnA Tool initialized on: {device_info}")
    
    # Log memory if using GPU
    if device != "cpu":
        mem_info = get_memory_info()
        if mem_info:
            print(f"   GPU Memory: {mem_info['total_gb']}GB total, "
                  f"{mem_info['allocated_gb']}GB allocated")
    
    # Initialize BLIP model with graceful device handling
    try:
        processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
        model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
        
        # Try to move to selected device, fallback to CPU on CUDA errors
        try:
            model = model.to(device)
        except (RuntimeError, torch.cuda.OutOfMemoryError) as cuda_error:
            print(f"⚠️  CUDA error: {cuda_error}")
            print("   Falling back to CPU...")
            device = "cpu"
            model = model.to("cpu")
            torch.cuda.empty_cache()  # Clear CUDA memory
        
        # Set eval mode for inference
        model.eval()
        
    except Exception as e:
        print(f"❌ Error loading BLIP model: {e}")
        print("   Attempting fallback initialization on CPU...")
        device = "cpu"
        processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
        model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
        model.eval()
    
    @tool("image_qna_tool")
    def image_qna_tool(img_url: str, query: str) -> str:
        """
        Extracts visual data from an image using BLIP VQA model with GPU acceleration.
        
        Args:
            img_url: Path or URL to the image. Example: `images/img_0.jpg`
            query: A direct, imperative query describing data to extract.
                   BAD: "Can you tell me what is in this?"
                   GOOD: "list of objects visible in image"
                   GOOD: "primary colors in the painting"
                   GOOD: "art style and technique used"
            
        Returns:
            JSON string containing the extraction result with status, image_url, query, and answer.
        """
        try:
            image = _load_image(str(img_url))
            
            # Prepare inputs on the device
            inputs = processor(image, query, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Run inference with torch.no_grad for efficiency
            with torch.no_grad():
                output_ids = model.generate(**inputs, max_length=50)
            
            answer = processor.decode(output_ids[0], skip_special_tokens=True)
            
            # Return structured response that agent can parse
            return json.dumps({
                "status": "success",
                "image_url": img_url,
                "query": query,
                "answer": answer,
                "device_used": device
            })
            
        except FileNotFoundError as e:
            return json.dumps({
                "status": "error",
                "image_url": img_url,
                "query": query,
                "error": f"Image not found: {str(e)}"
            })
        except Exception as e:
            return json.dumps({
                "status": "error", 
                "image_url": img_url,
                "query": query,
                "error": str(e)
            })
    
    return image_qna_tool


# ============================================================================
# AGENT NODE WITH STATE-AWARE PROMPTING
# ============================================================================

def _extract_images_from_message(content: str) -> List[str]:
    """Extract image paths from message content."""
    import re
    
    # Try to extract from "Images to analyze: [...]" format
    json_match = re.search(r'Images to analyze:\s*(\[.*?\])', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to extract from "img_path=[...]" format
    img_path_match = re.search(r'img_path\s*=\s*(\[.*?\])', content, re.DOTALL)
    if img_path_match:
        try:
            return json.loads(img_path_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Fallback: find all image paths matching pattern
    matches = re.findall(r'images/img_\d+\.jpg', content)
    return list(set(matches))


def _extract_context_from_message(content: str) -> str:
    """Extract context from previous tools in the message."""
    import re
    
    context_match = re.search(r'Context from previous tools:\s*(.*?)(?:\n\n|$)', content, re.DOTALL)
    if context_match:
        return context_match.group(1).strip()
    return ""


def create_agent_node(llm, tools):
    """Create agent node that is aware of accumulated state."""
    
    def agent_node(state: ImageAnalysisState):
        # Extract images and context from the first user message if not in state
        images_to_process = list(state.get("images_to_process", []))
        extracted_context = ""
        
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                # Extract images if not already set
                if not images_to_process:
                    images_to_process = _extract_images_from_message(msg.content)
                # Extract context from previous tools
                extracted_context = _extract_context_from_message(msg.content)
                break
        
        # Build context-aware system prompt
        system_prompt = """You are an Expert Visual Data Analyst for artwork databases.

## Your Role
Analyze artwork images to extract specific visual information requested by the task.
You MUST use the image_qna_tool to analyze each image.

## Tool Usage Rules (CRITICAL)
When using image_qna_tool:
- Use DIRECT, SPECIFIC queries based on what the task asks for
- ❌ FORBIDDEN: "Can you see...", "Is there...", "What is in this image?"
- ✅ REQUIRED: Task-specific queries like:
  - "number of swords in the image" (if task asks about swords)
  - "number of babies visible" (if task asks about babies)  
  - "art style of the painting" (if task asks about style)
  - "main subjects depicted" (if task asks about subjects/content)

## CRITICAL: Match Your Query to the Task
- If task asks "how many swords" → query each image with "number of swords in the image"
- If task asks "what is depicted" → query each image with "main subjects and objects depicted"
- If task asks about a specific thing → query specifically for that thing

## Workflow
1. **Understand the Task**: Read the original task carefully to know WHAT to look for
2. **Query Each Image**: Call image_qna_tool for EACH image with a task-relevant query
3. **Process Results**: The tool returns JSON with the answer
4. **Summarize**: After ALL images are processed, provide a summary table

## Important
- You MUST process ALL images listed
- Make ONE tool call per image with the appropriate query
- If an image errors, continue with other images
"""
        
        # Add dynamic context to prompt
        context_parts = []
        
        # Show original task prominently
        original_task = state.get("original_task", "")
        if original_task:
            context_parts.append(f"## 🎯 ORIGINAL TASK\n{original_task}\n")
        
        # Show context from previous steps (e.g., database query results)
        if extracted_context:
            context_parts.append(f"## 📋 CONTEXT FROM PREVIOUS STEPS\n{extracted_context}\n")
        
        # Show images that need to be processed
        images_processed = state.get("images_processed", [])
        remaining = [img for img in images_to_process if img not in images_processed]
        
        if images_to_process:
            context_parts.append(f"## 🖼️ IMAGES TO ANALYZE\nTotal: {len(images_to_process)} images")
            context_parts.append(f"Image paths: {json.dumps(images_to_process)}\n")
        
        if remaining:
            context_parts.append(f"## ⏳ REMAINING IMAGES ({len(remaining)} left)")
            context_parts.append(f"Still need to process: {json.dumps(remaining)}\n")
        elif images_to_process and not remaining:
            context_parts.append("## ✅ ALL IMAGES PROCESSED\nProvide your final summary now.\n")
        
        # Show what's been analyzed so far
        records = state.get("analysis_records", [])
        if records:
            context_parts.append(f"## 📊 COMPLETED ANALYSES ({len(records)} done)")
            for i, record in enumerate(records, 1):
                if isinstance(record, dict):
                    context_parts.append(f"  {i}. {record.get('image_url', 'N/A')}: Q=\"{record.get('query', 'N/A')}\" → A=\"{record.get('answer', 'N/A')}\"")
                elif hasattr(record, 'to_string'):
                    context_parts.append(f"  {i}. {record.to_string()}")
                else:
                    context_parts.append(f"  {i}. {str(record)}")
            context_parts.append("")
        
        full_system = system_prompt + "\n" + "\n".join(context_parts)
        
        messages_for_llm = [SystemMessage(content=full_system)] + state["messages"]
        
        response = llm.bind_tools(tools).invoke(messages_for_llm)
        
        # Update state with extracted images if they weren't set
        updates = {"messages": [response]}
        if images_to_process and not state.get("images_to_process"):
            updates["images_to_process"] = images_to_process
        
        return updates
    
    return agent_node


# ============================================================================
# TOOL RESULT PROCESSOR - UPDATES STATE FROM TOOL OUTPUTS
# ============================================================================

def process_tool_results(state: ImageAnalysisState):
    """
    Process tool messages and update state with structured analysis records.
    This node runs after tools to properly track what was analyzed.
    """
    updates = {
        "analysis_records": [],
        "images_processed": []
    }
    
    # Find the most recent tool messages
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            try:
                result = json.loads(msg.content)
                if result.get("status") == "success":
                    record = ImageAnalysisRecord(
                        image_url=result["image_url"],
                        query=result["query"],
                        answer=result["answer"]
                    )
                    updates["analysis_records"].append(record)
                    if result["image_url"] not in updates["images_processed"]:
                        updates["images_processed"].append(result["image_url"])
            except (json.JSONDecodeError, KeyError):
                # Not a JSON tool response, skip
                pass
        elif isinstance(msg, AIMessage):
            # Stop when we hit the AI message that triggered tools
            break
    
    return updates


# ============================================================================
# EVALUATOR NODE WITH FULL CONTEXT
# ============================================================================

def create_evaluator_node(llm):
    """Create evaluator with full context awareness."""
    
    def evaluator_node(state: ImageAnalysisState):
        last_message = state["messages"][-1]
        
        # Skip if last message is a tool message (agent hasn't processed it yet)
        if isinstance(last_message, ToolMessage):
            return {}
        
        # Build comprehensive context for evaluator
        eval_context = {
            "original_task": state.get("original_task", "Unknown"),
            "total_analyses": len(state.get("analysis_records", [])),
            "images_processed": state.get("images_processed", []),
            "images_to_process": state.get("images_to_process", []),
            "analysis_summary": []
        }
        
        for record in state.get("analysis_records", []):
            if isinstance(record, dict):
                eval_context["analysis_summary"].append(record)
            elif hasattr(record, 'model_dump'):
                eval_context["analysis_summary"].append(record.model_dump())
            else:
                eval_context["analysis_summary"].append(str(record))
        
        system_message = SystemMessage(content=f"""You are a Task Completion Evaluator for an image analysis agent.

## Context You Have Access To:
{json.dumps(eval_context, indent=2)}

## Your Job:
1. Assess if the ORIGINAL TASK has been fully accomplished
2. Check if ALL required images have been analyzed
3. Evaluate data quality for CSV export readiness
4. Provide specific CSV structuring instructions

## Evaluation Criteria:
- task_complete=True ONLY if all required analyses are done
- data_quality_score based on answer usefulness (1-5)
- missing_analyses should list any gaps
- storing_instruction must include: column names, data format, file path suggestion

## Be Strict:
If the agent said it's done but you see missing analyses, mark task_complete=False.""")
        
        evaluator = llm.with_structured_output(ImageAnalysisOutput)
        evaluation: ImageAnalysisOutput = evaluator.invoke([system_message] + state["messages"])
        
        # Handle errors - return to parent for replan
        if evaluation.error:
            return Command(
                goto=END, 
                graph=Command.PARENT, 
                update={
                    "current_step": 0, 
                    "feedback": f"Image analysis failed: {evaluation.error_message}"
                }
            )
        
        # Handle incomplete task - agent needs to do more
        if not evaluation.task_complete:
            feedback_msg = AIMessage(content=f"""Task incomplete. 

**Missing**: {evaluation.missing_analyses}
**Evaluator Notes**: {evaluation.reasoning}

Please improvise and complete the remaining analyses accurately.""")
            return {"messages": [feedback_msg]}
        
        # Task complete - prepare for workspace update
        workspace_dir = str(_CURRENT_DIR.parent / "workspace" / "outputs")
        
        # Build comprehensive storage prompt
        analysis_data = json.dumps(eval_context["analysis_summary"], indent=2)
        
        prompt_to_store = f"""## Data Storage Task

**Original Goal**: {evaluation.task}

**Extracted Data**:
{analysis_data}

**Storage Instructions**: {evaluation.storing_instruction}

**Target Directory**: {workspace_dir}
**Suggested Path**: {workspace_dir}/image_analysis_results.csv

Create Python code to:
1. Structure the extracted data into a proper DataFrame
2. Save as CSV to the workspace
3. Ensure data is extractable and plottable"""
        
        storing_message = AIMessage(content=prompt_to_store)
        
        return Command(
            goto="update_workspace", 
            update={
                "messages": [storing_message], 
                "tools_complete": True
            }
        )
    
    return evaluator_node


# ============================================================================
# WORKSPACE UPDATE NODE
# ============================================================================

# Default workspace paths - can be overridden (using relative path)
DEFAULT_WORKSPACE_PATH = _CURRENT_DIR.parent / "workspace"  # backend/app/agents/dev/workspace
DEFAULT_OUTPUT_PATH = DEFAULT_WORKSPACE_PATH / "outputs"


def create_update_workspace_node(llm, output_path: Path = None):
    """Create workspace update node for CSV saving.
    
    Args:
        llm: Language model for code generation
        output_path: Path to save CSV outputs. Uses DEFAULT_OUTPUT_PATH if not provided.
    """
    
    # Import here to avoid circular imports
    from .data_plotting_tool import PythonREPL, CodeGeneratorOutput
    
    # Use provided output_path or fall back to default
    csv_output_path = output_path or DEFAULT_OUTPUT_PATH
    
    def update_workspace(state: ImageAnalysisState):
        """Save analysis results to CSV file."""
        
        # Build a clear prompt for CSV generation
        analysis_records = state.get("analysis_records", [])
        original_task = state.get("original_task", "")
        
        # Create structured prompt for code generation
        csv_prompt = f"""## Task
Save the following image analysis results to a CSV file.

## Original Task
{original_task}

## Analysis Results
"""
        for record in analysis_records:
            if hasattr(record, 'to_string'):
                csv_prompt += f"- {record.to_string()}\n"
            else:
                csv_prompt += f"- Image: {record.image_url}, Query: {record.query}, Answer: {record.answer}\n"
        
        csv_prompt += f"""

## Instructions
1. Generate Python code to save this data to a CSV file
2. Use pandas to create a DataFrame with columns: image_url, query, answer
3. Save to: {csv_output_path}/image_analysis_results.csv
4. Use the ABSOLUTE path: {csv_output_path}/image_analysis_results.csv
5. Print the full absolute path after saving

## Output Path (MUST USE THIS EXACT PATH)
{csv_output_path}/image_analysis_results.csv
"""
        
        workspace_helper = llm.with_structured_output(CodeGeneratorOutput)
        workspace_details: CodeGeneratorOutput = workspace_helper.invoke([
            SystemMessage(content="You are a Python code generator. Generate code to save data to CSV."),
            HumanMessage(content=csv_prompt)
        ])
        
        python_repl = PythonREPL()
        
        if not workspace_details.code:
            output_message = AIMessage(
                content=f"Code generation failed: {workspace_details.reasoning}"
            )
            return Command(
                goto=END,
                graph=Command.PARENT,
                update={
                    "messages": [output_message],
                    "feedback": f"CSV storage failed: {workspace_details.reasoning}"
                }
            )
        
        # Ensure output directory exists
        csv_output_path.mkdir(parents=True, exist_ok=True)
        
        # Execute the code
        result = python_repl.run(workspace_details.code)
        
        if "Error" in result:
            output_message = AIMessage(
                content=f"Code execution failed: {result}"
            )
            return Command(
                goto=END,
                graph=Command.PARENT,
                update={
                    "messages": [output_message],
                    "feedback": f"CSV storage execution failed: {result}"
                }
            )
        
        # Determine the actual file path - prefer absolute path
        file_name = workspace_details.file_name
        if not os.path.isabs(file_name):
            # Convert to absolute path in outputs directory
            file_name = str(csv_output_path / os.path.basename(file_name))
        
        output_message = AIMessage(
            content=f"✅ Analysis complete. Data saved to: {file_name}\\n\\nExecution result: {result}"
        )
        
        return Command(
            goto=END,
            update={
                "messages": [output_message],
            }
        )
    
    return update_workspace


# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_after_agent(state: ImageAnalysisState) -> Literal["tools", "evaluator"]:
    """Route based on agent's last action."""
    last_message = state["messages"][-1]
    
    # If agent wants to use tools, go to tools
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    # Otherwise, evaluate
    return "evaluator"


def route_after_evaluator(state: ImageAnalysisState) -> Literal["agent", "update_workspace", END]:
    """Route based on evaluator's decision."""
    # If tools_complete is set, we're going to update_workspace (handled by Command)
    if state.get("tools_complete"):
        return "update_workspace"
    
    # Otherwise, back to agent for more work
    return "agent"


# ============================================================================
# BUILD THE GRAPH - WITH CONFIGURABLE LLM
# ============================================================================

def build_image_qna_agent(model_name: str = "gpt-4o", use_gpu: Optional[bool] = None, output_path: Path = None):
    """
    Build the complete image QnA agent graph with configurable LLM and GPU support.
    
    Args:
        model_name: LLM model to use with init_chat_model. Examples: "gpt-4o", "claude-3-5-sonnet",
                   "claude-opus", "gemini-2.0-flash", etc. Defaults to "gpt-4o".
        use_gpu: GPU usage for image analysis tool.
                - None: Auto-detect and use GPU if available (default)
                - True: Prefer GPU, gracefully fallback to CPU if unavailable
                - False: Force CPU even if GPU available
        output_path: Path to save CSV outputs. Uses DEFAULT_OUTPUT_PATH if not provided.
    
    Returns:
        Compiled LangGraph StateGraph for the image analysis agent.
    """
    
    import os
    from langchain.chat_models import init_chat_model
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Initialize LLM with provided model name
    print(f"🤖 Initializing LLM: {model_name}")
    llm = init_chat_model(model_name)
    
    # Set output path for CSV exports
    csv_output_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH
    print(f"   Output path: {csv_output_path}")
    
    # Build tools with GPU configuration
    print(f"🖼️  Building image analysis tool (GPU: {'auto-detect' if use_gpu is None else use_gpu})...")
    image_qna_tool = build_image_qna_tool(use_gpu=use_gpu)
    tools = [image_qna_tool]
    
    # Build nodes
    agent_node = create_agent_node(llm, tools)
    evaluator_node = create_evaluator_node(llm)
    update_workspace_node = create_update_workspace_node(llm, output_path=csv_output_path)
    
    # Create custom tool node that also processes results
    tool_node = ToolNode(tools)
    
    def tools_with_state_update(state: ImageAnalysisState):
        """Run tools and then update state with results."""
        # First, run the actual tools
        tool_result = tool_node.invoke(state)
        
        # Process tool results into structured records
        new_records = []
        new_images = list(state.get("images_processed", []))
        
        for msg in tool_result.get("messages", []):
            if isinstance(msg, ToolMessage):
                try:
                    result = json.loads(msg.content)
                    if result.get("status") == "success":
                        record = ImageAnalysisRecord(
                            image_url=result["image_url"],
                            query=result["query"],
                            answer=result["answer"]
                        )
                        new_records.append(record)
                        if result["image_url"] not in new_images:
                            new_images.append(result["image_url"])
                except (json.JSONDecodeError, KeyError):
                    pass
        
        # Combine tool messages with state updates
        return {
            "messages": tool_result.get("messages", []),
            "analysis_records": new_records,
            "images_processed": new_images
        }
    
    # Build graph
    builder = StateGraph(ImageAnalysisState)
    
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_with_state_update)
    builder.add_node("evaluator", evaluator_node)
    builder.add_node("update_workspace", update_workspace_node)
    
    # Add edges
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        ["tools", "evaluator"]
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        ["agent", "update_workspace", END]
    )
    builder.add_edge("update_workspace", END)
    
    return builder.compile()


# ============================================================================
# HELPER: WRAP AS TOOL FOR SUPERVISOR
# ============================================================================

def create_image_analysis_tool_for_supervisor(model_name: str = "gpt-4o", use_gpu: Optional[bool] = None):
    """
    Wrap the image analysis agent as a tool that can be called by a supervisor.
    This handles the state initialization and result extraction.
    
    Args:
        model_name: LLM model to use. Examples: "gpt-4o", "claude-3-5-sonnet", etc.
        use_gpu: GPU configuration for the image analysis tool.
    
    Returns:
        A tool function that can be used by supervisor agents.
    """
    graph = build_image_qna_agent(model_name=model_name, use_gpu=use_gpu)
    
    @tool("image_analysis_tool")
    def image_analysis_tool(task: str, image_urls: List[str]) -> str:
        """
        Analyze artwork images and extract structured data.
        
        Args:
            task: Description of what to analyze (e.g., "extract art style, subjects, and color palette for each painting")
            image_urls: List of image URLs/paths to analyze
            
        Returns:
            Path to the generated CSV file with analysis results, or error message.
        """
        # Initialize state with task context
        initial_state = {
            "messages": [HumanMessage(content=task)],
            "original_task": task,
            "images_to_process": image_urls,
            "images_processed": [],
            "analysis_records": [],
            "tools_complete": False
        }
        
        # Run the graph
        result = graph.invoke(initial_state)
        
        # Extract final message
        if result.get("messages"):
            last_msg = result["messages"][-1]
            return last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        return "Image analysis completed but no output message generated."
    
    return image_analysis_tool


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Example 1: Build with default settings (GPT-4o, GPU auto-detect)
    print("=" * 80)
    print("Example 1: Default settings (GPT-4o, GPU auto-detect)")
    print("=" * 80)
    agent = build_image_qna_agent()
    
    # Example 2: Build with different LLM and explicit GPU usage
    print("\n" + "=" * 80)
    print("Example 2: Using Claude Sonnet with GPU")
    print("=" * 80)
    # agent = build_image_qna_agent(model_name="claude-3-5-sonnet-20241022", use_gpu=True)
    
    # Example 3: Using CPU only
    print("\n" + "=" * 80)
    print("Example 3: Using CPU only")
    print("=" * 80)
    # agent = build_image_qna_agent(use_gpu=False)
    
    # Test with a sample task
    test_state = {
        "messages": [HumanMessage(content="Analyze the art style and main subjects in images/img_0.jpg and images/img_1.jpg")],
        "original_task": "Analyze art style and subjects",
        "images_to_process": ["images/img_0.jpg", "images/img_1.jpg"],
        "images_processed": [],
        "analysis_records": [],
        "tools_complete": False
    }
    
    print("\n🚀 Starting image analysis agent test...")
    # result = agent.invoke(test_state)
    # print("Result:", result)
