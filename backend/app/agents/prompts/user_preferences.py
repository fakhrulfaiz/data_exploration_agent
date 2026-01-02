"""User preference prompt builder"""
import logging
from typing import Optional, Dict, Any
from app.services.redis_profile_service import RedisProfileService
from app.services.profile_service import ProfileService

logger = logging.getLogger(__name__)


def get_user_preference_prompt(
    user_id: str,
    redis_service: RedisProfileService,
    profile_service: ProfileService
) -> str:
    """
    Fetch user preferences and build personalized prompt.
    Uses Redis cache with database fallback.
    
    Args:
        user_id: User ID to fetch preferences for
        redis_service: Redis profile service (injected)
        profile_service: Profile service (injected)
    """
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
        'concise': 'ALWAYS be brief and to-the-point. Avoid lengthy explanations unless explicitly requested.',
        'detailed': 'ALWAYS provide comprehensive explanations with examples and context. Prioritize thoroughness over brevity.',
        'balanced': 'Balance brevity with clarity. Provide sufficient detail without being verbose.'
    }
    sections.append(f"\n**COMMUNICATION RULES:**")
    sections.append(f"- {style_map.get(style, style_map['balanced'])}")
    
    # Custom instructions - highest priority
    if prefs.get('custom_instructions'):
        sections.append(f"\n**MANDATORY USER INSTRUCTIONS:**")
        sections.append(f"You MUST follow these specific user requirements:")
        sections.append(f"{prefs['custom_instructions']}")
    
    return "\n".join(sections)
