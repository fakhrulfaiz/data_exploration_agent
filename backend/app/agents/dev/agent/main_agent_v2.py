# main_agent_v2.py - Redesigned supervisor/main agent with proper state management

"""
Key Fixes:
1. Structured planning with validation and tool capability awareness
2. Proper state updates from subagent results
3. Step tracking with completion detection
4. Feedback integration for intelligent replanning
5. Final answer aggregation from all step results
"""

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import MemorySaver

# Load environment variables
load_dotenv()

# Import enhanced state
from .state.main_agent_state_v2 import (
    MainAgentState,
    PlanStep,
    StepResult,
    ExecutionPlan,
    StepExecutionDecision,
    FinalAnswer,
    TOOL_CAPABILITIES
)

# ============================================================================
# SUBAGENT IMPORTS
# ============================================================================

# Import the subagents
from .data_exploration_subagent_v2 import build_data_exploration_agent
from .image_qna_subagent_v2 import build_image_qna_agent
from .data_plotting_subagent import build_plotting_agent

# Try to import plotting agent, fallback if not available
try:
    # from .data_plotting_subagent import build_plotting_agent
    HAS_PLOTTING_AGENT = True
except ImportError:
    HAS_PLOTTING_AGENT = False
    print("Warning: data_plotting_subagent not available")


# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize the model
model = init_chat_model("gpt-4o-mini")

# Build subagents (lazy initialization)
_data_exploration_agent = None
_image_qna_agent = None
_plotting_agent = None


def get_data_exploration_agent():
    global _data_exploration_agent
    if _data_exploration_agent is None:
        _data_exploration_agent = build_data_exploration_agent()
    return _data_exploration_agent


def get_image_qna_agent():
    global _image_qna_agent
    if _image_qna_agent is None:
        _image_qna_agent = build_image_qna_agent()
    return _image_qna_agent


def get_plotting_agent():
    global _plotting_agent
    if _plotting_agent is None and HAS_PLOTTING_AGENT:
        _plotting_agent = build_plotting_agent()
    return _plotting_agent


# ============================================================================
# DATABASE SCHEMA CONTEXT
# ============================================================================

DATABASE_SCHEMA = """
## Table: paintings

### Columns
| Column Name | Data Type | Description |
|------------|-----------|-------------|
| title | TEXT | Name of the painting |
| inception | INTEGER | Year the painting was created (e.g., 1503, 1642) |
| movement | TEXT | Art movement (e.g., Renaissance, Baroque) |
| genre | TEXT | Artistic genre (e.g., portrait, landscape) |
| image_url | TEXT | Public URL to the painting image (DO NOT USE for image analysis) |
| img_path | TEXT | Local file path to the image (e.g., 'images/img_0.jpg') - USE THIS for image_qna_agent |

### CRITICAL: Image Analysis Workflow
1. ALWAYS use `img_path` column (NOT image_url) when you need visual analysis
2. First query the database to get img_path values
3. Then pass those img_path values to image_qna_agent
4. img_path format is like: 'images/img_0.jpg', 'images/img_1.jpg', etc.

### Query Tips
- The database CANNOT tell you about visual content (colors, subjects, people, etc.)
- Always include img_path in SELECT when visual analysis will follow
- For date filtering: use inception column (it's a year integer, e.g., WHERE inception BETWEEN 1600 AND 1700)
- Always specify row limits (e.g., LIMIT 10) to avoid overwhelming the system
"""


# ============================================================================
# TOOL WRAPPERS WITH PROPER STATE UPDATES
# ============================================================================

