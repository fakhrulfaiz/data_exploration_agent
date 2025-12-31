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
        policy_audits: List[PolicyAuditResult] = None
    ) -> str:
        
        metadata = get_tool_metadata(tool_name)
        alternative = metadata.get("alternative")
        tool_desc = self._get_tool_description(tool_name)
        
        prompt = f"""You are an AI assistant explaining tool executions for a data exploration agent.

**CONTEXT:**
User Input: {context}
Data Evidence: {f"Query returned {row_count} rows" if row_count is not None else "Unknown"}

**ACTION TAKEN:**
Tool: {tool_name}
Description: {tool_desc}
Input: {tool_input}
Output Summary: {str(tool_output)[:300]}...

**ALTERNATIVE TOOL:** {alternative if alternative else "None"}

**YOUR TASK:**
Generate a structured explanation.

1. **decision**: What happened? (e.g. "Retrieved 50 rows of patient data").
2. **reasoning**: Why? (e.g. "User asked for recent patients. Used SQL to filter by date.").
3. **tool_justification**: Why {tool_name}? (e.g. "Most direct way to query database").
4. **contrastive_explanation**: Why NOT {alternative}? (If applicable).
5. **data_evidence**: Mention row counts or data size if relevant.
6. **counterfactual**: A brief "What-if" (e.g. "If dataset was larger (>1000 rows), we would aggregate first").

"""
        if policy_audits:
            prompt += "\n**POLICY CHECK RESULTS**:\n"
            for audit in policy_audits:
                status = "PASS" if audit.passed else "FAIL"
                prompt += f"- {status}: {audit.policy_name} ({audit.message})\n"
            prompt += "\nIncorporated these policy results into your reasoning where relevant.\n"

        return prompt

    def explain_step(self, step: Dict[str, Any], messages: List = None) -> DomainExplanation:  
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
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
            
            # Build Prompt
            prompt = self._build_explanation_prompt(
                tool_name, tool_input, tool_output, context, row_count, policy_audits
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
        steps = state.get("steps", [])
        messages = state.get("messages", [])
        
        # Find steps needing explanation
        for i, step in enumerate(steps):
            if "decision" not in step:
                explanation, audits = self.explain_step(step, messages)
                
                # Update step with flattened explanation fields (no policy_audits)
                steps[i].update(explanation.model_dump())
                
                # Create Explanation Message for frontend streaming
                # Matches ExplanationMessage.tsx props (no policy_audits)
                explanation_data = explanation.model_dump()
                
                from langchain_core.messages import AIMessage
                msg = AIMessage(
                    content=json.dumps(explanation_data),
                    additional_kwargs={"is_explanation": True}
                )
                messages.append(msg)
                
        return {**state, "steps": steps, "messages": messages}

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.execute_sync(state)
        except Exception as e:
            logger.error(f"Error in ExplainerNode.execute: {e}")
            return state

