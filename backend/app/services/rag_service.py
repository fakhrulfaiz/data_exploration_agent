"""
RAG Service for Explainability Knowledge Retrieval.

This service loads knowledge from markdown files and stores them in Chroma vector stores
for semantic search during explanation generation.
"""

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


class RAGService:
    
    def __init__(self, persist_directory: str = "./chroma_rag_db"):
        """
        Initialize RAG service with separate collections for different knowledge types.
        
        Args:
            persist_directory: Directory to persist Chroma vector store
        """
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize separate collections for different knowledge types
        self.tool_kb = Chroma(
            collection_name="tool_selection_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/tool_kb"
        )
        
        self.explanation_kb = Chroma(
            collection_name="explanation_patterns_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/explanation_kb"
        )
        
        self.error_kb = Chroma(
            collection_name="error_explanations_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/error_kb"
        )
        
        self.domain_kb = Chroma(
            collection_name="domain_knowledge_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/domain_kb"
        )
        
        # Feedback vector store for continuous learning
        self.feedback_kb = Chroma(
            collection_name="explanation_feedback_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/feedback_kb"
        )
        
        logger.info("RAG Service initialized with 5 knowledge bases")
    
    # ==================== Tool Selection KB ====================
    
    def retrieve_tool_guidance(
        self, 
        query: str, 
        current_step_goal: str,
        available_tools: Optional[List[str]] = None,
        n_results: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve guidance for tool selection based on query and step goal.
        
        Args:
            query: User's original query
            current_step_goal: Current step goal from the plan
            available_tools: List of available tool names (optional filter)
            n_results: Number of results to retrieve
            
        Returns:
            List of relevant tool knowledge entries
        """
        # Combine query and step goal for better retrieval
        search_query = f"Query: {query}\nGoal: {current_step_goal}"
        
        results = self.tool_kb.similarity_search_with_score(
            search_query,
            k=n_results
        )
        
        guidance = []
        for doc, score in results:
            tool_name = doc.metadata.get("tool_name", "unknown")
            
            # Filter by available tools if specified
            if available_tools and tool_name not in available_tools:
                continue
            
            guidance.append({
                "tool_name": tool_name,
                "content": doc.page_content,
                "relevance_score": 1 - score,  # Convert distance to similarity
                "metadata": doc.metadata
            })
        
        logger.info(f"Retrieved {len(guidance)} tool guidance entries")
        return guidance
    
    # ==================== Explanation Pattern KB ====================
    
    def retrieve_explanation_patterns(
        self,
        layer: str,
        query: str,
        context: Dict[str, Any],
        n_results: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Retrieve explanation patterns for a specific layer.
        
        Args:
            layer: Explanation layer (understanding, tool_selection, etc.)
            query: User's query
            context: Additional context (tool_name, step_goal, etc.)
            n_results: Number of patterns to retrieve
            
        Returns:
            List of relevant explanation patterns
        """
        search_query = f"Layer: {layer}\nQuery: {query}\nContext: {json.dumps(context)}"
        
        results = self.explanation_kb.similarity_search_with_score(
            search_query,
            k=n_results
        )
        
        patterns = []
        for doc, score in results:
            patterns.append({
                "pattern": doc.metadata,
                "content": doc.page_content,
                "relevance_score": 1 - score,
                "example": doc.metadata.get("example", {})
            })
        
        logger.info(f"Retrieved {len(patterns)} explanation patterns for layer: {layer}")
        return patterns
    
    # ==================== Error Explanation KB ====================
    
    def retrieve_error_explanation(
        self,
        error_message: str,
        tool_name: str,
        error_type: Optional[str] = None,
        n_results: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve explanation for an error.
        
        Args:
            error_message: The error message
            tool_name: Tool that generated the error
            error_type: Optional error type
            n_results: Number of results to retrieve
            
        Returns:
            Error explanation knowledge or None
        """
        search_query = f"Error: {error_message}\nTool: {tool_name}"
        if error_type:
            search_query += f"\nType: {error_type}"
        
        results = self.error_kb.similarity_search_with_score(
            search_query,
            k=n_results
        )
        
        if not results:
            return None
        
        doc, score = results[0]
        return {
            "error_type": doc.metadata.get("error_type"),
            "explanation": doc.metadata.get("user_friendly_explanation"),
            "suggested_actions": doc.metadata.get("suggested_actions", []),
            "example": doc.metadata.get("example", {}),
            "relevance_score": 1 - score
        }
    
    # ==================== Domain Knowledge KB ====================
    
    def retrieve_domain_knowledge(
        self,
        query: str,
        category: Optional[str] = None,
        n_results: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant domain knowledge.
        
        Args:
            query: Search query
            category: Optional category filter
            n_results: Number of results to retrieve
            
        Returns:
            List of relevant domain knowledge entries
        """
        results = self.domain_kb.similarity_search_with_score(
            query,
            k=n_results
        )
        
        knowledge = []
        for doc, score in results:
            # Filter by category if specified
            if category and doc.metadata.get("category") != category:
                continue
                
            knowledge.append({
                "topic": doc.metadata.get("topic"),
                "category": doc.metadata.get("category"),
                "content": doc.page_content,
                "examples": doc.metadata.get("examples", []),
                "relevance_score": 1 - score
            })
        
        logger.info(f"Retrieved {len(knowledge)} domain knowledge entries")
        return knowledge
    
    # ==================== Feedback Collection ====================
    
    def store_explanation_feedback(
        self,
        explanation_id: str,
        user_id: str,
        query: str,
        layer: str,
        explanation_content: str,
        feedback_type: str,  # "positive", "negative", "neutral"
        feedback_comment: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Store user feedback on an explanation.
        
        This creates a feedback entry that will influence future retrievals.
        Positive feedback → explanation ranked higher
        Negative feedback → explanation ranked lower
        """
        feedback_score = {
            "positive": 1,
            "neutral": 0,
            "negative": -1
        }.get(feedback_type, 0)
        
        doc = Document(
            page_content=f"""
            Query: {query}
            Layer: {layer}
            Explanation: {explanation_content}
            Feedback: {feedback_type}
            Comment: {feedback_comment or 'No comment'}
            """,
            metadata={
                "explanation_id": explanation_id,
                "user_id": user_id,
                "query": query,
                "layer": layer,
                "feedback_type": feedback_type,
                "feedback_score": feedback_score,
                "feedback_comment": feedback_comment,
                "context": context or {},
                "timestamp": datetime.now().isoformat()
            }
        )
        
        self.feedback_kb.add_documents([doc])
        logger.info(f"Stored {feedback_type} feedback for explanation {explanation_id}")
    
    # ==================== Feedback-Weighted Retrieval ====================
    
    def retrieve_with_feedback_weighting(
        self,
        query: str,
        layer: str,
        kb_type: str = "explanation",  # "explanation", "tool", "error"
        n_results: int = 3,
        feedback_weight: float = 0.3  # How much to weight feedback vs. similarity
    ) -> List[Dict[str, Any]]:
        """
        Retrieve knowledge with feedback weighting.
        
        This combines:
        1. Semantic similarity (from vector search)
        2. User feedback scores (from feedback KB)
        
        Args:
            query: Search query
            layer: Explanation layer
            kb_type: Which knowledge base to search
            n_results: Number of results
            feedback_weight: Weight for feedback (0-1, default 0.3)
        
        Returns:
            List of results ranked by combined score
        """
        # Step 1: Get semantic similarity results
        kb = {
            "explanation": self.explanation_kb,
            "tool": self.tool_kb,
            "error": self.error_kb
        }.get(kb_type, self.explanation_kb)
        
        similarity_results = kb.similarity_search_with_score(
            query,
            k=n_results * 2  # Get more candidates for reranking
        )
        
        # Step 2: Get feedback scores for these results
        reranked_results = []
        
        for doc, similarity_score in similarity_results:
            # Query feedback KB for this explanation pattern
            try:
                feedback_results = self.feedback_kb.similarity_search_with_score(
                    doc.page_content,
                    k=10  # Get recent feedback
                )
                
                # Calculate average feedback score
                if feedback_results:
                    feedback_scores = [
                        fb_doc.metadata.get("feedback_score", 0) 
                        for fb_doc, _ in feedback_results
                    ]
                    avg_feedback = sum(feedback_scores) / len(feedback_scores)
                else:
                    avg_feedback = 0  # Neutral if no feedback
            except Exception as e:
                logger.warning(f"Error retrieving feedback: {e}")
                avg_feedback = 0
            
            # Combine similarity and feedback
            # similarity_score is distance (lower is better), convert to similarity
            similarity = 1 - similarity_score
            
            # Combined score: weighted average
            combined_score = (
                (1 - feedback_weight) * similarity +
                feedback_weight * ((avg_feedback + 1) / 2)  # Normalize -1,1 to 0,1
            )
            
            reranked_results.append({
                "document": doc,
                "similarity_score": similarity,
                "feedback_score": avg_feedback,
                "combined_score": combined_score,
                "metadata": doc.metadata
            })
        
        # Sort by combined score (descending)
        reranked_results.sort(key=lambda x: x["combined_score"], reverse=True)
        
        # Return top N
        return reranked_results[:n_results]


# Global RAG service instance
rag_service = None


def get_rag_service() -> RAGService:
    """Get or create the global RAG service instance."""
    global rag_service
    if rag_service is None:
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        persist_dir = os.path.join(backend_dir, "chroma_rag_db")
        rag_service = RAGService(persist_directory=persist_dir)
    return rag_service
