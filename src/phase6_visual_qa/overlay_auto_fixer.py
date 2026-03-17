"""
Phase 6C — Overlay Auto-Fixer.

Automated overlay fixes via FFmpeg. Applies corrections to text overlays
that failed QA checks without requiring full recomposition.

Fix types:
  - contrast: Add semi-transparent dark box behind text
  - position: Move text to safe zone
  - timing: Adjust overlay start/end timestamps
  - font_size: Increase/decrease font size
  - rtl_fix: Switch to known-good Arabic font (Noto Naskh Arabic)
"""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Safe zones (fraction of frame)
SAFE_ZONE_TOP = 0.08      # Avoid YouTube title bar
SAFE_ZONE_BOTTOM = 0.12   # Avoid YouTube controls
SAFE_ZONE_LEFT = 0.03
SAFE_ZONE_RIGHT = 0.03

# Default overlay params
DEFAULT_FONT = "Cairo-SemiBold"
RTL_SAFE_FONT = "NotoNaskhArabic-Regular"
DEFAULT_FONT_SIZE = 42
MIN_FONT_SIZE = 28
MAX_FONT_SIZE = 72
CONTRAST_BOX_OPACITY = 0.6
CONTRAST_BOX_PADDING = 10


class OverlayAutoFixer:
    """
    Apply automated FFmpeg-based fixes to text overlays that failed QA.
    Each fix type maps to specific FFmpeg filter adjustments.
    """

    def __init__(self, config: dict = None, ffmpeg_path: str = "ffmpeg"):
        self.config = config or {}
        self.ffmpeg = ffmpeg_path

    def apply_fixes(
        self,
        video_path: str,
        fix_instructions: list[dict],
        output_path: Optional[str] = None,
    ) -> str:
        """
        Apply overlay fixes to a video.

        Args:
            video_path: Path to the composed video with overlays.
            fix_instructions: List of fix dicts, each with:
                - scene_index (int)
                - fix_type (str): "contrast"|"position"|"timing"|"font_size"|"rtl_fix"
                - params (dict): fix-type-specific parameters
            output_path: Path for the fixed video (auto-generated if None).

        Returns:
            Path to the fixed video file, or empty string on failure.
        """
        if not fix_instructions:
            logger.info("No fixes to apply")
            return video_path

        video = Path(video_path)
        if not video.exists():
            logger.error(f"Video not found: {video_path}")
            return ""

        if output_path is None:
            stem = video.stem
            output_path = str(video.parent / f"{stem}_fixed{video.suffix}")

        logger.info(f"Applying {len(fix_instructions)} overlay fixes to {video.name}")

        # Group fixes by type for efficient processing
        fixes_by_type = {}
        for fix in fix_instructions:
            fix_type = fix.get("fix_type", "")
            if fix_type not in fixes_by_type:
                fixes_by_type[fix_type] = []
            fixes_by_type[fix_type].append(fix)

        # Build FFmpeg filter chain
        current_input = video_path
        temp_files = []

        try:
            for fix_type, fixes in fixes_by_type.items():
                temp_output = tempfile.mktemp(suffix=".mp4", prefix=f"fix_{fix_type}_")
                temp_files.append(temp_output)

                success = False
                if fix_type == "contrast":
                    success = self._fix_contrast(current_input, temp_output, fixes)
                elif fix_type == "position":
                    success = self._fix_position(current_input, temp_output, fixes)
                elif fix_type == "timing":
                    success = self._fix_timing(current_input, temp_output, fixes)
                elif fix_type == "font_size":
                    success = self._fix_font_size(current_input, temp_output, fixes)
                elif fix_type == "rtl_fix":
                    success = self._fix_rtl(current_input, temp_output, fixes)
                else:
                    logger.warning(f"Unknown fix type: {fix_type}")
                    continue

                if success and Path(temp_output).exists():
                    current_input = temp_output
                else:
                    logger.warning(f"Fix type '{fix_type}' failed, skipping")

            # Copy final result to output
            if current_input != video_path:
                shutil.copy2(current_input, output_path)
                logger.info(f"Fixed video saved to {output_path}")
                return output_path
            else:
                logger.warning("No fixes were successfully applied")
                return ""
        finally:
            # Cleanup temp files
            for tf in temp_files:
                try:
                    Path(tf).unlink(missing_ok=True)
                except Exception:
                    pass

    def _fix_contrast(self, input_path: str, output_path: str, fixes: list[dict]) -> bool:
        """
        Add semi-transparent dark box behind text overlays.
        Uses FFmpeg drawbox filter at overlay positions.
        """
        filter_parts = []
        for fix in fixes:
            params = fix.get("params", {})
            x = params.get("text_x", 0)
            y = params.get("text_y", 0)
            w = params.get("text_width", 400)
            h = params.get("text_height", 60)
            start_time = params.get("start_time", 0)
            end_time = params.get("end_time", 0)
            opacity = params.get("opacity", CONTRAST_BOX_OPACITY)

            # Add padding
            bx = max(0, x - CONTRAST_BOX_PADDING)
            by = max(0, y - CONTRAST_BOX_PADDING)
            bw = w + CONTRAST_BOX_PADDING * 2
            bh = h + CONTRAST_BOX_PADDING * 2

            # drawbox with enable between timestamps
            alpha_hex = hex(int(opacity * 255))[2:].zfill(2)
            enable = f"between(t,{start_time},{end_time})" if end_time > 0 else "1"
            filter_parts.append(
                f"drawbox=x={bx}:y={by}:w={bw}:h={bh}:"
                f"color=black@{opacity}:t=fill:enable='{enable}'"
            )

        if not filter_parts:
            return False

        filter_chain = ",".join(filter_parts)
        return self._run_ffmpeg(input_path, output_path, filter_chain)

    def _fix_position(self, input_path: str, output_path: str, fixes: list[dict]) -> bool:
        """
        Reposition text overlays to safe zones.
        Requires re-rendering text overlays with adjusted coordinates.
        """
        # This requires the original overlay specs to re-render.
        # We use the drawtext filter with corrected positions.
        filter_parts = []
        for fix in fixes:
            params = fix.get("params", {})
            text = params.get("text", "")
            if not text:
                continue

            # Calculate safe position
            new_x, new_y = self._calculate_safe_position(
                params.get("original_x", 0),
                params.get("original_y", 0),
                params.get("frame_width", 1920),
                params.get("frame_height", 1080),
            )

            font = params.get("font", DEFAULT_FONT)
            font_size = params.get("font_size", DEFAULT_FONT_SIZE)
            color = params.get("color", "white")
            start_time = params.get("start_time", 0)
            end_time = params.get("end_time", 0)

            enable = f"between(t,{start_time},{end_time})" if end_time > 0 else "1"

            # Escape text for FFmpeg
            escaped_text = text.replace("'", "'\\''").replace(":", "\\:")
            filter_parts.append(
                f"drawtext=text='{escaped_text}':x={new_x}:y={new_y}:"
                f"fontfile={font}:fontsize={font_size}:fontcolor={color}:"
                f"enable='{enable}'"
            )

        if not filter_parts:
            return False

        filter_chain = ",".join(filter_parts)
        return self._run_ffmpeg(input_path, output_path, filter_chain)

    def _fix_timing(self, input_path: str, output_path: str, fixes: list[dict]) -> bool:
        """
        Adjust overlay timing by re-rendering with corrected timestamps.
        This is a re-compose operation with adjusted subtitle/overlay timing.
        """
        # For timing fixes, we generate an ASS subtitle file with corrected times
        # and burn it into the video
        ass_content = self._generate_ass_from_fixes(fixes)
        if not ass_content:
            return False

        ass_path = tempfile.mktemp(suffix=".ass", prefix="timing_fix_")
        try:
            Path(ass_path).write_text(ass_content, encoding="utf-8")
            filter_chain = f"ass={ass_path}"
            return self._run_ffmpeg(input_path, output_path, filter_chain)
        finally:
            Path(ass_path).unlink(missing_ok=True)

    def _fix_font_size(self, input_path: str, output_path: str, fixes: list[dict]) -> bool:
        """Adjust font size for overlays that are too small or too large."""
        filter_parts = []
        for fix in fixes:
            params = fix.get("params", {})
            text = params.get("text", "")
            if not text:
                continue

            current_size = params.get("current_font_size", DEFAULT_FONT_SIZE)
            adjustment = params.get("adjustment", "increase")

            if adjustment == "increase":
                new_size = min(current_size + 8, MAX_FONT_SIZE)
            else:
                new_size = max(current_size - 6, MIN_FONT_SIZE)

            x = params.get("x", 100)
            y = params.get("y", 100)
            font = params.get("font", DEFAULT_FONT)
            color = params.get("color", "white")
            start_time = params.get("start_time", 0)
            end_time = params.get("end_time", 0)

            enable = f"between(t,{start_time},{end_time})" if end_time > 0 else "1"
            escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

            filter_parts.append(
                f"drawtext=text='{escaped_text}':x={x}:y={y}:"
                f"fontfile={font}:fontsize={new_size}:fontcolor={color}:"
                f"enable='{enable}'"
            )

        if not filter_parts:
            return False

        filter_chain = ",".join(filter_parts)
        return self._run_ffmpeg(input_path, output_path, filter_chain)

    def _fix_rtl(self, input_path: str, output_path: str, fixes: list[dict]) -> bool:
        """
        Fix RTL rendering issues by switching to a known-good Arabic font.
        Uses Noto Naskh Arabic which has proper RTL shaping support.
        """
        filter_parts = []
        for fix in fixes:
            params = fix.get("params", {})
            text = params.get("text", "")
            if not text:
                continue

            x = params.get("x", 100)
            y = params.get("y", 100)
            font_size = params.get("font_size", DEFAULT_FONT_SIZE)
            color = params.get("color", "white")
            start_time = params.get("start_time", 0)
            end_time = params.get("end_time", 0)

            enable = f"between(t,{start_time},{end_time})" if end_time > 0 else "1"
            escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

            # Use RTL-safe font with text_shaping enabled
            filter_parts.append(
                f"drawtext=text='{escaped_text}':x={x}:y={y}:"
                f"fontfile={RTL_SAFE_FONT}:fontsize={font_size}:"
                f"fontcolor={color}:text_shaping=1:"
                f"enable='{enable}'"
            )

        if not filter_parts:
            return False

        filter_chain = ",".join(filter_parts)
        return self._run_ffmpeg(input_path, output_path, filter_chain)

    # ═══ Helper Methods ═══════════════════════════════════════

    def _run_ffmpeg(self, input_path: str, output_path: str, video_filter: str) -> bool:
        """Run FFmpeg with a video filter chain."""
        cmd = [
            self.ffmpeg, "-y",
            "-i", input_path,
            "-vf", video_filter,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr[:500]}")
                return False
            if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                return True
            return False
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timed out")
            return False
        except Exception as e:
            logger.error(f"FFmpeg execution error: {e}")
            return False

    def _calculate_safe_position(
        self,
        original_x: int,
        original_y: int,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int, int]:
        """Calculate safe text position within the safe zone."""
        min_x = int(frame_width * SAFE_ZONE_LEFT)
        max_x = int(frame_width * (1 - SAFE_ZONE_RIGHT))
        min_y = int(frame_height * SAFE_ZONE_TOP)
        max_y = int(frame_height * (1 - SAFE_ZONE_BOTTOM))

        safe_x = max(min_x, min(original_x, max_x))
        safe_y = max(min_y, min(original_y, max_y))

        return safe_x, safe_y

    def _generate_ass_from_fixes(self, fixes: list[dict]) -> str:
        """Generate ASS subtitle content from timing fixes."""
        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\n"
            "PlayResY: 1080\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{RTL_SAFE_FONT},{DEFAULT_FONT_SIZE},"
            "&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        events = []
        for fix in fixes:
            params = fix.get("params", {})
            text = params.get("text", "")
            start = params.get("corrected_start", params.get("start_time", 0))
            end = params.get("corrected_end", params.get("end_time", 0))

            if not text or end <= start:
                continue

            start_ass = self._seconds_to_ass_time(start)
            end_ass = self._seconds_to_ass_time(end)
            events.append(
                f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}"
            )

        if not events:
            return ""

        return header + "\n".join(events) + "\n"

    @staticmethod
    def _seconds_to_ass_time(seconds: float) -> str:
        """Convert seconds to ASS timestamp format (H:MM:SS.CC)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        cs = int((s % 1) * 100)
        return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"
