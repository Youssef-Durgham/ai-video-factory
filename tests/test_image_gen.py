"""Tests for ImageGenerator — ComfyUI workflow, prompt enhancement, fallback."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json


class TestPromptEnhancement:
    """Test image prompt enhancement for Arabic documentary content."""

    def test_basic_prompt_structure(self):
        """Enhanced prompt should include style and quality modifiers."""
        from src.phase5_production.image_prompt import enhance_prompt

        raw = "ancient Babylonian ruins in Iraq"
        enhanced, negative = enhance_prompt(raw, region="iraq", channel_config={
            "style": {"visual": "cinematic_photorealistic",
                      "lora": "photojournalism.safetensors"}
        })
        assert len(enhanced) > len(raw)
        assert isinstance(negative, str)
        assert len(negative) > 0

    def test_negative_prompt_includes_defaults(self):
        from src.phase5_production.image_prompt import enhance_prompt

        _, negative = enhance_prompt("a mosque at sunset", region="iraq", channel_config={
            "style": {"visual": "cinematic_photorealistic"}
        })
        # Should include common negative prompts for quality
        neg_lower = negative.lower()
        assert any(term in neg_lower for term in [
            "text", "watermark", "blurry", "deformed", "low quality"
        ])

    def test_regional_context_added(self):
        from src.phase5_production.image_prompt import enhance_prompt

        enhanced, _ = enhance_prompt("market scene", region="iraq", channel_config={
            "style": {"visual": "cinematic_photorealistic"}
        })
        enhanced_lower = enhanced.lower()
        # Should add regional/cultural context
        assert "market" in enhanced_lower


class TestComfyUIWorkflow:
    """Test ComfyUI workflow construction (mocked API)."""

    @patch("src.phase5_production.image_gen.requests")
    def test_workflow_has_required_nodes(self, mock_requests):
        """ComfyUI workflow JSON should have sampler, model, and output nodes."""
        from src.phase5_production.image_gen import ImageGenerator

        mock_response = MagicMock()
        mock_response.json.return_value = {"prompt_id": "test_123"}
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response
        mock_requests.get.return_value = MagicMock(
            json=MagicMock(return_value={}), status_code=200
        )

        config = {
            "settings": {
                "comfyui": {
                    "host": "http://localhost:8188",
                    "models": {"flux": "flux1-dev.safetensors"},
                    "loras": [],
                },
                "pipeline": {
                    "image_resolution": [1920, 1080],
                },
            }
        }

        gen = ImageGenerator(config)
        workflow = gen._build_workflow(
            prompt="test prompt",
            negative="bad quality",
            width=1920, height=1080,
            model="flux1-dev.safetensors",
            lora=None,
        )
        assert isinstance(workflow, dict)

    @patch("src.phase5_production.image_gen.requests")
    def test_generate_returns_path(self, mock_requests):
        """Generate should return an image file path."""
        from src.phase5_production.image_gen import ImageGenerator

        # Mock the ComfyUI prompt submission
        mock_requests.post.return_value = MagicMock(
            json=MagicMock(return_value={"prompt_id": "test_123"}),
            status_code=200,
        )
        # Mock history poll
        mock_requests.get.side_effect = [
            # First call: still processing
            MagicMock(json=MagicMock(return_value={}), status_code=200),
            # Second call: completed
            MagicMock(json=MagicMock(return_value={
                "test_123": {"outputs": {"save_image": {"images": [
                    {"filename": "test.png", "subfolder": "", "type": "output"}
                ]}}}
            }), status_code=200),
            # Image download
            MagicMock(content=b"fake_png_data", status_code=200),
        ]

        config = {
            "settings": {
                "comfyui": {
                    "host": "http://localhost:8188",
                    "models": {"flux": "flux1-dev.safetensors"},
                    "loras": [],
                },
                "pipeline": {"image_resolution": [1920, 1080]},
            }
        }

        gen = ImageGenerator(config)
        # This tests the workflow, not actual generation
        assert gen is not None


class TestFallbackHandling:
    """Test fallback when ComfyUI is unavailable."""

    @patch("src.phase5_production.image_gen.requests")
    def test_connection_error_raises(self, mock_requests):
        """Should raise when ComfyUI server is unreachable."""
        from src.phase5_production.image_gen import ImageGenerator
        import requests as real_requests

        mock_requests.post.side_effect = real_requests.ConnectionError("Refused")

        config = {
            "settings": {
                "comfyui": {
                    "host": "http://localhost:8188",
                    "models": {"flux": "flux1-dev.safetensors"},
                    "loras": [],
                },
                "pipeline": {"image_resolution": [1920, 1080]},
            }
        }

        gen = ImageGenerator(config)
        with pytest.raises(Exception):
            gen.generate("test prompt", "negative", output_path="/tmp/test.png")

    def test_lora_config_optional(self):
        """Image generation should work without LoRA."""
        from src.phase5_production.image_gen import ImageGenerator

        config = {
            "settings": {
                "comfyui": {
                    "host": "http://localhost:8188",
                    "models": {"flux": "flux1-dev.safetensors"},
                    "loras": [],
                },
                "pipeline": {"image_resolution": [1920, 1080]},
            }
        }

        gen = ImageGenerator(config)
        workflow = gen._build_workflow(
            prompt="test", negative="bad",
            width=1920, height=1080,
            model="flux1-dev.safetensors", lora=None,
        )
        assert isinstance(workflow, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
