"""
Error Explainer Node for generating user-friendly error explanations.
Provides context-aware explanations when tool execution or agent operations fail.
"""

from langchain_core.messages import SystemMessage, BaseMessage
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class ErrorExplanation(BaseModel):
    what_happened: str = Field(description="Simple, user-friendly description of what went wrong")
    why_it_happened: str = Field(description="Root cause analysis in plain language")
    what_was_attempted: str = Field(description="What the agent was trying to accomplish")
    alternative_suggestions: List[str] = Field(description="List of alternative approaches or solutions")
    user_action_needed: str = Field(description="Clear guidance on what the user should do next")
    technical_details: Optional[str] = Field(default=None, description="Optional technical details for advanced users")


class ErrorExplainerNode:
    """
    Node that generates user-friendly explanations when errors occur.
    Uses conversation context to provide relevant suggestions.
    """
    
    def __init__(self, llm):
        self.llm = llm
    
    def explain_error(
        self, 
        error_info: Dict[str, Any],
        conversation_messages: List[BaseMessage]
    ) -> ErrorExplanation:
        """
        Generate a user-friendly error explanation.
        
        Args:
            error_info: Dictionary containing error details (error_message, error_type, tool_name, tool_input)
            conversation_messages: Recent conversation messages for context
            
        Returns:
            ErrorExplanation object with user-friendly explanation
        """
        try:
            error_message = error_info.get("error_message", "Unknown error")
            error_type = error_info.get("error_type", "Error")
            tool_name = error_info.get("tool_name", "unknown tool")
            tool_input = error_info.get("tool_input", {})
            
            # Extract recent user messages for context
            recent_context = ""
            for msg in reversed(conversation_messages[-5:]):  # Last 5 messages
                if hasattr(msg, 'content') and msg.content:
                    msg_type = type(msg).__name__
                    if 'HumanMessage' in msg_type:
                        recent_context += f"User: {msg.content}\n"
                    elif 'AIMessage' in msg_type and not hasattr(msg, 'tool_calls'):
                        recent_context += f"Assistant: {msg.content[:100]}...\n"
            
            prompt = f"""You are an AI assistant helping users understand what went wrong when an error occurs.

**Error Details:**
- Error Type: {error_type}
- Error Message: {error_message}
- Tool That Failed: {tool_name}
- Tool Input: {tool_input}

**Recent Conversation Context:**
{recent_context}

**Your Task:**
Generate a helpful, user-friendly error explanation that:
1. Explains what happened in simple terms (avoid technical jargon)
2. Explains why it happened (root cause)
3. Describes what the system was trying to do
4. Provides 2-3 specific alternative suggestions or solutions
5. Gives clear guidance on what the user should do next

**Guidelines:**
- Be empathetic and helpful, not blaming
- Use plain language that non-technical users can understand
- Provide actionable suggestions
- If it's a SQL error, suggest checking table names, column names, or query syntax
- If it's a tool error, suggest alternative tools or approaches
- Keep explanations concise but complete

Generate a structured explanation following the ErrorExplanation model."""

            messages = [SystemMessage(content=prompt)]
            
            llm_with_structure = self.llm.with_structured_output(ErrorExplanation)
            explanation = llm_with_structure.invoke(messages)
            
            explanation.technical_details = f"{error_type}: {error_message}"
            
            logger.info(f"Generated error explanation for {tool_name} failure")
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating error explanation: {e}")
      
            return ErrorExplanation(
                what_happened=f"An error occurred while using {tool_name}",
                why_it_happened="The system encountered an unexpected issue",
                what_was_attempted=f"The system was trying to execute {tool_name}",
                alternative_suggestions=[
                    "Try rephrasing your question",
                    "Check if the data you're asking about exists",
                    "Try a simpler query first"
                ],
                user_action_needed="Please try again with a different approach or contact support if the issue persists",
                technical_details=str(error_info.get("error_message", "Unknown error"))
            )
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        error_info = state.get("error_info")
        if not error_info:
            logger.warning("Error explainer called but no error_info in state")
            return state
        
        messages = state.get("messages", [])
        
        explanation = self.explain_error(error_info, messages)
        
        explanation_dict = explanation.model_dump()
    
        from langchain_core.messages import ToolMessage
        
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        
        # tool_call_id = None
        # if last_message and hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        #     tool_call_id = last_message.tool_calls[0].get('id')
        
        # if tool_call_id:
        #     error_tool_message = ToolMessage(
        #         content=f"Error: {error_info.get('error_message', 'Unknown error')}",
        #         tool_call_id=tool_call_id,
        #         name=error_info.get('tool_name', 'unknown')
        #     )
        #     messages = messages + [error_tool_message]
        
        return {
            "error_explanation": explanation_dict,
            "messages": messages
        }
