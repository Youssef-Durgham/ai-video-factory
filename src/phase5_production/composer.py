"""
Phase 5 — Video Composer (THE CRITICAL FILE).

FFmpeg assembly pipeline:
  • Video clips + voice narration + music + SFX
  • Arabic text overlays via PyCairo + HarfBuzz (transparent layers)
  • Music auto-ducking under narration
  • Scene transitions (crossfade, cut, dissolve, fade-to-black)
  • Intro/outro insertion
  • Final render: H.264, AAC 320kbps, 1080p MP4
"""

import json
import os
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from .text_animator import TextAnimationRenderer, TextOverlayConfig

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# TRANSITION DEFINITIONS
# ════════════════════════════════════════════════════════════════

TRANSITIONS: dict[str, dict] = {
    "cut":        {"duration": 0.0,  "xfade": None},
    "crossfade":  {"duration": 0.5,  "xfade": "fade"},
    "dissolve":   {"duration": 1.0,  "xfade": "dissolve"},
    "fade_black": {"duration": 1.5,  "xfade": None, "method": "fade_black"},
    "fade_white": {"duration": 1.0,  "xfade": None, "method": "fade_white"},
    "wipe_left":  {"duration": 0.5,  "xfade": "wipeleft"},
    "wipe_right": {"duration": 0.5,  "xfade": "wiperight"},
    "slide_up":   {"duration": 0.4,  "xfade": "slideup"},
    "slide_down": {"duration": 0.4,  "xfade": "slidedown"},
}


@dataclass
class ComposerConfig:
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    fps: int = 24
    width: int = 1920
    height: int = 1080
    video_codec: str = "libx264"
    video_preset: str = "medium"
    video_crf: int = 18
    audio_codec: str = "aac"
    audio_bitrate: str = "320k"
    audio_sample_rate: int = 44100
    # Volume levels
    voice_volume: float = 1.0       # 100%
    music_volume: float = 0.25      # 25% base
    music_duck_volume: float = 0.10 # 10% during narration
    sfx_volume: float = 0.50        # 50%
    duck_attack_ms: int = 300
    duck_release_ms: int = 500
    # Output
    pixel_format: str = "yuv420p"
    # LUFS target
    target_lufs: float = -14.0


@dataclass
class ComposerResult:
    success: bool
    output_path: Optional[str] = None
    duration_sec: float = 0.0
    file_size_mb: float = 0.0
    error: Optional[str] = None


