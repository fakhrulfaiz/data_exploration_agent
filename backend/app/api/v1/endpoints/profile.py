"""
Profile API endpoints for managing user profiles.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.services.profile_service import ProfileService
from app.services.redis_profile_service import RedisProfileService
from app.services.dependencies import get_profile_service, get_redis_profile_service
from app.models.supabase_user import SupabaseUser
from app.core.auth import get_current_user


router = APIRouter(
    prefix="/profile",
    tags=["profile"]
)


class ProfileUpdateRequest(BaseModel):
    nickname: Optional[str] = None
    role: Optional[str] = None
    about_user: Optional[str] = None
    custom_instructions: Optional[str] = None
    communication_style: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    nickname: Optional[str] = None
    role: Optional[str] = None
    about_user: Optional[str] = None
    custom_instructions: Optional[str] = None
    communication_style: str = "balanced"


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: SupabaseUser = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """
    Get user profile.
    
    Returns:
    {
        "id": "uuid",
        "name": "User Name",
        "email": "user@example.com",
        "nickname": "Faiz",
        "role": "Data Analyst",
        "about_user": "I work with financial data...",
        "custom_instructions": "Be concise and technical...",
        "communication_style": "balanced"
    }
    """
    try:
        profile_data = profile_service.get_profile(current_user.user_id)
        
        if not profile_data:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        return ProfileResponse(**profile_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")


@router.put("", response_model=Dict[str, Any])
async def update_profile(
    request: ProfileUpdateRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service),
    redis_service: RedisProfileService = Depends(get_redis_profile_service)
):
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
        # Only include non-None fields
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        success = profile_service.update_profile(current_user.user_id, updates)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update profile")
        
        # Invalidate Redis cache
        redis_service.invalidate_preferences(current_user.user_id)
        
        return {
            "success": True,
            "message": "Profile updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")
