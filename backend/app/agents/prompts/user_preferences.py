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
    
    # User context
    if prefs.get('nickname') or prefs.get('role'):
        sections.append("USER CONTEXT:")
        if prefs.get('nickname'):
            sections.append(f"- User: {prefs['nickname']}")
        if prefs.get('role'):
            sections.append(f"- Role: {prefs['role']}")
    
    # About user
    if prefs.get('about_user'):
        sections.append(f"\nABOUT USER:\n{prefs['about_user']}")
    
    # Communication style
    style = prefs.get('communication_style', 'balanced')
    style_map = {
        'concise': 'Be brief and to-the-point.',
        'detailed': 'Provide comprehensive explanations.',
        'balanced': 'Balance brevity with clarity.'
    }
    sections.append(f"\nSTYLE: {style_map.get(style, style_map['balanced'])}")
    
    # Custom instructions
    if prefs.get('custom_instructions'):
        sections.append(f"\nCUSTOM INSTRUCTIONS:\n{prefs['custom_instructions']}")
    
    return "\n".join(sections)
