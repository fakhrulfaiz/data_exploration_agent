from typing import Optional, Literal
from pydantic import BaseModel, Field

class UserProfile(BaseModel):
    """User profile data from Supabase profiles table."""
    
    id: str = Field(..., description="User ID")
    name: Optional[str] = None
    email: Optional[str] = None
    
    # New personalization fields
    nickname: Optional[str] = None
    role: Optional[str] = Field(None, description="User's job role or professional persona")
    about_user: Optional[str] = Field(None, description="Additional context about the user")
    custom_instructions: Optional[str] = Field(None, description="Explicit instructions for the agent")
    
    # Preferences
    communication_style: Literal["concise", "detailed", "balanced"] = "balanced"
    
    class Config:
        from_attributes = True
