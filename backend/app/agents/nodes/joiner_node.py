# """Joiner Node - Decides whether to finish or replan"""
# from typing import Dict, Any, Union, List, Optional
# from langchain_core.messages import AIMessage, SystemMessage, ToolMessage, HumanMessage
# from app.agents.state import ExplainableAgentState
# from pydantic import BaseModel, Field
# import logging
# import json

# logger = logging.getLogger(__name__)


# class FinalResponse(BaseModel):
#     """Final response to user"""
#     response: str


# class Replan(BaseModel):
#     """Feedback for complete replanning (starting over)"""
#     feedback: str = Field(description="Why we need to completely replan from scratch")


# class ContinuePlan(BaseModel):
#     """Continue with additional steps to complete the task"""
#     feedback: str = Field(description="What's missing and what additional steps are needed to complete the task")


# class ReasoningStep(BaseModel):
#     """Single step in the reasoning chain"""
#     step_number: int = Field(description="Sequential step number")
#     tool_used: str = Field(description="Tool that was executed")
#     what_happened: str = Field(description="Brief description of what this step accomplished")
#     key_finding: Optional[str] = Field(default=None, description="Most important result or insight from this step")


# class JoinerDecision(BaseModel):
#     """Joiner decision with reasoning chain"""
#     thought: str = Field(description="Overall synthesis: how all steps work together to answer the query")
#     reasoning_chain: List[ReasoningStep] = Field(description="Step-by-step breakdown of what happened in each execution step")
#     action: Union[FinalResponse, ContinuePlan, Replan]


# class JoinerNode:
    
#     def __init__(self, llm):
#         self.llm = llm
    
#     def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        
#         group_results = state.get("group_results", {})
#         query = state.get("query", "")
#         task_groups = state.get("task_groups", [])
#         steps = state.get("steps", [])  # Get executed steps
   
#         # Build steps summary for LLM
#         steps_summary = self._build_steps_summary(steps)
        
#         # System message: General instructions and role definition
#         system_instructions = """You are an execution analyzer for a data exploration agent.

# Your job is to:
# 1. **Build a reasoning chain**: For each step that was executed, create a ReasoningStep with:
#    - step_number: Sequential number (1, 2, 3...)
#    - tool_used: Name of the tool that was executed
#    - what_happened: Brief, clear description of what this step accomplished
#    - key_finding: **Detailed** result with specific data points, numbers, or insights (REQUIRED for every step)

# 2. **Provide overall thought**: Synthesize how all steps work together to answer the query
#    - Explain the narrative: how steps connect to each other
#    - State whether we successfully answered the query
#    - If finishing: what the final answer is
#    - If continuing/replanning: what's missing or what went wrong

# 3. **Decide next action**:
#    - **FinalResponse**: If we have sufficient information to fully answer the query
#      * CRITICAL: Check if the ORIGINAL QUERY asked for visualization/plotting/charts
#      * If query mentions "plot", "chart", "visualize", "graph" → Data retrieval alone is NOT sufficient
#      * Only use FinalResponse if ALL requested outputs have been generated
#    - **ContinuePlan**: If the current plan is on the right track but incomplete (e.g., missing visualization, missing final step)
#      * Use this when: Steps executed successfully but task isn't complete
#      * Example: Query asks to "plot X vs Y" but only data retrieval was done → ContinuePlan needed
#      * Example: Query asks to "plot X vs Y" but only data retrieval was done → ContinuePlan needed
#      * The planner will ADD steps to complete the task
#    - **Replan**: ONLY if the current approach is fundamentally wrong and we need to start over
#      * Use this when: Wrong tool used, wrong approach, or steps failed completely
#      * ⚠️ WARNING: This discards all progress and starts fresh
#      * If you can't solve it at all, use FinalResponse to explain why instead of Replan

# CRITICAL GUIDELINES FOR REASONING CHAIN:
# - **Be specific**: Don't say "executed successfully" - describe WHAT was found/created
# - **Extract detailed key findings**: Include specific numbers, counts, values, or concrete insights from EVERY step
# - **Show progression**: Make it clear how each step builds on the previous one
# - **Acknowledge failures**: If a step failed, explain what went wrong

# GUIDELINES FOR KEY FINDINGS:
# - ALWAYS include specific, measurable details (numbers, counts, names, values, ranges)
# - Mention WHAT was processed: data sources, objects, entities involved
# - Mention HOW MUCH: quantities, sizes, counts, percentages
# - Mention KEY RESULTS: specific outcomes, values discovered, patterns identified
# - For queries/searches: what was found, how many results, key attributes
# - For data operations: what changed, scale of change, affected items
# - For analysis/computation: actual values, ranges, statistical measures
# - For outputs/artifacts: what was created, format, key characteristics