def _extract_img_paths_from_content(content: str) -> List[str]:
    """Extract image paths from result content."""
    img_paths = []
    # Match patterns like images/img_0.jpg, images/img_123.jpg
    import re
    matches = re.findall(r'images/img_\d+\.jpg', content)
    img_paths.extend(matches)
    # Also try to match from JSON arrays in content
    try:
        # Look for JSON array patterns
        json_matches = re.findall(r'\[[\s\S]*?"images/img_\d+\.jpg"[\s\S]*?\]', content)
        for match in json_matches:
            parsed = json.loads(match)
            if isinstance(parsed, list):
                img_paths.extend([p for p in parsed if isinstance(p, str) and 'img_' in p])
    except:
        pass
    return list(set(img_paths))  # Remove duplicates


def execute_data_exploration(query: str) -> tuple[StepResult, str]:
    """Execute data exploration agent and return result with context summary."""
    try:
        agent = get_data_exploration_agent()
        result = agent.invoke({
            "messages": [HumanMessage(content=query)],
            "original_task": query,
            "query_history": [],
            "tables_queried": [],
            "exploration_complete": False,
            "ready_for_export": False,
            "result_summary": ""  # Initialize result_summary
        })
        
        # Extract result
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        content = last_message.content if last_message and hasattr(last_message, 'content') else str(result)
        
        # Get the result_summary from subagent state (markdown format)
        result_summary = result.get("result_summary", "")
        
        # Check for output file
        output_file = None
        if "saved to:" in content.lower():
            import re
            match = re.search(r'saved to[:\s]+([^\s\n]+\.csv)', content, re.IGNORECASE)
            if match:
                output_file = match.group(1)
        
        # Build context string for downstream tools
        context = f"## Database Query Result (Step {{step_number}})\n\n"
        if result_summary:
            context += result_summary
        else:
            # Fallback: use content
            context += content[:1000]
        
        if output_file:
            context += f"\n\n**Output File**: {output_file}"
        
        step_result = StepResult(
            step_number=0,  # Will be set by caller
            success=True,
            result_content=content,
            output_file=output_file
        )
        
        return step_result, context
        
    except Exception as e:
        step_result = StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        )
        return step_result, f"## Database Query Error\n\nError: {str(e)}"


def execute_image_qna(query: str, img_paths: List[str], tool_context: str = "") -> tuple[StepResult, str]:
    """Execute image QnA agent and return result with context summary.
    
    Args:
        query: The analysis query
        img_paths: List of image paths to analyze
        tool_context: Previous tool context (e.g., database results) for reference
    """
    try:
        agent = get_image_qna_agent()
        
        # Format the query with image paths and context from previous tools
        full_query = f"{query}\n\nImages to analyze: {json.dumps(img_paths)}"
        if tool_context:
            full_query += f"\n\n## Context from Previous Steps\n{tool_context}"
        
        result = agent.invoke({
            "messages": [HumanMessage(content=full_query)],
            "original_task": query,
            "images_to_process": img_paths,
            "images_processed": [],
            "analysis_records": [],
            "tools_complete": False
        })
        
        # Extract result
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        content = last_message.content if last_message and hasattr(last_message, 'content') else str(result)
        
        # Check for output file
        output_file = None
        if "saved to:" in content.lower():
            import re
            match = re.search(r'saved to[:\s]+([^\s\n]+\.csv)', content, re.IGNORECASE)
            if match:
                output_file = match.group(1)
        
        # Build context string for downstream tools
        context = f"## Image Analysis Result (Step {{step_number}})\n\n"
        context += f"**Images Analyzed**: {len(img_paths)}\n"
        context += f"**Query**: {query}\n\n"
        context += content[:1000]
        
        if output_file:
            context += f"\n\n**Output File**: {output_file}"
        
        step_result = StepResult(
            step_number=0,
            success=True,
            result_content=content,
            output_file=output_file
        )
        
        return step_result, context
        
    except Exception as e:
        step_result = StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        )
        return step_result, f"## Image Analysis Error\n\nError: {str(e)}"


