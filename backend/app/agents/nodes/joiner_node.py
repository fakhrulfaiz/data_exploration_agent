"""Joiner Node - Decides whether to finish or replan"""
from typing import Dict, Any, Union
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from app.agents.state import ExplainableAgentState
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class FinalResponse(BaseModel):
    """Final response to user"""
    response: str


class Replan(BaseModel):
    """Feedback for replanning"""
    feedback: str = Field(description="Why we need to replan")


class JoinerDecision(BaseModel):
    """Joiner decision"""
    thought: str = Field(description="Chain of thought reasoning")
    action: Union[FinalResponse, Replan]


class JoinerNode:
    """Combines group results and decides next action"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Analyze group results and decide: finish or replan"""
        
        group_results = state.get("group_results", {})
        query = state.get("query", "")
        task_groups = state.get("task_groups", [])
        
        # Build context from group results
        context = self._build_context(task_groups, group_results)
        
        # Prompt for joiner
        joiner_prompt = f"""Analyze the execution results and decide whether to finish or replan.

Original Query: {query}

Executed Groups & Results:
{context}

Your job is to:
1. **Analyze the results**: What was actually accomplished? Did the tools succeed or fail? What data/insights were obtained?
2. **Assess completeness**: Do we have enough information to answer the original query?
3. **Decide next action**:
   - FinalResponse: If we have sufficient information to answer the query
   - Replan: If we need to try a different approach or gather more information

CRITICAL GUIDELINES:
- **Be specific about results**: Don't just say "executed successfully" - describe WHAT was found/created
- **Acknowledge failures**: If tools failed, explain what went wrong
- **Assess data quality**: Comment on whether the results are useful for answering the query
- **Be honest about limitations**: If results are partial or incomplete, say so
- **Consider the original query**: Does what we have actually answer what was asked?

Examples of GOOD analysis:
- "The query returned 5 playlists with their total track times. The data shows Classical Mix has the longest duration at 2.5 hours."
- "The SQL query failed because the 'duration' column doesn't exist. We need to replan using the correct schema."
- "We successfully retrieved 100 customer records, but the query asked for a visualization which we haven't created yet."

Examples of BAD analysis (avoid these):
- "All tasks executed successfully" (too vague)
- "The plan worked" (doesn't describe results)
- "Everything is done" (doesn't assess if query is answered)

Provide your decision:"""
        
        # Get structured response
        llm_with_structure = self.llm.with_structured_output(JoinerDecision)
        
        messages = state.get("messages", [])
        
        # Filter out tool messages and system messages to avoid OpenAI validation errors
        filtered_messages = []
        for msg in messages:
            # Skip system messages (we add our own)
            if hasattr(msg, 'type') and msg.type == 'system':
                continue
                
            # Skip ToolMessages
            if isinstance(msg, ToolMessage):
                continue
                
            # Skip AIMessages with tool_calls
            if isinstance(msg, AIMessage) and msg.tool_calls:
                continue
                
            filtered_messages.append(msg)
        
        decision_messages = [
            SystemMessage(content=joiner_prompt)
        ] + filtered_messages
        
        decision = llm_with_structure.invoke(decision_messages)
        
        # Process decision
        if isinstance(decision.action, FinalResponse):
            return {
                "joiner_decision": "finish",
                "assistant_response": decision.action.response,
                "messages": [
                    AIMessage(content=f"Thought: {decision.thought}"),
                    AIMessage(content=decision.action.response)
                ]
            }
        else:
            return {
                "joiner_decision": "replan",
                "messages": [
                    AIMessage(content=f"Thought: {decision.thought}"),
                    SystemMessage(content=f"Replan needed: {decision.action.feedback}")
                ]
            }
    
    def _build_context(self, task_groups: list, group_results: Dict[int, Any]) -> str:
        """Build readable context from group results"""
        lines = []
        
        for idx, group in enumerate(task_groups):
            result = group_results.get(idx, "Not executed")
            
            lines.append(f"Group {idx + 1}: {', '.join(group)}")
            lines.append(f"  Result: {str(result)[:1000]}")  # Show more context
            lines.append("")
        
        return "\n".join(lines)
