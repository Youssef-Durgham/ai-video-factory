"""
Phase 8 — Subtitle Styler: Generate .ass (Advanced SubStation Alpha) styled subtitles.

Converts SRT to .ass with font matching from the video's font_animation_config,
proper Arabic text rendering settings (RTL, encoding), and styled appearance
(outline, shadow, colors) matching the channel brand.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SubtitleStyler:
    """
    Converts SRT subtitles to styled .ass format matching the video's
    font configuration and channel branding.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.output_base = Path(config["settings"].get("output_dir", "output"))

    def generate_ass(self, job_id: str, srt_path: str) -> str:
        """
        Convert SRT to styled .ass subtitle file.

        Args:
            job_id: The job for font/style context.
            srt_path: Path to the source .srt file.

        Returns:
            Path to the generated .ass file.
        """
        import json

        if not srt_path or not Path(srt_path).exists():
            logger.warning(f"SRT file not found: {srt_path}")
            return ""

        job = self.db.get_job(job_id)
        font_config = json.loads(job.get("font_animation_config") or "{}")

        # Extract style parameters
        accent_font = font_config.get("accent_font", "Cairo")
        body_font = font_config.get("body_font", "Tajawal")
        accent_color = font_config.get("accent_color", "#e94560")
        bg_style = font_config.get("background_style", "box")

        # Parse accent color to ASS format (&HAABBGGRR)
        primary_color = self._hex_to_ass_color(accent_color)
        outline_color = "&H00000000"  # Black outline
        back_color = "&H80000000"     # Semi-transparent black background

        # Parse SRT cues
        cues = self._parse_srt(srt_path)
        if not cues:
            logger.warning(f"No cues parsed from {srt_path}")
            return ""

        # Build .ass content
        ass_path = Path(srt_path).with_suffix(".ass")

        # Determine resolution from pipeline config
        resolution = self.config["settings"]["pipeline"].get("image_resolution", [1920, 1080])
        play_res_x, play_res_y = resolution

        ass_content = self._build_ass(
            cues=cues,
            font_name=body_font,
            font_size=48,
            primary_color=primary_color,
            outline_color=outline_color,
            back_color=back_color,
            play_res_x=play_res_x,
            play_res_y=play_res_y,
            bg_style=bg_style,
        )

        ass_path.write_text(ass_content, encoding="utf-8-sig")
        logger.info(f"ASS subtitle generated: {ass_path} ({len(cues)} cues)")
        return str(ass_path)

    def _build_ass(
        self,
        cues: list[dict],
        font_name: str,
        font_size: int,
        primary_color: str,
        outline_color: str,
        back_color: str,
        play_res_x: int,
        play_res_y: int,
        bg_style: str,
    ) -> str:
        """Build complete .ass file content."""
        # Border style: 1=outline+shadow, 3=opaque box
        border_style = 3 if bg_style == "box" else 1
        outline_size = 2
        shadow_size = 1 if bg_style != "box" else 0
        margin_v = 50  # Bottom margin

        header = f"""[Script Info]
Title: AI Video Factory Subtitles
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},{back_color},-1,0,0,0,100,100,0,0,{border_style},{outline_size},{shadow_size},2,20,20,{margin_v},178

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Encoding 178 = Arabic

        events = []
        for cue in cues:
            start = self._srt_time_to_ass(cue["start"])
            end = self._srt_time_to_ass(cue["end"])
            # Replace newlines with \N for ASS format
            text = cue["text"].replace("\n", "\\N")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        return header + "\n".join(events) + "\n"

    def _parse_srt(self, srt_path: str) -> list[dict]:
        """Parse SRT file into list of cue dicts."""
        content = Path(srt_path).read_text(encoding="utf-8")
        cues = []
        blocks = re.split(r"\n\s*\n", content.strip())

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            # Line 1: index, Line 2: timestamps, Line 3+: text
            time_match = re.match(
                r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
                lines[1],
            )
            if not time_match:
                continue

            cues.append({
                "start": time_match.group(1),
                "end": time_match.group(2),
                "text": "\n".join(lines[2:]),
            })

        return cues

    @staticmethod
    def _srt_time_to_ass(srt_time: str) -> str:
        """Convert SRT timestamp (HH:MM:SS,mmm) to ASS (H:MM:SS.cc)."""
        parts = srt_time.replace(",", ".").split(":")
        hours = int(parts[0])
        minutes = parts[1]
        sec_ms = parts[2]  # SS.mmm
        sec, ms = sec_ms.split(".")
        centisec = int(ms[:2])  # ASS uses centiseconds
        return f"{hours}:{minutes}:{sec}.{centisec:02d}"

    @staticmethod
    def _hex_to_ass_color(hex_color: str) -> str:
        """
        Convert hex color (#RRGGBB) to ASS color format (&H00BBGGRR).
        ASS uses BGR order with alpha prefix.
        """
        hex_color = hex_color.lstrip("#")
        r = hex_color[0:2]
        g = hex_color[2:4]
        b = hex_color[4:6]
        return f"&H00{b}{g}{r}"