def execute_plotting(task: str, file_path: str) -> tuple[StepResult, str]:
    """Execute plotting agent and return result with context summary."""
    try:
        agent = get_plotting_agent()
        if agent is None:
            step_result = StepResult(
                step_number=0,
                success=False,
                result_content="",
                error_message="Plotting agent not available"
            )
            return step_result, "## Plotting Error\n\nPlotting agent not available"
        
        # Invoke with proper state structure for the new plotting subagent
        result = agent.invoke({
            "messages": [HumanMessage(content=f"Create plots for: {task}\nData file: {file_path}")],
            "original_task": task,
            "files_to_plot": [file_path],
            "plot_records": [],
            "plots_generated": [],
            "tools_complete": False,
            "result_summary": ""
        })
        
        # Extract result
        last_message = result.get("messages", [])[-1] if result.get("messages") else None
        content = last_message.content if last_message and hasattr(last_message, 'content') else str(result)
        
        # Get result_summary from plotting agent state
        result_summary = result.get("result_summary", "")
        
        # Get generated plots
        plots_generated = result.get("plots_generated", [])
        
        # Check for output file (plot)
        output_file = None
        if plots_generated:
            output_file = plots_generated[0]  # Use first plot as primary output
        elif "saved" in content.lower() and ".png" in content.lower():
            import re
            match = re.search(r'([^\s\n]+\.png)', content, re.IGNORECASE)
            if match:
                output_file = match.group(1)
        
        # Build context string
        if result_summary:
            context = result_summary
        else:
            context = f"## Plotting Result (Step {{step_number}})\n\n"
            context += f"**Task**: {task}\n"
            context += f"**Input File**: {file_path}\n"
            context += content[:500]
            
            if output_file:
                context += f"\n\n**Plot File**: {output_file}"
            
            if plots_generated:
                context += f"\n\n**All Generated Plots**: {json.dumps(plots_generated)}"
        
        step_result = StepResult(
            step_number=0,
            success=True,
            result_content=content,
            output_file=output_file
        )
        
        return step_result, context
        
    except Exception as e:
        step_result = StepResult(
            step_number=0,
            success=False,
            result_content="",
            error_message=str(e)
        )
        return step_result, f"## Plotting Error\n\nError: {str(e)}"


# ============================================================================
# NODE: PLANNER
# ============================================================================

