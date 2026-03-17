"""
Phase 8 — Thumbnail Generation via FLUX (ComfyUI) + PyCairo text overlay.

Generates 3 thumbnail variants (1280x720), applies color grade LUT,
and renders Arabic text using PyCairo with accent_font/accent_color from config.
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import requests
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# LUT application constants
LUT_SIZE = 33  # Standard .cube LUT size


class ThumbnailGenerator:
    """
    Generates 3 thumbnail variants per video using FLUX via ComfyUI,
    then applies color grading and Arabic text overlay.
    """

    # Thumbnail prompt templates by font category
    STYLE_PROMPTS = {
        "formal_news": [
            "professional news thumbnail, clean background, dramatic lighting, {subject}, photojournalism",
            "broadcast-style thumbnail, bold composition, studio lighting, {subject}, editorial",
            "minimalist documentary thumbnail, single subject focus, {subject}, clean professional",
        ],
        "dramatic": [
            "dark cinematic thumbnail, dramatic shadows, high contrast, {subject}, thriller atmosphere",
            "moody dramatic thumbnail, smoke effects, rim lighting, {subject}, tension",
            "epic wide angle thumbnail, dramatic sky, {subject}, cinematic color grading",
        ],
        "historical": [
            "vintage documentary thumbnail, aged parchment texture, {subject}, sepia tones",
            "historical photograph style, archival look, {subject}, classical composition",
            "oil painting inspired thumbnail, renaissance lighting, {subject}, warm tones",
        ],
        "modern_tech": [
            "futuristic tech thumbnail, neon accents, digital grid, {subject}, cyberpunk",
            "clean technology thumbnail, holographic elements, {subject}, minimalist",
            "data visualization style thumbnail, circuit patterns, {subject}, modern",
        ],
        "islamic": [
            "elegant arabesque patterns, golden ornaments, {subject}, warm lighting",
            "geometric Islamic art background, mosque silhouette, {subject}, warm gold tones",
            "calligraphy inspired composition, ornamental border, {subject}, elegant",
        ],
        "military": [
            "tactical military thumbnail, cold steel tones, {subject}, harsh lighting",
            "war documentary style, smoke and debris, {subject}, high contrast",
            "strategic map overlay, military stencil aesthetic, {subject}, commanding",
        ],
        "editorial": [
            "clean editorial thumbnail, neutral background, {subject}, professional photography",
            "magazine cover style, balanced composition, {subject}, clean typography space",
            "journalistic thumbnail, documentary feel, {subject}, neutral tones",
        ],
        "storytelling": [
            "warm storytelling thumbnail, golden hour lighting, {subject}, inviting",
            "narrative scene thumbnail, soft focus background, {subject}, emotional",
            "cinematic story frame, warm color palette, {subject}, engaging composition",
        ],
    }

    NEGATIVE_PROMPT = (
        "text, writing, letters, words, watermark, subtitle, blurry, "
        "low quality, deformed, ugly, cartoon, anime, 3d render"
    )

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.comfyui_host = config["settings"]["comfyui"]["host"]
        self.output_base = Path(config["settings"].get("output_dir", "output"))
        self.luts_dir = Path("src/phase5_production/luts")
        self.fonts_dir = Path("src/phase5_production/fonts")

    def generate_thumbnails(self, job_id: str) -> list[str]:
        """
        Generate 3 thumbnail variants for a job.
        Returns list of file paths to generated thumbnails.
        """
        job = self.db.get_job(job_id)
        seo_rows = self.db.conn.execute(
            "SELECT * FROM seo_data WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        seo = dict(seo_rows) if seo_rows else {}

        # Get font/animation config for style consistency
        font_config = json.loads(job.get("font_animation_config") or "{}")
        font_category = font_config.get("font_category", "editorial")
        accent_font = font_config.get("accent_font", "Cairo")
        accent_color = font_config.get("accent_color", "#e94560")
        bg_style = font_config.get("background_style", "box")

        # Determine subject from topic
        subject = job.get("topic", "documentary scene")
        title = seo.get("selected_title") or job.get("topic", "")

        # Get style prompts for this category
        prompts = self.STYLE_PROMPTS.get(font_category, self.STYLE_PROMPTS["editorial"])

        thumb_dir = self.output_base / job_id / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        variants = ["A", "B", "C"]

        for i, (variant, prompt_template) in enumerate(zip(variants, prompts)):
            prompt = prompt_template.format(subject=subject)
            logger.info(f"Generating thumbnail {variant} for {job_id}")

            # Generate base image via ComfyUI FLUX
            base_path = thumb_dir / f"thumb_{variant}_base.png"
            self._generate_flux_image(prompt, str(base_path))

            # Apply color grade LUT (same as video)
            color_config = json.loads(job.get("color_grade_config") or "{}")
            lut_name = color_config.get("lut_file")
            if lut_name:
                self._apply_lut(str(base_path), str(base_path), lut_name)

            # Apply Arabic text overlay
            final_path = thumb_dir / f"thumb_{variant}.png"
            self._apply_text_overlay(
                str(base_path),
                str(final_path),
                title,
                accent_font=accent_font,
                accent_color=accent_color,
                bg_style=bg_style,
                variant_index=i,
            )

            # Save to DB
            self.db.conn.execute(
                """INSERT INTO thumbnails (job_id, variant, file_path, prompt, text_overlay, style)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (job_id, variant, str(final_path), prompt, title, font_category),
            )
            self.db.conn.commit()

            paths.append(str(final_path))
            logger.info(f"Thumbnail {variant} saved: {final_path}")

        return paths

    def _generate_flux_image(self, prompt: str, output_path: str):
        """Generate a 1280x720 image via ComfyUI FLUX workflow."""
        workflow = self._build_flux_workflow(prompt, 1280, 720)

        try:
            # Queue prompt
            resp = requests.post(
                f"{self.comfyui_host}/prompt",
                json={"prompt": workflow, "client_id": str(uuid.uuid4())[:8]},
                timeout=30,
            )
            resp.raise_for_status()
            prompt_id = resp.json().get("prompt_id")

            # Poll for completion
            for _ in range(120):  # 2 min max
                time.sleep(1)
                hist = requests.get(
                    f"{self.comfyui_host}/history/{prompt_id}", timeout=10
                ).json()
                if prompt_id in hist:
                    outputs = hist[prompt_id].get("outputs", {})
                    for node_id, node_out in outputs.items():
                        images = node_out.get("images", [])
                        if images:
                            img_info = images[0]
                            img_resp = requests.get(
                                f"{self.comfyui_host}/view",
                                params={
                                    "filename": img_info["filename"],
                                    "subfolder": img_info.get("subfolder", ""),
                                    "type": img_info.get("type", "output"),
                                },
                                timeout=30,
                            )
                            Path(output_path).write_bytes(img_resp.content)
                            # Resize to exact 1280x720
                            img = Image.open(output_path)
                            if img.size != (1280, 720):
                                img = img.resize((1280, 720), Image.LANCZOS)
                                img.save(output_path)
                            return
            raise TimeoutError("ComfyUI thumbnail generation timed out")

        except Exception as e:
            logger.error(f"FLUX thumbnail generation failed: {e}")
            # Create fallback solid color thumbnail
            img = Image.new("RGB", (1280, 720), (26, 26, 46))
            img.save(output_path)

    def _build_flux_workflow(self, prompt: str, width: int, height: int) -> dict:
        """Build a ComfyUI FLUX workflow for thumbnail generation."""
        flux_model = self.config["settings"]["comfyui"]["models"]["flux"]
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": flux_model},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1],
                },
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": self.NEGATIVE_PROMPT,
                    "clip": ["1", 1],
                },
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": int(time.time()) % (2**32),
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {"images": ["6", 0], "filename_prefix": "thumbnail"},
            },
        }

    def _apply_lut(self, input_path: str, output_path: str, lut_name: str):
        """Apply a .cube LUT file to an image for color grading."""
        lut_path = self.luts_dir / lut_name
        if not lut_path.exists():
            logger.warning(f"LUT file not found: {lut_path}, skipping color grade")
            return

        try:
            lut = self._load_cube_lut(str(lut_path))
            img = Image.open(input_path).convert("RGB")
            arr = np.array(img, dtype=np.float32) / 255.0

            # Apply 3D LUT via trilinear interpolation
            size = lut.shape[0]
            scaled = arr * (size - 1)
            lower = np.floor(scaled).astype(int)
            lower = np.clip(lower, 0, size - 2)
            frac = scaled - lower

            # Simple nearest-neighbor LUT for speed
            idx = np.clip(np.round(scaled).astype(int), 0, size - 1)
            result = lut[idx[..., 0], idx[..., 1], idx[..., 2]]

            result = np.clip(result * 255, 0, 255).astype(np.uint8)
            Image.fromarray(result).save(output_path)
        except Exception as e:
            logger.error(f"LUT application failed: {e}")

    def _load_cube_lut(self, path: str) -> np.ndarray:
        """Parse a .cube LUT file into a 3D numpy array."""
        size = LUT_SIZE
        data = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LUT_3D_SIZE"):
                    size = int(line.split()[-1])
                elif line and not line.startswith("#") and not line.startswith("TITLE") and not line.startswith("DOMAIN"):
                    parts = line.split()
                    if len(parts) == 3:
                        data.append([float(x) for x in parts])
        arr = np.array(data, dtype=np.float32)
        return arr.reshape(size, size, size, 3)

    def _apply_text_overlay(
        self,
        input_path: str,
        output_path: str,
        text: str,
        accent_font: str = "Cairo",
        accent_color: str = "#e94560",
        bg_style: str = "box",
        variant_index: int = 0,
    ):
        """
        Render Arabic text overlay on thumbnail using PyCairo.
        Falls back to Pillow if PyCairo is unavailable.
        """
        try:
            self._render_cairo_text(
                input_path, output_path, text,
                accent_font, accent_color, bg_style, variant_index,
            )
        except ImportError:
            logger.warning("PyCairo not available, falling back to Pillow")
            self._render_pillow_text(
                input_path, output_path, text,
                accent_font, accent_color, bg_style, variant_index,
            )

    def _render_cairo_text(
        self, input_path: str, output_path: str, text: str,
        font_name: str, color_hex: str, bg_style: str, variant_index: int,
    ):
        """Render Arabic text using PyCairo + Pango for proper shaping."""
        import cairo
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo

        # Load base image
        img = Image.open(input_path).convert("RGBA")
        width, height = img.size

        # Create Cairo surface from image
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)

        # Draw base image
        base_surface = cairo.ImageSurface.create_from_png(input_path)
        ctx.set_source_surface(base_surface, 0, 0)
        ctx.paint()

        # Parse accent color
        r, g, b = self._hex_to_rgb(color_hex)

        # Text positioning varies by variant
        positions = [
            (width * 0.5, height * 0.35),   # Center-top
            (width * 0.5, height * 0.5),     # Center
            (width * 0.7, height * 0.45),    # Right-center
        ]
        x, y = positions[variant_index % len(positions)]

        # Create Pango layout
        layout = PangoCairo.create_layout(ctx)
        layout.set_text(text, -1)
        layout.set_alignment(Pango.Alignment.CENTER)

        font_desc = Pango.FontDescription(f"{font_name} Bold 52")
        layout.set_font_description(font_desc)
        layout.set_width(int(width * 0.8 * Pango.SCALE))

        # Get text extents
        ink_rect, logical_rect = layout.get_pixel_extents()
        text_w = logical_rect.width
        text_h = logical_rect.height

        tx = x - text_w / 2
        ty = y - text_h / 2

        # Background
        if bg_style == "box":
            pad = 20
            ctx.set_source_rgba(0, 0, 0, 0.7)
            ctx.rectangle(tx - pad, ty - pad, text_w + 2 * pad, text_h + 2 * pad)
            ctx.fill()
        elif bg_style == "gradient":
            pat = cairo.LinearGradient(tx, ty, tx, ty + text_h)
            pat.add_color_stop_rgba(0, 0, 0, 0, 0.8)
            pat.add_color_stop_rgba(1, 0, 0, 0, 0.3)
            ctx.set_source(pat)
            ctx.rectangle(tx - 20, ty - 10, text_w + 40, text_h + 20)
            ctx.fill()

        # Text shadow
        ctx.move_to(tx + 2, ty + 2)
        ctx.set_source_rgba(0, 0, 0, 0.8)
        PangoCairo.show_layout(ctx, layout)

        # Main text
        ctx.move_to(tx, ty)
        ctx.set_source_rgb(r, g, b)
        PangoCairo.show_layout(ctx, layout)

        surface.write_to_png(output_path)

    def _render_pillow_text(
        self, input_path: str, output_path: str, text: str,
        font_name: str, color_hex: str, bg_style: str, variant_index: int,
    ):
        """Fallback: render Arabic text using Pillow."""
        from PIL import ImageDraw, ImageFont

        img = Image.open(input_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        width, height = img.size

        # Try to load font
        font_size = 56
        font = ImageFont.load_default()
        for font_dir in [self.fonts_dir, Path("/usr/share/fonts")]:
            for ext in ["*.ttf", "*.otf"]:
                for fp in font_dir.rglob(ext):
                    if font_name.lower().replace(" ", "") in fp.stem.lower().replace(" ", ""):
                        try:
                            font = ImageFont.truetype(str(fp), font_size)
                            break
                        except Exception:
                            continue

        # Position
        positions = [
            (width * 0.5, height * 0.35),
            (width * 0.5, height * 0.5),
            (width * 0.7, height * 0.45),
        ]
        x, y = positions[variant_index % len(positions)]

        bbox = draw.textbbox((0, 0), text, font=font, anchor="mm")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # Background box
        if bg_style in ("box", "gradient"):
            pad = 20
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            od.rectangle(
                [x - tw / 2 - pad, y - th / 2 - pad, x + tw / 2 + pad, y + th / 2 + pad],
                fill=(0, 0, 0, 180),
            )
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

        # Shadow
        draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 200), font=font, anchor="mm")
        # Main text
        r, g, b = self._hex_to_rgb(color_hex)
        draw.text((x, y), text, fill=(int(r * 255), int(g * 255), int(b * 255), 255), font=font, anchor="mm")

        img.convert("RGB").save(output_path)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
        """Convert hex color to 0-1 RGB tuple."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return r / 255.0, g / 255.0, b / 255.0
