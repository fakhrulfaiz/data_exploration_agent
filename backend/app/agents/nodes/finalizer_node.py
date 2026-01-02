"""Finalizer Node - Evaluates execution results and always finishes"""
from typing import Dict, Any, List, Optional
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage, HumanMessage
from app.agents.state import ExplainableAgentState
from pydantic import BaseModel, Field
import logging
import json

logger = logging.getLogger(__name__)


class ReasoningStep(BaseModel):
    step_number: int = Field(description="Sequential step number")
    tool_used: str = Field(description="Tool that was executed")
    what_happened: str = Field(description="Brief description of what this step accomplished")
    key_finding: Optional[str] = Field(default=None, description="Most important result or insight from this step")


class FinalizerDecision(BaseModel):
    thought: str = Field(description="Overall synthesis: how all steps work together to answer the query")
    reasoning_chain: List[ReasoningStep] = Field(description="Step-by-step breakdown of what happened in each execution step")
    final_response: str = Field(description="Final response to the user summarizing the results")


class FinalizerNode:   
    def __init__(self, llm):
        self.llm = llm
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        query = state.get("query", "")
        steps = state.get("steps", [])
        messages = state.get("messages", [])
        
        # Build steps summary for LLM
        steps_summary = self._build_steps_summary(steps)
        
        # Build system instructions and analysis request
        system_instructions = self._build_system_instructions()
        analysis_request = self._build_analysis_request(query, steps_summary)


        
        llm_with_structure = self.llm.with_structured_output(FinalizerDecision)
        
        logger.info(f"Finalizer received {len(messages)} messages")
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else "no content"
            logger.info(f"  Message {i}: {msg_type} - {content_preview}")
        
        # Filter messages similar to joiner_node
        tool_call_ids_to_skip = set()
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_call_ids_to_skip.add(tool_call['id'])
        
        filtered_messages = []
        for msg in messages:
            if hasattr(msg, 'type') and msg.type == 'system':
                continue
                
            if isinstance(msg, AIMessage) and msg.tool_calls:
                continue
                
            if isinstance(msg, ToolMessage) and msg.tool_call_id in tool_call_ids_to_skip:
                continue
                
            filtered_messages.append(msg)
        
        decision_messages = [
            SystemMessage(content=system_instructions)
        ] + filtered_messages + [
            HumanMessage(content=analysis_request)
        ]
        
        decision = llm_with_structure.invoke(decision_messages)
        
        # Format reasoning chain as JSON for frontend
        reasoning_chain_json = self._format_reasoning_chain(decision.reasoning_chain)
        
        logger.info(f"Finalizer completed evaluation with {len(decision.reasoning_chain)} reasoning steps")
        
        # Always finish - return final response with reasoning chain
        return {
            "assistant_response": decision.final_response,
            "messages": [
                AIMessage(content= "Thought: " + decision.thought),
                AIMessage(
                    content=reasoning_chain_json,
                    additional_kwargs={"is_reasoning_chain": True}
                ),
                AIMessage(content=decision.final_response)
            ]
        }
    
    def _build_steps_summary(self, steps: List[Dict[str, Any]]) -> str:
        """Build a summary of executed steps for the LLM to analyze"""
        if not steps:
            return "No steps executed yet."
        
        lines = []
        for idx, step in enumerate(steps):
            tool_calls = step.get("tool_calls", [])
            if not tool_calls:
                continue
            
            # Get tool name from first tool call (all calls in a step use same tool)
            tool_name = tool_calls[0].get("tool_name", "unknown")
            decision = step.get("decision", "")
            reasoning = step.get("reasoning", "")
            data_evidence = step.get("data_evidence", "")
            
            # Header with tool name and call count
            if len(tool_calls) > 1:
                lines.append(f"**Step {idx + 1}: {tool_name}** ({len(tool_calls)} calls)")
            else:
                lines.append(f"**Step {idx + 1}: {tool_name}**")
            
            # Show each tool call's input and output
            for i, tc in enumerate(tool_calls):
                tool_input = tc.get("input", "{}")
                tool_output = tc.get("output", "No output")
                
                # Truncate long outputs
                tool_output_str = str(tool_output)[:500] + "..." if len(str(tool_output)) > 500 else str(tool_output)
                
                if len(tool_calls) > 1:
                    lines.append(f"  Call {i+1}:")
                    lines.append(f"    Input: {tool_input}")
                    lines.append(f"    Output: {tool_output_str}")
                else:
                    lines.append(f"  Input: {tool_input}")
                    lines.append(f"  Output: {tool_output_str}")
            
            # Add step-level metadata
            if decision:
                lines.append(f"  Decision: {decision}")
            if reasoning:
                lines.append(f"  Reasoning: {reasoning[:200]}")  # Truncate long reasoning
            if data_evidence:
                lines.append(f"  Evidence: {data_evidence}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_reasoning_chain(self, reasoning_steps: List[ReasoningStep]) -> str:
        """Format reasoning chain as JSON for frontend display"""
        chain_data = {
            "type": "reasoning_chain",
            "steps": [
                {
                    "step_number": step.step_number,
                    "tool_used": step.tool_used,
                    "what_happened": step.what_happened,
                    "key_finding": step.key_finding
                }
                for step in reasoning_steps
            ]
        }
        
        return json.dumps(chain_data)
    
    def _build_system_instructions(self) -> str:
        """
        Build system instructions for the finalizer LLM.
        
        This method is separated for easy customization and extension.
        Override this method to customize the prompt for specific use cases.
        """
        role_definition = self._get_role_definition()
        tasks = self._get_tasks()
        guidelines = self._get_guidelines()
        examples = self._get_examples()
        
        return f"""{role_definition}

{tasks}

{guidelines}

{examples}"""
    
    def _get_role_definition(self) -> str:
        """Define the role of the execution analyzer."""
        return "You are an execution analyzer for a data exploration agent."
    
    def _get_tasks(self) -> str:
        """Define the main tasks for the analyzer."""
        return """Your job is to:
1. **Build a reasoning chain**: For each step that was executed, create a ReasoningStep with:
   - step_number: Sequential number (1, 2, 3...)
   - tool_used: Name of the tool that was executed
   - what_happened: Brief, clear description of what this step accomplished
   - key_finding: **Detailed** result with specific data points, numbers, or insights (REQUIRED for every step)

2. **Provide overall thought**: Synthesize how all steps work together to answer the query
   - Explain the narrative: how steps connect to each other
   - State whether we successfully answered the query
   - Summarize what was accomplished

3. **Generate final response**: Create a comprehensive response to the user that:
   - Directly answers their original query
   - Summarizes key findings from all steps
   - Mentions any visualizations or outputs created
   - Acknowledges any limitations or partial results"""
    
    def _get_guidelines(self) -> str:
        return """CRITICAL GUIDELINES FOR REASONING CHAIN:
- **Be specific**: Don't say "executed successfully" - describe WHAT was found/created
- **Extract detailed key findings**: Include specific numbers, counts, values, or concrete insights from EVERY step
- **Show progression**: Make it clear how each step builds on the previous one
- **Acknowledge failures**: If a step failed, explain what went wrong

GUIDELINES FOR KEY FINDINGS:
- ALWAYS include specific, measurable details (numbers, counts, names, values, ranges)
- Mention WHAT was processed: data sources, objects, entities involved
- Mention HOW MUCH: quantities, sizes, counts, percentages
- Mention KEY RESULTS: specific outcomes, values discovered, patterns identified
- For queries/searches: what was found, how many results, key attributes
- For data operations: what changed, scale of change, affected items
- For analysis/computation: actual values, ranges, statistical measures
- For outputs/artifacts: what was created, format, key characteristics

FINAL RESPONSE GUIDELINES:
- Start with a direct answer to the user's query
- Be conversational and helpful
- Include specific findings and numbers
- Mention any visualizations or files created
- If the task was only partially completed, be honest about it
- Keep it concise but informative"""
    
    def _get_examples(self) -> str:
        """Provide examples of good and bad reasoning steps."""
        return """EXAMPLES OF GOOD REASONING STEPS:

Step 1 (Data Retrieval):
- tool_used: "Data Retrieval name"
- what_happened: "Generated and executed query to retrieve data based on user criteria"
- key_finding: "Retrieved 1,247 records across 5 columns (ID, Name, Value, Date, Category), date range: 2023-01-01 to 2024-12-31, covering 3 distinct categories"

Step 2 (Data Processing):
- tool_used: "Data Processing name"
- what_happened: "Processed and aggregated data by category"
- key_finding: "Aggregated 1,247 records into 3 category groups: Category A (523 records, avg value: 45.2), Category B (412 records, avg value: 67.8), Category C (312 records, avg value: 52.1)"

Step 3 (Visualization):
- tool_used: "Visualization name"
- what_happened: "Created interactive chart to display aggregated results"
- key_finding: "Generated bar chart showing category comparison with 3 bars, highlighting Category B as highest performer (67.8 avg), includes hover tooltips and interactive legend"

EXAMPLES OF BAD REASONING STEPS (avoid):
- what_happened: "Executed tool" (too vague - what did it do?)
- what_happened: "Got results" (not descriptive - what results?)
- what_happened: "Tool failed" (missing error details and impact)
- key_finding: "Success" (not informative - what was achieved?)
- key_finding: "Query returned data" (no specific details - how much? what kind?)
- key_finding: "Retrieved 5 rows" (missing what those rows contain)
- key_finding: "Error occurred" (missing what error, why it happened, what was the impact)"""
    
    def _build_analysis_request(self, query: str, steps_summary: str) -> str:
        """
        Build the analysis request message.
        
        Args:
            query: The original user query
            steps_summary: Summary of executed steps
            
        Returns:
            Formatted analysis request string
        """
        return f"""Analyze the following execution results and provide your evaluation.

**Original Query:** {query}

**Executed Steps:**
{steps_summary}

Please provide:
1. A detailed reasoning chain for each step
2. Your overall thought on how the steps work together
3. A final response to the user summarizing the results"""

