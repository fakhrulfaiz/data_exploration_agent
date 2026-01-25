from langchain_core.messages import SystemMessage, AIMessage
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List
import logging
import json
from app.agents.prompts.user_preferences import get_user_preference_prompt_safe

logger = logging.getLogger(__name__)

# Tool category and alternative mappings
TOOL_METADATA = {
    "data_exploration_tool": {
        "category": "data_retrieval",
    },
    "smart_transform_for_viz": {
        "category": "visualization",
        "alternative": "large_plotting_tool"
    },
    "large_plotting_tool": {
        "category": "visualization",
        "alternative": "smart_transform_for_viz"
    },
    "python_repl": {
        "category": "analysis",
        "alternative": "data_exploration_tool"
    },
    "image_analysis": {
        "category": "analysis"
    }
}

def get_tool_metadata(tool_name: str) -> Dict[str, Any]:
    """Get metadata (category, alternative) for a tool"""
    return TOOL_METADATA.get(tool_name, {"category": "general"})


# Tool-specific fact extractors (scalable design)
class ToolFactExtractor:
    """Base class for tool-specific fact extraction"""
    
    def extract(self, tool_output: str) -> Dict[str, Any]:
        """Extract verifiable facts from tool output"""
        return {
            'has_error': False,
            'output_type': 'unknown'
        }


class DomainExplanation(BaseModel):
 
    task_completion_status: str = Field(
        description="Did the tool execution achieve the task goal? (success/partial/failed/unknown)"
    )
    execution_summary: str = Field(
        description="FACTUAL summary of what the tool returned and execution status (not performance claims)"
    )
    
    data_evidence: Optional[str] = Field(
        default=None,
        description="Specific evidence from the output (row counts, data size, patterns)"
    )
    
    # ===== P1: CONFIDENCE SCORING =====
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        default=0.5,
        description="Confidence in this explanation's accuracy (0.0-1.0)"
    )
    confidence_factors: List[str] = Field(
        default=[],
        description="Specific factors contributing to the confidence score"
    )

    
    @validator('execution_summary')
    def no_unverifiable_claims(cls, v):
        """Prevent hallucinated performance claims"""
        if v is None:
            return v
        
        # Forbidden phrases (no data to support these claims)
        forbidden_phrases = [
            ('efficiently', 'performance claim without metrics'),
            ('quickly', 'speed claim without timing data'),
            ('fast', 'speed claim without timing data'),
            ('slow', 'speed claim without timing data'),
            ('milliseconds', 'timing claim without actual measurement'),
            ('seconds', 'timing claim without actual measurement'),
            ('<100ms', 'specific timing without measurement'),
            ('optimized', 'optimization claim without evidence'),
            ('performant', 'performance claim without metrics'),
            ('high-performance', 'performance claim without metrics'),
        ]
        
        v_lower = v.lower()
        for phrase, reason in forbidden_phrases:
            if phrase in v_lower:
                logger.warning(
                    f"execution_summary contains unverifiable claim: '{phrase}' ({reason}). "
                    "This should describe WHAT was returned, not HOW WELL it performed."
                )
                # Don't raise error - just warn. LLM will learn from feedback.
        
        return v
    
    @validator('data_evidence')
    def must_be_specific(cls, v):
        """Ensure data_evidence contains specific facts"""
        if v is None:
            return v
        
        # Acceptable vague phrases (admitting uncertainty is good)
        acceptable_vague = ['not available', 'unknown', 'unclear', 'cannot determine']
        if any(phrase in v.lower() for phrase in acceptable_vague):
            return v
        
        # Should contain numbers or specific data points
        if not any(char.isdigit() for char in v):
            logger.info(
                "data_evidence lacks specific numbers - may be too vague. "
                "Consider including row counts, column counts, or other metrics."
            )
        
        return v


