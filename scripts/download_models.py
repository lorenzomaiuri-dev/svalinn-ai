"""
Svalinn AI - Model Downloader
Fetches the required GGUF models from HuggingFace.
"""

import logging
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Target Directory
MODEL_DIR = Path("models")

# Model Definitions
MODELS = {
    "input_output_guardian": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    },
    "honeypot": {
        # Official Qwen GGUF repository
        "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
    },
}


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    logger.info(f"Checking models in {MODEL_DIR.absolute()}...")

    for _key, config in MODELS.items():
        filename = config["filename"]
        destination = MODEL_DIR / filename

        if destination.exists():
            logger.info(f"✅ {filename} already exists.")
            continue

        logger.info(f"⬇️  Downloading {filename} from {config['repo_id']}...")
        try:
            hf_hub_download(
                repo_id=config["repo_id"],
                filename=config["filename"],
                local_dir=MODEL_DIR,
                local_dir_use_symlinks=False,
            )
            logger.info(f"✅ Downloaded {filename}")
        except Exception:
            logger.exception(f"❌ Failed to download {filename}")
            sys.exit(1)

    logger.info("\n🎉 All models ready! You can now run the pipeline.")


if __name__ == "__main__":
    main()
