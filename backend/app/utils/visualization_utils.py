"""Utility functions for visualization data processing."""

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def normalize_visualizations(visualizations: Any) -> List[Dict[str, Any]]:
    """
    Normalize visualization data to ensure consistent format.
    
    Args:
        visualizations: Raw visualization data (can be list of dicts or JSON strings)
        
    Returns:
        List of normalized visualization dictionaries
    """
    try:
        if not visualizations:
            return []
        
        normalized: List[Dict[str, Any]] = []
        
        for v in visualizations:
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        normalized.append(parsed)
                except Exception as e:
                    logger.warning(f"Failed to parse visualization JSON string: {e}")
                    continue
            elif isinstance(v, dict):
                normalized.append(v)
            else:
                logger.warning(f"Unexpected visualization type: {type(v)}")
        
        return normalized
    except Exception as e:
        logger.error(f"Error normalizing visualizations: {e}")
        return []


def get_visualization_summary(visualizations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get a summary of visualization data.
    
    Args:
        visualizations: List of visualization dictionaries
        
    Returns:
        Dictionary with summary information
    """
    try:
        if not visualizations:
            return {
                "visualization_count": 0,
                "has_visualizations": False,
                "visualization_types": []
            }
        
        # Calculate summary statistics
        viz_types = [viz.get("type", "unknown") for viz in visualizations]
        unique_types = list(set(viz_types))
        
        return {
            "visualization_count": len(visualizations),
            "has_visualizations": True,
            "visualization_types": unique_types,
            "visualizations_preview": [
                {
                    "type": viz.get("type", "unknown"),
                    "title": viz.get("title", "Untitled"),
                    "data_points": len(viz.get("data", [])) if isinstance(viz.get("data"), list) else 0
                }
                for viz in visualizations[:3]  # First 3 visualizations as preview
            ]
        }
        
    except Exception as e:
        logger.error(f"Error creating visualization summary: {e}")
        return {
            "visualization_count": 0,
            "has_visualizations": False,
            "error": str(e)
        }
