"""
Phase 5 — Text Animator: PyCairo + HarfBuzz Arabic Text Rendering.

Renders animated Arabic text overlays as transparent video layers,
then composites with FFmpeg. Handles:
  • Proper RTL text with tashkeel (diacritics)
  • HarfBuzz shaping for Arabic ligatures and marks
  • Multiple animation styles (fade, slide, typewriter, blur, glitch)
  • Easing functions for smooth motion
  • Frame-by-frame PNG → ProRes 4444 transparent overlay

THIS IS THE CRITICAL FILE for Arabic text rendering.
FFmpeg drawtext is NOT used — too limited for Arabic.
"""

import math
import os
import random
import shutil
import struct
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# ANIMATION STYLES
# ════════════════════════════════════════════════════════════════

class FontCategory(str, Enum):
    """Font category — selected per video based on topic/mood."""
    FORMAL_NEWS     = "formal_news"
    DRAMATIC        = "dramatic"
    HISTORICAL      = "historical"
    MODERN_TECH     = "modern_tech"
    ISLAMIC         = "islamic"
    MILITARY        = "military"
    EDITORIAL       = "editorial"
    STORYTELLING    = "storytelling"


# Font library — curated Arabic fonts (all free/open-source)
FONT_LIBRARY = {
    FontCategory.FORMAL_NEWS: {
        "primary": "IBM Plex Sans Arabic",
        "accent": "Noto Naskh Arabic",
        "fallback": "Cairo",
        "weight_range": [400, 700],
    },
    FontCategory.DRAMATIC: {
        "primary": "Aref Ruqaa",
        "accent": "Lemonada",
        "fallback": "Tajawal",
        "weight_range": [700, 900],
    },
    FontCategory.HISTORICAL: {
        "primary": "Amiri",
        "accent": "Scheherazade New",
        "fallback": "Noto Naskh Arabic",
        "weight_range": [400, 700],
    },
    FontCategory.MODERN_TECH: {
        "primary": "IBM Plex Sans Arabic",
        "accent": "Readex Pro",
        "fallback": "Cairo",
        "weight_range": [300, 600],
    },
    FontCategory.ISLAMIC: {
        "primary": "Scheherazade New",
        "accent": "Amiri",
        "fallback": "Amiri",
        "weight_range": [400, 700],
    },
    FontCategory.MILITARY: {
        "primary": "Cairo",
        "accent": "El Messiri",
        "fallback": "Tajawal",
        "weight_range": [600, 900],
    },
    FontCategory.EDITORIAL: {
        "primary": "Tajawal",
        "accent": "Cairo",
        "fallback": "Noto Sans Arabic",
        "weight_range": [400, 700],
    },
    FontCategory.STORYTELLING: {
        "primary": "Lemonada",
        "accent": "Aref Ruqaa",
        "fallback": "Cairo",
        "weight_range": [400, 700],
    },
}

# Animation presets per font category
ANIMATION_PRESETS = {
    FontCategory.FORMAL_NEWS:  {"style": "fade_in", "duration": 0.5, "easing": "ease_out"},
    FontCategory.DRAMATIC:     {"style": "slide_right", "duration": 0.7, "easing": "ease_in_out"},
    FontCategory.HISTORICAL:   {"style": "fade_in", "duration": 0.8, "easing": "ease_out"},
    FontCategory.MODERN_TECH:  {"style": "typewriter", "duration": 0.6, "easing": "linear"},
    FontCategory.ISLAMIC:      {"style": "fade_in", "duration": 1.0, "easing": "ease_out"},
    FontCategory.MILITARY:     {"style": "glitch", "duration": 0.4, "easing": "linear"},
    FontCategory.EDITORIAL:    {"style": "slide_right", "duration": 0.5, "easing": "ease_out"},
    FontCategory.STORYTELLING: {"style": "fade_in", "duration": 0.7, "easing": "ease_in_out"},
}


