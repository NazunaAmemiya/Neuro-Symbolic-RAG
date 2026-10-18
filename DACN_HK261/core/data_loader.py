import os
from huggingface_hub import snapshot_download
import logging
from dotenv import load_dotenv

load_dotenv()

hf_token = os.environ.get("HF_TOKEN")
repo_id = os.environ.get("REPO_ID")

logger = logging.getLogger(__name__)

def load_data():
    if not repo_id:
        logger.error("Missing repo_id")
        raise ValueError("Request repo_id")

    logger.info("Start loading data")
    try:
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir="./data",
            token=hf_token,
            resume_download=True
        )
        logger.info("Loading data succeed")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