class VideoComposer:
    """
    Assembles the final video from all Phase 5 assets.

    Pipeline:
    1. Concatenate video clips with transitions
    2. Overlay text animations (PyCairo-rendered transparent layers)
    3. Mix audio: voice (100%) + music (25%, auto-ducked) + SFX
    4. Insert intro/outro
    5. Final render to H.264 MP4
    """

    def __init__(self, config: Optional[ComposerConfig] = None):
        self.config = config or ComposerConfig()
        self.text_renderer = TextAnimationRenderer(ffmpeg_path=self.config.ffmpeg)

    # ═══════════════════════════════════════════════════════
    # MAIN COMPOSE METHOD
    # ═══════════════════════════════════════════════════════

    def compose(
        self,
        scenes: list[dict],
        output_path: str,
        intro_path: Optional[str] = None,
        outro_path: Optional[str] = None,
        music_tracks: Optional[dict] = None,
    ) -> ComposerResult:
        """
        Full video composition pipeline.

        Args:
            scenes: List of scene dicts with paths to all assets:
                - video_clip_path: str
                - voice_path: str (optional)
                - sfx_paths: list[str] (optional)
                - text_overlay: dict (optional) {text, style, position}
                - transition_to_next: str
                - duration_seconds: float
                - start_time_sec: float (computed if missing)
            output_path: Final MP4 output path.
            intro_path: Optional intro video .mp4.
            outro_path: Optional outro video .mp4.
            music_tracks: Dict of music track paths keyed by role:
                {"background": "path.wav", "intro": "path.wav", ...}

        Returns:
            ComposerResult with path to final video.
        """
        tmp_dir = tempfile.mkdtemp(prefix="compose_")
        try:
            logger.info(f"Starting composition: {len(scenes)} scenes")

            # Step 1: Compute timeline
            timeline = self._compute_timeline(scenes)

            # Step 2: Concatenate video clips with transitions
            video_concat = os.path.join(tmp_dir, "video_concat.mp4")
            self._concatenate_clips(timeline, video_concat, tmp_dir)

            # Step 3: Render text overlays
            overlays = self._render_text_overlays(timeline, tmp_dir)

            # Step 4: Composite text overlays onto video
            if overlays:
                video_with_text = os.path.join(tmp_dir, "video_text.mp4")
                self._composite_overlays(video_concat, overlays, timeline, video_with_text)
            else:
                video_with_text = video_concat

            # Step 5: Mix audio (voice + music + SFX with ducking)
            audio_mix = os.path.join(tmp_dir, "audio_mix.wav")
            self._mix_audio(timeline, music_tracks, audio_mix, tmp_dir)

            # Step 6: Insert intro/outro
            if intro_path or outro_path:
                video_full = os.path.join(tmp_dir, "video_full.mp4")
                self._insert_intro_outro(
                    video_with_text, video_full, intro_path, outro_path
                )
            else:
                video_full = video_with_text

            # Step 7: Final mux (video + audio)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            self._final_render(video_full, audio_mix, output_path)

            # Get file info
            duration = self._get_duration(output_path)
            size_mb = os.path.getsize(output_path) / (1024 * 1024)

            logger.info(
                f"Composition complete: {output_path} "
                f"({duration:.1f}s, {size_mb:.1f}MB)"
            )
            return ComposerResult(
                success=True,
                output_path=output_path,
                duration_sec=duration,
                file_size_mb=round(size_mb, 2),
            )

        except Exception as e:
            logger.error(f"Composition failed: {e}", exc_info=True)
            return ComposerResult(success=False, error=str(e))

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ═══════════════════════════════════════════════════════
    # STEP 1: TIMELINE COMPUTATION
    # ═══════════════════════════════════════════════════════

    def _compute_timeline(self, scenes: list[dict]) -> list[dict]:
        """Compute absolute start/end times for each scene."""
        timeline = []
        current_time = 0.0

        for i, scene in enumerate(scenes):
            dur = scene.get("duration_seconds", scene.get("duration_sec", 5.0))
            entry = {
                **scene,
                "index": scene.get("scene_index", i),
                "start_time": current_time,
                "end_time": current_time + dur,
                "duration": dur,
            }
            timeline.append(entry)

            # Account for transition overlap
            trans = scene.get("transition_to_next", "crossfade")
            trans_dur = TRANSITIONS.get(trans, TRANSITIONS["crossfade"]).get("duration", 0)
            current_time += dur - trans_dur

        return timeline

    # ═══════════════════════════════════════════════════════
    # STEP 2: VIDEO CONCATENATION WITH TRANSITIONS
    # ═══════════════════════════════════════════════════════

    def _concatenate_clips(
        self, timeline: list[dict], output_path: str, tmp_dir: str
    ):
        """Concatenate video clips with scene transitions."""
        clips = []
        for entry in timeline:
            clip_path = entry.get("video_clip_path")
            if clip_path and os.path.exists(clip_path):
                clips.append(clip_path)
            else:
                # Generate black clip as placeholder
                black = os.path.join(tmp_dir, f"black_{entry['index']:03d}.mp4")
                self._generate_black_clip(black, entry["duration"])
                clips.append(black)

        if len(clips) == 0:
            raise ValueError("No video clips to concatenate")

        if len(clips) == 1:
            shutil.copy2(clips[0], output_path)
            return

        # Use xfade filter chain for transitions
        # For many clips, build a complex filtergraph
        self._xfade_concat(clips, timeline, output_path, tmp_dir)

    def _xfade_concat(
        self,
        clips: list[str],
        timeline: list[dict],
        output_path: str,
        tmp_dir: str,
    ):
        """Concatenate clips using FFmpeg xfade transitions."""
        # For simplicity and reliability with many clips,
        # we concat in pairs iteratively
        current = clips[0]

        for i in range(1, len(clips)):
            trans_name = timeline[i - 1].get("transition_to_next", "crossfade")
            trans = TRANSITIONS.get(trans_name, TRANSITIONS["crossfade"])
            trans_dur = trans.get("duration", 0.5)
            xfade_type = trans.get("xfade")

            next_clip = clips[i]
            merged = os.path.join(tmp_dir, f"merged_{i:03d}.mp4")

            if xfade_type and trans_dur > 0:
                # Get current clip duration
                cur_dur = self._get_duration(current)
                offset = max(0, cur_dur - trans_dur)

                cmd = [
                    self.config.ffmpeg, "-y",
                    "-i", current,
                    "-i", next_clip,
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition={xfade_type}:duration={trans_dur}:offset={offset}[v]",
                    "-map", "[v]",
                    "-c:v", self.config.video_codec,
                    "-preset", "fast",
                    "-crf", str(self.config.video_crf),
                    "-pix_fmt", self.config.pixel_format,
                    "-an",
                    merged,
                ]
            elif trans.get("method") == "fade_black":
                # Fade to black between clips
                cur_dur = self._get_duration(current)
                half = trans_dur / 2
                cmd = [
                    self.config.ffmpeg, "-y",
                    "-i", current,
                    "-i", next_clip,
                    "-filter_complex",
                    f"[0:v]fade=t=out:st={cur_dur - half}:d={half}[v0];"
                    f"[1:v]fade=t=in:st=0:d={half}[v1];"
                    f"[v0][v1]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]",
                    "-c:v", self.config.video_codec,
                    "-preset", "fast",
                    "-crf", str(self.config.video_crf),
                    "-pix_fmt", self.config.pixel_format,
                    "-an",
                    merged,
                ]
            else:
                # Hard cut — simple concat
                concat_file = os.path.join(tmp_dir, f"concat_{i}.txt")
                with open(concat_file, "w") as f:
                    f.write(f"file '{current}'\nfile '{next_clip}'\n")
                cmd = [
                    self.config.ffmpeg, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:v", self.config.video_codec,
                    "-preset", "fast",
                    "-crf", str(self.config.video_crf),
                    "-pix_fmt", self.config.pixel_format,
                    "-an",
                    merged,
                ]

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                logger.warning(
                    f"Transition failed at clip {i}, using hard cut: {proc.stderr[:200]}"
                )
                # Fallback: hard concat
                concat_file = os.path.join(tmp_dir, f"fallback_{i}.txt")
                with open(concat_file, "w") as f:
                    f.write(f"file '{current}'\nfile '{next_clip}'\n")
                subprocess.run([
                    self.config.ffmpeg, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy", "-an", merged,
                ], capture_output=True, timeout=120)

            current = merged

        shutil.copy2(current, output_path)

    # ═══════════════════════════════════════════════════════
    # STEP 3: TEXT OVERLAY RENDERING
    # ═══════════════════════════════════════════════════════

    def _render_text_overlays(
        self, timeline: list[dict], tmp_dir: str
    ) -> list[dict]:
        """
        Render text overlays for scenes that have them.
        Returns list of {overlay_path, start_time, duration}.
        """
        overlays = []
        overlay_dir = os.path.join(tmp_dir, "overlays")
        os.makedirs(overlay_dir, exist_ok=True)

        for entry in timeline:
            text_data = entry.get("text_overlay")
            if not text_data:
                continue

            # Parse text overlay data
            if isinstance(text_data, str):
                try:
                    text_data = json.loads(text_data)
                except (json.JSONDecodeError, TypeError):
                    continue

            text = text_data.get("text", "")
            if not text or not text.strip():
                continue

            # Build config
            config = TextOverlayConfig(
                text=text,
                font_path=text_data.get("font_path", ""),
                font_size=text_data.get("font_size", 56),
                position=text_data.get("position", "lower_third"),
                entry_animation=text_data.get("animation", "fade_in"),
                exit_animation="fade_out",
                bg_style=text_data.get("bg_style", "box"),
            )

            out_path = os.path.join(
                overlay_dir, f"overlay_{entry['index']:03d}.mov"
            )

            result = self.text_renderer.render_overlay(
                text=text,
                config=config,
                duration_sec=entry["duration"],
                fps=self.config.fps,
                width=self.config.width,
                height=self.config.height,
                output_path=out_path,
            )

            if result and os.path.exists(result):
                overlays.append({
                    "path": result,
                    "start_time": entry["start_time"],
                    "duration": entry["duration"],
                })

        logger.info(f"Rendered {len(overlays)} text overlays")
        return overlays

    # ═══════════════════════════════════════════════════════
    # STEP 4: COMPOSITE TEXT OVERLAYS
    # ═══════════════════════════════════════════════════════

    def _composite_overlays(
        self,
        video_path: str,
        overlays: list[dict],
        timeline: list[dict],
        output_path: str,
    ):
        """
        Overlay transparent text animations on the base video.
        Uses FFmpeg overlay filter with enable expressions for timing.
        """
        if not overlays:
            shutil.copy2(video_path, output_path)
            return

        # Build filter graph
        inputs = ["-i", video_path]
        filter_parts = []
        prev_label = "0:v"

        for i, ov in enumerate(overlays):
            inputs.extend(["-i", ov["path"]])
            in_idx = i + 1
            out_label = f"v{i}" if i < len(overlays) - 1 else "vout"
            start = ov["start_time"]
            end = start + ov["duration"]

            filter_parts.append(
                f"[{prev_label}][{in_idx}:v]overlay=0:0:"
                f"enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
            )
            prev_label = out_label

        filtergraph = ";".join(filter_parts)

        cmd = [
            self.config.ffmpeg, "-y",
            *inputs,
            "-filter_complex", filtergraph,
            "-map", f"[{prev_label}]",
            "-c:v", self.config.video_codec,
            "-preset", self.config.video_preset,
            "-crf", str(self.config.video_crf),
            "-pix_fmt", self.config.pixel_format,
            "-an",
            output_path,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            logger.warning(f"Overlay composite failed: {proc.stderr[:300]}")
            # Fallback: no overlays
            shutil.copy2(video_path, output_path)

    # ═══════════════════════════════════════════════════════
    # STEP 5: AUDIO MIXING WITH AUTO-DUCKING
    # ═══════════════════════════════════════════════════════

    def _mix_audio(
        self,
        timeline: list[dict],
        music_tracks: Optional[dict],
        output_path: str,
        tmp_dir: str,
    ):
        """
        Mix voice + music + SFX with auto-ducking.

        Voice is at full volume. Music ducks during narration.
        """
        total_dur = timeline[-1]["end_time"] if timeline else 0

        # Step 5a: Concatenate all voice tracks into one timeline
        voice_track = os.path.join(tmp_dir, "voice_full.wav")
        self._build_voice_track(timeline, voice_track, total_dur)

        # Step 5b: Build music track (looped/trimmed to video length)
        music_track = None
        if music_tracks:
            bg_music = music_tracks.get("background")
            if bg_music and os.path.exists(bg_music):
                music_track = os.path.join(tmp_dir, "music_trimmed.wav")
                self._trim_or_loop_audio(bg_music, music_track, total_dur)

        # Step 5c: Build SFX track
        sfx_track = os.path.join(tmp_dir, "sfx_full.wav")
        has_sfx = self._build_sfx_track(timeline, sfx_track, total_dur)

        # Step 5d: Mix with ducking
        self._ducking_mix(
            voice_path=voice_track,
            music_path=music_track,
            sfx_path=sfx_track if has_sfx else None,
            output_path=output_path,
            total_dur=total_dur,
        )

    def _build_voice_track(
        self, timeline: list[dict], output_path: str, total_dur: float
    ):
        """
        Place voice clips at correct timestamps on a silent base track.
        """
        # Create silent base
        silent = output_path + ".silent.wav"
        subprocess.run([
            self.config.ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={self.config.audio_sample_rate}:cl=stereo",
            "-t", str(total_dur),
            silent,
        ], capture_output=True, timeout=60)

        # Overlay each voice clip at its start time
        current = silent
        for i, entry in enumerate(timeline):
            voice = entry.get("voice_path")
            if not voice or not os.path.exists(voice):
                continue

            next_path = output_path + f".v{i}.wav"
            delay_ms = int(entry["start_time"] * 1000)

            cmd = [
                self.config.ffmpeg, "-y",
                "-i", current,
                "-i", voice,
                "-filter_complex",
                f"[1:a]adelay={delay_ms}|{delay_ms}[delayed];"
                f"[0:a][delayed]amix=inputs=2:duration=first:dropout_transition=0[out]",
                "-map", "[out]",
                "-ar", str(self.config.audio_sample_rate),
                "-ac", "2",
                next_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                current = next_path
            else:
                logger.warning(f"Voice placement failed for scene {entry['index']}")

        if current != output_path:
            shutil.copy2(current, output_path)

    def _build_sfx_track(
        self, timeline: list[dict], output_path: str, total_dur: float
    ) -> bool:
        """Place SFX at correct timestamps. Returns True if any SFX exist."""
        has_sfx = False

        # Create silent base
        silent = output_path + ".silent.wav"
        subprocess.run([
            self.config.ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={self.config.audio_sample_rate}:cl=stereo",
            "-t", str(total_dur),
            silent,
        ], capture_output=True, timeout=60)

        current = silent
        sfx_idx = 0

        for entry in timeline:
            sfx_paths = entry.get("sfx_paths", [])
            if isinstance(sfx_paths, str):
                try:
                    sfx_paths = json.loads(sfx_paths)
                except Exception:
                    sfx_paths = []

            for sfx_path in sfx_paths:
                if not sfx_path or not os.path.exists(sfx_path):
                    continue

                has_sfx = True
                next_path = output_path + f".s{sfx_idx}.wav"
                delay_ms = int(entry["start_time"] * 1000)

                cmd = [
                    self.config.ffmpeg, "-y",
                    "-i", current,
                    "-i", sfx_path,
                    "-filter_complex",
                    f"[1:a]adelay={delay_ms}|{delay_ms},volume={self.config.sfx_volume}[sfx];"
                    f"[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=0[out]",
                    "-map", "[out]",
                    "-ar", str(self.config.audio_sample_rate),
                    "-ac", "2",
                    next_path,
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if proc.returncode == 0:
                    current = next_path
                sfx_idx += 1

        if has_sfx and current != output_path:
            shutil.copy2(current, output_path)

        return has_sfx

    def _ducking_mix(
        self,
        voice_path: str,
        music_path: Optional[str],
        sfx_path: Optional[str],
        output_path: str,
        total_dur: float,
    ):
        """
        Final audio mix with music auto-ducking under narration.

        Uses FFmpeg sidechaincompress to duck music when voice is present.
        """
        inputs = ["-i", voice_path]
        filter_parts = []

        if music_path and os.path.exists(music_path):
            inputs.extend(["-i", music_path])
            # Sidechain compress: music ducks when voice is loud
            filter_parts.append(
                f"[1:a]volume={self.config.music_volume}[music];"
                f"[music][0:a]sidechaincompress="
                f"threshold=0.02:ratio=6:attack={self.config.duck_attack_ms}:"
                f"release={self.config.duck_release_ms}[ducked_music]"
            )
            mix_inputs = "[0:a][ducked_music]"
            mix_count = 2
        else:
            mix_inputs = "[0:a]"
            mix_count = 1

        if sfx_path and os.path.exists(sfx_path):
            sfx_input_idx = len(inputs) // 2  # approximate
            inputs.extend(["-i", sfx_path])
            sfx_label = f"[{sfx_input_idx + 1}:a]"

            if mix_count > 1:
                filter_parts.append(
                    f"{mix_inputs}{sfx_label}amix=inputs={mix_count + 1}:"
                    f"duration=first:dropout_transition=0[mixed]"
                )
            else:
                filter_parts.append(
                    f"{mix_inputs}{sfx_label}amix=inputs=2:"
                    f"duration=first:dropout_transition=0[mixed]"
                )
            final_label = "[mixed]"
        elif mix_count > 1:
            filter_parts.append(
                f"{mix_inputs}amix=inputs={mix_count}:"
                f"duration=first:dropout_transition=0[mixed]"
            )
            final_label = "[mixed]"
        else:
            final_label = "[0:a]"
            filter_parts = []

        # Loudness normalization to YouTube target
        if filter_parts:
            filtergraph = ";".join(filter_parts)
            # Add loudnorm
            filtergraph += f";{final_label}loudnorm=I={self.config.target_lufs}:TP=-1.5:LRA=11[final]"
            final_label = "[final]"
        else:
            filtergraph = f"[0:a]loudnorm=I={self.config.target_lufs}:TP=-1.5:LRA=11[final]"
            final_label = "[final]"

        cmd = [
            self.config.ffmpeg, "-y",
            *inputs,
            "-filter_complex", filtergraph,
            "-map", final_label,
            "-ar", str(self.config.audio_sample_rate),
            "-ac", "2",
            output_path,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            logger.warning(f"Ducking mix failed: {proc.stderr[:300]}")
            # Fallback: simple voice only
            shutil.copy2(voice_path, output_path)

    # ═══════════════════════════════════════════════════════
    # STEP 6: INTRO/OUTRO
    # ═══════════════════════════════════════════════════════

    def _insert_intro_outro(
        self,
        main_video: str,
        output_path: str,
        intro_path: Optional[str],
        outro_path: Optional[str],
    ):
        """Prepend intro and/or append outro to main video."""
        parts = []
        if intro_path and os.path.exists(intro_path):
            parts.append(intro_path)
        parts.append(main_video)
        if outro_path and os.path.exists(outro_path):
            parts.append(outro_path)

        if len(parts) == 1:
            shutil.copy2(parts[0], output_path)
            return

        # Create concat file
        concat_file = output_path + ".concat.txt"
        with open(concat_file, "w") as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")

        cmd = [
            self.config.ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        os.unlink(concat_file)

        if proc.returncode != 0:
            logger.warning(f"Intro/outro concat failed: {proc.stderr[:200]}")
            shutil.copy2(main_video, output_path)

    # ═══════════════════════════════════════════════════════
    # STEP 7: FINAL RENDER
    # ═══════════════════════════════════════════════════════

    def _final_render(
        self, video_path: str, audio_path: str, output_path: str
    ):
        """Mux video and audio into final H.264/AAC MP4."""
        cmd = [
            self.config.ffmpeg, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", self.config.video_codec,
            "-preset", self.config.video_preset,
            "-crf", str(self.config.video_crf),
            "-pix_fmt", self.config.pixel_format,
            "-c:a", self.config.audio_codec,
            "-b:a", self.config.audio_bitrate,
            "-ar", str(self.config.audio_sample_rate),
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise RuntimeError(f"Final render failed: {proc.stderr[:500]}")

    # ═══════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════

    def _get_duration(self, path: str) -> float:
        """Get media duration in seconds."""
        try:
            proc = subprocess.run(
                [self.config.ffprobe, "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(proc.stdout.strip())
        except Exception:
            return 0.0

    def _generate_black_clip(self, output_path: str, duration: float):
        """Generate a black video clip as placeholder."""
        cmd = [
            self.config.ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={self.config.width}x{self.config.height}:r={self.config.fps}",
            "-t", str(duration),
            "-c:v", self.config.video_codec,
            "-pix_fmt", self.config.pixel_format,
            "-an",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)

    def _trim_or_loop_audio(
        self, audio_path: str, output_path: str, target_dur: float
    ):
        """Trim or loop an audio file to match target duration."""
        src_dur = self._get_duration(audio_path)
        if src_dur <= 0:
            return

        if src_dur >= target_dur:
            # Trim with fade out
            cmd = [
                self.config.ffmpeg, "-y",
                "-i", audio_path,
                "-t", str(target_dur),
                "-af", f"afade=t=out:st={target_dur - 2}:d=2",
                "-ar", str(self.config.audio_sample_rate),
                output_path,
            ]
        else:
            # Loop
            loops = int(target_dur / src_dur) + 1
            cmd = [
                self.config.ffmpeg, "-y",
                "-stream_loop", str(loops),
                "-i", audio_path,
                "-t", str(target_dur),
                "-af", f"afade=t=out:st={target_dur - 2}:d=2",
                "-ar", str(self.config.audio_sample_rate),
                output_path,
            ]

        subprocess.run(cmd, capture_output=True, timeout=120)
