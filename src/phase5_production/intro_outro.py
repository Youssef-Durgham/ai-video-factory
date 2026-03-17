"""
Phase 5 — Dynamic Intro/Outro Engine.

Generates intro and outro video segments that adapt to the video's
content type (font_category). Uses PyCairo for text rendering and
FFmpeg for final composition.

Intro variants per FontCategory:
  formal_news  → Clean news broadcast open
  dramatic     → Dark reveal with particles
  historical   → Parchment/aged paper unfold
  modern_tech  → Digital grid/HUD glitch-in
  islamic      → Geometric arabesque pattern
  military     → Tactical map zoom
  editorial    → Minimal typography
  storytelling → Warm cinematic fade

Outro: Universal subscribe CTA + end screen zones, styled per category.
"""

import json
import logging
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# INTRO TEMPLATES
# ════════════════════════════════════════════════════════════════

@dataclass
class IntroTemplate:
    """Template configuration for an intro variant."""
    style: str
    description: str
    duration_sec: float
    bg_color: tuple[float, float, float, float]  # RGBA 0-1
    text_color: tuple[float, float, float, float]
    accent_color: tuple[float, float, float, float]
    animation: str               # animation type key
    music_sting: str = ""        # path to pre-made audio sting
    font_name: str = "Cairo"
    font_size_title: int = 72
    font_size_subtitle: int = 36


INTRO_TEMPLATES: dict[str, IntroTemplate] = {
    "formal_news": IntroTemplate(
        style="formal_news",
        description="News broadcast open — logo + title slide + date",
        duration_sec=3.5,
        bg_color=(0.05, 0.05, 0.15, 1.0),
        text_color=(1.0, 1.0, 1.0, 1.0),
        accent_color=(0.8, 0.1, 0.1, 1.0),
        animation="slide_in",
        font_name="IBM Plex Sans Arabic",
        font_size_title=68,
    ),
    "dramatic": IntroTemplate(
        style="dramatic",
        description="Dark reveal — smoke/particles + logo from darkness",
        duration_sec=5.5,
        bg_color=(0.0, 0.0, 0.0, 1.0),
        text_color=(0.95, 0.95, 0.95, 1.0),
        accent_color=(0.9, 0.6, 0.1, 1.0),
        animation="fade_reveal",
        font_name="El Messiri",
        font_size_title=80,
    ),
    "historical": IntroTemplate(
        style="historical",
        description="Parchment/aged paper — title in classical font",
        duration_sec=4.5,
        bg_color=(0.85, 0.78, 0.65, 1.0),
        text_color=(0.2, 0.15, 0.1, 1.0),
        accent_color=(0.6, 0.3, 0.1, 1.0),
        animation="ink_write",
        font_name="Amiri",
        font_size_title=76,
    ),
    "modern_tech": IntroTemplate(
        style="modern_tech",
        description="Digital grid/HUD — logo glitch-in",
        duration_sec=3.5,
        bg_color=(0.02, 0.02, 0.08, 1.0),
        text_color=(0.0, 0.9, 0.7, 1.0),
        accent_color=(0.0, 0.6, 1.0, 1.0),
        animation="glitch_in",
        font_name="Readex Pro",
        font_size_title=64,
    ),
    "islamic": IntroTemplate(
        style="islamic",
        description="Geometric Islamic pattern → title reveal",
        duration_sec=4.5,
        bg_color=(0.05, 0.1, 0.15, 1.0),
        text_color=(0.95, 0.85, 0.5, 1.0),
        accent_color=(0.8, 0.65, 0.2, 1.0),
        animation="pattern_expand",
        font_name="Scheherazade New",
        font_size_title=76,
    ),
    "military": IntroTemplate(
        style="military",
        description="Tactical map → zoom to title, stencil font",
        duration_sec=3.5,
        bg_color=(0.1, 0.12, 0.1, 1.0),
        text_color=(0.85, 0.9, 0.85, 1.0),
        accent_color=(0.6, 0.8, 0.3, 1.0),
        animation="tactical_zoom",
        font_name="Cairo",
        font_size_title=68,
        font_size_subtitle=32,
    ),
    "editorial": IntroTemplate(
        style="editorial",
        description="Minimal typography — clean, modern",
        duration_sec=3.0,
        bg_color=(0.98, 0.98, 0.96, 1.0),
        text_color=(0.1, 0.1, 0.1, 1.0),
        accent_color=(0.2, 0.2, 0.2, 1.0),
        animation="minimal_type",
        font_name="Tajawal",
        font_size_title=60,
    ),
    "storytelling": IntroTemplate(
        style="storytelling",
        description="Warm cinematic fade — inviting title reveal",
        duration_sec=4.0,
        bg_color=(0.15, 0.08, 0.02, 1.0),
        text_color=(1.0, 0.92, 0.75, 1.0),
        accent_color=(0.9, 0.5, 0.1, 1.0),
        animation="warm_fade",
        font_name="Lemonada",
        font_size_title=72,
    ),
}


