"""
Memory Service for managing user memories with semantic search.

Architecture:
- Supabase: Metadata storage (id, user_id, content, timestamps)
- LangChain Chroma: Vector embeddings for semantic search
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing user memories with semantic search."""
    
    def __init__(self):
        try:
            from supabase import create_client, Client
            
            self.supabase_client: Client = create_client(
                app_settings.supabase_url,
                app_settings.supabase_service_role_key
            )
            
            # Initialize LangChain Chroma for vector storage
            self.vectorstore = Chroma(
                collection_name="user_memories",
                embedding_function=HuggingFaceEmbeddings(
                    model_name="all-MiniLM-L6-v2"
                ),
                persist_directory="./chroma_memory_db"
            )
            
            logger.info("Initialized MemoryService with Supabase + LangChain Chroma")
        except ImportError:
            logger.error("Required packages not installed. Install with: pip install supabase langchain-chroma")
            raise
    
    def create_memory(
        self, 
        user_id: str, 
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new memory.
        
        Args:
            user_id: User ID
            content: Memory content
            metadata: Additional metadata (conversation_id, etc.)
        
        Returns:
            Created memory with id
        """
        try:
            memory_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            # Store metadata in Supabase
            memory_data = {
                "id": memory_id,
                "user_id": user_id,
                "content": content,
                "metadata": metadata or {},
                "created_at": now.isoformat(),
                "updated_at": now.isoformat()
            }
            
            response = self.supabase_client.table("memories").insert(memory_data).execute()
            
            if not response.data:
                raise Exception("Failed to create memory in Supabase")
            
            # Generate and store embedding in ChromaDB
            embedding = self.embedding_model.encode(content).tolist()
            
            self.collection.add(
                ids=[memory_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{
                    "user_id": user_id,
                    "created_at": now.isoformat(),
                    **(metadata or {})
                }]
            )
            
            logger.info(f"Created memory {memory_id[:8]}... for user {user_id[:8]}...")
            return response.data[0]
            
        except Exception as e:
            logger.error(f"Error creating memory: {str(e)}")
            raise
    
    def get_memories(
        self, 
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all memories for a user (paginated).
        
        Args:
            user_id: User ID
            limit: Max memories to return
            offset: Pagination offset
        
        Returns:
            List of memories
        """
        try:
            response = self.supabase_client.table("memories").select("*").eq(
                "user_id", user_id
            ).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error fetching memories for user {user_id}: {str(e)}")
            return []
    
    def search_memories(
        self,
        user_id: str,
        query: str,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for relevant memories.
        
        Args:
            user_id: User ID
            query: Search query
            n_results: Number of results to return
        
        Returns:
            List of relevant memories with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode(query).tolist()
            
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where={"user_id": user_id}
            )
            
            if not results['ids'] or len(results['ids'][0]) == 0:
                return []
            
            # Fetch full metadata from Supabase
            memory_ids = results['ids'][0]
            response = self.supabase_client.table("memories").select("*").in_(
                "id", memory_ids
            ).execute()
            
            # Combine with similarity scores
            memories_by_id = {m['id']: m for m in (response.data or [])}
            
            relevant_memories = []
            for i, memory_id in enumerate(memory_ids):
                if memory_id in memories_by_id:
                    memory = memories_by_id[memory_id]
                    memory['similarity_score'] = 1 - results['distances'][0][i]  # Convert distance to similarity
                    relevant_memories.append(memory)
            
            logger.info(f"Found {len(relevant_memories)} relevant memories for query")
            return relevant_memories
            
        except Exception as e:
            logger.error(f"Error searching memories: {str(e)}")
            return []
    
    def update_memory(
        self,
        memory_id: str,
        user_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update a memory.
        
        Args:
            memory_id: Memory ID
            user_id: User ID (for authorization)
            content: New content (if updating)
            metadata: New metadata (if updating)
        
        Returns:
            True if successful
        """
        try:
            updates = {"updated_at": datetime.utcnow().isoformat()}
            
            if content is not None:
                updates["content"] = content
            
            if metadata is not None:
                updates["metadata"] = metadata
            
            # Update Supabase
            response = self.supabase_client.table("memories").update(updates).eq(
                "id", memory_id
            ).eq("user_id", user_id).execute()
            
            if not response.data:
                return False
            
            # Update ChromaDB if content changed
            if content is not None:
                embedding = self.embedding_model.encode(content).tolist()
                self.collection.update(
                    ids=[memory_id],
                    embeddings=[embedding],
                    documents=[content]
                )
            
            logger.info(f"Updated memory {memory_id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error updating memory {memory_id}: {str(e)}")
            return False
    
    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """
        Delete a memory.
        
        Args:
            memory_id: Memory ID
            user_id: User ID (for authorization)
        
        Returns:
            True if successful
        """
        try:
            # Delete from Supabase
            response = self.supabase_client.table("memories").delete().eq(
                "id", memory_id
            ).eq("user_id", user_id).execute()
            
            if not response.data:
                return False
            
            # Delete from ChromaDB
            self.collection.delete(ids=[memory_id])
            
            logger.info(f"Deleted memory {memory_id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id}: {str(e)}")
            return False
    
    def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about user's memories."""
        try:
            response = self.supabase_client.table("memories").select(
                "id", count="exact"
            ).eq("user_id", user_id).execute()
            
            return {
                "total_memories": response.count or 0,
                "user_id": user_id
            }
            
        except Exception as e:
            logger.error(f"Error getting memory stats: {str(e)}")
            return {"total_memories": 0, "user_id": user_id}