class AnimationStyle(str, Enum):
    FADE_IN       = "fade_in"
    FADE_OUT      = "fade_out"
    SLIDE_RIGHT   = "slide_right"    # RTL natural direction
    SLIDE_LEFT    = "slide_left"
    SLIDE_UP      = "slide_up"
    SCALE_UP      = "scale_up"
    BLUR_REVEAL   = "blur_reveal"
    GLITCH_IN     = "glitch_in"
    TYPEWRITER    = "typewriter"      # Character-by-character RTL
    WORD_BY_WORD  = "word_by_word"
    LETTER_CASCADE = "letter_cascade"
    NONE          = "none"


# ════════════════════════════════════════════════════════════════
# EASING FUNCTIONS
# ════════════════════════════════════════════════════════════════

def ease_linear(t: float) -> float:
    return t

def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3

def ease_out_expo(t: float) -> float:
    return 1 - 2 ** (-10 * t) if t > 0 else 0.0

def ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2

def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1) / 2

def ease_out_quart(t: float) -> float:
    return 1 - (1 - t) ** 4

def ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * ((t - 1) ** 3) + c1 * ((t - 1) ** 2)


EASING_MAP: dict[str, Callable] = {
    "linear":           ease_linear,
    "ease_out_cubic":   ease_out_cubic,
    "ease_out_expo":    ease_out_expo,
    "ease_in_out_quad": ease_in_out_quad,
    "ease_in_out_sine": ease_in_out_sine,
    "ease_out_quart":   ease_out_quart,
    "ease_out_back":    ease_out_back,
}


# ════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════

@dataclass
class TextOverlayConfig:
    """Configuration for a single text overlay."""
    text: str = ""
    font_path: str = ""                  # Path to .ttf/.otf
    font_size: int = 56
    font_weight: int = 400               # 400=regular, 700=bold
    text_color: tuple = (255, 255, 255, 255)  # RGBA
    shadow_color: tuple = (0, 0, 0, 160)
    shadow_offset: tuple = (3, 3)
    outline_color: tuple = (0, 0, 0, 200)
    outline_width: float = 2.0
    bg_style: str = "none"               # "none"|"box"|"gradient"|"blur"
    bg_color: tuple = (0, 0, 0, 128)     # RGBA for box background
    bg_padding: int = 20
    bg_corner_radius: float = 8.0
    position: str = "bottom_center"      # position preset
    margin_x: int = 80
    margin_y: int = 60
    entry_animation: str = "fade_in"
    exit_animation: str = "fade_out"
    entry_duration_ms: int = 500
    exit_duration_ms: int = 300
    easing: str = "ease_out_cubic"
    # Position presets → (x_ratio, y_ratio) of frame
    # Actual pixel positions computed at render time


POSITION_MAP: dict[str, tuple[float, float]] = {
    "top_left":      (0.05, 0.08),
    "top_center":    (0.5,  0.08),
    "top_right":     (0.95, 0.08),
    "center":        (0.5,  0.5),
    "center_left":   (0.05, 0.5),
    "center_right":  (0.95, 0.5),
    "bottom_left":   (0.05, 0.85),
    "bottom_center": (0.5,  0.85),
    "bottom_right":  (0.95, 0.85),
    "lower_third":   (0.5,  0.78),
}


# ════════════════════════════════════════════════════════════════
# HARFBUZZ + PYCAIRO ARABIC TEXT RENDERER
# ════════════════════════════════════════════════════════════════

