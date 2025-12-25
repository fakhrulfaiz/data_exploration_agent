"""Joiner Node - Decides whether to finish or replan"""
from typing import Dict, Any, Union
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage, HumanMessage
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
    thought: str = Field(description="Chain of thought reasoning with final decision if available")
    action: Union[FinalResponse, Replan]


class JoinerNode:
    
    def __init__(self, llm):
        self.llm = llm
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        
        group_results = state.get("group_results", {})
        query = state.get("query", "")
        task_groups = state.get("task_groups", [])
   
        joiner_prompt = f"""Analyze the execution results and decide whether to finish or replan.

Original Query: {query}

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
- "The query returned 5 playlists with their total track times. The data shows Classical Mix has the longest duration at 2.5 hours." (Mention the results in final answer)
- "The SQL query failed because the 'duration' column doesn't exist. We need to replan using the correct schema."
- "We successfully retrieved 100 customer records, but the query asked for a visualization which we haven't created yet."

Examples of BAD analysis (avoid these):
- "All tasks executed successfully" (too vague)
- "The plan worked" (doesn't describe results)
- "Everything is done" (doesn't assess if query is answered)

The execution results will be provided in the next message. Analyze them carefully."""
        
        llm_with_structure = self.llm.with_structured_output(JoinerDecision)
        
        messages = state.get("messages", [])
        
        logger.info(f"Joiner received {len(messages)} messages")
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else "no content"
            logger.info(f"  Message {i}: {msg_type} - {content_preview}")
        
     
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
        
        execution_results = self._build_execution_results(task_groups, group_results)
        
        execution_results_message = HumanMessage(
            content=f"""**Execution Results:**

{execution_results}

Please analyze these results and provide your decision."""
        )
        
        decision_messages = [
            SystemMessage(content=joiner_prompt)
        ] + filtered_messages + [execution_results_message]
        
        decision = llm_with_structure.invoke(decision_messages)
        
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
    
    def _build_execution_results(self, task_groups: list, group_results: Dict[int, Any]) -> str:
        lines = []
        
        for idx, group in enumerate(task_groups):
            result = group_results.get(idx, "Not executed")
            
            lines.append(f"**Group {idx + 1}:**")
            
            if isinstance(result, str):
                result_lines = result.split('\n')
                current_tool = None
                
                for line in result_lines:
                    if ' result: ' in line:
                        tool_name, output = line.split(' result: ', 1)
                        truncated_output = output[:2000] + '...' if len(output) > 2000 else output
                        lines.append(f"  - {tool_name}: {truncated_output}")
            else:
                lines.append(f"  Result: {str(result)[:2000]}")
            
            lines.append("")
        
        return "\n".join(lines)
