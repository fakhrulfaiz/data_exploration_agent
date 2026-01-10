"""
Preload heavy models at application startup to avoid blocking during requests.
This should be called in the FastAPI lifespan/startup event.
"""

import logging

logger = logging.getLogger(__name__)

def preload_models():
    """Preload BLIP VQA model to avoid first-request delay."""
    try:
        logger.info("Preloading BLIP VQA model at startup...")
        from app.agents.tools.image_QA_tools import VisualQA
        
        # Initialize the singleton - this loads the model
        vqa = VisualQA()
        logger.info("✅ BLIP VQA model preloaded successfully")
        
    except Exception as e:
        logger.warning(f"Failed to preload BLIP model (will load on first use): {e}")

if __name__ == "__main__":
    preload_models()
