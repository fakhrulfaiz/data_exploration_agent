"""
Graph structure endpoint for agent visualization.
Provides the graph structure (nodes and edges) for frontend visualization.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from typing import List, Dict, Any, Optional
import logging

from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/graph",
    tags=["graph-structure"]
)


def get_agent_service(request: Request) -> AgentService:
    """Get agent service from app state."""
    agent_service = request.app.state.agent_service
    if not hasattr(agent_service, '_agent') or agent_service._agent is None:
        raise HTTPException(status_code=500, detail="Agent service not properly initialized")
    return agent_service


@router.get("/structure")
async def get_graph_structure(
    agent_service: AgentService = Depends(get_agent_service)
) -> Dict[str, Any]:
    """
    Get the agent's graph structure for visualization.
    Returns nodes and edges with their types (fixed or conditional).
    """
    try:
        agent = agent_service.get_agent()
        
        # Get the main agent's internal graph structure
        # We want to visualize the MainAgent flow, not the assistant routing
        # The full graph includes assistant handoff which is tool-based
        main_agent = agent  # This is the MainAgent instance
        
        # Build a subgraph for just the main agent flow
        # Extract nodes from the main agent's workflow
        main_flow_nodes = [
            "start",           # Entry point
            "planner",
            "process_query", 
            "tools",
            "explainer",
            "finalizer",
            "human_feedback",
            "end"              # Exit point
        ]
        
        # Extract nodes
        nodes_data = []
        
        # Define node types for styling
        # Define nodes with specific positions per user requirements
        # Define nodes with specific positions per user requirements
        nodes_data = [
            {
                "id": "start",
                "label": "Start",
                "type": "entry",
                "status": "pending",
                "position": {"x": -50.157, "y": -62.764}
            },
            {
                "id": "planner",
                "label": "Planner",
                "type": "planner",
                "status": "pending",
                "position": {"x": -49.995, "y": 82.409}
            },
            {
                "id": "process_query",
                "label": "Process Query",
                "type": "executor",
                "status": "pending",
                "position": {"x": -174.983, "y": 235.182}
            },
            {
                "id": "tools",
                "label": "Tools",
                "type": "tools",
                "status": "pending",
                "position": {"x": -288.902, "y": 352.871}
            },
            {
                "id": "explainer",
                "label": "Explainer",
                "type": "explainer",
                "status": "pending",
                "position": {"x": -173.685, "y": 494.228}
            },
            {
                "id": "finalizer",
                "label": "Finalizer",
                "type": "finalizer",
                "status": "pending",
                "position": {"x": 95.468, "y": 401.462}
            },
            {
                "id": "human_feedback",
                "label": "Human Feedback",
                "type": "feedback",
                "status": "pending",
                "position": {"x": 84.196, "y": 235.349}
            },
            {
                "id": "end",
                "label": "End",
                "type": "end",
                "status": "pending",
                "position": {"x": 95.382, "y": 560.946}
            }
        ]
        
        # Manual edges as defined by user requirements
        processed_edges = [
            ("end", "finalizer", "top", "bottom"),
            ("planner", "start", "top", "bottom"),
            ("explainer", "tools", "left-top", "bottom"),
            ("explainer", "process_query", "top", "bottom"),
            ("finalizer", "process_query", "left-top", "right-bottom"),
            ("human_feedback", "process_query", "left-top", "right-top"),
            ("human_feedback", "planner", "top", "right-bottom"),
            ("planner", "process_query", "left-bottom", "top"),
            ("process_query", "tools", "left-bottom", "top"),
            ("finalizer", "human_feedback", "top", "bottom")
        ]
        
        edges_data = []
        for idx, (source, target, source_handle, target_handle) in enumerate(processed_edges):
            edge_data = {
                "id": f"edge_{idx}",
                "source": source,
                "target": target,
                "type": "smoothstep",
                "label": None,
                "active": False
            }
            
            # Add handles if specified
            if source_handle:
                edge_data["sourceHandle"] = source_handle
            if target_handle:
                edge_data["targetHandle"] = target_handle
                
            edges_data.append(edge_data)
            
        logger.info(f"Created {len(edges_data)} manual edges with custom handles")
        
        return {
            "success": True,
            "data": {
                "nodes": nodes_data,
                "edges": edges_data
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting graph structure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get graph structure: {str(e)}")