# EXAMPLES OF GOOD REASONING STEPS:

# Step 1:
# - tool_used: "text2SQL"
# - what_happened: "Generated SQL query to find playlists with total track times"
# - key_finding: "Created query joining Playlist and Track tables, using SUM(Milliseconds) grouped by PlaylistId - targets 5 columns including Name and TotalDuration"

# Step 2:
# - tool_used: "sql_db_to_df"
# - what_happened: "Executed query and stored results as DataFrame"
# - key_finding: "Retrieved 5 playlists with durations ranging from 45 minutes (Jazz Favorites) to 150 minutes (Classical Mix) - total 25 tracks analyzed"

# Step 3:
# - tool_used: "smart_transform_for_viz"
# - what_happened: "Created interactive bar chart showing playlist durations"
# - key_finding: "Bar chart reveals Classical Mix (150 min) is 3.3x longer than shortest playlist, with clear visual hierarchy showing Rock Hits (90 min) as median"

# EXAMPLES OF BAD REASONING STEPS (avoid):
# - what_happened: "Executed tool" (too vague)
# - what_happened: "Got results" (not descriptive)
# - key_finding: "Success" (not informative)
# - key_finding: "Query returned data" (no specific details)
# - key_finding: "Retrieved 5 rows" (missing what those rows contain)"""
        
#         # Human message: Specific data to analyze
#         analysis_request = f"""Analyze the following execution results and provide your decision.

# **Original Query:** {query}

# **Executed Steps:**
# {steps_summary}

# **CRITICAL ANALYSIS REQUIRED:**
# 1. Compare the ORIGINAL QUERY against the EXECUTED STEPS
# 2. Did the original query ask for visualization, plotting, charts, or graphs?
# 3. If YES, were any visualization tools executed (smart_transform_for_viz, large_plotting_tool)?
# 4. If NO visualization was executed but the query requested it → Use ContinuePlan

# Please provide:
# 1. A detailed reasoning chain for each step
# 2. Your overall thought on how the steps work together
# 3. Your decision (FinalResponse, ContinuePlan, or Replan)"""
        
#         llm_with_structure = self.llm.with_structured_output(JoinerDecision)
        
#         messages = state.get("messages", [])
        
#         logger.info(f"Joiner received {len(messages)} messages")
#         for i, msg in enumerate(messages):
#             msg_type = type(msg).__name__
#             content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else "no content"
#             logger.info(f"  Message {i}: {msg_type} - {content_preview}")
        
     
#         tool_call_ids_to_skip = set()
#         for msg in messages:
#             if isinstance(msg, AIMessage) and msg.tool_calls:
#                 for tool_call in msg.tool_calls:
#                     tool_call_ids_to_skip.add(tool_call['id'])
        
#         filtered_messages = []
#         for msg in messages:
#             if hasattr(msg, 'type') and msg.type == 'system':
#                 continue
                
#             if isinstance(msg, AIMessage) and msg.tool_calls:
#                 continue
                
#             if isinstance(msg, ToolMessage) and msg.tool_call_id in tool_call_ids_to_skip:
#                 continue
                
#             filtered_messages.append(msg)
        
#         decision_messages = [
#             SystemMessage(content=system_instructions)
#         ] + filtered_messages + [
#             HumanMessage(content=analysis_request)
#         ]
        
#         decision = llm_with_structure.invoke(decision_messages)
        
#         # Format reasoning chain as JSON for frontend
#         reasoning_chain_json = self._format_reasoning_chain(decision.reasoning_chain)
        
