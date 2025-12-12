"""Supabase user model for JWT authentication."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SupabaseUser(BaseModel):
    """User model extracted from Supabase JWT token."""
    
    user_id: str = Field(..., description="Supabase user ID (from 'sub' claim)")
    email: Optional[str] = Field(None, description="User email")
    role: str = Field(default="user", description="User role from app_metadata")
    
    @classmethod
    def from_jwt_payload(cls, payload: Dict[str, Any]) -> "SupabaseUser":
        """
        Create SupabaseUser from JWT payload.
        
        Args:
            payload: Decoded JWT payload
            
        Returns:
            SupabaseUser instance
        """
        # Extract user_id from 'sub' claim
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("JWT payload missing 'sub' claim")
        
        # Extract email
        email = payload.get("email")
        
        # Extract role from app_metadata or user_metadata
        role = "user"
        if "app_metadata" in payload and isinstance(payload["app_metadata"], dict):
            role = payload["app_metadata"].get("role", "user")
        elif "user_metadata" in payload and isinstance(payload["user_metadata"], dict):
            role = payload["user_metadata"].get("role", "user")
        
        return cls(
            user_id=user_id,
            email=email,
            role=role
        )
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "role": "user"
            }
        }
