"""API router for version 1."""

from fastapi import APIRouter

from app.api.v1.endpoints import agent, graph, streaming_graph, conversation, data

api_router = APIRouter()

# Group all v1 endpoints under a common prefix
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(graph.router)
api_router.include_router(streaming_graph.router)
api_router.include_router(conversation.router)
api_router.include_router(data.router)