#         if isinstance(decision.action, FinalResponse):
#             return {
#                 "joiner_decision": "finish",
#                 "assistant_response": decision.action.response,
#                 "messages": [
#                     AIMessage(content=decision.thought),
#                     AIMessage(
#                         content=reasoning_chain_json,
#                         additional_kwargs={"is_reasoning_chain": True}
#                     ),
#                     AIMessage(content=decision.action.response)
#                 ]
#             }
#         elif isinstance(decision.action, ContinuePlan):
#             # Continue plan: pass thought and feedback to planner as context
#             return {
#                 "joiner_decision": "continue",
#                 "messages": [
#                     AIMessage(content=decision.thought),
#                     AIMessage(
#                         content=reasoning_chain_json,
#                         additional_kwargs={"is_reasoning_chain": True}
#                     ),
#                     HumanMessage(content=f"The task is not complete. {decision.action.feedback}")
#                 ]
#             }
#         else:  # Replan
#             return {
#                 "joiner_decision": "replan",
#                 "messages": [
#                     AIMessage(content=decision.thought),
#                     AIMessage(
#                         content=reasoning_chain_json,
#                         additional_kwargs={"is_reasoning_chain": True}
#                     ),
#                     HumanMessage(content=f"The current approach needs to be reconsidered. {decision.action.feedback}")
#                 ]
#             }
    
#     def _build_execution_results(self, task_groups: list, group_results: Dict[int, Any]) -> str:
#         lines = []
        
#         for idx, group in enumerate(task_groups):
#             result = group_results.get(idx, "Not executed")
            
#             lines.append(f"**Group {idx + 1}:**")
            
#             if isinstance(result, str):
#                 result_lines = result.split('\n')
#                 current_tool = None
                
#                 for line in result_lines:
#                     if ' result: ' in line:
#                         tool_name, output = line.split(' result: ', 1)
#                         truncated_output = output[:2000] + '...' if len(output) > 2000 else output
#                         lines.append(f"  - {tool_name}: {truncated_output}")
#             else:
#                 lines.append(f"  Result: {str(result)[:2000]}")
            
#             lines.append("")
        
#         return "\n".join(lines)
    
#     def _build_steps_summary(self, steps: List[Dict[str, Any]]) -> str:
#         """Build a summary of executed steps for the LLM to analyze"""
#         if not steps:
#             return "No steps executed yet."
        
#         lines = []
#         for idx, step in enumerate(steps):
#             tool_name = step.get("tool_name", "unknown")
#             decision = step.get("decision", "")
#             reasoning = step.get("reasoning", "")
#             data_evidence = step.get("data_evidence", "")
            
#             # Handle multi-tool steps
#             if step.get("type") == "multi_tool":
#                 tool_names = step.get("tool_names", [tool_name])
#                 lines.append(f"**Step {idx + 1}: {', '.join(tool_names)}**")
                
#                 # Show inputs and outputs for each tool in multi-tool step
#                 inputs = step.get("inputs", [])
#                 outputs = step.get("outputs", [])
#                 for i, tn in enumerate(tool_names):
#                     tool_input = inputs[i] if i < len(inputs) else {}
#                     tool_output = outputs[i] if i < len(outputs) else "No output"
                    
#                     # Truncate long outputs
#                     tool_output_str = str(tool_output)[:500] + "..." if len(str(tool_output)) > 500 else str(tool_output)
                    
#                     lines.append(f"  Tool {i+1} ({tn}):")
#                     lines.append(f"    Input: {json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)}")
#                     lines.append(f"    Output: {tool_output_str}")
#             else:
#                 lines.append(f"**Step {idx + 1}: {tool_name}**")
                
#                 # Show input and output for single-tool step
#                 tool_input = step.get("input", step.get("inputs", [{}])[0] if step.get("inputs") else {})
#                 tool_output = step.get("output", step.get("outputs", ["No output"])[0] if step.get("outputs") else "No output")
                
#                 # Truncate long outputs
#                 tool_output_str = str(tool_output)[:500] + "..." if len(str(tool_output)) > 500 else str(tool_output)
                
#                 lines.append(f"  Input: {tool_input if isinstance(tool_input, str) else json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)}")
#                 lines.append(f"  Output: {tool_output_str}")
            
#             if decision:
#                 lines.append(f"  Decision: {decision}")
#             if reasoning:
#                 lines.append(f"  Reasoning: {reasoning[:200]}")  # Truncate long reasoning
#             if data_evidence:
#                 lines.append(f"  Evidence: {data_evidence}")
#             lines.append("")
        
#         return "\n".join(lines)
    
#     def _format_reasoning_chain(self, reasoning_steps: List[ReasoningStep]) -> str:
#         """Format reasoning chain as JSON for frontend display"""
#         chain_data = {
#             "type": "reasoning_chain",
#             "steps": [
#                 {
#                     "step_number": step.step_number,
#                     "tool_used": step.tool_used,
#                     "what_happened": step.what_happened,
#                     "key_finding": step.key_finding
#                 }
#                 for step in reasoning_steps
#             ]
#         }
        
#         return json.dumps(chain_data)
