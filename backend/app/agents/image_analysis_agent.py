
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
from typing_extensions import Annotated, TypedDict
import operator
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode


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

def _load_image(img_url: str) -> Image.Image:
    """Load an image strictly from local filesystem."""

    current_dir = Path(__file__).resolve().parent

    resource_dir = current_dir.parent / "resource"

    if img_url.startswith("file://"):
        img_url = urlparse(img_url).path
        
    if os.path.isabs(img_url) and os.path.exists(img_url):
         return Image.open(img_url).convert("RGB")

    # Construct resource path
    resource_path = resource_dir / img_url
    if resource_path.exists():
        return Image.open(resource_path).convert("RGB")
        
    # Try one level up if resource dir mapping is tricky (backend/resource vs backend/app/resource)
    # The user said @[backend/app/agents/dev] exists. 
    # Current file: backend/app/agents/image_analysis_agent.py (simulated)
    # Actual file writes to: backend/app/agents/image_analysis_agent.py
    
    # Fallback: try direct path if CWD is backend root
    if os.path.exists(img_url):
        return Image.open(img_url).convert("RGB")

    raise FileNotFoundError(f"Image not found locally: {img_url}. Checked paths: {resource_path}, {img_url}")


# ============================================================================
# BUILD IMAGE QNA TOOL WITH PROPER STATE UPDATES
# ============================================================================

