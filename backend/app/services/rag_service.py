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
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        # Thought Process KB - stores query pattern examples and reasoning templates
        self.thought_process_kb = Chroma(
            collection_name="thought_process_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/thought_process_kb"
        )
        
        # Feedback KB - stores user feedback for continuous learning
        self.feedback_kb = Chroma(
            collection_name="feedback_kb",
            embedding_function=self.embeddings,
            persist_directory=f"{persist_directory}/feedback_kb"
        )
        
        logger.info("RAG Service initialized with 2 knowledge bases: thought_process_kb, feedback_kb")

    
    
    # ==================== Thought Process KB ====================
    
    def retrieve_thought_patterns(
        self,
        query: str,
        n_results: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant thought process patterns for a query.
        
        Returns examples of how to think about similar queries.
        Critical for low-parameter LLMs that need guidance.
        
        Args:
            query: User's query
            n_results: Number of pattern examples to retrieve
            
        Returns:
            List of thought pattern examples with metadata
        """
        results = self.thought_process_kb.similarity_search_with_score(
            query,
            k=n_results
        )
        
        patterns = []
        for doc, score in results:
            patterns.append({
                "pattern_type": doc.metadata.get("pattern_type", "unknown"),
                "complexity": doc.metadata.get("complexity", "medium"),
                "example_query": doc.metadata.get("example_query", ""),
                "example_thought": doc.page_content,
                "template": doc.metadata.get("template", ""),
                "relevance_score": 1 - score,  # Convert distance to similarity
                "metadata": doc.metadata
            })
        
        logger.info(f"Retrieved {len(patterns)} thought pattern examples for query: {query[:50]}...")
        return patterns
    
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
        n_results: int = 2,
        feedback_weight: float = 0.3  # How much to weight feedback vs. similarity
    ) -> List[Dict[str, Any]]:
      
        # Step 1: Get semantic similarity results
        similarity_results = self.thought_process_kb.similarity_search_with_score(
            query,
            k=n_results * 2  # Get more candidates for reranking
        )
        
        # Step 2: Get feedback scores for these results
        reranked_results = []
        
        for doc, similarity_score in similarity_results:
            # Query feedback KB for this thought pattern
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
                "pattern_type": doc.metadata.get("pattern_type", "unknown"),
                "complexity": doc.metadata.get("complexity", "medium"),
                "example_query": doc.metadata.get("example_query", ""),
                "example_thought": doc.page_content,
                "template": doc.metadata.get("template", ""),
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
