"""
Error Explainer Node for generating user-friendly error explanations.
Provides context-aware explanations using Database Schema and History.
"""

from langchain_core.messages import SystemMessage, BaseMessage
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging
import json
from sqlalchemy import inspect
from app.services.redis_dataframe_service import get_redis_dataframe_service

logger = logging.getLogger(__name__)


class ErrorExplanation(BaseModel):
    what_happened: str = Field(description="Simple, user-friendly description of what went wrong")
    why_it_happened: str = Field(description="Root cause analysis in plain language")
    
    # NEW: Focused clarifying questions to help resolve the issue
    clarifying_questions: List[str] = Field(
        default=[],
        description="List of specific questions to help user resolve the issue (max 2 to avoid hallucination)"
    )
    
    # Simplified: Single clear next step instead of multiple suggestions
    next_step: str = Field(description="Single clear action user should take to resolve the issue")


class ErrorExplainerNode:
    """
    Node that generates user-friendly explanations when errors occur.
    Uses conversation context to provide relevant suggestions.
    """
    
    def __init__(self, llm, db_engine=None):
        self.llm = llm
        self.db_engine = db_engine

    def _gather_context(self, error_info: Dict[str, Any], df_id: Optional[str] = None) -> str:
        """
        Dynamically gather system context based on which tool failed.
        This provides the 'Ground Truth' to prevent hallucinations.
        """
        tool_name = error_info.get("tool_name", "")
        details = error_info.get("details", {})
        
        context_lines = []

        # 1. SQL / Database Errors
        if tool_name in ["data_exploration_tool", "sql_db_tool"] or "sql" in str(error_info).lower():
            if self.db_engine:
                try:
                    inspector = inspect(self.db_engine)
                    tables = inspector.get_table_names()
                    context_lines.append(f"Database Reality Check: The database contains these tables: {', '.join(tables)}.")
                    
                    # Enhanced: Fetch columns for each table to debug 'column not found' errors
                    for table in tables:
                        try:
                            columns = [col['name'] for col in inspector.get_columns(table)]
                            context_lines.append(f" - Table '{table}' has columns: {', '.join(columns)}")
                        except Exception as inner_e:
                            logger.warning(f"Could not fetch columns for table {table}: {inner_e}")
                            
                except Exception as e:
                    context_lines.append(f"Database Reality Check: Could not fetch schema ({str(e)}).")

        # 2. DataFrame / Analysis / Plotting Errors
        if tool_name in ["smart_data_analysis", "large_plotting_tool", "image_batch_qa_tool"]:
            # Try to find df_id in multiple places
            target_df_id = df_id or details.get("df_id")
            
            if target_df_id:
                try:
                    redis_service = get_redis_dataframe_service()
                    metadata = redis_service.get_metadata(target_df_id)
                    if metadata:
                        cols = metadata.get("columns", [])
                        shape = metadata.get("shape", "unknown")
                        context_lines.append(f"DataFrame Reality Check (ID: {target_df_id}):")
                        context_lines.append(f" - Shape: {shape}")
                        context_lines.append(f" - Actual Columns: {', '.join(map(str, cols))}")
                    else:
                        context_lines.append(f"DataFrame Reality Check: DataFrame {target_df_id} EXPIRED or invalid.")
                except Exception as e:
                     context_lines.append(f"DataFrame Reality Check: Error checking cache ({str(e)}).")
            else:
                 context_lines.append("DataFrame Reality Check: No DataFrame ID found in error context.")

        if not context_lines:
             return "No specific system context available for this tool."
             
        return "\n".join(context_lines)
    
    def explain_error(
        self, 
        error_info: Dict[str, Any],
        conversation_messages: List[BaseMessage],
        df_id: Optional[str] = None
    ) -> ErrorExplanation:
        """
        Generate a user-friendly error explanation.
        """
        try:
            error_message = error_info.get("error_message", "Unknown error")
            error_type = error_info.get("error_type", "Error")
            tool_name = error_info.get("tool_name", "unknown tool")
            tool_input = error_info.get("tool_input", {})
            
            # Extract recent user messages for context
            recent_context = ""
            logger.info(f"Extracting context from {len(conversation_messages)} messages")
            for msg in reversed(conversation_messages[-5:]):  # Last 5 messages
                if hasattr(msg, 'content') and msg.content:
                    msg_type = type(msg).__name__
                    logger.info(f"Processing message type: {msg_type}, content: {str(msg.content)[:50]}")
                    if 'HumanMessage' in msg_type:
                        recent_context += f"User: {msg.content}\n"
                    elif 'AIMessage' in msg_type and not hasattr(msg, 'tool_calls'):
                        recent_context += f"Assistant: {msg.content[:100]}...\n"
            
            # Get user preferences (full profile, not just communication style)
            user_id = error_info.get('user_id')  # Pass user_id in error_info from state
            user_preferences = ""
            if user_id:
                try:
                    from app.services.dependencies import get_redis_profile_service, get_profile_service
                    from app.agents.prompts.user_preferences import get_user_preference_prompt_safe
                    
                    redis_service = get_redis_profile_service()
                    profile_service = get_profile_service()
                    user_preferences = get_user_preference_prompt_safe(
                        user_id,
                        redis_service,
                        profile_service
                    )
                except Exception as e:
                    logger.warning(f"Failed to fetch user preferences in error explainer: {e}")
            
            # Build system prompt with user preferences
            base_system_prompt = """You are an AI assistant helping users understand what went wrong when an error occurs.

Your Role:
- Analyze technical errors and translate them into simple, non-technical language
- Provide actionable solutions and guidance
- Be empathetic and helpful"""
            
            if user_preferences:
                system_prompt = user_preferences + "\n\n" + base_system_prompt
            else:
                system_prompt = base_system_prompt

            human_prompt = f"""**Error Details:**
- Error Type: {error_type}
- Error Message: {error_message}
- Tool That Failed: {tool_name}
- Tool Input: {tool_input}

**Recent Conversation Context:**
{recent_context}

**System Knowledge (Grounding Context):**
{self._gather_context(error_info, df_id)}

**Your Task:**
Generate a focused, natural error explanation with these fields:

1. **what_happened**: Explain what went wrong in natural, first-person language
   - Be specific about what failed
   - Use conversational phrasing like "I tried to..." or "I couldn't find..."
   
2. **why_it_happened**: Provide detailed analysis of the root cause (2-3 sentences minimum)
   - Explain the underlying reason in detail
   - Reference specific details from the error context (table names, column names, etc.)
   - Help the user understand the technical reason in accessible language
   
3. **clarifying_questions**: Ask 1-2 SPECIFIC questions based on the error:
   - If column not found → Ask about alternative column names from actual schema
   - If table not found → Ask which table they meant from actual tables
   - If data missing → Ask about date range or filters
   - Keep it focused - max 2 questions
   
4. **next_step**: Provide clear, conversational guidance (mention 1-3 action options)
   - Explain WHAT to do and WHY it will help
   - Mention if they should Retry (with what change), Replan (why), or Cancel (why not possible)
   - Use natural language, not robotic instructions

**CRITICAL RULES:**
- ONLY use information from "System Knowledge (Grounding Context)" above
- DO NOT suggest columns/tables that aren't in the actual schema
- Use first-person, conversational language ("I tried to...", "I found that...")
- Provide detailed analysis (2-3 sentences minimum for why_it_happened)
- Be empathetic and helpful, not blaming

**Example for "table 'customer' not found":**
{{
  "what_happened": "I tried to query the 'customer' table, but it doesn't exist in your database.",
  "why_it_happened": "After checking your database schema, I found that only the 'paintings' table is available. The 'customer' table you're asking about hasn't been created yet, or it might be named differently in your database structure.",
  "clarifying_questions": ["Did you mean to query the 'paintings' table instead? It contains columns: title, artist, year_created, movement"],
  "next_step": "I recommend trying again (Retry) with the 'paintings' table instead. If you actually need customer data, you'll need to either create that table first or check if the data exists under a different name. Would you like me to show you what's in the paintings table?"
}}

Generate a structured explanation following the ErrorExplanation model."""

            from langchain_core.messages import HumanMessage
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            llm_with_structure = self.llm.with_structured_output(ErrorExplanation)
            explanation = llm_with_structure.invoke(messages)
      
            logger.info(f"Generated error explanation for {tool_name} failure")
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating error explanation: {e}")
      
            return ErrorExplanation(
                what_happened=f"An error occurred while using {tool_name}",
                why_it_happened="The system encountered an unexpected issue",
                clarifying_questions=[
                    "Would you like to try rephrasing your question?",
                    "Should I show you what data is available?"
                ],
                next_step="Please try again with a different approach or contact support if the issue persists"
            )
    
    def _get_communication_style_directive(self, user_id: Optional[str] = None) -> str: 
        if not user_id:
            return ""
        
        try:
            from app.services.dependencies import get_redis_profile_service, get_profile_service
            redis_service = get_redis_profile_service()
            profile_service = get_profile_service()
            
            profile = profile_service.get_user_profile(user_id)
            style = profile.get('communication_style', 'balanced') if profile else 'balanced'
            
        except Exception as e:
            logger.warning(f"Failed to fetch communication style: {e}")
            style = 'balanced'
        
        directives = {
            'concise': """
**ERROR COMMUNICATION STYLE: CONCISE**
- One sentence for what happened
- One sentence for why
- One specific clarifying question
- One clear next step
- Skip lengthy explanations
Example: "Column 'inception' not found. The database uses 'year_created' instead. Did you mean 'year_created'? Try using 'year_created' in your query."
""",
            'detailed': """
**ERROR COMMUNICATION STYLE: DETAILED**
- Explain what the user was trying to do
- Explain why the system couldn't do it
- Provide context about the database structure
- Ask clarifying questions with full context
- Explain the recommended next step
Example: "You asked about 'inception' dates for paintings, but our database schema uses the column name 'year_created' to track when artworks were made. The 'inception' column doesn't exist in the artworks table, which has columns: title, artist, year_created, movement, img_path. Would you like to see paintings sorted by 'year_created' instead? I can help you rephrase the query to use the correct column name."
""",
            'balanced': """
**ERROR COMMUNICATION STYLE: BALANCED**
- Clear explanation of the error
- Brief context about why it occurred
- One focused clarifying question with available options
- Clear next step
Example: "The column 'inception' doesn't exist in our database. The artworks table uses 'year_created' instead. Did you mean 'year_created'? (Available date columns: year_created, acquisition_date). Try rephrasing your question using 'year_created' instead of 'inception'."
"""
        }
        
        return directives.get(style, directives['balanced'])
    
    def execute(self, state: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        messages = state.get("messages", [])
        df_id = kwargs.get("df_id") # extracted passed arg
        
        # 1. Try to get explicit error info from state
        error_info = state.get("error_info")
        
        # 2. If missing, try to extract from the last ToolMessage (robust fallback)
        if not error_info and messages:
             # Find the last tool message
            tool_messages = [msg for msg in messages if type(msg).__name__ == "ToolMessage"]
            if tool_messages:
                last_tool_msg = tool_messages[-1]
                content = str(last_tool_msg.content)
                tool_name = getattr(last_tool_msg, "name", "unknown_tool")
                
                extracted_error = None
                
                # Check JSON
                import json
                try:
                    content_json = json.loads(content)
                    if isinstance(content_json, dict) and "error" in content_json:
                        extracted_error = content_json["error"]
                except json.JSONDecodeError:
                    pass
                
                # Check String Prefix
                if not extracted_error:
                    if content.startswith("Error:") or "error" in content.lower():
                        extracted_error = content
                
                if extracted_error:
                    error_info = {
                        "error_message": extracted_error,
                        "error_type": "ToolExecutionError",
                        "tool_name": tool_name,
                        "tool_input": "See conversation history",
                        "user_id": state.get("user_id")  # NEW: Pass user_id for style directive
                    }
                    logger.info(f"Extracted error info from tool message: {extracted_error[:100]}...")

        if not error_info:
            logger.warning("Error explainer called but could not find error info")
            # Create a generic error placeholder so we still explain *something*
            error_info = {
                "error_message": "An unspecified error occurred during execution.",
                "error_type": "UnknownError",
                "tool_name": "Agent System",
                "tool_input": "N/A",
                "user_id": state.get("user_id")  # NEW: Pass user_id for style directive
            }
        
        # 4. Generate Explanation (with dual detection support)
        explanation_result = self.explain_error(error_info or {}, messages, df_id=df_id)
        
        return {
            "error_explanation": explanation_result.model_dump(),
            "error_details": [],  # Clear error details to prevent rerunning error_explainer
            "feedback": None  # Clear feedback as well
        }
