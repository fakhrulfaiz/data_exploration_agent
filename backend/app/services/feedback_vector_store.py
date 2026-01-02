import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
import json
import gzip
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FeedbackVectorStore:
    """
    Manage explanation feedback in vector database with scalability features.
    
    Architecture:
    - Hot storage: ChromaDB (last 30 days, max 100k entries)
    - Metadata: PostgreSQL (all feedback)
    - Archive: Compressed JSON files (>30 days old)
    """
    
    # Configuration
    MAX_VECTORS = 100_000  # Maximum vectors in hot storage
    RETENTION_DAYS = 30    # Days to keep in hot storage
    ARCHIVE_DIR = "data/feedback_archives"
    
    def __init__(
        self, 
        persist_directory: str = "./chroma_feedback_db",
        archive_directory: str = None,
        max_vectors: int = None,
        retention_days: int = None
    ):
        """
        Initialize vector store with Chroma.
        
        Args:
            persist_directory: Where to store the vector database
            archive_directory: Where to store archived feedback
            max_vectors: Maximum vectors in hot storage (default: 100k)
            retention_days: Days to keep in hot storage (default: 30)
        """
        # Configuration
        self.max_vectors = max_vectors or self.MAX_VECTORS
        self.retention_days = retention_days or self.RETENTION_DAYS
        self.archive_dir = Path(archive_directory or self.ARCHIVE_DIR)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
        # Create or get collection
        self.collection = self.client.get_or_create_collection(
            name="explanation_feedback",
            metadata={"description": "User feedback on AI explanations"}
        )
        
        # Embedding model for semantic search
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        current_count = self.collection.count()
        logger.info(
            f"Initialized FeedbackVectorStore: "
            f"{current_count} vectors, "
            f"max={self.max_vectors}, "
            f"retention={self.retention_days}d"
        )
        
        # Check if cleanup needed
        if current_count > self.max_vectors * 0.9:
            logger.warning(f"Vector store at {current_count}/{self.max_vectors} capacity")
    
    def add_feedback(
        self,
        conversation_id: str,
        message_id: str,
        helpful: bool,
        feedback_comment: Optional[str] = None,
        tool_name: Optional[str] = None,
        explanation_type: Optional[str] = None,
        explanation_text: Optional[str] = None
    ) -> str:
        """
        Add feedback to vector store.
        
        Automatically triggers cleanup if size limit reached.
        
        Returns:
            feedback_id: Unique ID for this feedback
        """
        # Check if cleanup needed before adding
        if self.collection.count() >= self.max_vectors:
            logger.warning(f"Vector store full ({self.max_vectors}), triggering cleanup")
            self.cleanup_old_feedback()
        
        feedback_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()
        
        # Create text for embedding
        embedding_text = self._create_embedding_text(
            tool_name=tool_name,
            explanation_type=explanation_type,
            helpful=helpful,
            feedback_comment=feedback_comment,
            explanation_text=explanation_text
        )
        
        # Generate embedding
        embedding = self.embedding_model.encode(embedding_text).tolist()
        
        # Metadata for filtering
        metadata = {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "helpful": helpful,
            "tool_name": tool_name or "unknown",
            "explanation_type": explanation_type or "general",
            "timestamp": timestamp.isoformat(),
            "has_comment": feedback_comment is not None,
            "comment": feedback_comment or ""
        }
        
        # Store in vector DB
        self.collection.add(
            ids=[feedback_id],
            embeddings=[embedding],
            documents=[embedding_text],
            metadatas=[metadata]
        )
        
        logger.info(
            f"Added feedback {feedback_id[:8]}... for tool '{tool_name}' "
            f"(helpful={helpful}, total={self.collection.count()})"
        )
        
        return feedback_id
    
    def find_similar_feedback(
        self,
        query_text: str,
        n_results: int = 5,
        tool_name: Optional[str] = None,
        helpful_only: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Find similar feedback using semantic search.
        
        Args:
            query_text: Text to search for (e.g., current explanation)
            n_results: Number of similar feedbacks to return
            tool_name: Filter by specific tool
            helpful_only: If True, only helpful feedback; if False, only unhelpful
        
        Returns:
            List of similar feedback entries with metadata
        """
        # Generate embedding for query
        query_embedding = self.embedding_model.encode(query_text).tolist()
        
        # Build filter
        where_filter = {}
        if tool_name:
            where_filter["tool_name"] = tool_name
        if helpful_only is not None:
            where_filter["helpful"] = helpful_only
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter if where_filter else None
        )
        
        # Format results
        similar_feedbacks = []
        if results['ids'] and len(results['ids'][0]) > 0:
            for i in range(len(results['ids'][0])):
                similar_feedbacks.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if 'distances' in results else None
                })
        
        logger.info(f"Found {len(similar_feedbacks)} similar feedback for query")
        return similar_feedbacks
    
    def get_feedback_stats(
        self,
        tool_name: Optional[str] = None,
        explanation_type: Optional[str] = None,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about feedback.
        
        Args:
            tool_name: Filter by tool
            explanation_type: Filter by explanation type
            days: Only count feedback from last N days
        """
        # Build filter
        where_filter = {}
        if tool_name:
            where_filter["tool_name"] = tool_name
        if explanation_type:
            where_filter["explanation_type"] = explanation_type
        
        # Get all matching feedback
        results = self.collection.get(
            where=where_filter if where_filter else None
        )
        
        # Filter by date if specified
        feedbacks = results['metadatas']
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            feedbacks = [
                f for f in feedbacks 
                if datetime.fromisoformat(f['timestamp']) > cutoff
            ]
        
        total = len(feedbacks)
        helpful_count = sum(1 for f in feedbacks if f.get('helpful'))
        with_comments = sum(1 for f in feedbacks if f.get('has_comment'))
        
        return {
            "total_feedback": total,
            "helpful_count": helpful_count,
            "unhelpful_count": total - helpful_count,
            "helpfulness_rate": helpful_count / total if total > 0 else 0,
            "feedback_with_comments": with_comments,
            "comment_rate": with_comments / total if total > 0 else 0,
            "tool_name": tool_name,
            "explanation_type": explanation_type,
            "days_range": days
        }
    
    def get_common_issues(
        self,
        tool_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most common issues from unhelpful feedback.
        
        Returns:
            List of feedback entries that were marked unhelpful
        """
        where_filter = {"helpful": False}
        if tool_name:
            where_filter["tool_name"] = tool_name
        
        results = self.collection.get(
            where=where_filter,
            limit=limit
        )
        
        issues = []
        for i in range(len(results['ids'])):
            issues.append({
                "id": results['ids'][i],
                "document": results['documents'][i],
                "metadata": results['metadatas'][i]
            })
        
        logger.info(f"Retrieved {len(issues)} common issues for tool '{tool_name}'")
        return issues
    
    def cleanup_old_feedback(self, force: bool = False) -> Dict[str, Any]:
        """
        Archive and remove old feedback from vector store.
        
        This is automatically called when size limit is reached,
        but can also be called manually.
        
        Args:
            force: If True, archive even if not at limit
        
        Returns:
            Stats about cleanup operation
        """
        current_count = self.collection.count()
        
        if not force and current_count < self.max_vectors:
            logger.info(f"No cleanup needed ({current_count}/{self.max_vectors})")
            return {"cleaned": 0, "archived": 0, "reason": "under_limit"}
        
        logger.info(f"Starting cleanup: {current_count} vectors")
        
        # Get all feedback
        all_feedback = self.collection.get()
        
        # Sort by timestamp
        feedback_with_time = [
            (
                all_feedback['ids'][i],
                all_feedback['metadatas'][i],
                all_feedback['documents'][i],
                all_feedback['embeddings'][i] if 'embeddings' in all_feedback else None,
                datetime.fromisoformat(all_feedback['metadatas'][i]['timestamp'])
            )
            for i in range(len(all_feedback['ids']))
        ]
        feedback_with_time.sort(key=lambda x: x[4])  # Sort by timestamp
        
        # Determine cutoff
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        
        # Separate old and keep
        to_archive = [f for f in feedback_with_time if f[4] < cutoff_date]
        
        # If still too many, archive oldest until under limit
        if len(feedback_with_time) - len(to_archive) > self.max_vectors * 0.8:
            target_size = int(self.max_vectors * 0.7)  # Keep at 70% capacity
            to_archive = feedback_with_time[:len(feedback_with_time) - target_size]
        
        if not to_archive:
            logger.info("No feedback to archive")
            return {"cleaned": 0, "archived": 0, "reason": "nothing_old"}
        
        # Archive to file
        archive_path = self._archive_feedback(to_archive)
        
        # Delete from vector store
        ids_to_delete = [f[0] for f in to_archive]
        self.collection.delete(ids=ids_to_delete)
        
        new_count = self.collection.count()
        logger.info(
            f"Cleanup complete: {current_count} -> {new_count} vectors, "
            f"archived {len(to_archive)} to {archive_path}"
        )
        
        return {
            "cleaned": len(to_archive),
            "archived": len(to_archive),
            "archive_path": str(archive_path),
            "before_count": current_count,
            "after_count": new_count
        }
    
    def _archive_feedback(self, feedback_list: List[tuple]) -> Path:
        """Archive feedback to compressed JSON file."""
        timestamp = datetime.utcnow()
        year_month = timestamp.strftime("%Y-%m")
        archive_subdir = self.archive_dir / year_month
        archive_subdir.mkdir(parents=True, exist_ok=True)
        
        filename = f"feedback_{timestamp.strftime('%Y-%m-%d_%H%M%S')}.json.gz"
        archive_path = archive_subdir / filename
        
        # Prepare archive data
        archive_data = {
            "archive_date": timestamp.isoformat(),
            "feedback_count": len(feedback_list),
            "feedbacks": [
                {
                    "id": f[0],
                    "metadata": f[1],
                    "document": f[2],
                    "embedding": f[3]
                }
                for f in feedback_list
            ]
        }
        
        # Write compressed
        with gzip.open(archive_path, 'wt', encoding='utf-8') as f:
            json.dump(archive_data, f, indent=2)
        
        logger.info(f"Archived {len(feedback_list)} feedback to {archive_path}")
        return archive_path
    
    def _create_embedding_text(
        self,
        tool_name: Optional[str],
        explanation_type: Optional[str],
        helpful: bool,
        feedback_comment: Optional[str],
        explanation_text: Optional[str]
    ) -> str:
        """Create text for embedding from feedback components."""
        parts = [
            f"Tool: {tool_name or 'unknown'}",
            f"Type: {explanation_type or 'general'}",
            f"Helpful: {'yes' if helpful else 'no'}"
        ]
        
        if feedback_comment:
            parts.append(f"Comment: {feedback_comment}")
        
        if explanation_text:
            parts.append(f"Explanation: {explanation_text}")
        
        return "\n".join(parts)
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get information about storage usage."""
        vector_count = self.collection.count()
        
        # Count archived feedback
        archived_count = 0
        archive_size_bytes = 0
        if self.archive_dir.exists():
            for archive_file in self.archive_dir.rglob("*.json.gz"):
                archive_size_bytes += archive_file.stat().st_size
                # Could parse to count, but expensive
        
        return {
            "hot_storage": {
                "vector_count": vector_count,
                "max_vectors": self.max_vectors,
                "usage_percent": (vector_count / self.max_vectors * 100) if self.max_vectors > 0 else 0,
                "retention_days": self.retention_days
            },
            "archive_storage": {
                "archive_size_mb": archive_size_bytes / (1024 * 1024),
                "archive_dir": str(self.archive_dir)
            }
        }


# Global instance
_feedback_store = None

def get_feedback_store() -> FeedbackVectorStore:
    """Get or create global feedback store instance."""
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackVectorStore()
    return _feedback_store