def create_planner_node(llm):
    """Create the planning node with structured output."""
    
    def planner_node(state: MainAgentState):
        """Create a structured execution plan based on user query."""
        
        # Get the original query
        query = state.get("original_query") or ""
        if not query and state.get("messages"):
            # Extract from first human message
            for msg in state["messages"]:
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
        
        # Build context for replanning if needed
        replan_context = ""
        if state.get("feedback"):
            replan_context = f"""
## REPLANNING REQUIRED
Previous plan failed with feedback: {state['feedback']}

Previous step results:
{_format_step_results(state.get('step_results', []))}

Please create a revised plan that addresses these issues.
"""
        
        # Build tool capability context
        tool_context = "\n".join([
            f"- **{cap.name}**: {cap.description}\n  Required args: {cap.required_args}\n  Can produce CSV: {cap.can_produce_csv}\n  Requires CSV input: {cap.requires_csv_input}"
            for cap in TOOL_CAPABILITIES.values()
        ])
        
        system_prompt = f"""You are an expert task planner for an artwork analysis system.

## Your Job
Create a MINIMAL, efficient plan to accomplish the user's goal. Use ONLY the tools that are necessary.

## Available Tools
{tool_context}

## Database Schema
{DATABASE_SCHEMA}

## CRITICAL PLANNING RULES

### 1. MINIMAL TOOL USAGE (VERY IMPORTANT)
- DO NOT use all tools for every task
- Only include steps that are NECESSARY for the user's goal
- If a task can be done with 1 tool, use 1 tool
- If a task can be done with 2 tools, use 2 tools - NOT 3

### 2. When to Use Each Tool

**database_exploration_agent** - Use when:
- User asks about paintings metadata (title, year, genre, movement, etc.)
- User needs counts, aggregations, or statistics from database
- User wants to retrieve data for plotting
- Output: Can save results to CSV file

**image_qna_agent** - Use ONLY when:
- User EXPLICITLY asks about visual content (colors, people, objects, scenes)
- User wants to analyze what's IN the images
- NEVER use for metadata queries (year, title, genre - these are in database!)
- REQUIRES img_path from database first

**data_plotting_agent** - Use when:
- User asks to plot, chart, visualize, or graph data
- REQUIRES a CSV file from a previous step

### 3. Common Task Patterns

**"Plot/chart X by Y" (e.g., "Plot paintings per year"):**
1. database_exploration_agent: Query and aggregate data, save to CSV
2. data_plotting_agent: Create chart from CSV
⚠️ NO image analysis needed!

**"What colors are in painting X?":**
1. database_exploration_agent: Get img_path for painting X
2. image_qna_agent: Analyze visual content using img_path

**"How many paintings in genre X?":**
1. database_exploration_agent: COUNT query - DONE!
⚠️ Only 1 step needed!

**"Count people in paintings from period X":**
1. database_exploration_agent: Get img_paths for period X
2. image_qna_agent: Count people in each image
3. data_plotting_agent: (only if user asks for visualization)

### 4. Dependencies
- image_qna_agent MUST depend on database step that returns img_path
- data_plotting_agent MUST depend on step that produces CSV

{replan_context}

## User Query
{query}

Think carefully: What is the MINIMUM number of steps needed? Do NOT add unnecessary steps.
Create a plan with ONLY the necessary steps.
"""
        
        planner = llm.with_structured_output(ExecutionPlan)
        
        try:
            plan: ExecutionPlan = planner.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Create a plan for: {query}")
            ])
            
            # Update step numbers and validate
            for i, step in enumerate(plan.steps):
                step.step_number = i + 1
                step.status = "pending"
            
            return {
                "original_query": query,
                "plan_steps": plan.steps,
                "total_steps": len(plan.steps),
                "current_step_index": 0,
                "completed_steps": 0,
                "feedback": None,  # Clear feedback after replanning
                "pending_interrupt": False,
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"**Plan Created** ({len(plan.steps)} steps)\n\n"
                              f"{plan.understanding}\n\n"
                              f"**Why this is minimal:** {plan.minimal_approach}\n\n"
                              f"**Steps:**\n" + 
                              "\n".join([s.to_prompt_string() for s in plan.steps]) +
                              f"\n\n**Reasoning:** {plan.reasoning}")
                ]
            }
            
        except Exception as e:
            # Fallback: return error state
            return {
                "feedback": f"Planning failed: {str(e)}",
                "pending_interrupt": True
            }
    
    return planner_node


def _format_step_results(results: List[StepResult]) -> str:
    """Format step results for context."""
    if not results:
        return "No previous results."
    
    lines = []
    for r in results:
        status = "✅" if r.success else "❌"
        lines.append(f"{status} Step {r.step_number}: {r.result_content[:200]}...")
        if r.output_file:
            lines.append(f"   Output: {r.output_file}")
        if r.error_message:
            lines.append(f"   Error: {r.error_message}")
    
    return "\n".join(lines)


# ============================================================================
# NODE: STEP EXECUTOR
# ============================================================================

