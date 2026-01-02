"""
Explainer Node for generating step explanations.
Provides reasoning, confidence scores, and justifications for tool executions.
"""

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging
import json

from app.agents.policies import run_all_policies, PolicyResult

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


class PolicyAuditResult(BaseModel):
    """Result of a policy audit for structured output compliance."""
    policy_name: str = Field(description="Name of the policy that was checked")
    passed: bool = Field(description="Whether the policy check passed")
    message: str = Field(description="Explanation of the policy result")
    severity: str = Field(description="Severity level: info, warning, or error")


class DomainExplanation(BaseModel):
    """
    Explanation schema aligned with frontend ExplanationMessage.tsx
    """
    decision: str = Field(description="What action was taken (1-2 user-friendly sentences)")
    reasoning: Optional[str] = Field(description="Why this action was necessary")
    
    # Optional fields for detailed view
    tool_justification: Optional[str] = Field(description="Why this specific tool was chosen")
    contrastive_explanation: Optional[str] = Field(description="Why the alternative was NOT chosen")
    data_evidence: Optional[str] = Field(description="Data supporting the decision (e.g. row counts)")
    counterfactual: Optional[str] = Field(description="What-if scenario (e.g. if conditions were different)")
    
    # Policy audits (handled separately in execution, but kept in model for completeness if needed)
    # Note: Frontend renders these from a separate prop, or we can include them here if strict mode allows.
    # For now, we'll keep them out of the LLM prompt to identify them separately.


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
    
    def _extract_row_count(self, messages: List) -> Optional[int]:
        """Extract row count from recent messages"""
        for msg in reversed(messages):
            if hasattr(msg, 'content'):
                try:
                    # Look for tool outputs with row_count
                    content = msg.content
                    if isinstance(content, str) and '"row_count":' in content:
                        data = json.loads(content)
                        return data.get("row_count")
                except:
                    pass
        return None

    def _build_explanation_prompt(
        self, 
        tool_name: str, 
        tool_input: str, 
        tool_output: str, 
        context: str,
        row_count: Optional[int] = None,
        policy_audits: List[PolicyAuditResult] = None,
        existing_decision: Optional[str] = None,
        existing_reasoning: Optional[str] = None
    ) -> str:
        
        metadata = get_tool_metadata(tool_name)
        alternative = metadata.get("alternative")
        tool_desc = self._get_tool_description(tool_name)
        
        # Build prompt focusing on RESULTS (decision/reasoning already provided)
        prompt = f"""You are an AI assistant explaining tool execution RESULTS for a data exploration agent.

**DECISION ALREADY MADE**:
{existing_decision if existing_decision else "Tool was selected for this step"}

**REASONING ALREADY PROVIDED**:
{existing_reasoning if existing_reasoning else "Tool selection reasoning was provided earlier"}

**EXECUTION RESULT**:
Tool: {tool_name}
Description: {tool_desc}
Input: {tool_input}
Output Summary: {str(tool_output)[:300]}...
Data Evidence: {f"Query returned {row_count} rows" if row_count is not None else "Unknown"}

**YOUR TASK**:
Generate a structured explanation focusing on WHAT HAPPENED (not why the tool was chosen).

1. **decision**: What the tool accomplished (e.g. "Retrieved 50 rows of patient data").
2. **reasoning**: Brief context about the execution (e.g. "Filtered by date range as requested").
3. **tool_justification**: How this tool performed for this specific task (e.g. "SQL query executed efficiently").
4. **contrastive_explanation**: Why alternative ({alternative if alternative else "other approaches"}) would have been different (if applicable).
5. **data_evidence**: Specific evidence from the output (row counts, data size, patterns observed).
6. **counterfactual**: A brief "What-if" scenario (e.g. "If dataset was larger (>1000 rows), we would need to aggregate first").

DO NOT re-explain why the tool was chosen (already provided above). Focus on the RESULT and what was accomplished.
"""
        if policy_audits:
            prompt += "\n**POLICY CHECK RESULTS**:\n"
            for audit in policy_audits:
                status = "PASS" if audit.passed else "FAIL"
                prompt += f"- {status}: {audit.policy_name} ({audit.message})\n"
            prompt += "\nIncorporate these policy results into your data_evidence or reasoning where relevant.\n"

        return prompt

    def explain_step(self, step: Dict[str, Any], messages: List = None) -> DomainExplanation:  
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
            # Extract existing decision/reasoning from process_query
            existing_decision = step.get("decision", None)
            existing_reasoning = step.get("reasoning", None)
            
            # Extract basic evidence
            row_count = self._extract_row_count(messages) if messages else None
            
            # Run policies
            policy_context = {
                'tool_name': tool_name,
                'tool_input': tool_input,
                'tool_output': tool_output,
                'row_count': row_count
            }
            policy_results = run_all_policies(policy_context)
            
            # Convert to audits
            policy_audits = [
                PolicyAuditResult(
                    policy_name=pr.policy_name,
                    passed=pr.passed,
                    message=pr.message,
                    severity=pr.severity
                )
                for pr in policy_results
            ]
            
            # Build Prompt with existing decision/reasoning
            prompt = self._build_explanation_prompt(
                tool_name, tool_input, tool_output, context, row_count, policy_audits,
                existing_decision=existing_decision,
                existing_reasoning=existing_reasoning
            )
            
            system_msg = SystemMessage(content=prompt)
            
            # Invoke LLM
            llm_with_structure = self.llm.with_structured_output(DomainExplanation)
            explanation = llm_with_structure.invoke([system_msg])
            
            logger.info(f"Generated explanation for {tool_name}")
            return explanation, policy_audits
            
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            # Fallback
            return DomainExplanation(
                decision=f"Executed {step.get('tool_name', 'tool')}",
                reasoning="Required to process the user's request"
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
            
            explanation, audits = self.explain_step(step_for_explanation, messages)
            
            # Update step with explanation fields
            step['tool_justification'] = explanation.tool_justification
            step['data_evidence'] = explanation.data_evidence
            step['counterfactual'] = explanation.counterfactual
                
        return {**state, "steps": steps, "messages": messages}

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.execute_sync(state)
        except Exception as e:
            logger.error(f"Error in ExplainerNode.execute: {e}")
            return state