def build_image_qna_tool():
    """
    Build the image QnA tool with proper state management.
    The tool now returns structured data that updates state correctly.
    """
    processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
    model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
    
    @tool("image_qna_tool")
    def image_qna_tool(img_url: str, query: str) -> str:
        try:
            image = _load_image(str(img_url))
            inputs = processor(image, query, return_tensors="pt")
            
            with torch.no_grad():
                output_ids = model.generate(**inputs, max_length=50)
            
            answer = processor.decode(output_ids[0], skip_special_tokens=True)
            
            # Return structured response that agent can parse
            return json.dumps({
                "status": "success",
                "image_url": img_url,
                "query": query,
                "answer": answer
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

def create_agent_node(llm, tools):
    """Create agent node that is aware of accumulated state."""
    
    def agent_node(state: ImageAnalysisState):
        # Build context-aware system prompt
        system_prompt = """You are an Expert Visual Data Analyst for artwork databases.

## Your Role
Transform raw images into structured, tabular data using the image_qna_tool.

## Tool Usage Rules (CRITICAL)
When using image_qna_tool, use DIRECT IMPERATIVE QUERIES:
- ❌ FORBIDDEN: "Can you see...", "Is there...", "What is...?"
- ✅ REQUIRED: "main subjects in the image", "color palette used", "art style and technique"

## Workflow
1. **Extract**: Call image_qna_tool for each required analysis
2. **Parse**: Process tool responses (JSON format with status, image_url, query, answer)
3. **Accumulate**: Track all analyses for final synthesis
4. **Report**: When done, provide summary table of all findings

## Important
- Process ALL images mentioned in the task
- If a tool returns an error, note it and continue with other images
- Your final response should summarize ALL extracted data in tabular format

## Current Context
"""
        
        # Add accumulated analysis context to prompt
        context_parts = []
        
        if state.get("original_task"):
            context_parts.append(f"**Original Task**: {state['original_task']}")
        
        # Show what's been analyzed so far
        records = state.get("analysis_records", [])
        if records:
            context_parts.append(f"\\n**Analyses Completed ({len(records)})**:")
            for i, record in enumerate(records, 1):
                if isinstance(record, dict):
                    context_parts.append(f"  {i}. Image: {record.get('image_url', 'N/A')} | Q: {record.get('query', 'N/A')} | A: {record.get('answer', 'N/A')}")
                else:
                    context_parts.append(f"  {i}. {record.to_string() if hasattr(record, 'to_string') else str(record)}")
        
        # Show images yet to process
        images_processed = state.get("images_processed", [])
        images_to_process = state.get("images_to_process", [])
        remaining = [img for img in images_to_process if img not in images_processed]
        if remaining:
            context_parts.append(f"\\n**Remaining Images**: {remaining}")
        
        full_system = system_prompt + "\\n".join(context_parts)
        
        messages_for_llm = [SystemMessage(content=full_system)] + state["messages"]
        
        response = llm.bind_tools(tools).invoke(messages_for_llm)
        
        return {"messages": [response]}
    
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
                pass
        elif isinstance(msg, AIMessage):
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

Please complete the remaining analyses.""")
            # In langgraph, adding a message usually resumes conversation with the agent
            return {"messages": [feedback_msg]}
        
        # Task complete - prepare for workspace update
        # Set workspace as sibling to agents directory typically
        current_dir = Path(__file__).resolve().parent
        workspace_dir = current_dir.parent / "workspace"
        if not workspace_dir.exists():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            
        workspace_path_str = str(workspace_dir).replace("\\\\", "/")
        
        # Build comprehensive storage prompt
        analysis_data = json.dumps(eval_context["analysis_summary"], indent=2)
        
        prompt_to_store = f"""## Data Storage Task

**Original Goal**: {evaluation.task}

**Extracted Data**:
{analysis_data}

**Storage Instructions**: {evaluation.storing_instruction}

**Target Directory**: {workspace_path_str}
**Suggested Path**: {workspace_path_str}/image_analysis_results.csv

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
# WORKSPACE UPDATE NODE (NEEDS PYTHON REPL)
# ============================================================================

# Assumes data_plotting_tool exists and has PythonREPL, CodeGeneratorOutput
try:
    from .tools.visualization_tools import PythonREPL # Adjust import based on user structure
except ImportError:
    # Fallback/Mock if specific tool not found in expected location
    # User had 'from data_plotting_tool import PythonREPL' in dev code
    # We will try to find where PythonREPL is in main app
    from langchain_experimental.utilities import PythonREPL as LangChainPythonREPL
    class PythonREPL(LangChainPythonREPL):
        pass

# Define CodeGeneratorOutput structure locally if import fails
class CodeGeneratorOutput(BaseModel):
    code: str = Field(..., description="The python code to execute")
    reasoning: str = Field(..., description="Reasoning for the code")
    file_name: str = Field(..., description="Name of the file created")


def create_update_workspace_node(llm):
    """Create workspace update node for CSV saving."""
    
    def update_workspace(state: ImageAnalysisState):
        """Save analysis results to CSV file."""
        
        workspace_helper = llm.with_structured_output(CodeGeneratorOutput)
        workspace_details: CodeGeneratorOutput = workspace_helper.invoke(state["messages"])
        
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
        
        output_message = AIMessage(
            content=f"✅ Analysis complete. Data saved to: {workspace_details.file_name}\\n\\nExecution result: {result}"
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
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    return "evaluator"


def route_after_evaluator(state: ImageAnalysisState) -> Literal["agent", "update_workspace", END]:
    """Route based on evaluator's decision."""
    if state.get("tools_complete"):
        return "update_workspace"
    
    return "agent"


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_image_qna_agent():
    """Build the complete image QnA agent graph."""
    
    from langchain.chat_models import init_chat_model
    from dotenv import load_dotenv
    
    load_dotenv()
    llm = init_chat_model("gpt-4o-mini")
    
    # Build tools
    image_qna_tool = build_image_qna_tool()
    tools = [image_qna_tool]
    
    # Build nodes
    agent_node = create_agent_node(llm, tools)
    evaluator_node = create_evaluator_node(llm)
    update_workspace_node = create_update_workspace_node(llm)
    
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

def create_image_analysis_tool_for_supervisor():
    """
    Wrap the image analysis agent as a tool that can be called by a supervisor.
    """
    graph = build_image_qna_agent()
    
    @tool("image_analysis_tool")
    def image_analysis_tool(task: str, image_urls: List[str]) -> str:
        initial_state = {
            "messages": [HumanMessage(content=task)],
            "original_task": task,
            "images_to_process": image_urls,
            "images_processed": [],
            "analysis_records": [],
            "tools_complete": False
        }
        
        result = graph.invoke(initial_state)
        
        if result.get("messages"):
            last_msg = result["messages"][-1]
            return last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        return "Image analysis completed but no output message generated."
    
    return image_analysis_tool
