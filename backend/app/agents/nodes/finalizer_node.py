"""Finalizer Node - Evaluates execution results and always finishes"""
from typing import Dict, Any, List, Optional
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage, HumanMessage
from app.agents.state import ExplainableAgentState
import logging
import json

logger = logging.getLogger(__name__)


class FinalizerNode:   
    def __init__(self, llm, error_explainer=None):
        self.llm = llm
        self.error_explainer = error_explainer
    
    def execute(self, state: ExplainableAgentState) -> Dict[str, Any]:
        query = state.get("query", "")
        steps = state.get("steps", [])
        messages = state.get("messages", [])
        use_explainer = state.get("use_explainer", True)
        status = state.get("status")
        error_details = state.get("error_details", [])
        user_id = state.get("user_id")  # Extract user_id for preferences
        
        # Handle cancellation with error explanation
        if status == "cancelled" and error_details and self.error_explainer:
            logger.info("Generating friendly error summary for cancelled execution")
            
            explanation = self.error_explainer.explain_error(
                error_info=error_details[0],
                conversation_messages=messages
            )
            
            # Create friendly cancellation message
            cancel_message = f"""**Execution Cancelled**

**What happened:** {explanation.what_happened}

**Why it happened:** {explanation.why_it_happened}

**What you can try next:**
{chr(10).join(f"- {suggestion}" for suggestion in explanation.alternative_suggestions)}

{explanation.user_action_needed}
"""
            
            return {
                "assistant_response": cancel_message,
                "messages": [AIMessage(content=cancel_message)]
            }
        
        # Build steps summary for LLM
        steps_summary = self._build_steps_summary(steps)
        
        if use_explainer:
            # Two-step process: thought + reasoning chain, then final response
            return self._execute_with_explainer(query, steps, steps_summary, messages, user_id)
        else:
            # Simple process: just final response
            return self._execute_simple(query, steps_summary, messages, user_id)
    
    
    def _execute_with_explainer(
        self, 
        query: str, 
        steps: List[Dict[str, Any]], 
        steps_summary: str, 
        messages: List,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute with full explainability: thought + reasoning chain + final response"""
        
        # Step 1: Generate thought (still use LLM for synthesis)
        thought_prompt = self._build_thought_prompt(query, steps_summary)
        thought_message = self._generate_thought_only(thought_prompt, user_id)
    
        # Step 2: Build reasoning chain directly from steps (no LLM)
        reasoning_chain = self._build_reasoning_chain_from_steps(steps)
        reasoning_chain_json = self._format_reasoning_chain(reasoning_chain)
        
        # Create reasoning message
        reasoning_message = AIMessage(
            content=reasoning_chain_json,
            additional_kwargs={"is_reasoning_chain": True}
        )
        
        # Step 3: Generate final response AFTER creating thought/reasoning messages
        # This ensures thought and reasoning stream before final response
        final_response_text = self._generate_final_response(
            query=query,
            thought=thought_message.content,
            steps_summary=steps_summary,
            user_id=user_id
        )
        
        logger.info(f"Finalizer completed with {len(reasoning_chain)} reasoning steps")
    
        # Mark thought message with special flag
        thought_message.additional_kwargs = {"is_thought": True}
        
        return {
            "assistant_response": final_response_text,
            "messages": [
                thought_message, 
                reasoning_message,
                AIMessage(content=final_response_text) # Append final response to messages
            ]
        }
    
    def _execute_simple(
        self, 
        query: str, 
        steps_summary: str, 
        messages: List,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        
        final_response_text = self._generate_final_response(
            query=query,
            thought=None,  # No thought when explainer is off
            steps_summary=steps_summary,
            user_id=user_id
        )
        
        logger.info("Finalizer completed (simple mode)")
        
        return {
            "assistant_response": final_response_text,
            "messages": [
                AIMessage(content=final_response_text)
            ]
        }
    
    def _get_thought_system_prompt(self, user_id: Optional[str] = None) -> str:
        from app.agents.prompts.finalizer_prompts import get_finalizer_thought_system_prompt
        from app.agents.prompts.user_preferences import get_user_preference_prompt_safe
        
        # Fetch user preferences if available
        user_preferences = ""
        if user_id:
            try:
                from app.services.dependencies import get_redis_profile_service, get_profile_service
                
                redis_service = get_redis_profile_service()
                profile_service = get_profile_service()
                user_preferences = get_user_preference_prompt_safe(
                    user_id,
                    redis_service,
                    profile_service
                )
            except Exception as e:
                logger.warning(f"Failed to fetch user preferences in finalizer: {e}")
        
        return get_finalizer_thought_system_prompt(user_preferences)
    
    def _generate_thought_only(self, thought_prompt: str, user_id: Optional[str] = None):
        """Generate thought synthesis using structured output"""
        from pydantic import BaseModel, Field
        
        class ThoughtOnly(BaseModel):
            thought: str = Field(description="Overall synthesis of all steps and whether ready for final response")
        
        llm_with_thought = self.llm.with_structured_output(ThoughtOnly)
        result = llm_with_thought.invoke([
            SystemMessage(content=self._get_thought_system_prompt(user_id)),
            HumanMessage(content=thought_prompt)
        ])
        
        # Return AIMessage with the thought content
        return AIMessage(content=result.thought)
    
    def _build_reasoning_chain_from_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
     
        reasoning_chain = []
        
        for idx, step in enumerate(steps):
            tool_calls = step.get("tool_calls", [])
            if not tool_calls:
                continue
            
            # Get tool name from first tool call
            tool_name = tool_calls[0].get("tool_name", "unknown")
            
            # Get execution status from step
            task_status = step.get("task_completion_status", "unknown")
            execution_summary = step.get("execution_summary", "")
            data_evidence = step.get("data_evidence", "")
            
            # Check if any tool call had an error
            has_error = any(tc.get("has_error", False) for tc in tool_calls)
            
            # Build what_happened from execution summary or fallback
            if execution_summary:
                what_happened = execution_summary
            elif has_error:
                what_happened = f"Attempted to execute {tool_name} but encountered an error"
            else:
                what_happened = f"Executed {tool_name}"
            
            # Build key_finding from data evidence or status
            key_finding = None
            if has_error:
                # Extract error message from first failed tool call
                for tc in tool_calls:
                    if tc.get("has_error"):
                        output = tc.get("output", "")
                        # Try to parse error from output
                        try:
                            import json
                            output_data = json.loads(output)
                            if isinstance(output_data, dict) and "error" in output_data:
                                key_finding = f"Error: {output_data.get('error', 'Unknown error')}"
                                break
                        except:
                            key_finding = f"Error occurred during execution"
                        break
            elif data_evidence:
                key_finding = data_evidence
            elif task_status == "success":
                key_finding = "Completed successfully"
            
            reasoning_chain.append({
                "step_number": idx + 1,
                "tool_used": tool_name,
                "what_happened": what_happened,
                "key_finding": key_finding,
                "status": task_status,
                "has_error": has_error
            })
        
        return reasoning_chain
    
    
    def _build_thought_prompt(self, query: str, steps_summary: str) -> str:
        return f"""Analyze the following execution:

**Original User Query:** {query}

**Executed Steps:**
{steps_summary}

Provide an overall synthesis starting with "Thought:":
- How do all the steps work together?
- Did we successfully answer the user's query?
- Are we ready for the final response?
- Any limitations or gaps?"""
    
    def _generate_final_response(
        self, 
        query: str, 
        thought: Optional[str], 
        steps_summary: str, 
        user_id: Optional[str] = None
    ) -> str:
        """Generate final response to user using structured output"""
        from app.agents.prompts.finalizer_prompts import get_finalizer_response_system_prompt, get_finalizer_response_prompt
        from app.agents.prompts.user_preferences import get_user_preference_prompt_safe
        from pydantic import BaseModel, Field
        
        # Defined structured output schema
        class FinalResponse(BaseModel):
            response: str = Field(description="The comprehensive final response to the user's query, incorporating all findings.")
        
        # Fetch user preferences if available
        user_preferences = ""
        if user_id:
            try:
                from app.services.dependencies import get_redis_profile_service, get_profile_service
                
                redis_service = get_redis_profile_service()
                profile_service = get_profile_service()
                user_preferences = get_user_preference_prompt_safe(
                    user_id,
                    redis_service,
                    profile_service
                )
            except Exception as e:
                logger.warning(f"Failed to fetch user preferences in finalizer response: {e}")
        
        # Use placeholder if no thought provided
        thought_text = thought if thought else "No detailed thought process available."
        
        # Build prompt using template
        system_prompt = get_finalizer_response_system_prompt(user_preferences)
        prompt = get_finalizer_response_prompt(query, thought_text, steps_summary, user_preferences)
        
        # Use structured output to enforce clean response
        llm_with_structure = self.llm.with_structured_output(FinalResponse)
        
        try:
            result = llm_with_structure.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            return result.response
        except Exception as e:
            logger.error(f"Structured output failed for final response: {e}")
            # Fallback to raw string
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            return response.content
    
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
                tool_output_str = str(tool_output)
                
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
    
    def _format_reasoning_chain(self, reasoning_steps: List[Dict[str, Any]]) -> str:
        """Format reasoning chain as JSON for frontend display"""
        chain_data = {
            "type": "reasoning_chain",
            "steps": [
                {
                    "step_number": step.get("step_number"),
                    "tool_used": step.get("tool_used"),
                    "what_happened": step.get("what_happened"),
                    "key_finding": step.get("key_finding"),
                    "status": step.get("status", "unknown"),
                    "has_error": step.get("has_error", False)
                }
                for step in reasoning_steps
            ]
        }
        
        return json.dumps(chain_data)



