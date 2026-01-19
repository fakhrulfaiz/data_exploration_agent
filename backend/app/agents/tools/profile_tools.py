"""
Profile management tool for the assistant agent.
"""

from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool("update_user_profile")
def update_user_profile(
    nickname: Optional[str] = None,
    role: Optional[str] = None,
    about_user: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    communication_style: Optional[str] = None
) -> str:
    """Update the user's profile preferences. Use this when the user explicitly asks to update their profile settings or preferences.
    
    Args:
        nickname: User's preferred nickname (e.g., "Faiz", "Alex")
        role: User's role or job title (e.g., "Data Analyst", "Researcher")
        about_user: Information about the user's work or interests
        custom_instructions: Custom instructions for how the agent should behave
        communication_style: Preferred communication style - must be one of: "concise", "detailed", or "balanced"
    
    Returns:
        Success or error message
    
    Examples:
        - User says "Call me Faiz" -> update_user_profile(nickname="Faiz")
        - User says "I'm a data scientist" -> update_user_profile(role="Data Scientist")
        - User says "Be more concise" -> update_user_profile(communication_style="concise")
    """
    try:
        from app.services.dependencies import get_profile_service
        from langgraph.prebuilt import InjectedState
        from typing import Annotated, Dict, Any
        
        # Try to get user_id from LangGraph config (works with context_schema)
        user_id = None
        try:
            from langgraph.config import get_config
            config = get_config()
            if config and "configurable" in config:
                user_id = config["configurable"].get("user_id")
        except Exception as e:
            logger.debug(f"Could not get user_id from config: {e}")
        
        logger.info(f"Profile tool called. User ID: {user_id}")
        
        if not user_id:
            error_msg = "Error: User ID not found in session. This tool requires an authenticated user context."
            logger.warning(f"{error_msg}. This is expected in playground/testing environments.")
            return error_msg
        
        # Build updates dictionary with only provided values
        updates = {}
        if nickname is not None:
            updates["nickname"] = nickname
        if role is not None:
            updates["role"] = role
        if about_user is not None:
            updates["about_user"] = about_user
        if custom_instructions is not None:
            updates["custom_instructions"] = custom_instructions
        if communication_style is not None:
            # Validate communication style
            valid_styles = ["concise", "detailed", "balanced"]
            if communication_style.lower() not in valid_styles:
                return f"Error: communication_style must be one of: {', '.join(valid_styles)}"
            updates["communication_style"] = communication_style.lower()
        
        if not updates:
            return "No profile fields provided to update"
        
        # Update profile
        profile_service = get_profile_service()
        success = profile_service.update_profile(user_id, updates)
        
        if success:
            updated_fields = ", ".join(updates.keys())
            logger.info(f"Successfully updated profile for user {user_id}: {updated_fields}")
            return f"Successfully updated your profile: {updated_fields}"
        else:
            return "Failed to update profile. Please try again."
            
    except Exception as e:
        logger.error(f"Error in update_user_profile tool: {e}", exc_info=True)
        return f"Error updating profile: {str(e)}"
