#!/usr/bin/env python3
"""
Download sentence-transformers model for offline use.

Run this script once while online to cache the model locally.
After running this, JobPipe can score jobs offline.

Usage:
    python scripts/download_embedding_model.py
"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

LOGGER = logging.getLogger(__name__)


def download_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
    """
    Download and cache the sentence-transformers model for offline use.

    This function:
    1. Downloads the model while online
    2. Caches it in the default HuggingFace cache directory
    3. Verifies the model can be loaded offline
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        LOGGER.error("sentence-transformers not installed. Install with: pip install sentence-transformers")
        sys.exit(1)

    LOGGER.info("Downloading model: %s", model_name)
    LOGGER.info("This may take a few minutes for the first download (~80MB)...")

    # Download and cache the model
    # SentenceTransformer automatically caches to ~/.cache/huggingface/hub
    model = SentenceTransformer(model_name)

    LOGGER.info("Model downloaded successfully!")
    LOGGER.info("Cache location: %s", os.path.expanduser("~/.cache/huggingface/hub"))

    # Verify offline loading works
    LOGGER.info("Verifying offline loading...")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    try:
        model_offline = SentenceTransformer(model_name, local_files_only=True)
        LOGGER.info("✓ Offline loading verified successfully!")
        LOGGER.info("JobPipe can now score jobs offline.")
    except Exception as exc:
        LOGGER.error("✗ Offline loading failed: %s", exc)
        LOGGER.error("Try running this script again, or check your cache directory permissions.")
        sys.exit(1)


if __name__ == "__main__":
    download_model()
