"""
Profile Service for managing user profiles and custom instructions.
"""

import logging
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ProfileService:
    """Service for managing user profiles."""
    
    def __init__(self):
        try:
            from supabase import create_client, Client
            
            self.client: Client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key
            )
            
            logger.info("Initialized ProfileService")
        except ImportError:
            logger.error("Supabase client not installed. Install with: pip install supabase")
            raise
    
    def get_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile.
        
        Returns:
        {
            "id": "uuid",
            "name": "User Name",
            "email": "user@example.com",
            "nickname": "Faiz",
            "role": "Data Analyst",
            "about_user": "I work with...",
            "custom_instructions": "Be concise...",
            "communication_style": "balanced"
        }
        """
        try:
            response = self.client.table("profiles").select(
                "id, name, email, nickname, role, about_user, custom_instructions, communication_style"
            ).eq("id", user_id).single().execute()
            
            if not response.data:
                logger.warning(f"No profile found for user_id: {user_id}")
                return {}
            
            return response.data
            
        except Exception as e:
            logger.error(f"Failed to fetch profile for {user_id}: {str(e)}")
            return {}
    
    def update_profile(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update user profile.
        
        Accepts:
        {
            "nickname": "Faiz",
            "role": "Data Analyst",
            "about_user": "...",
            "custom_instructions": "...",
            "communication_style": "concise"
        }
        """
        try:
            # Whitelist allowed update fields
            allowed_fields = [
                "nickname", 
                "role", 
                "about_user", 
                "custom_instructions", 
                "communication_style"
            ]
            
            safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}
            
            # Validate communication_style
            if "communication_style" in safe_updates:
                if safe_updates["communication_style"] not in ["concise", "detailed", "balanced"]:
                    logger.warning(f"Invalid communication_style: {safe_updates['communication_style']}")
                    safe_updates.pop("communication_style")
            
            if not safe_updates:
                logger.warning(f"No valid fields to update for user_id: {user_id}")
                return False
            
            response = self.client.table("profiles").update(safe_updates).eq("id", user_id).execute()
            
            if not response.data:
                logger.warning(f"Failed to update profile for user_id: {user_id}")
                return False
            
            logger.info(f"Successfully updated profile for user_id: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating profile for {user_id}: {str(e)}")
            return False