@dataclass
class OutroConfig:
    """Outro configuration — universal structure, styled per category."""
    duration_sec: float = 10.0
    subscribe_cta: str = "اشترك في القناة"
    end_screen_compatible: bool = True
    # YouTube end screen: last 20s, safe zones for 2 video recs + subscribe
    end_screen_start_sec: float = -20.0  # relative to video end


@dataclass
class IntroOutroResult:
    """Result of intro/outro generation."""
    intro_path: str = ""
    outro_path: str = ""
    intro_duration_sec: float = 0.0
    outro_duration_sec: float = 0.0
    font_category: str = ""
    success: bool = True
    error: str = ""


# ════════════════════════════════════════════════════════════════
# ENGINE
# ════════════════════════════════════════════════════════════════

class IntroOutroEngine:
    """
    Generate dynamic intro and outro segments for videos.

    Uses PyCairo for frame rendering and FFmpeg to encode the
    resulting PNG sequences into video segments with transparency.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.fps: int = self.config.get("fps", 24)
        self.width: int = self.config.get("width", 1920)
        self.height: int = self.config.get("height", 1080)
        self.ffmpeg: str = self.config.get("ffmpeg", "ffmpeg")
        self.fonts_dir: str = self.config.get(
            "fonts_dir",
            str(Path(__file__).parent / "fonts"),
        )
        self.brands_dir: str = self.config.get("brands_dir", "config/brands")

    # ─── Public API ───────────────────────────────────────────

    def generate(
        self,
        job_id: str,
        font_category: str,
        title: str,
        channel_id: str = "",
        subtitle: str = "",
        episode: str = "",
        date_str: str = "",
        output_dir: str = "",
    ) -> IntroOutroResult:
        """
        Generate intro and outro video files for a job.

        Args:
            job_id: Unique job identifier.
            font_category: Content type key (matches INTRO_TEMPLATES).
            title: Video title (Arabic).
            channel_id: Channel ID for brand kit lookup.
            subtitle: Optional subtitle text.
            episode: Episode number string (for series).
            date_str: Date string (for news-type content).
            output_dir: Directory to write output files.

        Returns:
            IntroOutroResult with paths to generated segments.
        """
        if not output_dir:
            output_dir = f"output/{job_id}"
        os.makedirs(output_dir, exist_ok=True)

        template = INTRO_TEMPLATES.get(font_category)
        if not template:
            logger.warning(
                "Unknown font_category '%s', falling back to 'editorial'",
                font_category,
            )
            template = INTRO_TEMPLATES["editorial"]

        result = IntroOutroResult(font_category=font_category)

        # Generate intro
        try:
            intro_path = os.path.join(output_dir, "intro.mp4")
            self._render_intro(
                template=template,
                title=title,
                subtitle=subtitle,
                date_str=date_str,
                episode=episode,
                output_path=intro_path,
                channel_id=channel_id,
            )
            result.intro_path = intro_path
            result.intro_duration_sec = template.duration_sec
        except Exception as e:
            logger.error("Intro generation failed: %s", e)
            result.success = False
            result.error = f"Intro failed: {e}"

        # Generate outro
        try:
            outro_path = os.path.join(output_dir, "outro.mp4")
            self._render_outro(
                template=template,
                title=title,
                channel_id=channel_id,
                output_path=outro_path,
            )
            result.outro_path = outro_path
            result.outro_duration_sec = 10.0
        except Exception as e:
            logger.error("Outro generation failed: %s", e)
            result.success = False
            result.error += f" Outro failed: {e}"

        return result

    # ─── Intro Rendering ──────────────────────────────────────

    def _render_intro(
        self,
        template: IntroTemplate,
        title: str,
        subtitle: str,
        date_str: str,
        episode: str,
        output_path: str,
        channel_id: str,
    ) -> None:
        """Render intro frames via PyCairo and encode with FFmpeg."""
        try:
            import cairo
        except ImportError:
            logger.error("PyCairo not installed — cannot render intro frames")
            raise RuntimeError("PyCairo required for intro/outro generation")

        total_frames = int(template.duration_sec * self.fps)

        with tempfile.TemporaryDirectory(prefix="intro_") as tmpdir:
            for frame_idx in range(total_frames):
                progress = frame_idx / max(total_frames - 1, 1)  # 0→1

                surface = cairo.ImageSurface(
                    cairo.FORMAT_ARGB32, self.width, self.height,
                )
                ctx = cairo.Context(surface)

                # Background
                ctx.set_source_rgba(*template.bg_color)
                ctx.paint()

                # Animate based on template type
                self._draw_intro_frame(
                    ctx, template, title, subtitle,
                    date_str, episode, progress,
                )

                # Brand logo overlay (if exists)
                self._overlay_logo(ctx, channel_id)

                frame_path = os.path.join(tmpdir, f"frame_{frame_idx:05d}.png")
                surface.write_to_png(frame_path)

            # Encode PNG sequence → MP4
            self._encode_sequence(tmpdir, output_path, template.duration_sec)

        logger.info("Intro rendered: %s (%.1fs)", output_path, template.duration_sec)

    def _draw_intro_frame(
        self,
        ctx,  # cairo.Context
        template: IntroTemplate,
        title: str,
        subtitle: str,
        date_str: str,
        episode: str,
        progress: float,
    ) -> None:
        """Draw a single intro frame based on animation type and progress."""
        # Common: compute alpha for fade-in
        alpha = min(1.0, progress * 3.0)  # fade in over first 1/3

        anim = template.animation

        if anim == "slide_in":
            # Title slides in from right
            offset_x = (1.0 - min(1.0, progress * 2.5)) * self.width * 0.3
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, offset_x=offset_x, alpha=alpha,
            )
            if date_str:
                self._draw_text_centered(
                    ctx, date_str, template.font_name, template.font_size_subtitle,
                    template.accent_color, y_offset=80, alpha=alpha * 0.8,
                )

        elif anim == "fade_reveal":
            # Slow fade from black
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, alpha=min(1.0, progress * 2.0),
            )

        elif anim == "ink_write":
            # Simulate ink writing: reveal characters progressively
            chars_shown = max(1, int(len(title) * min(1.0, progress * 1.8)))
            partial = title[:chars_shown]
            self._draw_text_centered(
                ctx, partial, template.font_name, template.font_size_title,
                template.text_color, alpha=1.0,
            )

        elif anim == "glitch_in":
            # Glitch: random offset that settles
            import random
            jitter = max(0, int((1.0 - progress) * 20))
            ox = random.randint(-jitter, jitter) if jitter else 0
            oy = random.randint(-jitter, jitter) if jitter else 0
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, offset_x=ox, y_offset=oy, alpha=alpha,
            )

        elif anim == "pattern_expand":
            # Draw geometric pattern lines expanding from center
            self._draw_geometric_pattern(ctx, template, progress)
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, alpha=min(1.0, max(0, (progress - 0.4) * 3)),
            )

        elif anim == "tactical_zoom":
            # Scale effect: text starts large, zooms to fit
            scale = 1.0 + (1.0 - min(1.0, progress * 2.5)) * 0.5
            ctx.save()
            ctx.translate(self.width / 2, self.height / 2)
            ctx.scale(scale, scale)
            ctx.translate(-self.width / 2, -self.height / 2)
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, alpha=alpha,
            )
            ctx.restore()

        elif anim == "minimal_type":
            # Simple centered text, fast fade
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, alpha=min(1.0, progress * 4.0),
            )

        elif anim == "warm_fade":
            # Warm glow: accent circle expanding behind text
            if progress < 0.6:
                r = progress / 0.6 * self.height * 0.3
                cx, cy = self.width / 2, self.height / 2
                import cairo
                grad = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
                grad.add_color_stop_rgba(0, *template.accent_color[:3], 0.3)
                grad.add_color_stop_rgba(1, *template.accent_color[:3], 0.0)
                ctx.set_source(grad)
                ctx.paint()
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color,
                alpha=min(1.0, max(0, (progress - 0.3) * 2.5)),
            )

        else:
            # Default: simple fade
            self._draw_text_centered(
                ctx, title, template.font_name, template.font_size_title,
                template.text_color, alpha=alpha,
            )

        # Subtitle (if present) — appears after main title
        if subtitle and progress > 0.5:
            sub_alpha = min(1.0, (progress - 0.5) * 4.0)
            self._draw_text_centered(
                ctx, subtitle, template.font_name, template.font_size_subtitle,
                template.accent_color, y_offset=100, alpha=sub_alpha,
            )

        # Episode number
        if episode and progress > 0.6:
            ep_alpha = min(1.0, (progress - 0.6) * 4.0)
            self._draw_text_centered(
                ctx, episode, template.font_name, 28,
                template.text_color, y_offset=150, alpha=ep_alpha * 0.7,
            )

    # ─── Outro Rendering ──────────────────────────────────────

    def _render_outro(
        self,
        template: IntroTemplate,
        title: str,
        channel_id: str,
        output_path: str,
    ) -> None:
        """Render outro frames: subscribe CTA + end screen zones."""
        try:
            import cairo
        except ImportError:
            raise RuntimeError("PyCairo required for intro/outro generation")

        outro_cfg = OutroConfig()
        total_frames = int(outro_cfg.duration_sec * self.fps)

        with tempfile.TemporaryDirectory(prefix="outro_") as tmpdir:
            for frame_idx in range(total_frames):
                progress = frame_idx / max(total_frames - 1, 1)

                surface = cairo.ImageSurface(
                    cairo.FORMAT_ARGB32, self.width, self.height,
                )
                ctx = cairo.Context(surface)

                # Background (same style as intro)
                ctx.set_source_rgba(*template.bg_color)
                ctx.paint()

                # Subscribe CTA
                cta_alpha = min(1.0, progress * 3.0)
                self._draw_text_centered(
                    ctx, outro_cfg.subscribe_cta,
                    template.font_name, 56,
                    template.accent_color, y_offset=-100, alpha=cta_alpha,
                )

                # End screen placeholder zones (2 video + subscribe)
                if progress > 0.2:
                    zone_alpha = min(1.0, (progress - 0.2) * 2.0) * 0.3
                    self._draw_end_screen_zones(ctx, template, zone_alpha)

                # Logo
                self._overlay_logo(ctx, channel_id)

                frame_path = os.path.join(tmpdir, f"frame_{frame_idx:05d}.png")
                surface.write_to_png(frame_path)

            self._encode_sequence(tmpdir, output_path, outro_cfg.duration_sec)

        logger.info("Outro rendered: %s (%.1fs)", output_path, outro_cfg.duration_sec)

    # ─── Drawing Helpers ──────────────────────────────────────

    def _draw_text_centered(
        self,
        ctx,
        text: str,
        font_name: str,
        font_size: int,
        color: tuple,
        offset_x: float = 0,
        y_offset: float = 0,
        alpha: float = 1.0,
    ) -> None:
        """Draw centered Arabic text using PyCairo."""
        try:
            ctx.select_font_face(font_name)
        except Exception:
            ctx.select_font_face("sans-serif")
        ctx.set_font_size(font_size)

        extents = ctx.text_extents(text)
        x = (self.width - extents.width) / 2 - extents.x_bearing + offset_x
        y = (self.height + extents.height) / 2 + y_offset

        r, g, b = color[:3]
        ctx.set_source_rgba(r, g, b, alpha)
        ctx.move_to(x, y)
        ctx.show_text(text)

    def _draw_geometric_pattern(
        self,
        ctx,
        template: IntroTemplate,
        progress: float,
    ) -> None:
        """Draw expanding Islamic geometric pattern from center."""
        cx, cy = self.width / 2, self.height / 2
        max_r = max(self.width, self.height) * 0.4
        current_r = max_r * min(1.0, progress * 1.5)

        r, g, b = template.accent_color[:3]
        line_alpha = 0.3 * min(1.0, progress * 2)
        ctx.set_source_rgba(r, g, b, line_alpha)
        ctx.set_line_width(1.5)

        # 8-fold symmetry lines
        for i in range(8):
            angle = i * math.pi / 4
            x1 = cx + math.cos(angle) * current_r
            y1 = cy + math.sin(angle) * current_r
            ctx.move_to(cx, cy)
            ctx.line_to(x1, y1)
        ctx.stroke()

        # Concentric octagonal rings
        for ring in range(1, 4):
            ring_r = current_r * ring / 4
            if ring_r < 10:
                continue
            ctx.new_path()
            for i in range(9):
                angle = i * math.pi / 4
                x = cx + math.cos(angle) * ring_r
                y = cy + math.sin(angle) * ring_r
                if i == 0:
                    ctx.move_to(x, y)
                else:
                    ctx.line_to(x, y)
            ctx.close_path()
            ctx.stroke()

    def _draw_end_screen_zones(
        self,
        ctx,
        template: IntroTemplate,
        alpha: float,
    ) -> None:
        """Draw placeholder rectangles for YouTube end screen elements."""
        r, g, b = template.accent_color[:3]
        ctx.set_source_rgba(r, g, b, alpha)

        # Left video recommendation zone
        ctx.rectangle(
            self.width * 0.05, self.height * 0.55,
            self.width * 0.28, self.height * 0.3,
        )
        ctx.fill()

        # Right video recommendation zone
        ctx.rectangle(
            self.width * 0.67, self.height * 0.55,
            self.width * 0.28, self.height * 0.3,
        )
        ctx.fill()

    def _overlay_logo(self, ctx, channel_id: str) -> None:
        """Overlay channel logo if brand kit exists."""
        if not channel_id:
            return
        logo_path = Path(self.brands_dir) / channel_id / "logo.png"
        if not logo_path.exists():
            return

        try:
            import cairo
            logo_surface = cairo.ImageSurface.create_from_png(str(logo_path))
            # Place logo top-right corner, scaled to 80px height
            logo_h = logo_surface.get_height()
            logo_w = logo_surface.get_width()
            scale = 80.0 / logo_h if logo_h > 0 else 1.0
            ctx.save()
            ctx.translate(self.width - logo_w * scale - 40, 40)
            ctx.scale(scale, scale)
            ctx.set_source_surface(logo_surface, 0, 0)
            ctx.paint_with_alpha(0.9)
            ctx.restore()
        except Exception as e:
            logger.debug("Logo overlay failed: %s", e)

    # ─── Encoding ─────────────────────────────────────────────

    def _encode_sequence(
        self,
        frames_dir: str,
        output_path: str,
        duration_sec: float,
    ) -> None:
        """Encode PNG frame sequence to MP4 via FFmpeg."""
        cmd = [
            self.ffmpeg, "-y",
            "-framerate", str(self.fps),
            "-i", os.path.join(frames_dir, "frame_%05d.png"),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-t", str(duration_sec),
            output_path,
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("FFmpeg encode failed: %s", result.stderr[-500:])
            raise RuntimeError(f"FFmpeg intro/outro encode failed: {result.returncode}")
