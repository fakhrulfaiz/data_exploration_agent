"""
Enhanced Explainer Node with comprehensive LLM-based explainability.
Provides chain-of-thought reasoning, alternative approaches, confidence breakdown,
and actionable insights for better transparency and trust.
"""

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class EnhancedStepExplanation(BaseModel):
    """Enhanced model for step explanation with comprehensive explainability"""
    
    # Core explanation fields
    decision: str = Field(description="What decision was made")
    reasoning: str = Field(description="Why this decision was made")
    why_chosen: str = Field(description="Why this tool/approach was chosen")
    confidence: float = Field(description="Confidence score (0.0-1.0)")
    
    # Chain-of-Thought fields
    thought_process: str = Field(
        description="Step-by-step reasoning that led to this decision"
    )
    query_interpretation: str = Field(
        description="How the agent understood the user's request"
    )
    
    # Alternative approaches
    alternatives_considered: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Other tools/approaches considered and why they were rejected"
    )
    
    # Confidence breakdown
    confidence_factors: Dict[str, float] = Field(
        default_factory=dict,
        description="Factors contributing to confidence score"
    )
    
    # Expected outcome
    expected_outcome: str = Field(
        description="What the agent expects this tool to accomplish"
    )
    
    # Risk assessment
    potential_issues: List[str] = Field(
        default_factory=list,
        description="Potential problems or edge cases to watch for"
    )
    
    # Next steps suggestion
    suggested_next_steps: List[str] = Field(
        default_factory=list,
        description="What the user might want to do next"
    )


