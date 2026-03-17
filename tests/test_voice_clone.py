"""Tests for voice cloning — embedding creation, quality scoring, voice selection."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
import yaml


class TestVoiceLibrary:
    """Test voice library loading and structure."""

    def test_load_voice_library(self):
        lib_path = os.path.join(os.path.dirname(__file__),
                                "..", "config", "voices", "voice_library.yaml")
        with open(lib_path) as f:
            data = yaml.safe_load(f)

        voices = data["voice_library"]
        assert len(voices) >= 3  # At least 3 profiles

        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "gender" in voice
            assert "age_range" in voice
            assert "emotion_range" in voice
            assert "quality_score" in voice
            assert "language" in voice
            assert voice["language"] == "ar"
            assert isinstance(voice["quality_score"], (int, float))
            assert voice["quality_score"] > 0

    def test_voice_ids_unique(self):
        lib_path = os.path.join(os.path.dirname(__file__),
                                "..", "config", "voices", "voice_library.yaml")
        with open(lib_path) as f:
            data = yaml.safe_load(f)
        ids = [v["id"] for v in data["voice_library"]]
        assert len(ids) == len(set(ids))


class TestVoiceSelection:
    """Test voice selector logic."""

    @patch("src.phase5_production.voice_selector.load_voice_library")
    def test_select_by_channel_default(self, mock_load):
        from src.phase5_production.voice_selector import VoiceSelector

        mock_load.return_value = [
            {"id": "v_male_auth_01", "quality_score": 9.2,
             "best_for": ["documentary"], "emotion_range": ["authoritative"]},
            {"id": "v_male_enrg_01", "quality_score": 8.8,
             "best_for": ["science"], "emotion_range": ["energetic"]},
        ]

        selector = VoiceSelector()
        channel_config = {
            "voice": {"default_voice_id": "v_male_auth_01", "allow_voice_switch": False}
        }
        selected = selector.select(job={"topic_category": "science"},
                                   channel_config=channel_config)
        # Channel lock should override content match
        assert selected == "v_male_auth_01"

    @patch("src.phase5_production.voice_selector.load_voice_library")
    def test_select_by_content_match(self, mock_load):
        from src.phase5_production.voice_selector import VoiceSelector

        mock_load.return_value = [
            {"id": "v_male_auth_01", "quality_score": 9.2,
             "best_for": ["documentary", "history"], "emotion_range": ["authoritative"]},
            {"id": "v_male_myst_01", "quality_score": 8.5,
             "best_for": ["mysteries", "crime"], "emotion_range": ["mysterious"]},
        ]

        selector = VoiceSelector()
        channel_config = {
            "voice": {"default_voice_id": None, "allow_voice_switch": True}
        }
        selected = selector.select(
            job={"topic_category": "mysteries"},
            channel_config=channel_config
        )
        assert selected == "v_male_myst_01"

    @patch("src.phase5_production.voice_selector.load_voice_library")
    def test_fallback_to_highest_quality(self, mock_load):
        from src.phase5_production.voice_selector import VoiceSelector

        mock_load.return_value = [
            {"id": "v1", "quality_score": 7.0,
             "best_for": ["other"], "emotion_range": ["calm"]},
            {"id": "v2", "quality_score": 9.5,
             "best_for": ["other"], "emotion_range": ["calm"]},
        ]

        selector = VoiceSelector()
        channel_config = {
            "voice": {"default_voice_id": None, "allow_voice_switch": True}
        }
        selected = selector.select(
            job={"topic_category": "unknown_category"},
            channel_config=channel_config
        )
        assert selected == "v2"  # Highest quality fallback


class TestVoiceCloning:
    """Test voice cloning with mocked Fish Audio API."""

    @patch("src.phase5_production.voice_clone.FishAudioClient")
    def test_clone_creates_embedding(self, mock_client_cls):
        from src.phase5_production.voice_clone import VoiceCloner

        mock_client = MagicMock()
        mock_client.create_embedding.return_value = b"\x00" * 1024  # Fake embedding
        mock_client_cls.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            cloner = VoiceCloner(model_path=tmpdir)
            embedding_path = os.path.join(tmpdir, "test_voice.pt")

            cloner.clone(
                reference_wav="config/voices/male_authoritative_01.wav",
                voice_id="test_voice",
                output_path=embedding_path
            )
            mock_client.create_embedding.assert_called_once()

    @patch("src.phase5_production.voice_clone.FishAudioClient")
    def test_quality_scoring(self, mock_client_cls):
        from src.phase5_production.voice_clone import VoiceCloner

        mock_client = MagicMock()
        mock_client.evaluate_quality.return_value = {
            "clarity": 8.5,
            "naturalness": 7.8,
            "similarity": 9.0,
            "overall": 8.4,
        }
        mock_client_cls.return_value = mock_client

        cloner = VoiceCloner(model_path="/tmp")
        score = cloner.evaluate_quality("test_voice")
        assert score["overall"] > 7.0
        assert "clarity" in score
        assert "naturalness" in score
        assert "similarity" in score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