def create_executor_node(llm):
    """Create the step execution node."""
    
    def executor_node(state: MainAgentState):
        """Execute the current step in the plan."""
        
        # Check if we have steps to execute
        if not state.get("plan_steps"):
            return {
                "feedback": "No plan available",
                "pending_interrupt": True
            }
        
        # Check if all steps are done
        current_idx = state.get("current_step_index", 0)
        if current_idx >= len(state["plan_steps"]):
            return {
                "execution_complete": True
            }
        
        # Get current step
        current_step = state["plan_steps"][current_idx]
        
        # Check dependencies
        for dep_num in current_step.depends_on:
            dep_result = next(
                (r for r in state.get("step_results", []) if r.step_number == dep_num),
                None
            )
            if dep_result is None or not dep_result.success:
                # Dependency not met
                return {
                    "feedback": f"Step {current_step.step_number} depends on step {dep_num} which hasn't completed successfully",
                    "pending_interrupt": True
                }
        
        # Build context for execution decision
        previous_results = _format_step_results(state.get("step_results", []))
        
        # Get accumulated tool context (markdown summaries from previous tools)
        tool_context = state.get("tool_context", "")
        if not tool_context:
            tool_context = "No previous tool outputs yet."
        
        # Get available output files from previous steps
        available_files = [r.output_file for r in state.get("step_results", []) if r.output_file]
        
        # Decide how to execute this step
        decision_prompt = f"""You are executing step {current_step.step_number} of a plan.

## Current Step
{current_step.description}
Tool: {current_step.tool_name}

## Previous Tool Context (USE THIS DATA!)
{tool_context}

## Available Output Files
{json.dumps(available_files) if available_files else "None yet"}

## Tool Requirements
{json.dumps(TOOL_CAPABILITIES[current_step.tool_name].model_dump(), indent=2)}

## CRITICAL INSTRUCTIONS
1. For **image_qna_agent**: Extract img_paths from the "Previous Tool Context" above (look for image paths or img_path values)
2. For **data_plotting_agent**: You MUST use a file from "Available Output Files" above
3. Do NOT invent or guess img_paths - use ONLY the ones mentioned in the context above
4. If img_paths are needed but not available in context, set action to "replan" with reason

## Your Task
Provide the exact arguments for the tool call using data from previous steps.
"""
        
        decision_maker = llm.with_structured_output(StepExecutionDecision)
        
        try:
            decision: StepExecutionDecision = decision_maker.invoke([
                SystemMessage(content=decision_prompt),
                HumanMessage(content=f"Execute: {current_step.description}")
            ])
            
            if decision.action == "skip":
                # Skip this step
                updated_steps = state["plan_steps"].copy()
                updated_steps[current_idx].status = "skipped"
                
                return {
                    "plan_steps": updated_steps,
                    "current_step_index": current_idx + 1,
                    "step_results": [StepResult(
                        step_number=current_step.step_number,
                        success=True,
                        result_content=f"Skipped: {decision.skip_reason}"
                    )],
                    "messages": state.get("messages", []) + [
                        AIMessage(content=f"⏭️ Skipped step {current_step.step_number}: {decision.skip_reason}")
                    ]
                }
            
            elif decision.action == "replan":
                return {
                    "feedback": decision.replan_reason,
                    "pending_interrupt": True
                }
            
            else:  # execute
                # Update step status
                updated_steps = state["plan_steps"].copy()
                updated_steps[current_idx].status = "in_progress"
                
                # Execute the tool - now returns both result and context string
                tool_args = decision.get_tool_call_args() or {}
                current_context = state.get("tool_context", "")
                result, context = _execute_tool(current_step.tool_name, tool_args, current_context)
                result.step_number = current_step.step_number
                
                # Update step status based on result
                if result.success:
                    updated_steps[current_idx].status = "completed"
                    updated_steps[current_idx].result_summary = result.result_content[:200]
                    if result.output_file:
                        updated_steps[current_idx].output_file = result.output_file
                    
                    # Collect generated files
                    generated_files = list(state.get("generated_files", []))
                    if result.output_file:
                        generated_files.append(result.output_file)
                    
                    return {
                        "plan_steps": updated_steps,
                        "current_step_index": current_idx + 1,
                        "completed_steps": state.get("completed_steps", 0) + 1,
                        "step_results": [result],
                        "tool_context": context,  # Store context for downstream tools
                        "generated_files": generated_files,
                        "messages": state.get("messages", []) + [
                            AIMessage(content=f"✅ Step {current_step.step_number} completed:\n{result.result_content[:500]}...")
                        ]
                    }
                else:
                    updated_steps[current_idx].status = "failed"
                    
                    return {
                        "plan_steps": updated_steps,
                        "step_results": [result],
                        "tool_context": context,  # Store context even for failed steps
                        "feedback": f"Step {current_step.step_number} failed: {result.error_message}",
                        "pending_interrupt": True,
                        "messages": state.get("messages", []) + [
                            AIMessage(content=f"❌ Step {current_step.step_number} failed: {result.error_message}")
                        ]
                    }
                    
        except Exception as e:
            return {
                "feedback": f"Execution decision failed: {str(e)}",
                "pending_interrupt": True
            }
    
    return executor_node


