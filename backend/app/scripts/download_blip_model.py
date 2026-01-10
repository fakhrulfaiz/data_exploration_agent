"""
Pre-download BLIP VQA model to Docker's HuggingFace cache.
Run this inside the Docker container to cache the model for future use.
"""

import logging
from transformers import BlipProcessor, BlipForQuestionAnswering

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_blip_model():
    """Download and cache BLIP VQA model."""
    model_name = "Salesforce/blip-vqa-base"
    
    logger.info(f"Downloading BLIP VQA model: {model_name}")
    logger.info("This will download ~1GB and may take a few minutes...")
    
    try:
        # Download processor
        logger.info("Downloading processor...")
        processor = BlipProcessor.from_pretrained(model_name)
        logger.info("✅ Processor downloaded")
        
        # Download model
        logger.info("Downloading model...")
        model = BlipForQuestionAnswering.from_pretrained(model_name)
        logger.info("✅ Model downloaded")
        
        logger.info(f"""
 BLIP VQA model successfully cached!

Model: {model_name}
Cache location: /root/.cache/huggingface (persisted in Docker volume)

The model is now ready to use. It will load instantly on next use.
""")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error downloading model: {e}")
        return False

if __name__ == "__main__":
    download_blip_model()