class ExplainerNode:
    
    def __init__(self, llm, available_tools: List[Any] = None):
        self.llm = llm
        self.available_tools = available_tools or []
        self.tool_names = [tool.name for tool in self.available_tools if hasattr(tool, 'name')]
        self.tool_descriptions = {
            tool.name: getattr(tool, 'description', '')
            for tool in self.available_tools 
            if hasattr(tool, 'name')
        }
    
    def _get_tool_description(self, tool_name: str) -> str:
        return self.tool_descriptions.get(tool_name, "")
    
    def _build_explanation_prompt(
        self, 
        tool_name: str, 
        tool_input: str, 
        tool_output: str, 
        context: str,
        row_count: Optional[int] = None,
        existing_decision: Optional[str] = None,
        existing_reasoning: Optional[str] = None,
        user_id: Optional[str] = None,
        next_step_context: Optional[str] = None
    ) -> str:
        
        # Import fact extractor
        from app.agents.nodes.fact_extractors import get_fact_extractor
        
        # Extract VERIFIABLE facts using tool-specific extractor
        extractor = get_fact_extractor(tool_name)
        facts = extractor.extract(tool_output)
        
        # Build facts section
        facts_section = "**VERIFIABLE FACTS FROM OUTPUT**:\n"
        if facts.get('has_error'):
            facts_section += f"- Status: ERROR\n"
            facts_section += f"- Error Type: {facts.get('error_type', 'unknown')}\n"
            facts_section += f"- Error Message: {facts.get('error_message', 'Unknown error')}\n"
            facts_section += f"- Recoverable: {facts.get('recoverable', False)}\n"
        else:
            facts_section += f"- Status: SUCCESS\n"
            facts_section += f"- Output Type: {facts.get('output_type', 'unknown')}\n"
            
            # DYNAMIC FACT RENDERING: Add all other facts from extractor
            # This makes the system scalable - new extractors can add any facts
            for key, value in facts.items():
                # Skip already-handled fields
                if key in ['has_error', 'output_type', 'error_type', 'error_message', 'recoverable']:
                    continue
                
                # Skip None values
                if value is None:
                    continue
                
                # Convert key to human-readable format (e.g., 'row_count' -> 'Row Count')
                display_name = key.replace('_', ' ').title()
                
                # Format value appropriately based on type
                if isinstance(value, list):
                    # For lists, show first 5 items
                    value_str = ', '.join(str(v) for v in value[:5])
                    if len(value) > 5:
                        value_str += f" (and {len(value) - 5} more)"
                elif isinstance(value, tuple) and len(value) == 2:
                    # For tuples like shape (150, 5), format as "150 rows × 5 columns"
                    value_str = f"{value[0]} rows × {value[1]} columns"
                elif isinstance(value, dict):
                    # For dicts, show as key-value pairs
                    items = [f"{k}: {v}" for k, v in list(value.items())[:3]]
                    value_str = ', '.join(items)
                    if len(value) > 3:
                        value_str += f" (and {len(value) - 3} more)"
                else:
                    value_str = str(value)
                
                facts_section += f"- {display_name}: {value_str}\n"
        
        # Extract 1-2 sample rows from data_preview for context (if available)
        sample_data = None
        try:
            output_dict = json.loads(tool_output)
            if 'data_preview' in output_dict and output_dict['data_preview']:
                preview = output_dict['data_preview']
                # Take first 2 rows only
                sample_data = preview[:2] if isinstance(preview, list) else None
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Add sample data to facts if available
        if sample_data:
            facts_section += f"\n**Sample Data** (first 2 rows for context):\n"
            for i, row in enumerate(sample_data, 1):
                row_str = ', '.join(f"{k}: {v}" for k, v in list(row.items())[:4])  # First 4 columns only
                if len(row) > 4:
                    row_str += "..."
                facts_section += f"  {i}. {row_str}\n"
        
        metadata = get_tool_metadata(tool_name)
        alternative = metadata.get("alternative")
        tool_desc = self._get_tool_description(tool_name)
        
        # NEW: Retrieve explanation patterns from RAG (as reference examples)
        examples_context = ""
        try:
            from app.services.rag_service import get_rag_service
            
            rag_service = get_rag_service()
            patterns = rag_service.retrieve_explanation_patterns(
                tool_name=tool_name,
                task_goal=existing_reasoning or "execute task",
                n_results=2
            )
            
            if patterns:
                examples_context = "\n\n**REFERENCE EXAMPLES** (for inspiration, not strict rules):\n"
                examples_context += "These are examples of how similar executions were explained. Use them as a guide for structure and style, but adapt to the actual facts.\n\n"
                
                for i, pattern in enumerate(patterns, 1):
                    examples_context += f"Example {i} - {pattern['task_type']} ({pattern['complexity']} complexity):\n"
                    examples_context += f"Context: {pattern['context'][:150]}...\n"
                    examples_context += f"Template approach:\n{pattern['template'][:250]}...\n\n"
                
                logger.info(f"Retrieved {len(patterns)} explanation patterns for {tool_name}")
        except Exception as e:
            logger.warning(f"Failed to retrieve explanation patterns from RAG: {e}")
        
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
                logger.warning(f"Failed to fetch user preferences in explainer: {e}")
        
        # Build base prompt with user preferences
        from app.agents.prompts.explainer_prompts import get_explainer_system_prompt
        system_prompt = get_explainer_system_prompt(user_preferences)
        
        # Build the main prompt separately to avoid f-string conflicts with system_prompt
        main_prompt = f"""
**CRITICAL RULES**:
1. ONLY use facts from the "VERIFIABLE FACTS" section below
2. DO NOT make up performance metrics (execution time, speed, efficiency)
3. DO NOT claim success/failure unless explicitly stated in facts
4. If information is not available in facts, say "Not available" or omit the field
5. Describe WHAT the tool returned, NOT how well it performed

{examples_context}

**CONTEXT**:
- Decision: {existing_decision if existing_decision else "Tool was selected for this step"}
- Reasoning: {existing_reasoning if existing_reasoning else "Tool selection reasoning was provided earlier"}
- Next Planned Step: {next_step_context if next_step_context else "None (Final step or unknown)"}

{facts_section}

**TOOL INFORMATION**:
- Tool: {tool_name}
- Description: {tool_desc}
- Input: {tool_input}

**YOUR TASK**:
Generate the following fields based on VERIFIABLE FACTS:

1. **task_completion_status**: Evaluate if the tool execution achieved the task goal
   - **Task Goal**: {existing_reasoning if existing_reasoning else "Execute the planned step"}
   - Check if the output provides what is needed for the **Next Planned Step**.
   - Possible values:
     - "success" - Tool output clearly satisfies the task goal
     - "partial" - Tool returned data but may not fully satisfy goal  
     - "failed" - Tool execution failed (error occurred)
     - "unknown" - Cannot determine from output if goal was achieved

2. **execution_summary**: Describe **WHAT** the tool returned and **WHY** it is significant.
   - Explain the result in context of the task goal.
   - Mention key findings or patterns provided in the facts.
   - Briefly mention if it unblocks the Next Planned Step.
   - **Example**: "Retrieved 150 painting records with inception dates, confirming data availability for the subsequent sorting step."

3. **data_evidence**: Quote SPECIFIC facts from the VERIFIABLE FACTS section
   - Include row counts, column names, data types, visualization details
   - Only state facts that are explicitly listed above

4. **confidence_score**: Rate your confidence (0.0-1.0) in this explanation:
   - 0.9-1.0: Complete data, no errors, output perfectly matches goal
   - 0.7-0.8: Data returned successfully, minor uncertainty about completeness
   - 0.5-0.6: Partial data or some warnings, goal partially achieved
   - 0.3-0.4: Significant issues but some useful output
   - 0.0-0.2: Failed or highly uncertain output
   Base your score on: data completeness, error-free execution, goal alignment.

5. **confidence_factors**: List 2-3 specific factors explaining your confidence score.
   Use actual data from VERIFIABLE FACTS (row counts, column names, data ranges, anomalies).
   Avoid generic statements like "no errors" or "as expected" unless there were actual issues.
   Examples: "101 rows retrieved", "All 5 columns present", "Data spans 1400-2000", "3 rows missing dates".

REMEMBER: Only state facts from the VERIFIABLE FACTS section above!
"""
        
        # Combine system prompt with main prompt using concatenation
        prompt = system_prompt + "\n\n" + main_prompt
        
        return prompt

    def explain_step(self, step: Dict[str, Any], messages: List = None) -> DomainExplanation:  
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            user_id = step.get("user_id")  # Extract user_id
            
            
            # Get existing decision/reasoning from step
            existing_decision = step.get("decision")
            existing_reasoning = step.get("reasoning")
            next_step_context = step.get("next_step_context")
            
            # Build Prompt with fact extraction (NO policy checks)
            prompt = self._build_explanation_prompt(
                tool_name, 
                tool_input, 
                tool_output, 
                context, 
                row_count=None, 
                existing_decision=existing_decision,
                existing_reasoning=existing_reasoning,
                user_id=user_id,  # Pass user_id
                next_step_context=next_step_context
            )
            
            # Invoke LLM with structured output (default json_schema mode)
            from langchain_core.messages import HumanMessage
            
            llm_with_structure = self.llm.with_structured_output(DomainExplanation)
            explanation = llm_with_structure.invoke([
                SystemMessage(content=prompt), 
                HumanMessage(content="Generate the explanation based on the context and facts provided above.")
            ])
            
            logger.info(f"Generated explanation for {tool_name}")
            
            return explanation, [] 
            
        except Exception as e:
            logger.error(f"Error generating explanation for {step.get('tool_name', 'unknown')}: {e}", exc_info=True)
            # Fallback with more context
            return DomainExplanation(
                task_completion_status="unknown",
                execution_summary=f"Executed {step.get('tool_name', 'tool')} - explanation generation failed: {str(e)[:100]}",
                data_evidence="Unable to generate detailed explanation due to error"
            ), []
    
    def execute_sync(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Check if explainer is enabled
        use_explainer = state.get("use_explainer", True)
        if not use_explainer:
            logger.info("Explainer disabled (use_explainer=False), skipping explanation generation")
            return state
        
        steps = state.get("steps", [])
        messages = state.get("messages", [])
        
        # Only explain the last step (the one just executed)
        if not steps:
            return state
            
        # Get the logical current step (last one added)
        current_step_idx = len(steps) - 1
        step = steps[current_step_idx]
        
        # Skip if already has explanation
        if "task_completion_status" in step:
            return state
            
        # Get tool calls
        tool_calls = step.get('tool_calls', [])
        if not tool_calls:
            return state
        
        # Aggregate all tool calls for explanation
        tool_name = tool_calls[0].get('tool_name')
        tool_inputs = [tc.get('input') for tc in tool_calls]
        tool_outputs = [tc.get('output') for tc in tool_calls]

        # Determine next step context using Dynamic Plan
        next_step_context = None
        dynamic_plan = state.get("dynamic_plan")
        plan_step_index = step.get("plan_step_index")
        
         # 1. Try to get context from Dynamic Plan (Correct source for future steps)
        if dynamic_plan and plan_step_index is not None:
            # Handle both object and dict access for dynamic_plan
            plan_steps = getattr(dynamic_plan, 'steps', []) if not isinstance(dynamic_plan, dict) else dynamic_plan.get('steps', [])
            
            next_plan_idx = plan_step_index + 1
            if next_plan_idx < len(plan_steps):
                next_step = plan_steps[next_plan_idx]
                
                # Extract details handling both Pydantic objects and dicts
                if isinstance(next_step, dict):
                    next_goal = next_step.get('goal', 'Unknown Goal')
                    tool_options = next_step.get('tool_options', [])
                    if tool_options and isinstance(tool_options[0], dict):
                            next_tool = tool_options[0].get('tool_name', 'Unknown Tool')
                    elif tool_options:
                            next_tool = getattr(tool_options[0], 'tool_name', 'Unknown Tool')
                    else:
                            next_tool = "Unknown Tool"
                else:
                    next_goal = getattr(next_step, 'goal', 'Unknown Goal')
                    tool_options = getattr(next_step, 'tool_options', [])
                    if tool_options:
                        next_tool = getattr(tool_options[0], 'tool_name', 'Unknown Tool')
                    else:
                        next_tool = "Unknown Tool"
                        
                next_step_context = f"Step {next_plan_idx + 1}: {next_goal} (Using {next_tool})"
            else:
                next_step_context = "None (Final step of plan)"
        
        # 2. Fallback (if no plan index) - Look at steps length vs plan length or just default
        if next_step_context is None:
             next_step_context = "None (Final step or unknown)"
        
        # Build step object for explain_step with all tool calls
        step_for_explanation = {
            'tool_name': tool_name,
            'input': '\n---\n'.join(tool_inputs),  # Combine all inputs
            'output': '\n---\n'.join(tool_outputs),  # Combine all outputs
            'decision': step.get('decision', ''),
            'reasoning': step.get('reasoning', ''),
            'user_id': state.get('user_id'),  # Pass user_id for preferences
            'next_step_context': next_step_context
        }
        
        explanation, _ = self.explain_step(step_for_explanation, messages) 
        
        step['task_completion_status'] = explanation.task_completion_status
        step['execution_summary'] = explanation.execution_summary
        step['data_evidence'] = explanation.data_evidence
        step['confidence_score'] = explanation.confidence_score
        step['confidence_factors'] = explanation.confidence_factors
        
        explanation_json = {
            'task_completion_status': explanation.task_completion_status,
            'execution_summary': explanation.execution_summary,
            'data_evidence': explanation.data_evidence,
            'confidence_score': explanation.confidence_score,
            'confidence_factors': explanation.confidence_factors,
        }
        
        explanation_message = AIMessage(
            content=json.dumps(explanation_json),
            additional_kwargs={'is_explanation': True}
        )
        
        # Base updates
        updates = {
            **state, 
            "steps": steps, 
            "messages": [explanation_message] 
        }

        # CHECK FOR LOGICAL FAILURE
        if explanation.task_completion_status == 'failed':
            logger.warning(f"Explainer detected logical failure: {explanation.execution_summary}")
            
            # Set feedback to trigger interrupt in main execution flow
            updates["feedback"] = f"Logical Failure detected: {explanation.execution_summary}"
            
            # Create structured error detail
            error_detail = {
                'tool_name': tool_name,
                'tool_call_id': 'logical_failure',
                'error_message': explanation.execution_summary,
                'error_type': 'LogicalFailure',
                'details': {'evidence': explanation.data_evidence},
                'recoverable': True,
                'detection_method': 'explainer'
            }
            updates["error_details"] = [error_detail]
            
            # Rollback step index so we don't move to next step
            # Note: process_query incremented it, so we need to validly decrement to retry/replan THIS step
            current_index = state.get("current_step_index", 0)
            updates["current_step_index"] = max(0, current_index - 1)
        
        # CHECK FOR PARTIAL SUCCESS (AUTO-RETRY FOR IMAGE QA)
        elif explanation.task_completion_status == 'partial' and tool_name == 'image_batch_qa_tool':
            # Get current retry attempt from feedback
            current_feedback = state.get("feedback", "")
            retry_attempt = 1
            if current_feedback and "RETRY_IMAGE_QA" in current_feedback:
                # Extract attempt number from feedback like "RETRY_IMAGE_QA:2"
                try:
                    retry_attempt = int(current_feedback.split(":")[1]) + 1
                except:
                    retry_attempt = 2
            
            # Only retry if we haven't exceeded max attempts (2)
            if retry_attempt <= 2:
                # Set feedback to trigger retry (same as error retry flow)
                updates["feedback"] = f"RETRY_IMAGE_QA:{retry_attempt}"
                logger.info(f"Auto-retry scheduled (attempt {retry_attempt}/2)")

                current_index = state.get("current_step_index", 0)
                updates["current_step_index"] = max(0, current_index - 1)
            else:
                logger.info(f"Max retry attempts reached (2), not scheduling retry")
        
        
            
            
        return updates

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.execute_sync(state)
        except Exception as e:
            logger.error(f"Error in ExplainerNode.execute: {e}")
            return state