def _execute_tool(tool_name: str, args: Dict[str, Any], tool_context: str = "") -> tuple[StepResult, str]:
    """Execute a tool and return the result with context string."""
    
    if tool_name == "database_exploration_agent":
        query = args.get("query", "")
        return execute_data_exploration(query)
    
    elif tool_name == "image_qna_agent":
        query = args.get("query", "")
        img_paths = args.get("img_path", [])
        if isinstance(img_paths, str):
            img_paths = [img_paths]
        return execute_image_qna(query, img_paths, tool_context)
    
    elif tool_name == "data_plotting_agent":
        task = args.get("task", "")
        file_path = args.get("file_path", "")
        return execute_plotting(task, file_path)
    
    else:
        step_result = StepResult(
            step_number=0,
            success=False,
            error_message=f"Unknown tool: {tool_name}"
        )
        return step_result, f"## Error\n\nUnknown tool: {tool_name}"


# ============================================================================
# NODE: AGGREGATOR
# ============================================================================

def create_aggregator_node(llm):
    """Create the final answer aggregation node."""
    
    def aggregator_node(state: MainAgentState):
        """Aggregate all step results into a final answer."""
        
        # Format all results
        all_results = _format_step_results(state.get("step_results", []))
        generated_files = state.get("generated_files", [])
        
        aggregation_prompt = f"""You are summarizing the results of an executed plan.

## Original User Query
{state.get("original_query", "Unknown")}

## Executed Steps and Results
{all_results}

## Generated Files
{json.dumps(generated_files) if generated_files else "None"}

## Your Task
Create a comprehensive final answer that:
1. Directly answers the user's original question
2. Summarizes what was discovered
3. References any generated files (CSV data, plots)
4. Notes any limitations or caveats
"""
        
        aggregator = llm.with_structured_output(FinalAnswer)
        
        try:
            answer: FinalAnswer = aggregator.invoke([
                SystemMessage(content=aggregation_prompt),
                HumanMessage(content="Create the final answer")
            ])
            
            # Format the final message
            final_content = f"""## Summary
{answer.summary}

## Detailed Answer
{answer.detailed_answer}
"""
            
            if answer.generated_files:
                final_content += f"\n## Generated Files\n" + "\n".join([f"- {f}" for f in answer.generated_files])
            
            if answer.limitations:
                final_content += f"\n## Limitations\n{answer.limitations}"
            
            return {
                "final_answer": final_content,
                "execution_complete": True,
                "messages": state.get("messages", []) + [
                    AIMessage(content=final_content)
                ]
            }
            
        except Exception as e:
            # Fallback: simple concatenation
            simple_answer = f"Completed {state.get('completed_steps', 0)} of {state.get('total_steps', 0)} steps.\n\n"
            simple_answer += all_results
            
            return {
                "final_answer": simple_answer,
                "execution_complete": True,
                "messages": state.get("messages", []) + [
                    AIMessage(content=simple_answer)
                ]
            }
    
    return aggregator_node


# ============================================================================
# NODE: INTERRUPT HANDLER
# ============================================================================

