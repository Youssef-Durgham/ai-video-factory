"""Tests for VideoComposer — FFmpeg commands, scene sequencing, audio mixing."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, call


class TestFFmpegCommandConstruction:
    """Test FFmpeg command building without executing."""

    def test_basic_concat_command(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        scenes = [
            {"scene_index": 0, "video_path": "scene_0.mp4", "duration_sec": 10},
            {"scene_index": 1, "video_path": "scene_1.mp4", "duration_sec": 8},
        ]
        cmd = composer._build_concat_command(scenes, output="final.mp4")
        assert isinstance(cmd, list)
        assert "ffmpeg" in cmd[0].lower() or cmd[0] == "ffmpeg"
        assert "final.mp4" in cmd

    def test_audio_mix_command(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        cmd = composer._build_audio_mix_command(
            video_path="composed.mp4",
            voice_path="voice.wav",
            music_path="music.wav",
            sfx_paths=["sfx1.wav"],
            output="final.mp4",
            music_volume=0.25,
        )
        assert isinstance(cmd, list)
        # Should reference input files
        cmd_str = " ".join(cmd)
        assert "voice.wav" in cmd_str
        assert "music.wav" in cmd_str


class TestSceneSequencing:
    """Test scenes are assembled in correct order."""

    def test_scenes_ordered_by_index(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        scenes = [
            {"scene_index": 2, "video_path": "s2.mp4", "duration_sec": 5},
            {"scene_index": 0, "video_path": "s0.mp4", "duration_sec": 5},
            {"scene_index": 1, "video_path": "s1.mp4", "duration_sec": 5},
        ]
        ordered = composer._order_scenes(scenes)
        assert [s["scene_index"] for s in ordered] == [0, 1, 2]

    def test_transition_between_scenes(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        scenes = [
            {"scene_index": 0, "video_path": "s0.mp4", "duration_sec": 10,
             "transition_type": "crossfade"},
            {"scene_index": 1, "video_path": "s1.mp4", "duration_sec": 8,
             "transition_type": "cut"},
        ]
        filter_str = composer._build_transition_filter(scenes)
        assert isinstance(filter_str, str)


class TestAudioMixing:
    """Test audio ducking and mixing parameters."""

    def test_music_ducking_volume(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        # Music should duck to 20-30% during narration
        duck_params = composer._calculate_ducking_params(
            voice_duration=120.0,
            music_duration=130.0,
        )
        assert 0.15 <= duck_params["music_volume_during_voice"] <= 0.35
        assert duck_params["music_volume_intro"] >= 0.7

    def test_sfx_volume_range(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        vol = composer._get_sfx_volume(sfx_type="ambient")
        assert 0.2 <= vol <= 0.6

        vol = composer._get_sfx_volume(sfx_type="impact")
        assert 0.4 <= vol <= 0.8


class TestOverlayCompositing:
    """Test text overlay compositing commands."""

    def test_text_overlay_filter(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        overlay = {
            "text": "معركة القادسية",
            "position": "lower_third",
            "start_time": 5.0,
            "end_time": 10.0,
        }
        filter_str = composer._build_overlay_filter(overlay)
        assert isinstance(filter_str, str)
        assert "overlay" in filter_str.lower() or "drawtext" in filter_str.lower()

    def test_intro_outro_concat(self):
        from src.phase5_production.video_composer import VideoComposer

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)

        cmd = composer._build_intro_outro_command(
            intro_path="intro.mp4",
            main_path="main.mp4",
            outro_path="outro.mp4",
            output="final_with_io.mp4",
        )
        assert isinstance(cmd, list)
        cmd_str = " ".join(cmd)
        assert "intro.mp4" in cmd_str
        assert "outro.mp4" in cmd_str


class TestSubprocessExecution:
    """Test subprocess calls are made correctly (mocked)."""

    @patch("src.phase5_production.video_composer.subprocess")
    def test_run_ffmpeg_success(self, mock_subprocess):
        from src.phase5_production.video_composer import VideoComposer

        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)
        result = composer._run_ffmpeg(["ffmpeg", "-version"])
        assert result.returncode == 0

    @patch("src.phase5_production.video_composer.subprocess")
    def test_run_ffmpeg_failure_raises(self, mock_subprocess):
        from src.phase5_production.video_composer import VideoComposer

        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stderr="Error: invalid input"
        )

        config = {"settings": {"pipeline": {
            "video_fps": 24, "video_codec": "h264",
            "audio_codec": "aac", "audio_bitrate": "320k",
            "image_resolution": [1920, 1080],
        }}}
        composer = VideoComposer(config, db=None)
        with pytest.raises(RuntimeError):
            composer._run_ffmpeg(["ffmpeg", "-i", "nonexistent.mp4"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
