"""User preference prompt builder"""
import logging
from typing import Optional, Dict, Any
from functools import lru_cache
from app.services.redis_profile_service import RedisProfileService
from app.services.profile_service import ProfileService

logger = logging.getLogger(__name__)


class UserPreferenceContext:
    def __init__(
        self,
        redis_service: Optional[RedisProfileService] = None,
        profile_service: Optional[ProfileService] = None
    ):
        self.redis_service = redis_service
        self.profile_service = profile_service
    
    def get_preferences_prompt(self, user_id: Optional[str]) -> str:
        if not user_id or not self.redis_service or not self.profile_service:
            return ""
        
        try:
            return get_user_preference_prompt(
                user_id=user_id,
                redis_service=self.redis_service,
                profile_service=self.profile_service
            )
        except Exception as e:
            logger.warning(f"Failed to fetch user preferences for {user_id}: {e}")
            return ""
    
    def is_available(self) -> bool:
        return self.redis_service is not None and self.profile_service is not None


def get_user_preference_prompt(
    user_id: str,
    redis_service: RedisProfileService,
    profile_service: ProfileService
) -> str:
    # Try cache first
    prefs = redis_service.get_preferences(user_id)
    
    # Cache miss - fetch from database
    if not prefs:
        logger.info(f"Cache miss for user {user_id}, fetching from database")
        prefs = profile_service.get_profile(user_id)
        
        if prefs:
            # Cache for next time
            redis_service.store_preferences(user_id, prefs)
    
    return _build_prompt(prefs)


def _build_prompt(prefs: Optional[Dict[str, Any]]) -> str:
    if not prefs:
        return ""
    
    sections = []
    
    # User context - directive format
    if prefs.get('nickname') or prefs.get('role'):
        sections.append("**USER PROFILE REQUIREMENTS:**")
        if prefs.get('nickname'):
            sections.append(f"- Address the user as '{prefs['nickname']}' when appropriate")
        if prefs.get('role'):
            sections.append(f"- Tailor responses for a user with role: {prefs['role']}")
    
    # About user - convert to actionable context
    if prefs.get('about_user'):
        sections.append(f"\n**CONTEXT AWARENESS:**")
        sections.append(f"Consider the following about the user when planning and executing tasks:")
        sections.append(f"{prefs['about_user']}")
    
    # Communication style - imperative directives
    style = prefs.get('communication_style', 'balanced')
    style_map = {
        'concise': 'ALWAYS be extremely brief and direct. Use short sentences. Provide ONLY final results and key numbers. Skip explanations, examples, and technical details entirely. One or two sentences maximum per section.',
        'balanced': 'Balance brevity with clarity. Provide sufficient detail without being verbose. AVOID technical jargon (SQL queries, tool names, technical implementation details). Focus on WHAT happened and WHY it matters in plain language. Use 2-3 sentences per section.',
        'detailed': 'ALWAYS provide comprehensive, thorough explanations with examples and context. Include step-by-step breakdowns. You MAY include technical details (SQL queries, tool names, algorithms) BUT you MUST explain them in accessible, non-technical language FIRST. Use multiple paragraphs if needed.'
    }
    sections.append(f"\n**COMMUNICATION RULES:**")
    sections.append(f"- {style_map.get(style, style_map['balanced'])}")
    
    # Custom instructions - highest priority
    if prefs.get('custom_instructions'):
        sections.append(f"\n**MANDATORY USER INSTRUCTIONS:**")
        sections.append(f"You MUST follow these specific user requirements:")
        sections.append(f"{prefs['custom_instructions']}")
    
    return "\n".join(sections)


def get_user_preference_prompt_safe(
    user_id: Optional[str],
    redis_service: Optional[RedisProfileService],
    profile_service: Optional[ProfileService]
) -> str:
    """
    Safely fetch user preferences with fallback to empty string.
    
    This is a convenience wrapper around get_user_preference_prompt that
    handles None values and exceptions gracefully.
    
    Args:
        user_id: User ID to fetch preferences for (can be None)
        redis_service: Redis profile service (can be None)
        profile_service: Profile service (can be None)
    
    Returns:
        Formatted preference prompt string, or empty string if unavailable
    """
    if not user_id or not redis_service or not profile_service:
        return ""
    
    try:
        return get_user_preference_prompt(user_id, redis_service, profile_service)
    except Exception as e:
        logger.warning(f"Failed to fetch user preferences for {user_id}: {e}")
        return ""