def interrupt_for_replan_node(state: MainAgentState) -> Command[Literal["planner", "aggregator"]]:
    """Handle interrupts and decide whether to replan."""
    
    # Check replan limit
    if state.get("replan_count", 0) >= state.get("max_replans", 3):
        # Too many replans, go to aggregator with what we have
        return Command(
            goto="aggregator",
            update={
                "feedback": None,
                "pending_interrupt": False,
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"⚠️ Maximum replans ({state.get('max_replans', 3)}) reached. Providing partial results.")
                ]
            }
        )
    
    # Ask user for approval
    is_approved = interrupt({
        "question": f"Plan needs revision. Feedback: {state.get('feedback', 'Unknown issue')}\n\nDo you want to replan?",
        "options": ["Yes, replan", "No, show partial results"]
    })
    
    if is_approved == "Yes, replan" or is_approved is True:
        return Command(
            goto="planner",
            update={
                "replan_count": state.get("replan_count", 0) + 1,
                "pending_interrupt": False
            }
        )
    else:
        return Command(
            goto="aggregator",
            update={
                "feedback": None,
                "pending_interrupt": False
            }
        )


# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_after_executor(state: MainAgentState) -> Literal["executor", "aggregator", "interrupt_for_replan"]:
    """Route based on executor result."""
    
    # Check for pending interrupt (error/replan needed)
    if state.get("pending_interrupt"):
        return "interrupt_for_replan"
    
    # Check if execution is complete
    if state.get("execution_complete"):
        return "aggregator"
    
    # Check if all steps are done
    current_idx = state.get("current_step_index", 0)
    total_steps = state.get("total_steps", 0)
    
    if current_idx >= total_steps:
        return "aggregator"
    
    # More steps to execute
    return "executor"


def route_after_planner(state: MainAgentState) -> Literal["executor", "interrupt_for_replan"]:
    """Route based on planner result."""
    
    if state.get("pending_interrupt"):
        return "interrupt_for_replan"
    
    if state.get("plan_steps"):
        return "executor"
    
    return "interrupt_for_replan"


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_main_agent(checkpointer=None):
    """Build the main agent graph."""
    
    llm = init_chat_model("gpt-4o-mini")
    
    # Create nodes
    planner = create_planner_node(llm)
    executor = create_executor_node(llm)
    aggregator = create_aggregator_node(llm)
    
    # Build graph
    builder = StateGraph(MainAgentState)
    
    # Add nodes
    builder.add_node("planner", planner)
    builder.add_node("executor", executor)
    builder.add_node("aggregator", aggregator)
    builder.add_node("interrupt_for_replan", interrupt_for_replan_node)
    
    # Add edges
    builder.add_edge(START, "planner")
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        ["executor", "interrupt_for_replan"]
    )
    builder.add_conditional_edges(
        "executor",
        route_after_executor,
        ["executor", "aggregator", "interrupt_for_replan"]
    )
    builder.add_edge("aggregator", END)
    # interrupt_for_replan uses Command to route
    
    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def initialize_agent_with_checkpointer():
    """Initialize the main agent with a MemorySaver checkpointer."""
    checkpointer = MemorySaver()
    agent = build_main_agent(checkpointer)
    return agent, checkpointer


def create_thread_config(thread_id: str) -> dict:
    """Create a configuration dictionary for a specific thread."""
    return {"configurable": {"thread_id": thread_id}}


# ============================================================================
# TESTING
# ============================================================================

# Initialize default agent
main_agent = build_main_agent(MemorySaver())


if __name__ == "__main__":
    # Example usage
    questions = [
        "What is the oldest painting in the database?",
        # "Which genre has the most paintings?",
        # "Analyze the colors in Renaissance paintings and create a summary",
    ]
    
    config = {"configurable": {"thread_id": "dev-test"}}
    
    for question in questions:
        print(f"\n{'='*60}")
        print(f"Question: {question}")
        print('='*60)
        
        initial_state = {
            "messages": [HumanMessage(content=question)],
            "original_query": question
        }
        
        for step in main_agent.stream(
            initial_state,
            stream_mode="values",
            config=config,
        ):
            if step.get("messages"):
                print("\n--- Message ---")
                step["messages"][-1].pretty_print()
