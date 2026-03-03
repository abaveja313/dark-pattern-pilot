"""Tests for dark_patterns.utils module."""

import base64
import json
import os
import tempfile
import pytest
from dark_patterns.utils import (
    encode_image,
    get_mime_type,
    extract_score,
    extract_json_response,
    setup_logging,
    load_screenshots_manifest,
)


class TestEncodeImage:
    def test_encodes_png(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = encode_image(str(img))
        decoded = base64.b64decode(result)
        assert decoded[:4] == b"\x89PNG"

    def test_returns_base64_string(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        result = encode_image(str(img))
        assert isinstance(result, str)
        # Should be valid base64
        base64.b64decode(result)

    def test_raises_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            encode_image("/nonexistent/image.png")


class TestGetMimeType:
    def test_png(self):
        assert get_mime_type("screenshot.png") == "image/png"

    def test_jpg(self):
        assert get_mime_type("photo.jpg") == "image/jpeg"

    def test_jpeg(self):
        assert get_mime_type("photo.jpeg") == "image/jpeg"

    def test_webp(self):
        assert get_mime_type("image.webp") == "image/webp"

    def test_gif(self):
        assert get_mime_type("anim.gif") == "image/gif"

    def test_unknown_defaults_to_png(self):
        assert get_mime_type("file.bmp") == "image/png"


class TestExtractScore:
    """Test regex-based score extraction from model responses."""

    def test_score_slash_five(self):
        assert extract_score("Score: 3/5") == 3

    def test_recommendation_score(self):
        assert extract_score("Recommendation Score: 4/5") == 4

    def test_rating_colon(self):
        assert extract_score("Rating: 2") == 2

    def test_give_score(self):
        assert extract_score("I give this a 4 out of 5") == 4

    def test_bare_fraction(self):
        assert extract_score("My assessment is 3/5") == 3

    def test_score_one(self):
        assert extract_score("Score: 1/5 - terrible product") == 1

    def test_score_five(self):
        assert extract_score("Score: 5/5 - excellent!") == 5

    def test_returns_none_for_no_match(self):
        assert extract_score("This is a great product") is None

    def test_returns_none_for_out_of_range(self):
        assert extract_score("Score: 0/5") is None
        assert extract_score("Score: 9/5") is None

    def test_returns_none_for_empty(self):
        assert extract_score("") is None

    def test_multiline_response(self):
        text = """Based on my analysis, this product appears genuine.
        The reviews look legitimate.
        Recommendation Score: 4/5"""
        assert extract_score(text) == 4

    def test_case_insensitive(self):
        assert extract_score("SCORE: 3/5") == 3
        assert extract_score("score: 2/5") == 2


class TestExtractJsonResponse:
    """Test JSON extraction from model responses."""

    def test_valid_json(self):
        text = '{"score": 3, "explanation": "Looks good", "identified_tactics": ["urgency"]}'
        result = extract_json_response(text)
        assert result["score"] == 3
        assert result["explanation"] == "Looks good"
        assert "urgency" in result["identified_tactics"]

    def test_json_in_markdown_block(self):
        text = """Here is my analysis:
```json
{"score": 2, "explanation": "Suspicious", "identified_tactics": ["social_proof"]}
```"""
        result = extract_json_response(text)
        assert result["score"] == 2

    def test_returns_none_for_no_json(self):
        assert extract_json_response("Just a regular text response") is None

    def test_returns_none_for_invalid_json(self):
        assert extract_json_response('{"score": }') is None

    def test_extracts_score_from_nested(self):
        text = 'Some preamble {"score": 4, "explanation": "test", "identified_tactics": []} more text'
        result = extract_json_response(text)
        assert result is not None
        assert result["score"] == 4

    def test_validates_score_range(self):
        text = '{"score": 7, "explanation": "test", "identified_tactics": []}'
        result = extract_json_response(text)
        assert result is None  # score out of 1-5 range


class TestLoadScreenshotsManifest:
    def test_loads_valid_yaml(self, tmp_path):
        manifest = tmp_path / "screenshots.yaml"
        manifest.write_text(
            """images:
  - file: one-tag.png
    dark_pattern_type: social_proof
    subtype: activity_badge
    sp_element_count: 1
    is_control: false
    ground_truth_manipulation: true
    description: "Test image"
"""
        )
        images = load_screenshots_manifest(str(manifest))
        assert len(images) == 1
        assert images[0]["file"] == "one-tag.png"
        assert images[0]["sp_element_count"] == 1

    def test_raises_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_screenshots_manifest("/nonexistent/screenshots.yaml")


class TestSetupLogging:
    def test_returns_logger(self):
        logger = setup_logging(verbose=False)
        assert logger is not None

    def test_verbose_mode(self):
        import logging

        logger = setup_logging(verbose=True)
        assert logger.level == logging.DEBUG
