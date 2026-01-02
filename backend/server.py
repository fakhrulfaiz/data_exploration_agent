import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import db_manager
from app.core.checkpointer import initialize_checkpointer, checkpointer_manager
from app.agents import MainAgent
from app.services.agent_service import AgentService
from app.utils.logger import LoggerManager, get_logger


def setup_logging():
    LoggerManager.configure()
    logger = get_logger(__name__)
    logger.info("Logging configuration complete")
    return logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    logger = setup_logging()
    logger.info("Starting up Agent Backend API...")
    
    # Initialize database connection
    await db_manager.initialize()
    
    # Initialize checkpointer
    initialize_checkpointer()
    
    # Initialize LLM based on provider
    if settings.llm_provider == "openai":
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"),
        )
    else:
        # Default to OpenAI for now
        llm = ChatOpenAI(model="gpt-4o-mini")
    
    # Initialize AgentService with proper service layer pattern
    agent_service = AgentService()
    agent_service.initialize_agent(
        llm=llm, 
        db_path=settings.database_path, 
        use_postgres_checkpointer=True
    )
    
    # Store services in app state for dependency injection
    app.state.agent_service = agent_service
    app.state.agent = agent_service.get_agent()  # For backward compatibility
    app.state.llm = llm
    
    logger.info(f"✅ Agent service initialized with DB: {settings.database_path}")
    logger.info(f"✅ Using LLM provider: {settings.llm_provider}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Agent Backend API...")
    await agent_service.shutdown()
    await db_manager.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


# Dependency functions
def get_agent(request: Request) -> MainAgent:
    """Get the initialized agent from app state."""
    return request.app.state.agent

def get_agent_service(request: Request) -> AgentService:
    """Get the initialized agent service from app state."""
    return request.app.state.agent_service


@app.get("/api/")
async def root():
    return {"message": "Agent Backend API", "status": "running"}


@app.get("/api/health")
async def health():
    return {"status": "healthy"}