"""
Supabase Storage Service for uploading plot images.
Handles secure file uploads with proper content-type handling and public URL generation.
"""

import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SupabaseStorageService:
    
    def __init__(self, supabase_url: str, supabase_service_role_key: str):
        if not supabase_url or not supabase_service_role_key:
            raise ValueError("Supabase URL and service role key must be configured")
        
        try:
            from supabase import create_client, Client
            
            self.client: Client = create_client(
                supabase_url,
                supabase_service_role_key
            )
            self.bucket_name = "plot-images"  # Dedicated bucket for plot images
            
            logger.info(f"Initialized Supabase storage service for bucket: {self.bucket_name}")
        except ImportError:
            logger.error("Supabase client not installed. Install with: pip install supabase")
            raise
    
    def _generate_file_path(self, filename: str) -> str:
        # Extract extension
        extension = filename.split('.')[-1] if '.' in filename else 'png'
        
        # Generate unique filename with timestamp and UUID
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:8]
        
        return f"plots/{timestamp}/{unique_id}.{extension}"
    
    def upload_plot_image(
        self, 
        image_data: bytes, 
        filename: str = "plot.png",
        content_type: str = "image/png"
    ) -> str:
    
        try:
            # Generate unique file path
            file_path = self._generate_file_path(filename)
            
            # Convert image_data to bytes if it's not already
            if not isinstance(image_data, bytes):
                image_data = bytes(image_data)
            
            # Upload with proper file options
            try:
                # Try with upsert as separate parameter (newer API)
                response = self.client.storage.from_(self.bucket_name).upload(
                    file_path,
                    image_data,
                    file_options={
                        "content-type": content_type,
                        "cache-control": "3600"  # Cache for 1 hour
                    },
                    upsert=False
                )
            except TypeError:
                # Fallback: try without upsert parameter (older API)
                response = self.client.storage.from_(self.bucket_name).upload(
                    file_path,
                    image_data,
                    file_options={
                        "content-type": content_type,
                        "cache-control": "3600"  # Cache for 1 hour
                    }
                )
            
            # Check for upload errors
            if isinstance(response, dict) and response.get("error"):
                raise Exception(f"Upload failed: {response.get('error')}")
            elif hasattr(response, 'error') and response.error:
                raise Exception(f"Upload failed: {response.error}")
            
            # Get public URL
            public_url = self.client.storage.from_(self.bucket_name).get_public_url(file_path)
            
            if not public_url or (isinstance(public_url, str) and not public_url.strip()):
                raise Exception("Failed to generate public URL")
            
            logger.info(f"Successfully uploaded plot image: {file_path}")
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to upload plot image: {str(e)}")
            raise Exception(f"Image upload failed: {str(e)}")
    
    def delete_plot_image(self, file_path: str) -> bool:
        try:
            response = self.client.storage.from_(self.bucket_name).remove([file_path])
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Failed to delete file {file_path}: {response.error}")
                return False
            
            logger.info(f"Successfully deleted plot image: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            return False

    # ==================== User Profile Management ====================

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Fetch user profile and preferences from Supabase.
        """
        try:
            # Select specific columns to ensure we get what we expect
            response = self.client.table("profiles").select(
                "id, name, email, nickname, role, about_user, custom_instructions, communication_style"
            ).eq("id", user_id).single().execute()
            
            if not response.data:
                logger.warning(f"No profile found for user_id: {user_id}")
                return {}
                
            return response.data
            
        except Exception as e:
            logger.error(f"Failed to fetch user profile for {user_id}: {str(e)}")
            return {}

    def update_user_profile(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update user profile in Supabase.
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
            
            if "communication_style" in safe_updates:
                if safe_updates["communication_style"] not in ["concise", "detailed", "balanced"]:
                    safe_updates.pop("communication_style") # Ignore invalid values
            
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
            logger.error(f"Error updating user profile for {user_id}: {str(e)}")
            return False

    # ==================== User Profile Management ====================

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Fetch user profile and preferences from Supabase.
        """
        try:
            response = self.client.table("profiles").select("*").eq("id", user_id).single().execute()
            
            if not response.data:
                logger.warning(f"No profile found for user_id: {user_id}")
                return {}
                
            return response.data
            
        except Exception as e:
            logger.error(f"Failed to fetch user profile for {user_id}: {str(e)}")
            return {}

    def update_user_profile(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update user profile in Supabase.
        """
        try:
            # We only allow updating specific fields to prevent overwriting critical data
            allowed_fields = ["preferences", "communication_style", "llm_provider", "llm_model"]
            safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}
            
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
            logger.error(f"Error updating user profile for {user_id}: {str(e)}")
            return False
