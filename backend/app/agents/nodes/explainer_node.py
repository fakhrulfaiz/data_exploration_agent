"""
Explainer Node for generating step explanations.
Provides reasoning, confidence scores, and justifications for tool executions.
"""

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class StepExplanation(BaseModel):
    """Model for step explanation"""
    decision: str = Field(description="What decision was made")
    reasoning: str = Field(description="Why this decision was made")
    why_chosen: str = Field(description="Why this tool/approach was chosen")
    confidence: float = Field(description="Confidence score (0.0-1.0)")


class ExplainerNode:
    """Node responsible for explaining agent steps and decisions"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def explain_step(self, step: Dict[str, Any]) -> StepExplanation:
        """Generate explanation for a single step
        
        Args:
            step: Step information containing tool name, input, output, etc.
            
        Returns:
            StepExplanation with decision, reasoning, confidence, and why_chosen
        """
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
            prompt = f"""You are an AI assistant explaining the reasoning behind tool executions.

Given the following information about a tool execution step, provide a clear explanation:

**Tool Used:** {tool_name}
**Input:** {tool_input}
**Output:** {tool_output}
**Context:** {context}

Provide a structured explanation with:
1. **Decision**: What action was taken (1-2 sentences)
2. **Reasoning**: Why this action was necessary (2-3 sentences)
3. **Why Chosen**: Why this specific tool was selected over alternatives (1-2 sentences)
4. **Confidence**: Your confidence in this decision (0.0-1.0)

Be concise, clear, and user-friendly. Avoid technical jargon unless necessary."""

            messages = [SystemMessage(content=prompt)]
            
            llm_with_structure = self.llm.with_structured_output(StepExplanation)
            explanation = llm_with_structure.invoke(messages)
            
            logger.info(f"Generated explanation for step using {tool_name}")
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            # Return default explanation on error
            return StepExplanation(
                decision=f"Execute {step.get('tool_name', 'tool')}",
                reasoning=f"Tool execution was required to process the query",
                why_chosen=f"Selected {step.get('tool_name', 'tool')} as the appropriate tool",
                confidence=0.5
            )
    
    def explain_multiple_steps(self, steps: list[Dict[str, Any]]) -> list[StepExplanation]:
        """Generate explanations for multiple steps
        
        Args:
            steps: List of step information dicts
            
        Returns:
            List of StepExplanation objects
        """
        explanations = []
        for step in steps:
            explanation = self.explain_step(step)
            explanations.append(explanation)
        
        return explanations
