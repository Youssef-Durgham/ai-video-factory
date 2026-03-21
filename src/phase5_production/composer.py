"""
Phase 5 — Video Composer: Assembles final video from all assets.

Concatenates video clips, mixes audio layers (voice + music + SFX),
and produces the final MP4 with crossfade transitions.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from src.phase5_production.ffmpeg_path import FFMPEG

logger = logging.getLogger(__name__)


@dataclass
class ComposerConfig:
    crossfade_sec: float = 0.5
    voice_volume: float = 1.0
    music_volume: float = 0.15
    sfx_volume: float = 0.35
    audio_bitrate: str = "320k"
    video_codec: str = "libx264"
    video_crf: int = 18
    video_preset: str = "medium"


@dataclass
class ComposerResult:
    success: bool
    video_path: Optional[str] = None
    duration_sec: float = 0.0
    error: Optional[str] = None


class VideoComposer:
    """Assembles final video from scene clips and audio layers."""

    def __init__(self, config: Optional[ComposerConfig] = None):
        self.config = config or ComposerConfig()

    def compose(
        self,
        job_id: str,
        scenes: list[dict],
        output_dir: str,
    ) -> ComposerResult:
        """
        Compose final video from all scene assets.

        Expected file structure:
            output/{job_id}/videos/scene_XXX.mp4
            output/{job_id}/voice/scene_XXX.mp3
            output/{job_id}/audio/sfx/scene_XXX.mp3  OR  scene_XXX_sfx_00.mp3, scene_XXX_sfx_01.mp3
            output/{job_id}/audio/music/background.mp3  (+ intro.mp3, tension.mp3, outro.mp3)
        """
        base = Path(output_dir).parent  # output/{job_id}
        final_path = str(base / "final.mp4")

        try:
            # Step 1: Concat video clips
            video_concat = str(base / "temp_video_concat.mp4")
            ok = self._concat_videos(scenes, base, video_concat)
            if not ok:
                return ComposerResult(success=False, error="Video concatenation failed")

            # Step 2: Concat voice clips
            voice_concat = str(base / "temp_voice_concat.mp3")
            self._concat_audio(scenes, base / "voice", voice_concat, "voice")

            # Step 3: Build music track (merge intro + background + outro if available)
            music_dir = base / "audio" / "music"
            music_path = str(base / "temp_music_full.mp3")
            self._build_music_track(music_dir, music_path)

            # Step 4: Merge per-scene SFX files (handle multi-file per scene)
            sfx_dir = base / "audio" / "sfx"
            self._prepare_sfx_per_scene(scenes, sfx_dir)

            # Step 5: Mix audio layers
            mixed_audio = str(base / "temp_mixed_audio.mp3")
            self._mix_audio(voice_concat, music_path, scenes, sfx_dir, mixed_audio)

            # Step 6: Merge video + audio
            ok = self._merge_video_audio(video_concat, mixed_audio, final_path)
            if not ok:
                return ComposerResult(success=False, error="Final merge failed")

            # Get duration
            duration = self._get_duration(final_path)

            # Cleanup temp files
            for tmp in [video_concat, voice_concat, mixed_audio, music_path]:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except Exception:
                    pass

            logger.info(f"Composed final video: {final_path} ({duration:.1f}s)")
            return ComposerResult(success=True, video_path=final_path, duration_sec=duration)

        except Exception as e:
            logger.error(f"Composition failed: {e}")
            return ComposerResult(success=False, error=str(e))

    def _build_music_track(self, music_dir: Path, output_path: str):
        """
        Build a full music track by concatenating: intro + background + outro.
        Falls back to just background.mp3 if others don't exist.
        """
        if not music_dir.exists():
            # Generate silence
            cmd = [
                FFMPEG, "-y", "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "1", "-codec:a", "libmp3lame",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
            return

        # Check which tracks exist
        intro = music_dir / "intro.mp3"
        background = music_dir / "background.mp3"
        outro = music_dir / "outro.mp3"

        tracks = []
        if intro.exists():
            tracks.append(str(intro))
        if background.exists():
            tracks.append(str(background))
        elif (music_dir / "background.wav").exists():
            tracks.append(str(music_dir / "background.wav"))
        if outro.exists():
            tracks.append(str(outro))

        if not tracks:
            # Try any mp3/wav in the dir
            for ext in ("*.mp3", "*.wav"):
                tracks.extend(str(f) for f in music_dir.glob(ext))
            if not tracks:
                cmd = [
                    FFMPEG, "-y", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", "1", "-codec:a", "libmp3lame",
                    output_path,
                ]
                subprocess.run(cmd, capture_output=True, timeout=30)
                return

        if len(tracks) == 1:
            # Just copy the single track
            import shutil
            shutil.copy2(tracks[0], output_path)
            return

        # Concatenate with crossfade
        self._concat_audio_files(tracks, output_path)

    def _prepare_sfx_per_scene(self, scenes: list[dict], sfx_dir: Path):
        """
        Merge multi-file SFX into one file per scene.

        AudioCoordinator generates: scene_001_sfx_00.mp3, scene_001_sfx_01.mp3, ...
        Composer expects: scene_001.mp3

        This method merges multiple SFX files for the same scene into one mixed file.
        """
        if not sfx_dir.exists():
            return

        for scene in scenes:
            idx = scene.get("scene_index", 0)
            single = sfx_dir / f"scene_{idx:03d}.mp3"

            if single.exists():
                continue  # Already have a single file

            # Find all SFX parts for this scene
            parts = sorted(sfx_dir.glob(f"scene_{idx:03d}_sfx_*.mp3"))
            if not parts:
                continue

            if len(parts) == 1:
                # Rename single part to expected name
                import shutil
                shutil.copy2(str(parts[0]), str(single))
                continue

            # Mix multiple SFX parts together (overlay, not concat)
            inputs = []
            for p in parts:
                inputs.extend(["-i", str(p)])

            filter_str = f"amix=inputs={len(parts)}:duration=longest:dropout_transition=1"
            cmd = [
                FFMPEG, "-y", *inputs,
                "-filter_complex", filter_str,
                "-codec:a", "libmp3lame", "-qscale:a", "4",
                str(single),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                logger.warning(f"SFX merge failed for scene {idx}: {proc.stderr[:200]}")
                # Fallback: just use the first part
                import shutil
                shutil.copy2(str(parts[0]), str(single))

    def _concat_videos(self, scenes: list[dict], base: Path, output_path: str) -> bool:
        """Concatenate video clips using ffmpeg concat demuxer."""
        videos_dir = base / "videos"
        filelist = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            vp = scene.get("video_clip_path") or str(videos_dir / f"scene_{idx:03d}.mp4")
            if Path(vp).exists():
                filelist.append(vp)
            else:
                logger.warning(f"Video clip missing: {vp}")

        if not filelist:
            logger.error("No video clips found")
            return False

        # Write concat list
        list_path = str(base / "temp_concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for vp in filelist:
                f.write(f"file '{vp}'\n")

        # Use concat with re-encoding for consistent format
        cmd = [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", self.config.video_codec,
            "-crf", str(self.config.video_crf),
            "-preset", self.config.video_preset,
            "-pix_fmt", "yuv420p",
            "-an",  # No audio in video concat
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        Path(list_path).unlink(missing_ok=True)

        if proc.returncode != 0:
            logger.error(f"Video concat failed: {proc.stderr[:300]}")
            return False
        return True

    def _concat_audio(self, scenes: list[dict], audio_dir: Path, output_path: str, label: str):
        """Concatenate audio files in scene order."""
        files = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            path_key = f"{label}_path"
            ap = scene.get(path_key) or str(audio_dir / f"scene_{idx:03d}.mp3")
            if Path(ap).exists():
                files.append(ap)

        if not files:
            # Create silence
            cmd = [
                FFMPEG, "-y", "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "1", "-codec:a", "libmp3lame",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
            return

        list_path = str(Path(output_path).parent / f"temp_{label}_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for ap in files:
                f.write(f"file '{ap}'\n")

        cmd = [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        Path(list_path).unlink(missing_ok=True)

    def _mix_audio(
        self,
        voice_path: str,
        music_path: str,
        scenes: list[dict],
        sfx_dir: Path,
        output_path: str,
    ):
        """Mix voice + music + SFX into a single audio track."""
        inputs = ["-i", voice_path]
        filter_parts = []
        input_idx = 1

        # Add music if exists
        has_music = Path(music_path).exists()
        if has_music:
            inputs.extend(["-i", music_path])
            filter_parts.append(f"[{input_idx}]volume={self.config.music_volume}[bg]")
            input_idx += 1

        # Concat SFX into one track if available
        sfx_files = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            sp = str(sfx_dir / f"scene_{idx:03d}.mp3")
            if Path(sp).exists():
                sfx_files.append(sp)

        has_sfx = False
        sfx_concat_path = str(Path(output_path).parent / "temp_sfx_concat.mp3")
        if sfx_files:
            self._concat_audio_files(sfx_files, sfx_concat_path)
            if Path(sfx_concat_path).exists():
                inputs.extend(["-i", sfx_concat_path])
                filter_parts.append(f"[{input_idx}]volume={self.config.sfx_volume}[sfx]")
                has_sfx = True
                input_idx += 1

        # Build filter complex
        if has_music and has_sfx:
            filter_parts.append("[0][bg][sfx]amix=inputs=3:duration=first:dropout_transition=2[out]")
        elif has_music:
            filter_parts.append("[0][bg]amix=inputs=2:duration=first:dropout_transition=2[out]")
        elif has_sfx:
            filter_parts.append("[0][sfx]amix=inputs=2:duration=first:dropout_transition=2[out]")
        else:
            # Voice only
            cmd = [FFMPEG, "-y", "-i", voice_path, "-codec:a", "libmp3lame", "-qscale:a", "2", output_path]
            subprocess.run(cmd, capture_output=True, timeout=300)
            return

        filter_str = ";".join(filter_parts)
        cmd = [FFMPEG, "-y"] + inputs + [
            "-filter_complex", filter_str,
            "-map", "[out]",
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            logger.warning(f"Audio mix failed, using voice only: {proc.stderr[:200]}")
            # Fallback: voice only
            cmd = [FFMPEG, "-y", "-i", voice_path, "-codec:a", "libmp3lame", "-qscale:a", "2", output_path]
            subprocess.run(cmd, capture_output=True, timeout=300)

        # Cleanup
        Path(sfx_concat_path).unlink(missing_ok=True)

    def _concat_audio_files(self, files: list[str], output_path: str):
        """Helper to concat a list of audio files."""
        list_path = str(Path(output_path).parent / "temp_sfx_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for fp in files:
                f.write(f"file '{fp}'\n")
        cmd = [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-codec:a", "libmp3lame", "-qscale:a", "4",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=300)
        Path(list_path).unlink(missing_ok=True)

    def _merge_video_audio(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Merge video and mixed audio into final MP4."""
        cmd = [
            FFMPEG, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", self.config.audio_bitrate,
            "-shortest",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            logger.error(f"Merge failed: {proc.stderr[:300]}")
            return False
        return True

    @staticmethod
    def _get_duration(path: str) -> float:
        """Get media duration via ffprobe."""
        try:
            result = subprocess.run(
                [FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return round(float(result.stdout.strip()), 2)
        except Exception:
            return 0.0