class EnhancedExplainerNode:
    """
    Enhanced explainer node that provides comprehensive explanations
    for LLM agent decisions using chain-of-thought reasoning and
    multi-faceted analysis.
    """
    
    def __init__(self, llm, available_tools: List[Any] = None):
        self.llm = llm
        self.available_tools = available_tools or []
        self.tool_names = [tool.name for tool in self.available_tools if hasattr(tool, 'name')]
    
    def explain_step(self, step: Dict[str, Any]) -> EnhancedStepExplanation:
        """
        Generate comprehensive explanation for a single step.
        
        Args:
            step: Dictionary containing:
                - tool_name: Name of the tool used
                - input: Tool input/arguments
                - output: Tool output/result
                - context: User query or context
                
        Returns:
            EnhancedStepExplanation with detailed reasoning
        """
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
            # Build comprehensive prompt
            prompt = self._build_explanation_prompt(
                tool_name, tool_input, tool_output, context
            )
            
            messages = [SystemMessage(content=prompt)]
            
            # Use structured output for consistent parsing
            llm_with_structure = self.llm.with_structured_output(EnhancedStepExplanation)
            explanation = llm_with_structure.invoke(messages)
            
            logger.info(f"Generated enhanced explanation for step using {tool_name}")
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating enhanced explanation: {e}")
            # Return comprehensive default explanation on error
            return self._get_fallback_explanation(step)
    
    def _build_explanation_prompt(
        self, 
        tool_name: str, 
        tool_input: str, 
        tool_output: str, 
        context: str
    ) -> str:
        """Build comprehensive prompt for explanation generation"""
        
        # Get list of alternative tools
        alternatives = [t for t in self.tool_names if t != tool_name]
        alternatives_str = ", ".join(alternatives[:5]) if alternatives else "None available"
        
        prompt = f"""You are an AI assistant explaining the reasoning behind tool executions in a data exploration agent.

**CONTEXT:**
User Query: {context}

**ACTION TAKEN:**
Tool Used: {tool_name}
Input: {tool_input}
Output: {tool_output}

**AVAILABLE ALTERNATIVES:**
{alternatives_str}

**YOUR TASK:**
Provide a comprehensive, structured explanation with the following components:

1. **decision**: What action was taken (1-2 sentences, user-friendly)
   Example: "Generated a SQL query to retrieve the top 5 actors from the database"

2. **reasoning**: Why this action was necessary (2-3 sentences, explain the logic)
   Example: "The user asked for ranked data which requires querying the database. Since we don't have a pre-written query, we need to generate one from the natural language request."

3. **why_chosen**: Why this specific tool was selected over alternatives (1-2 sentences)
   Example: "text2SQL was chosen because it can automatically convert natural language to SQL, which is more reliable than manual query writing and faster than using a general-purpose code generator."

4. **thought_process**: Step-by-step reasoning (numbered list, 3-5 steps)
   Example:
   1. Identified user wants data retrieval (keyword: "show me")
   2. Recognized aggregation need (keyword: "top 5")
   3. Determined entity type ("actors")
   4. Concluded SQL query generation is required
   5. Selected text2SQL as the most appropriate tool

5. **query_interpretation**: How you understood the user's request (1-2 sentences)
   Example: "User wants to see a ranked list of actors, likely by film count or popularity"

6. **alternatives_considered**: List of 2-3 alternative tools/approaches with rejection reasons
   Format: [{{"tool": "tool_name", "reason": "why it wasn't chosen"}}]
   Example: [{{"tool": "sql_db_query", "reason": "Requires pre-written SQL query which we don't have yet"}}, {{"tool": "python_repl", "reason": "Need to query database first before analysis"}}]

7. **confidence**: Your confidence in this decision (0.0-1.0)
   Consider: query clarity, tool availability, context sufficiency

8. **confidence_factors**: Breakdown of confidence score
   Format: {{"factor_name": score}} (3-4 factors, each 0.0-1.0)
   Example: {{"query_clarity": 0.9, "tool_availability": 1.0, "context_sufficiency": 0.7, "expected_success": 0.85}}

9. **expected_outcome**: What you expect this tool to accomplish (1-2 sentences)
   Example: "A valid SQL query that selects the top 5 actors ranked by film count, ready for execution"

10. **potential_issues**: List of 1-3 potential problems or edge cases
    Example: ["Ranking metric not specified - might default to film count", "Table/column names might not match expected schema"]

11. **suggested_next_steps**: List of 2-3 logical next actions
    Example: ["Execute the generated SQL query", "Verify the ranking metric matches user intent", "Consider visualization if user wants graphical representation"]

**GUIDELINES:**
- Be concise but comprehensive
- Use user-friendly language (avoid technical jargon unless necessary)
- Be honest about uncertainty (reflected in confidence scores)
- Focus on transparency and helping users understand the decision-making process
- Provide actionable insights in suggested_next_steps
"""
        
        return prompt
    
    def _get_fallback_explanation(self, step: Dict[str, Any]) -> EnhancedStepExplanation:
        """Generate fallback explanation when LLM fails"""
        tool_name = step.get('tool_name', 'tool')
        
        return EnhancedStepExplanation(
            decision=f"Execute {tool_name}",
            reasoning=f"Tool execution was required to process the query",
            why_chosen=f"Selected {tool_name} as the appropriate tool",
            confidence=0.5,
            thought_process=f"1. Received user query\n2. Identified {tool_name} as relevant\n3. Executed tool",
            query_interpretation="Processing user request",
            alternatives_considered=[
                {"tool": "other_tools", "reason": "Not applicable for this task"}
            ],
            confidence_factors={
                "query_clarity": 0.5,
                "tool_availability": 1.0,
                "context_sufficiency": 0.5
            },
            expected_outcome=f"{tool_name} will process the request",
            potential_issues=["Explanation generation failed - using fallback"],
            suggested_next_steps=["Review tool output", "Proceed with next step"]
        )
    
    def explain_multiple_steps(
        self, 
        steps: List[Dict[str, Any]]
    ) -> List[EnhancedStepExplanation]:
        """
        Generate explanations for multiple steps.
        
        Args:
            steps: List of step dictionaries
            
        Returns:
            List of EnhancedStepExplanation objects
        """
        explanations = []
        for step in steps:
            explanation = self.explain_step(step)
            explanations.append(explanation)
        
        return explanations
    
    def explain_counterfactual(
        self, 
        step: Dict[str, Any], 
        alternative_tool: str
    ) -> str:
        """
        Explain what would happen if a different tool was used.
        
        Args:
            step: The actual step taken
            alternative_tool: Alternative tool to consider
            
        Returns:
            Explanation of the counterfactual scenario
        """
        try:
            tool_name = step.get("tool_name", "unknown")
            context = step.get("context", "")
            
            prompt = f"""You are explaining a counterfactual scenario in a data exploration agent.

**ACTUAL ACTION:**
Tool Used: {tool_name}
Context: {context}

**COUNTERFACTUAL SCENARIO:**
What if {alternative_tool} was used instead?

**EXPLAIN:**
1. Would {alternative_tool} work for this task? Why or why not?
2. What would be different in the outcome?
3. Why is {tool_name} better (or worse) for this specific case?

Provide a clear, concise explanation (3-4 sentences).
"""
            
            messages = [SystemMessage(content=prompt)]
            response = self.llm.invoke(messages)
            
            return response.content if hasattr(response, 'content') else str(response)
            
        except Exception as e:
            logger.error(f"Error generating counterfactual explanation: {e}")
            return f"Unable to generate counterfactual explanation for {alternative_tool}"
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the explainer node on the agent state.
        
        Args:
            state: Agent state containing steps to explain
            
        Returns:
            Updated state with enhanced explanations
        """
        steps = state.get("steps", [])
        updated_steps = []
        
        for i, step in enumerate(steps):
            step_copy = step.copy()
            
            # Check if explanation fields are missing
            missing_fields = [
                field for field in [
                    "decision", "reasoning", "confidence", "why_chosen",
                    "thought_process", "query_interpretation"
                ] 
                if field not in step_copy
            ]
            
            if missing_fields:
                try:
                    # Generate enhanced explanation
                    explanation = self.explain_step(step_copy)
                    
                    # Update step with all explanation fields
                    step_copy.update({
                        "decision": explanation.decision,
                        "reasoning": explanation.reasoning,
                        "why_chosen": explanation.why_chosen,
                        "confidence": explanation.confidence,
                        "thought_process": explanation.thought_process,
                        "query_interpretation": explanation.query_interpretation,
                        "alternatives_considered": explanation.alternatives_considered,
                        "confidence_factors": explanation.confidence_factors,
                        "expected_outcome": explanation.expected_outcome,
                        "potential_issues": explanation.potential_issues,
                        "suggested_next_steps": explanation.suggested_next_steps
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to generate explanation for step {i}: {e}")
                    # Use fallback
                    fallback = self._get_fallback_explanation(step_copy)
                    step_copy.update(fallback.dict())
            
            updated_steps.append(step_copy)
        
        return {
            "messages": state.get("messages", []),
            "steps": updated_steps,
            "step_counter": state.get("step_counter", 0),
            "query": state.get("query", ""),
            "plan": state.get("plan", ""),
            "data_context": state.get("data_context"),
            "visualizations": state.get("visualizations", [])
        }
