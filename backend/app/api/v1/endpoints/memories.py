"""
Memory API endpoints for managing user memories with semantic search.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.services.memory_service import MemoryService
from app.services.dependencies import get_memory_service
from app.models.supabase_user import SupabaseUser
from app.core.auth import get_current_user


router = APIRouter(
    prefix="/memories",
    tags=["memories"]
)


class MemoryCreateRequest(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MemorySearchRequest(BaseModel):
    query: str
    n_results: int = 5


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    content: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


@router.post("", response_model=MemoryResponse)
async def create_memory(
    request: MemoryCreateRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    Create a new memory.
    
    Example:
    ```json
    {
        "content": "User is working on XMODE project for final year",
        "metadata": {
            "conversation_id": "abc123",
            "source": "manual"
        }
    }
    ```
    """
    try:
        memory = memory_service.create_memory(
            user_id=current_user.user_id,
            content=request.content,
            metadata=request.metadata
        )
        return MemoryResponse(**memory)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create memory: {str(e)}")


@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: SupabaseUser = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    List all memories for the current user (paginated).
    """
    try:
        memories = memory_service.get_memories(
            user_id=current_user.user_id,
            limit=limit,
            offset=offset
        )
        return [MemoryResponse(**m) for m in memories]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch memories: {str(e)}")


@router.post("/search", response_model=List[Dict[str, Any]])
async def search_memories(
    request: MemorySearchRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    Semantic search for relevant memories.
    
    Example:
    ```json
    {
        "query": "What is my final year project about?",
        "n_results": 5
    }
    ```
    
    Returns memories with similarity scores.
    """
    try:
        memories = memory_service.search_memories(
            user_id=current_user.user_id,
            query=request.query,
            n_results=request.n_results
        )
        return memories
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search memories: {str(e)}")


@router.put("/{memory_id}", response_model=Dict[str, Any])
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    current_user: SupabaseUser = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    Update a memory.
    """
    try:
        success = memory_service.update_memory(
            memory_id=memory_id,
            user_id=current_user.user_id,
            content=request.content,
            metadata=request.metadata
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found or unauthorized")
        
        return {"success": True, "message": "Memory updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update memory: {str(e)}")


@router.delete("/{memory_id}", response_model=Dict[str, Any])
async def delete_memory(
    memory_id: str,
    current_user: SupabaseUser = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    Delete a memory.
    """
    try:
        success = memory_service.delete_memory(
            memory_id=memory_id,
            user_id=current_user.user_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found or unauthorized")
        
        return {"success": True, "message": "Memory deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete memory: {str(e)}")


@router.get("/stats", response_model=Dict[str, Any])
async def get_memory_stats(
    current_user: SupabaseUser = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service)
):
    """
    Get statistics about user's memories.
    """
    try:
        stats = memory_service.get_memory_stats(current_user.user_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")
