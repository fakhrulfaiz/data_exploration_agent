from langchain_core.messages import SystemMessage, AIMessage
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List
import logging
import json

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
        "category": "analysis",
        "alternative": "dataframe_info"
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
    
    # ===== P1: CLICKABLE ACTIONS =====
    next_actions: List[str] = Field(
        default=[],
        description="2-3 clickable actions the user can take with this step's result"
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
        existing_reasoning: Optional[str] = None
    ) -> str:
        """Build prompt for LLM to generate explanation with fact extraction"""
        
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
            
            # Add tool-specific facts
            if facts.get('row_count') is not None:
                facts_section += f"- Row Count: {facts['row_count']}\n"
            if facts.get('columns'):
                facts_section += f"- Columns: {', '.join(facts['columns'][:5])}\n"
            if facts.get('shape'):
                facts_section += f"- Shape: {facts['shape'][0]} rows × {facts['shape'][1]} columns\n"
            if facts.get('viz_type'):
                facts_section += f"- Visualization Type: {facts['viz_type']}\n"
            if facts.get('total_rows') is not None:
                facts_section += f"- Total Rows: {facts['total_rows']}\n"
            if facts.get('displayed_rows') is not None:
                facts_section += f"- Displayed Rows: {facts['displayed_rows']}\n"
            if facts.get('data_points') is not None:
                facts_section += f"- Data Points: {facts['data_points']}\n"
            if facts.get('plot_type'):
                facts_section += f"- Plot Type: {facts['plot_type']}\n"
        
        metadata = get_tool_metadata(tool_name)
        alternative = metadata.get("alternative")
        tool_desc = self._get_tool_description(tool_name)
        
        prompt = f"""You are an AI assistant providing FACTUAL explanation for tool execution.

**CRITICAL RULES**:
1. ONLY use facts from the "VERIFIABLE FACTS" section below
2. DO NOT make up performance metrics (execution time, speed, efficiency)
3. DO NOT claim success/failure unless explicitly stated in facts
4. If information is not available in facts, say "Not available" or omit the field
5. Describe WHAT the tool returned, NOT how well it performed

**CONTEXT** (Decision and reasoning already generated):
- Decision: {existing_decision if existing_decision else "Tool was selected for this step"}
- Reasoning: {existing_reasoning if existing_reasoning else "Tool selection reasoning was provided earlier"}

{facts_section}

**TOOL INFORMATION**:
- Tool: {tool_name}
- Description: {tool_desc}
- Input: {tool_input}

**FULL TOOL OUTPUT** (for reference - use VERIFIABLE FACTS above):
```
{tool_output}
```

**YOUR TASK**:
Generate the following fields based on VERIFIABLE FACTS:

1. **task_completion_status**: Evaluate if the tool execution achieved the task goal
   - **Task Goal**: {existing_reasoning if existing_reasoning else "Execute the planned step"}
   - Possible values:
     - "success" - Tool output clearly satisfies the task goal
     - "partial" - Tool returned data but may not fully satisfy goal  
     - "failed" - Tool execution failed (error occurred)
     - "unknown" - Cannot determine from output if goal was achieved

2. **execution_summary**: Describe what the tool RETURNED and execution status (not how it "performed")

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

6. **next_actions**: Suggest 1-3 actions the user can take with THIS step's result.
   Each action will be sent as a new query, so phrase as complete questions/commands.
   Use actual column names and values from VERIFIABLE FACTS.
   
   By tool type:
   - data_exploration_tool: "View full table", "Filter by [column_name]", "Sort by [column_name]"
   - smart_transform_for_viz: "Switch to pie chart", "Show top 10 only"
   - image_qa: "Analyze similar images", "Compare with [subject]"
   
   Avoid: Generic actions, unimplementable features, actions needing data from other steps.

REMEMBER: Only state facts from the VERIFIABLE FACTS section above!
"""
        
        return prompt

    def explain_step(self, step: Dict[str, Any], messages: List = None) -> DomainExplanation:  
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
            
            # Get existing decision/reasoning from step
            existing_decision = step.get("decision")
            existing_reasoning = step.get("reasoning")
            
            # Build Prompt with fact extraction (NO policy checks)
            prompt = self._build_explanation_prompt(
                tool_name, 
                tool_input, 
                tool_output, 
                context, 
                row_count=None, 
                existing_decision=existing_decision,
                existing_reasoning=existing_reasoning
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
        
        # Find steps needing explanation
        for step in steps:
            # Skip if already has explanation
            if "tool_justification" in step:
                continue
            
            # Get first tool call to use for explanation
            tool_calls = step.get('tool_calls', [])
            if not tool_calls:
                continue
            
            # Aggregate all tool calls for explanation
            tool_name = tool_calls[0].get('tool_name')  # All tool calls use same tool
            tool_inputs = [tc.get('input') for tc in tool_calls]
            tool_outputs = [tc.get('output') for tc in tool_calls]
            
            # Build step object for explain_step with all tool calls
            step_for_explanation = {
                'tool_name': tool_name,
                'input': '\n---\n'.join(tool_inputs),  # Combine all inputs
                'output': '\n---\n'.join(tool_outputs),  # Combine all outputs
                'decision': step.get('decision', ''),
                'reasoning': step.get('reasoning', '')
            }
            
            explanation, _ = self.explain_step(step_for_explanation, messages) 
            
            step['task_completion_status'] = explanation.task_completion_status
            step['execution_summary'] = explanation.execution_summary
            step['data_evidence'] = explanation.data_evidence
            # P1: Confidence scoring
            step['confidence_score'] = explanation.confidence_score
            step['confidence_factors'] = explanation.confidence_factors
            # P1: Clickable actions
            step['next_actions'] = explanation.next_actions
            
            explanation_json = {
                'task_completion_status': explanation.task_completion_status,
                'execution_summary': explanation.execution_summary,
                'data_evidence': explanation.data_evidence,
                # P1: Confidence scoring
                'confidence_score': explanation.confidence_score,
                'confidence_factors': explanation.confidence_factors,
                # P1: Clickable actions
                'next_actions': explanation.next_actions,
            }
            
            explanation_message = AIMessage(
                content=json.dumps(explanation_json),
                additional_kwargs={'is_explanation': True}
            )
            
            return {
                **state, 
                "steps": steps, 
                "messages": [explanation_message] # Only return the NEW message
            }
                
        return {**state, "steps": steps} #

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.execute_sync(state)
        except Exception as e:
            logger.error(f"Error in ExplainerNode.execute: {e}")
            return state

