"""Utility functions for the Dark Patterns research study."""

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import yaml


def encode_image(image_path: str) -> str:
    """Encode an image file to base64 string.

    Args:
        image_path: Absolute or relative path to image file.

    Returns:
        Base64-encoded string of the image.

    Raises:
        FileNotFoundError: If image file doesn't exist.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_mime_type(filename: str) -> str:
    """Get MIME type from filename extension.

    Args:
        filename: Name or path of the image file.

    Returns:
        MIME type string (defaults to image/png for unknown).
    """
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mime_map.get(ext, "image/png")


def extract_score(text: str) -> Optional[int]:
    """Extract a 1-5 recommendation score from model response text using regex.

    Tries multiple patterns in order of specificity.

    Args:
        text: Raw model response text.

    Returns:
        Integer score 1-5, or None if not found.
    """
    if not text:
        return None

    patterns = [
        r"(?:recommendation\s+)?score[:\s]*(\d)\s*/\s*5",
        r"(?:rating|score)[:\s]*(\d)\b",
        r"(?:give|rate|assign)[^.]*?(\d)\s*/?\s*(?:out\s+of\s*)?5",
        r"\b(\d)\s*/\s*5\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            score = int(match.group(1))
            if 1 <= score <= 5:
                return score

    return None


def extract_json_response(text: str) -> Optional[Dict[str, Any]]:
    """Extract structured JSON response from model output.

    Tries to find JSON in the response, including inside markdown code blocks.
    Validates that the score is in the 1-5 range.

    Args:
        text: Raw model response text.

    Returns:
        Parsed dict with score, explanation, identified_tactics, or None.
    """
    if not text:
        return None

    # Try markdown code block first
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if md_match:
        try:
            data = json.loads(md_match.group(1).strip())
            if _validate_response_json(data):
                return data
        except (json.JSONDecodeError, KeyError):
            pass

    # Try finding raw JSON object
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            if _validate_response_json(data):
                return data
        except (json.JSONDecodeError, KeyError):
            pass

    # Try parsing entire text as JSON
    try:
        data = json.loads(text.strip())
        if _validate_response_json(data):
            return data
    except (json.JSONDecodeError, KeyError):
        pass

    return None


def _validate_response_json(data: Dict[str, Any]) -> bool:
    """Validate that parsed JSON has required fields and valid score range."""
    if not isinstance(data, dict):
        return False
    if "score" not in data:
        return False
    score = data["score"]
    if not isinstance(score, (int, float)) or not (1 <= score <= 5):
        return False
    return True


def load_screenshots_manifest(manifest_path: str) -> List[Dict[str, Any]]:
    """Load the screenshots YAML manifest.

    Args:
        manifest_path: Path to screenshots.yaml file.

    Returns:
        List of image metadata dicts.

    Raises:
        FileNotFoundError: If manifest file doesn't exist.
    """
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    with open(manifest_path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("images", [])


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the study.

    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("dark_patterns")
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    return logger


def short_model_name(model: str) -> str:
    """Convert full model ID to short display name.

    Args:
        model: Full model ID like 'anthropic/claude-opus-4.6'.

    Returns:
        Short name like 'claude-opus-4.6'.
    """
    return model.split("/")[-1] if "/" in model else model
