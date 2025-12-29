"""
Enhanced Explainer Node with domain-specific, scalable explanations.
Provides data-driven justifications for tool choices in the data exploration agent.
"""

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

# Tool category and alternative mappings (descriptions come from actual tool objects)
TOOL_METADATA = {
    "sql_db_query": {
        "category": "sql_execution",
        "alternative": "sql_db_to_df",
        "needs_row_count": True
    },
    "sql_db_to_df": {
        "category": "sql_execution",
        "alternative": "sql_db_query",
        "needs_row_count": True
    },
    "smart_transform_for_viz": {
        "category": "visualization",
        "alternative": "large_plotting_tool"
    },
    "large_plotting_tool": {
        "category": "visualization",
        "alternative": "smart_transform_for_viz"
    },
    "text2SQL": {
        "category": "sql_generation"
    },
    "python_repl": {
        "category": "analysis"
    },
    "dataframe_info": {
        "category": "analysis"
    }
}


def get_tool_metadata(tool_name: str) -> Dict[str, Any]:
    """Get metadata (category, alternative) for a tool"""
    return TOOL_METADATA.get(tool_name, {"category": "general"})

class DomainExplanation(BaseModel):
    """Scalable explanation schema - adapts to any tool"""
    
    # REQUIRED
    decision: str = Field(description="What action was taken")
    reasoning: str = Field(description="Why this was necessary")
    
    # OPTIONAL - LLM decides which to fill based on tool type
    tool_justification: Optional[str] = Field(
        default=None,
        description="Why THIS tool was appropriate for the task"
    )
    contrastive_explanation: Optional[str] = Field(
        default=None,
        description="Why alternative was NOT used (if applicable)"
    )
    data_evidence: Optional[str] = Field(
        default=None,
        description="Concrete data used in decision (e.g., row_count, data size)"
    )