class ArabicTextRenderer:
    """
    Renders Arabic text with proper RTL, tashkeel (diacritics),
    and ligatures using HarfBuzz for shaping + PyCairo for drawing.

    This is the core rendering engine — every animation style
    calls this to render individual frames.
    """

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        """Verify PyCairo and HarfBuzz are available."""
        try:
            import cairo
        except ImportError:
            raise ImportError(
                "PyCairo not installed. Install with: pip install pycairo"
            )
        try:
            import gi
            gi.require_version('HarfBuzz', '0.0')
            gi.require_version('PangoCairo', '1.0')
            gi.require_version('Pango', '1.0')
            from gi.repository import HarfBuzz, Pango, PangoCairo
            self._use_pango = True
        except (ImportError, ValueError):
            logger.warning(
                "GObject introspection (gi) not available for HarfBuzz/Pango. "
                "Falling back to basic PyCairo text rendering. "
                "Arabic shaping may be incomplete."
            )
            self._use_pango = False

    def render_frame(
        self,
        text: str,
        config: TextOverlayConfig,
        width: int,
        height: int,
        alpha: float = 1.0,
        x_offset: float = 0.0,
        y_offset: float = 0.0,
        scale: float = 1.0,
        blur_radius: float = 0.0,
        visible_chars: Optional[int] = None,
        glitch_intensity: float = 0.0,
    ) -> bytes:
        """
        Render a single frame of text overlay as RGBA PNG bytes.

        Args:
            text: Arabic text to render.
            config: Styling configuration.
            width, height: Frame dimensions (usually 1920x1080).
            alpha: Overall opacity (0.0–1.0).
            x_offset: Horizontal offset from base position (pixels).
            y_offset: Vertical offset from base position (pixels).
            scale: Scale factor (1.0 = normal).
            blur_radius: Gaussian blur radius (0 = sharp).
            visible_chars: For typewriter effect — how many chars to show.
            glitch_intensity: For glitch effect (0.0–1.0).

        Returns:
            PNG image bytes (RGBA, with transparency).
        """
        import cairo

        # Create transparent surface
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)

        # Apply global alpha
        if alpha < 1.0:
            ctx.push_group()

        # Compute base position
        pos_ratios = POSITION_MAP.get(config.position, (0.5, 0.85))
        base_x = int(pos_ratios[0] * width) + x_offset
        base_y = int(pos_ratios[1] * height) + y_offset

        # Handle typewriter: truncate text
        display_text = text
        if visible_chars is not None and visible_chars < len(text):
            display_text = text[:visible_chars]

        # Measure text
        text_w, text_h = self._measure_text(
            ctx, display_text, config, width
        )

        # Apply scale
        if scale != 1.0:
            ctx.save()
            ctx.translate(base_x, base_y)
            ctx.scale(scale, scale)
            ctx.translate(-base_x, -base_y)

        # Draw background box
        if config.bg_style == "box" and display_text:
            self._draw_background_box(
                ctx, base_x, base_y, text_w, text_h, config
            )

        # Draw text shadow
        if config.shadow_color[3] > 0 and display_text:
            self._draw_text(
                ctx, display_text, config,
                base_x + config.shadow_offset[0],
                base_y + config.shadow_offset[1],
                color=config.shadow_color,
                width_limit=width,
            )

        # Draw text outline
        if config.outline_width > 0 and display_text:
            self._draw_text_outline(
                ctx, display_text, config, base_x, base_y, width
            )

        # Draw main text
        if display_text:
            self._draw_text(
                ctx, display_text, config, base_x, base_y,
                color=config.text_color, width_limit=width,
            )

        if scale != 1.0:
            ctx.restore()

        # Apply alpha
        if alpha < 1.0:
            ctx.pop_group_to_source()
            ctx.paint_with_alpha(alpha)

        # Apply glitch effect
        if glitch_intensity > 0:
            surface = self._apply_glitch(surface, glitch_intensity)

        # Apply blur
        if blur_radius > 0:
            surface = self._apply_blur(surface, blur_radius)

        # Export as PNG bytes
        buf = io.BytesIO()
        surface.write_to_png(buf)
        return buf.getvalue()

    # ─── Text Drawing (PyCairo + Pango/HarfBuzz) ──────────

    def _draw_text(
        self, ctx, text: str, config: TextOverlayConfig,
        x: float, y: float, color: tuple, width_limit: int,
    ):
        """Draw shaped Arabic text using Pango (preferred) or fallback."""
        if self._use_pango:
            self._draw_text_pango(ctx, text, config, x, y, color, width_limit)
        else:
            self._draw_text_basic(ctx, text, config, x, y, color)

    def _draw_text_pango(
        self, ctx, text: str, config: TextOverlayConfig,
        x: float, y: float, color: tuple, width_limit: int,
    ):
        """
        Draw Arabic text using Pango + HarfBuzz.
        Pango handles: RTL, tashkeel, ligatures, line breaking.
        HarfBuzz runs under the hood for glyph shaping.
        """
        from gi.repository import Pango, PangoCairo

        layout = PangoCairo.create_layout(ctx)

        # Font description
        font_name = Path(config.font_path).stem.replace("-", " ") if config.font_path else "Noto Naskh Arabic"
        font_desc = Pango.FontDescription.from_string(
            f"{font_name} {config.font_size}"
        )
        if config.font_weight >= 700:
            font_desc.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(font_desc)

        # RTL + Arabic
        layout.set_auto_dir(True)
        layout.set_alignment(Pango.Alignment.RIGHT)  # RTL default

        # Width constraint
        layout.set_width(int(min(width_limit * 0.8, 1600) * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)

        layout.set_text(text, -1)

        # Get text extents for centering
        ink_rect, logical_rect = layout.get_pixel_extents()
        text_w = logical_rect.width
        text_h = logical_rect.height

        # Center text at position
        draw_x = x - text_w / 2
        draw_y = y - text_h / 2

        ctx.move_to(draw_x, draw_y)

        # Set color
        r, g, b, a = [c / 255.0 for c in color]
        ctx.set_source_rgba(r, g, b, a)

        PangoCairo.show_layout(ctx, layout)

    def _draw_text_basic(
        self, ctx, text: str, config: TextOverlayConfig,
        x: float, y: float, color: tuple,
    ):
        """
        Fallback: basic PyCairo text rendering.
        Less accurate for Arabic but works without Pango.
        """
        import cairo

        ctx.select_font_face(
            "Noto Naskh Arabic",
            cairo.FONT_SLANT_NORMAL,
            cairo.FONT_WEIGHT_BOLD if config.font_weight >= 700 else cairo.FONT_WEIGHT_NORMAL,
        )
        ctx.set_font_size(config.font_size)

        # Try to use the font file directly
        if config.font_path and Path(config.font_path).exists():
            try:
                face = cairo.ToyFontFace(
                    Path(config.font_path).stem.replace("-", " "),
                    cairo.FONT_SLANT_NORMAL,
                    cairo.FONT_WEIGHT_BOLD if config.font_weight >= 700 else cairo.FONT_WEIGHT_NORMAL,
                )
                ctx.set_font_face(face)
            except Exception:
                pass

        # Measure
        extents = ctx.text_extents(text)
        draw_x = x - extents.width / 2 - extents.x_bearing
        draw_y = y - extents.height / 2 - extents.y_bearing

        r, g, b, a = [c / 255.0 for c in color]
        ctx.set_source_rgba(r, g, b, a)
        ctx.move_to(draw_x, draw_y)
        ctx.show_text(text)

    def _draw_text_outline(
        self, ctx, text: str, config: TextOverlayConfig,
        x: float, y: float, width_limit: int,
    ):
        """Draw text outline (stroke) for readability."""
        if self._use_pango:
            from gi.repository import Pango, PangoCairo

            layout = PangoCairo.create_layout(ctx)
            font_name = Path(config.font_path).stem.replace("-", " ") if config.font_path else "Noto Naskh Arabic"
            font_desc = Pango.FontDescription.from_string(f"{font_name} {config.font_size}")
            if config.font_weight >= 700:
                font_desc.set_weight(Pango.Weight.BOLD)
            layout.set_font_description(font_desc)
            layout.set_auto_dir(True)
            layout.set_alignment(Pango.Alignment.RIGHT)
            layout.set_width(int(min(width_limit * 0.8, 1600) * Pango.SCALE))
            layout.set_text(text, -1)

            ink_rect, logical_rect = layout.get_pixel_extents()
            draw_x = x - logical_rect.width / 2
            draw_y = y - logical_rect.height / 2

            ctx.move_to(draw_x, draw_y)

            r, g, b, a = [c / 255.0 for c in config.outline_color]
            ctx.set_source_rgba(r, g, b, a)
            ctx.set_line_width(config.outline_width * 2)

            PangoCairo.layout_path(ctx, layout)
            ctx.stroke()

    def _measure_text(
        self, ctx, text: str, config: TextOverlayConfig, width_limit: int,
    ) -> tuple[float, float]:
        """Measure text dimensions."""
        if not text:
            return (0, 0)

        if self._use_pango:
            from gi.repository import Pango, PangoCairo
            layout = PangoCairo.create_layout(ctx)
            font_name = Path(config.font_path).stem.replace("-", " ") if config.font_path else "Noto Naskh Arabic"
            font_desc = Pango.FontDescription.from_string(f"{font_name} {config.font_size}")
            layout.set_font_description(font_desc)
            layout.set_width(int(min(width_limit * 0.8, 1600) * Pango.SCALE))
            layout.set_text(text, -1)
            _, logical = layout.get_pixel_extents()
            return (logical.width, logical.height)
        else:
            ctx.set_font_size(config.font_size)
            extents = ctx.text_extents(text)
            return (extents.width, extents.height)

    def _draw_background_box(
        self, ctx, x: float, y: float,
        text_w: float, text_h: float,
        config: TextOverlayConfig,
    ):
        """Draw semi-transparent background box behind text."""
        pad = config.bg_padding
        r = config.bg_corner_radius
        bx = x - text_w / 2 - pad
        by = y - text_h / 2 - pad
        bw = text_w + pad * 2
        bh = text_h + pad * 2

        # Rounded rectangle
        ctx.new_path()
        ctx.arc(bx + bw - r, by + r, r, -math.pi / 2, 0)
        ctx.arc(bx + bw - r, by + bh - r, r, 0, math.pi / 2)
        ctx.arc(bx + r, by + bh - r, r, math.pi / 2, math.pi)
        ctx.arc(bx + r, by + r, r, math.pi, 3 * math.pi / 2)
        ctx.close_path()

        cr, cg, cb, ca = [c / 255.0 for c in config.bg_color]
        ctx.set_source_rgba(cr, cg, cb, ca)
        ctx.fill()

    # ─── Effects ───────────────────────────────────────────

    def _apply_glitch(self, surface, intensity: float):
        """Apply digital glitch effect to surface."""
        import cairo

        w = surface.get_width()
        h = surface.get_height()
        data = bytearray(surface.get_data())

        stride = surface.get_stride()
        num_slices = max(1, int(intensity * 10))

        for _ in range(num_slices):
            y_start = random.randint(0, h - 5)
            slice_h = random.randint(2, max(3, int(intensity * 20)))
            x_shift = random.randint(-int(intensity * 30), int(intensity * 30))

            for y in range(y_start, min(y_start + slice_h, h)):
                row_start = y * stride
                row = data[row_start:row_start + w * 4]
                if x_shift > 0:
                    shifted = bytes(x_shift * 4) + row[:len(row) - x_shift * 4]
                elif x_shift < 0:
                    shifted = row[-x_shift * 4:] + bytes(-x_shift * 4)
                else:
                    shifted = row
                data[row_start:row_start + len(shifted)] = shifted[:w * 4]

        new_surface = cairo.ImageSurface.create_for_data(
            data, cairo.FORMAT_ARGB32, w, h, stride
        )
        return new_surface

    def _apply_blur(self, surface, radius: float):
        """Apply approximate Gaussian blur using box blur iterations."""
        # For production, use Pillow's GaussianBlur as it's much simpler
        try:
            from PIL import Image, ImageFilter
            import cairo

            w = surface.get_width()
            h = surface.get_height()

            # Cairo ARGB32 → PIL RGBA
            buf = surface.get_data()
            img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRa", 0, 1)
            img = img.filter(ImageFilter.GaussianBlur(radius=radius))

            # Back to cairo
            new_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            ctx = cairo.Context(new_surface)
            # Convert PIL → cairo
            pil_data = img.tobytes("raw", "BGRa")
            src = cairo.ImageSurface.create_for_data(
                bytearray(pil_data), cairo.FORMAT_ARGB32, w, h
            )
            ctx.set_source_surface(src)
            ctx.paint()
            return new_surface
        except Exception:
            return surface  # No blur on error


# ════════════════════════════════════════════════════════════════
# TEXT ANIMATION RENDERER — orchestrates frame generation
# ════════════════════════════════════════════════════════════════

import io


class TextAnimationRenderer:
    """
    Renders animated Arabic text overlays as transparent video files.

    Pipeline:
    1. Calculate frame count (entry + hold + exit)
    2. For each frame: compute animation state → render via ArabicTextRenderer
    3. Save frames as PNGs in temp directory
    4. Encode PNGs → ProRes 4444 transparent overlay (FFmpeg)
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg = ffmpeg_path
        self.renderer = ArabicTextRenderer()

    def render_overlay(
        self,
        text: str,
        config: TextOverlayConfig,
        duration_sec: float,
        fps: int = 24,
        width: int = 1920,
        height: int = 1080,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Render animated text overlay as transparent video.

        Args:
            text: Arabic text to animate.
            config: Text styling + animation config.
            duration_sec: Total display duration.
            fps: Frame rate.
            width, height: Video resolution.
            output_path: Output .mov path (ProRes 4444).

        Returns:
            Path to transparent overlay video, or None on failure.
        """
        if not text or not text.strip():
            return None

        entry_frames = max(1, int(config.entry_duration_ms / 1000 * fps))
        exit_frames = max(1, int(config.exit_duration_ms / 1000 * fps))
        total_frames = max(int(duration_sec * fps), entry_frames + exit_frames + 1)
        hold_frames = total_frames - entry_frames - exit_frames

        easing_fn = EASING_MAP.get(config.easing, ease_out_cubic)

        tmp_dir = tempfile.mkdtemp(prefix="text_anim_")
        try:
            # Render frames
            for i in range(total_frames):
                # Determine phase and progress
                if i < entry_frames:
                    phase = "entry"
                    raw_progress = i / max(entry_frames - 1, 1)
                    progress = easing_fn(raw_progress)
                elif i < entry_frames + hold_frames:
                    phase = "hold"
                    progress = 1.0
                else:
                    phase = "exit"
                    raw_progress = (i - entry_frames - hold_frames) / max(exit_frames - 1, 1)
                    progress = 1.0 - easing_fn(raw_progress)

                # Compute animation parameters
                anim_params = self._compute_animation_params(
                    phase=phase,
                    progress=progress,
                    entry_style=config.entry_animation,
                    exit_style=config.exit_animation,
                    width=width,
                    height=height,
                )

                # Render frame
                png_bytes = self.renderer.render_frame(
                    text=text,
                    config=config,
                    width=width,
                    height=height,
                    **anim_params,
                )

                # Save frame
                frame_path = os.path.join(tmp_dir, f"frame_{i:06d}.png")
                with open(frame_path, "wb") as f:
                    f.write(png_bytes)

            # Encode to ProRes 4444 with alpha
            if output_path is None:
                output_path = os.path.join(tmp_dir, "overlay.mov")

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            self._encode_frames(tmp_dir, output_path, fps)

            if os.path.exists(output_path):
                logger.info(
                    f"Text overlay rendered: {total_frames} frames → {output_path}"
                )
                return output_path
            else:
                logger.error("Overlay encoding failed — no output file")
                return None

        except Exception as e:
            logger.error(f"Text animation failed: {e}")
            return None
        finally:
            # Cleanup temp frames (keep output)
            if output_path and not output_path.startswith(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def render_batch(
        self,
        overlays: list[dict],
        output_dir: str,
        fps: int = 24,
        width: int = 1920,
        height: int = 1080,
    ) -> list[Optional[str]]:
        """
        Render multiple text overlays.

        Each overlay dict: {text, config: TextOverlayConfig, duration_sec, scene_index}
        """
        results = []
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, ov in enumerate(overlays):
            idx = ov.get("scene_index", i)
            out_path = str(out_dir / f"overlay_{idx:03d}.mov")

            path = self.render_overlay(
                text=ov.get("text", ""),
                config=ov.get("config", TextOverlayConfig()),
                duration_sec=ov.get("duration_sec", 5.0),
                fps=fps,
                width=width,
                height=height,
                output_path=out_path,
            )
            results.append(path)

        rendered = sum(1 for r in results if r is not None)
        logger.info(f"Text overlays: {rendered}/{len(overlays)} rendered")
        return results

    # ─── Animation Parameter Computation ───────────────────

    def _compute_animation_params(
        self,
        phase: str,
        progress: float,
        entry_style: str,
        exit_style: str,
        width: int,
        height: int,
    ) -> dict:
        """
        Compute render parameters based on animation style and progress.
        """
        style = entry_style if phase == "entry" else (
            exit_style if phase == "exit" else "none"
        )

        params = {
            "alpha": 1.0,
            "x_offset": 0.0,
            "y_offset": 0.0,
            "scale": 1.0,
            "blur_radius": 0.0,
            "visible_chars": None,
            "glitch_intensity": 0.0,
        }

        if phase == "hold":
            return params

        if style == AnimationStyle.FADE_IN or style == AnimationStyle.FADE_OUT:
            params["alpha"] = progress

        elif style == AnimationStyle.SLIDE_RIGHT:
            # Slide from right (RTL natural) — start off-screen right
            params["alpha"] = progress
            params["x_offset"] = (1 - progress) * width * 0.3

        elif style == AnimationStyle.SLIDE_LEFT:
            params["alpha"] = progress
            params["x_offset"] = -(1 - progress) * width * 0.3

        elif style == AnimationStyle.SLIDE_UP:
            params["alpha"] = progress
            params["y_offset"] = (1 - progress) * height * 0.15

        elif style == AnimationStyle.SCALE_UP:
            params["alpha"] = progress
            params["scale"] = 0.3 + progress * 0.7

        elif style == AnimationStyle.BLUR_REVEAL:
            params["alpha"] = progress
            params["blur_radius"] = (1 - progress) * 15

        elif style == AnimationStyle.GLITCH_IN:
            params["alpha"] = min(progress * 1.5, 1.0)
            params["glitch_intensity"] = max(0, 1 - progress * 2)

        elif style == AnimationStyle.TYPEWRITER:
            # For typewriter, we control visible_chars during entry
            # progress 0→1 maps to 0→len(text) chars
            # (actual char count set by caller using text length)
            params["alpha"] = 1.0
            params["visible_chars"] = -1  # Sentinel: use progress * len(text)

        elif style == AnimationStyle.LETTER_CASCADE:
            params["alpha"] = progress
            params["y_offset"] = -(1 - progress) * 40  # Letters fall down
            params["scale"] = 0.8 + progress * 0.2

        elif style == AnimationStyle.NONE:
            pass

        return params

    # ─── FFmpeg Encoding ───────────────────────────────────

    def _encode_frames(self, frames_dir: str, output_path: str, fps: int):
        """
        Encode PNG frames → ProRes 4444 with alpha channel.

        ProRes 4444 preserves transparency and quality.
        Alternative: VP9+alpha (smaller files) via WebM.
        """
        cmd = [
            self.ffmpeg,
            "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%06d.png"),
            "-c:v", "prores_ks",
            "-profile:v", "4444",
            "-pix_fmt", "yuva444p10le",
            "-vendor", "apl0",
            output_path,
        ]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )

        if proc.returncode != 0:
            # Fallback to VP9+alpha if ProRes fails
            logger.warning("ProRes encoding failed, trying VP9+alpha")
            webm_path = output_path.replace(".mov", ".webm")
            cmd_vp9 = [
                self.ffmpeg,
                "-y",
                "-framerate", str(fps),
                "-i", os.path.join(frames_dir, "frame_%06d.png"),
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-auto-alt-ref", "0",
                "-b:v", "2M",
                webm_path,
            ]
            proc2 = subprocess.run(
                cmd_vp9, capture_output=True, text=True, timeout=300,
            )
            if proc2.returncode == 0:
                # Rename to expected output path
                shutil.move(webm_path, output_path)
            else:
                logger.error(f"VP9 encoding also failed: {proc2.stderr[:300]}")
