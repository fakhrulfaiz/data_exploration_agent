"""Finalizer Node - Evaluates execution results and always finishes"""
from typing import Dict, Any, List, Optional, Tuple
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
        error_explanation = state.get("error_explanation")  # Get error explanation if exists
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
            # Two-step process: thought + reasoning chain, then final response + actions
            return self._execute_with_explainer(query, steps, steps_summary, messages, user_id, error_explanation)
        else:
            # Simple process: just final response + actions
            return self._execute_simple(query, steps, steps_summary, messages, user_id, error_explanation)
    
    
    def _execute_with_explainer(
        self, 
        query: str, 
        steps: List[Dict[str, Any]], 
        steps_summary: str, 
        messages: List,
        user_id: Optional[str] = None,
        error_explanation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute with full explainability: thought + reasoning chain + final response + actions"""
        
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
        
        # Step 3: Generate final response & actions (LLM decides based on RAG patterns)
        # This returns a dict with 'response' and 'actions' fields
        final_output = self._generate_final_response(
            query=query,
            thought=thought_message.content,
            steps_summary=steps_summary,
            steps=steps,  # Pass raw steps for context building
            user_id=user_id,
            error_explanation=error_explanation  # Pass error explanation for context
        )
        
        # Extract the response text from the output
        final_response_text = final_output.get("response", "")
        
        # Extract context data
        df_id, plot_urls = self._extract_context_data(steps)
        
        # Step 4: Deterministic actions based on actual execution data
        # Export is available if we have a dataframe, download if we have plots
        actions = {
            "export_dataframe": {"df_id": df_id} if df_id else None,
            "download_plots": {"plot_urls": plot_urls} if plot_urls else None,
            "next_queries": final_output.get("next_queries", [])  # Keep LLM suggestions
        }
        
        # Combine response and actions into single JSON
        final_response_data = {
            "response": final_response_text,
            "actions": actions
        }
        final_response_json = json.dumps(final_response_data)
        
        # Create combined message with special flag
        final_response_message = AIMessage(
            content=final_response_json,
            additional_kwargs={"is_finalizer_response": True}
        )
        
        logger.info(f"Finalizer completed with {len(reasoning_chain)} reasoning steps and {len(actions.get('next_queries', []))} query suggestions")
    
        # Mark thought message with special flag
        thought_message.additional_kwargs = {"is_thought": True}
        
        return {
            "assistant_response": final_response_text,
            "messages": [
                thought_message, 
                reasoning_message,
                final_response_message  # Single combined message
            ]
        }
    
    def _execute_simple(
        self, 
        query: str, 
        steps: List[Dict[str, Any]],
        steps_summary: str, 
        messages: List,
        user_id: Optional[str] = None,
        error_explanation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        
        # Final response generation with LLM-decided actions
        final_output = self._generate_final_response(
            query=query,
            thought=None,  # No thought when explainer is off
            steps_summary=steps_summary,
            steps=steps, 
            user_id=user_id,
            error_explanation=error_explanation  # Pass error explanation for context
        )
        
        final_response_text = final_output.get("response", "")
        
        # Extract context data
        df_id, plot_urls = self._extract_context_data(steps)
        
        # Deterministic actions based on actual execution data
        actions = {
            "export_dataframe": {"df_id": df_id} if df_id else None,
            "download_plots": {"plot_urls": plot_urls} if plot_urls else None,
            "next_queries": final_output.get("next_queries", [])
        }
        
        # Combine response and actions into single JSON
        final_response_data = {
            "response": final_response_text,
            "actions": actions
        }
        final_response_json = json.dumps(final_response_data)
        
        final_response_message = AIMessage(
            content=final_response_json,
            additional_kwargs={"is_finalizer_response": True}
        )
        
        logger.info("Finalizer completed (simple mode)")
        
        return {
            "assistant_response": final_response_text,
            "messages": [
                final_response_message
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
        steps: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        error_explanation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        from app.agents.prompts.finalizer_prompts import get_finalizer_response_system_prompt, get_finalizer_response_prompt
        from app.agents.prompts.user_preferences import get_user_preference_prompt_safe
        from app.services.rag_service import get_rag_service
        from pydantic import BaseModel, Field
        
        # Defined structured output schema - only response and suggestions, actions are deterministic
        class FinalResponse(BaseModel):
            response: str = Field(description="The comprehensive final response to the user's query, incorporating all findings.")
            next_queries: List[str] = Field(description="3 suggested follow-up queries as actionable commands not follow up questions)")
        
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

        # Retrieve RAG patterns using execution context
        patterns = []
        try:
            rag = get_rag_service()
            # Build search context from actual tool usage
            search_context = self._build_execution_context_string(steps)
            logger.info(f"Retrieving finalizer patterns for context: {search_context}")
            
            patterns = rag.retrieve_finalizer_patterns(search_context)
            logger.info(f"Retrieved {len(patterns)} finalizer guidelines")
        except Exception as e:
            logger.warning(f"Failed to retrieve finalizer patterns: {e}")
        
        # Use placeholder if no thought provided
        thought_text = thought if thought else "No detailed thought process available."
        
        # Build prompt using template - patterns go in system prompt now
        system_prompt = get_finalizer_response_system_prompt(user_preferences, patterns)
        
        # Add error explanation context if available
        error_context = ""
        if error_explanation:
            error_context = f"""

**Error Explanation Context:**
The error explainer already provided this guidance to the user:
- What happened: {error_explanation.get('what_happened', '')}
- Why: {error_explanation.get('why_it_happened', '')}
- Clarifying questions: {', '.join(error_explanation.get('clarifying_questions', []))}
- Next step suggested: {error_explanation.get('next_step', '')}

Use this context to suggest relevant follow-up queries that align with the error explanation."""
        
        prompt = get_finalizer_response_prompt(query, thought_text, steps_summary, user_preferences) + error_context
        
        # Use structured output to enforce clean response
        llm_with_structure = self.llm.with_structured_output(FinalResponse)
        
        try:
            result = llm_with_structure.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            return result.model_dump()
        except Exception as e:
            logger.error(f"Structured output failed for final response: {e}")
            # Fallback to raw string
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])
            # Return dict with response only, safe defaults for actions
            return {
                "response": response.content,
                "export_dataframe": False,
                "download_images": False,
                "next_queries": []
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
        
    def _extract_context_data(self, steps: List[Dict[str, Any]]) -> Tuple[Optional[str], List[str]]:
        """Extract df_id and plot_urls from steps"""
        df_id = None
        plot_urls = []
        
        for step in steps:
            tool_calls = step.get("tool_calls", [])
            for tc in tool_calls:
                output = tc.get("output", "")
                
                # Try to parse output as JSON
                try:
                    if isinstance(output, str):
                        output_data = json.loads(output)
                    else:
                        output_data = output
                    
                    # Check for df_id (from data_exploration_tool, smart_data_analysis, etc.)
                    if isinstance(output_data, dict):
                        if "data_context" in output_data and isinstance(output_data["data_context"], dict):
                            current_df_id = output_data["data_context"].get("df_id")
                            if current_df_id: 
                                df_id = current_df_id
                        elif "df_id" in output_data:
                            current_df_id = output_data["df_id"]
                            if current_df_id:
                                df_id = current_df_id
                        
                        # Check for plot URLs
                        if "plot_url" in output_data:
                            plot_url = output_data["plot_url"]
                            if plot_url and plot_url.startswith("http"):
                                plot_urls.append(plot_url)
                except (json.JSONDecodeError, TypeError):
                    pass
                    
        return df_id, plot_urls


    # Dead code _determine_actions removed/replaced by above helper + LLM decisions
        
        # Check for DataFrame availability
        df_id = None
        plot_urls = []
        
        for step in steps:
            tool_calls = step.get("tool_calls", [])
            for tc in tool_calls:
                output = tc.get("output", "")
                
                # Try to parse output as JSON
                try:
                    if isinstance(output, str):
                        output_data = json.loads(output)
                    else:
                        output_data = output
                    
                    # Check for df_id (from data_exploration_tool, smart_data_analysis, etc.)
                    if isinstance(output_data, dict):
                        if "data_context" in output_data and isinstance(output_data["data_context"], dict):
                            df_id = output_data["data_context"].get("df_id")
                        elif "df_id" in output_data:
                            df_id = output_data["df_id"]
                        
                        # Check for plot URLs (from large_plotting_tool)
                        if "plot_url" in output_data:
                            plot_url = output_data["plot_url"]
                            if plot_url and plot_url.startswith("http"):
                                plot_urls.append(plot_url)
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Set export action if DataFrame exists
        if df_id:
            actions["export_dataframe"] = {
                "enabled": True,
                "df_id": df_id
            }
        else:
            actions["export_dataframe"] = {
                "enabled": False,
                "reason": "No DataFrame available"
            }
        
        # Set download action if plots exist
        if plot_urls:
            actions["download_plots"] = {
                "enabled": True,
                "plot_urls": plot_urls,
                "count": len(plot_urls)
            }
        else:
            actions["download_plots"] = {
                "enabled": False,
                "reason": "No plots generated"
            }
        
        # Generate next query suggestions
        actions["next_queries"] = self._generate_next_queries(steps, query)
        
        return actions
    
    def _generate_next_queries(self, steps: List[Dict[str, Any]], original_query: str) -> List[str]:
        """Generate contextual next query suggestions"""
        suggestions = []
        
        # Analyze what tools were used
        tools_used = set()
        has_image_analysis = False
        has_plotting = False
        has_filtering = False
        
        for step in steps:
            tool_calls = step.get("tool_calls", [])
            for tc in tool_calls:
                tool_name = tc.get("tool_name", "")
                tools_used.add(tool_name)
                
                if "image" in tool_name.lower():
                    has_image_analysis = True
                if "plot" in tool_name.lower():
                    has_plotting = True
                if "transform" in tool_name.lower() or "filter" in original_query.lower():
                    has_filtering = True
        
        # Generate contextual suggestions
        if has_image_analysis and not has_plotting:
            suggestions.append("Plot the distribution of the analyzed image features")
        
        if has_plotting:
            suggestions.append("Show me the top 10 items from this data")
        
        if "data_exploration_tool" in tools_used:
            suggestions.append("Filter this data by a specific condition")
        
        # Generic fallback suggestions
        if len(suggestions) < 3:
            suggestions.append("Show me statistics for this dataset")
        if len(suggestions) < 3:
            suggestions.append("Compare this across different categories")
        if len(suggestions) < 3:
            suggestions.append("Visualize this data in a different way")
        
        return suggestions[:3]  # Return max 3 suggestions

    def _build_execution_context_string(self, steps: List[Dict[str, Any]]) -> str:
        if not steps:
            return "no_tools_executed"
            
        tool_sequence = []
        current_tool = None
        count = 0
        
        for step in steps:
            tool_calls = step.get("tool_calls", [])
            if not tool_calls:
                continue
                
            tool_name = tool_calls[0].get("tool_name", "unknown")
            
            if tool_name == current_tool:
                count += 1
            else:
                if current_tool:
                    if count > 1:
                        tool_sequence.append(f"{current_tool} (x{count})")
                    else:
                        tool_sequence.append(current_tool)
                
                current_tool = tool_name
                count = 1
        
        # Append last tool
        if current_tool:
            if count > 1:
                tool_sequence.append(f"{current_tool} (x{count})")
            else:
                tool_sequence.append(current_tool)
                
        return " -> ".join(tool_sequence)