class EnhancedExplainerNode:
  
    def __init__(self, llm, available_tools: List[Any] = None):
        self.llm = llm
        self.available_tools = available_tools or []
        self.tool_names = [tool.name for tool in self.available_tools if hasattr(tool, 'name')]
        # Build description lookup from actual tool objects
        self.tool_descriptions = {
            tool.name: tool.description 
            for tool in self.available_tools 
            if hasattr(tool, 'name') and hasattr(tool, 'description')
        }
    
    def _get_tool_description(self, tool_name: str) -> str:
        return self.tool_descriptions.get(tool_name, "")
    
    def _extract_row_count(self, messages: List) -> Optional[int]:
        for msg in reversed(messages):
            if hasattr(msg, 'name') and msg.name == 'text2SQL':
                try:
                    output = json.loads(msg.content)
                    return output.get("row_count")
                except:
                    pass
        return None
    
    def _extract_conversation_context(self, messages: List, max_tools: int = 5) -> str:
        tool_history = []
        
        for msg in reversed(messages):
            if len(tool_history) >= max_tools:
                break
            
            # Get tool messages
            if hasattr(msg, 'name') and msg.name:
                tool_name = msg.name
                content_preview = str(msg.content)[:200] if hasattr(msg, 'content') else ""
                tool_history.insert(0, f"- {tool_name}: {content_preview}")
        
        if tool_history:
            return "Prior tool executions:\n" + "\n".join(tool_history)
        return ""
    
    def _build_explanation_prompt(
        self,
        tool_name: str,
        tool_input: str,
        tool_output: str,
        context: str,
        row_count: Optional[int] = None,
        conversation_context: str = ""
    ) -> str:
        
        metadata = get_tool_metadata(tool_name)
        alternative = metadata.get("alternative")
        category = metadata.get("category", "general")
        
        # Get description from actual tool objects
        tool_desc = self._get_tool_description(tool_name)
        
        prompt = f"""You are explaining tool executions for a data exploration agent.
Your explanations should be user-friendly and help users understand WHY decisions were made.

**CURRENT TOOL EXECUTION**:
- Tool: {tool_name}
- Category: {category}
- Description: {tool_desc}
- Input: {tool_input}
- Output Preview: {str(tool_output)[:500]}

**USER CONTEXT**: {context}
"""
        
        # Add conversation context if available
        if conversation_context:
            prompt += f"\n**CONVERSATION HISTORY**:\n{conversation_context}\n"
        
        # Add row count if available
        if row_count is not None:
            prompt += f"\n**DATA EVIDENCE**: Query returns {row_count} rows"
        
        # Add alternative context if exists
        if alternative:
            alt_desc = self._get_tool_description(alternative)
            prompt += f"""

**ALTERNATIVE TOOL**: {alternative}
- Description: {alt_desc}
"""
        
        prompt += """

**YOUR TASK**:
Generate an explanation with the following fields:

REQUIRED:
- decision: What action was taken (1-2 sentences, user-friendly)
- reasoning: Why this was necessary (1-2 sentences)

OPTIONAL (fill only what's relevant for this specific tool):
- tool_justification: Why THIS tool was the right choice
- contrastive_explanation: Why the alternative was NOT used (only if there's an alternative)
- data_evidence: Concrete data supporting the decision (row count, data size, etc.)

**GUIDELINES**:
- Be specific to this tool, not generic
- Use concrete numbers when available (row_count)
- If there's an alternative, explain WHY NOT
- Keep it concise and user-friendly
"""
        
        return prompt
    
    def _get_fallback_explanation(self, step: Dict[str, Any]) -> DomainExplanation:
        """Generate fallback explanation when LLM fails"""
        tool_name = step.get('tool_name', 'tool')
        
        return DomainExplanation(
            decision=f"Executed {tool_name}",
            reasoning=f"Required to process the user's request",
            tool_justification=self._get_tool_description(tool_name) or None
        )
    
    def explain_step(self, step: Dict[str, Any], messages: List = None) -> DomainExplanation:
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
            # Extract evidence from messages
            row_count = None
            conversation_context = ""
            if messages:
                row_count = self._extract_row_count(messages)
                conversation_context = self._extract_conversation_context(messages)
            
            # Build adaptive prompt with full context
            prompt = self._build_explanation_prompt(
                tool_name, tool_input, tool_output, context, 
                row_count, conversation_context
            )
            
            llm_messages = [SystemMessage(content=prompt)]
            
            # Use structured output
            llm_with_structure = self.llm.with_structured_output(DomainExplanation)
            explanation = llm_with_structure.invoke(llm_messages)
            
            logger.info(f"Generated explanation for {tool_name}")
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return self._get_fallback_explanation(step)
    
    async def explain_step_async(self, step: Dict[str, Any], messages: List = None) -> DomainExplanation:
        """
        Async version of explain_step for parallel execution.
        
        Args:
            step: Dictionary containing tool_name, input, output, context
            messages: Conversation messages for extracting evidence (row_count)
            
        Returns:
            DomainExplanation with relevant fields filled
        """
        try:
            tool_name = step.get("tool_name", "unknown")
            tool_input = step.get("input", "")
            tool_output = step.get("output", "")
            context = step.get("context", "")
            
            # Extract evidence from messages
            row_count = None
            conversation_context = ""
            if messages:
                row_count = self._extract_row_count(messages)
                conversation_context = self._extract_conversation_context(messages)
            
            # Build adaptive prompt with full context
            prompt = self._build_explanation_prompt(
                tool_name, tool_input, tool_output, context, 
                row_count, conversation_context
            )
            
            llm_messages = [SystemMessage(content=prompt)]
            
            # Use structured output with ainvoke for async
            llm_with_structure = self.llm.with_structured_output(DomainExplanation)
            explanation = await llm_with_structure.ainvoke(llm_messages)
            
            logger.info(f"Generated explanation for {tool_name}")
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return self._get_fallback_explanation(step)
    
    async def explain_multiple_steps_async(
        self, 
        steps: List[Dict[str, Any]],
        messages: List = None,
        max_concurrent: int = 3
    ) -> List[DomainExplanation]:
        """
        Generate explanations for multiple steps in parallel with rate limiting.
        
        Args:
            steps: List of step dictionaries
            messages: Conversation messages
            max_concurrent: Maximum concurrent LLM calls (default 3 for rate limiting)
            
        Returns:
            List of DomainExplanation objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def limited_explain(step):
            async with semaphore:
                return await self.explain_step_async(step, messages)
        
        return await asyncio.gather(*[limited_explain(step) for step in steps])
    
    def execute_sync(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronous execution - generate explanations for steps.
        
        Args:
            state: Agent state containing steps to explain
            
        Returns:
            Updated state with explanations
        """
        steps = state.get("steps", [])
        messages = state.get("messages", [])
        
        # Find steps that need explanation
        steps_needing_explanation = []
        step_indices = []
        
        for i, step in enumerate(steps):
            if "decision" not in step or "reasoning" not in step:
                steps_needing_explanation.append(step)
                step_indices.append(i)
        
        if steps_needing_explanation:
            # Generate explanations sequentially (simpler, no async issues)
            explanations = []
            for step in steps_needing_explanation:
                try:
                    explanation = self.explain_step(step, messages)
                    explanations.append(explanation)
                except Exception as e:
                    logger.error(f"Error explaining step: {e}")
                    # Use fallback
                    explanations.append(DomainExplanation(
                        decision=f"Executed {step.get('tool_name', 'unknown')}",
                        reasoning="Required to process the user's request"
                    ))
            
            # Update steps with explanations
            updated_steps = steps.copy()
            for idx, explanation in zip(step_indices, explanations):
                updated_steps[idx] = {
                    **updated_steps[idx],
                    "decision": explanation.decision,
                    "reasoning": explanation.reasoning,
                    "tool_justification": explanation.tool_justification,
                    "contrastive_explanation": explanation.contrastive_explanation,
                    "data_evidence": explanation.data_evidence,
                }
            
            return {
                **state,
                "steps": updated_steps
            }
        
        return state
    
    def explain_multiple_steps(
        self, 
        steps: List[Dict[str, Any]],
        messages: List = None
    ) -> List[DomainExplanation]:
        """Generate explanations for multiple steps."""
        explanations = []
        for step in steps:
            explanation = self.explain_step(step, messages)
            explanations.append(explanation)
        return explanations
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execute method - just call sync version directly.
        
        Args:
            state: Agent state containing steps to explain
            
        Returns:
            Updated state with explanations
        """
        try:
            return self.execute_sync(state)
        except Exception as e:
            logger.error(f"Error in EnhancedExplainerNode.execute: {e}")
            # Return state unchanged if explanation fails
            return state
