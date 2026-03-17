"""
Brand Kit Agent — Visual identity enforcement.
Ensures all visual elements match channel brand (colors, fonts, watermark, intro/outro).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

DEFAULT_BRAND = {
    "colors": {
        "primary": "#1a1a2e",
        "secondary": "#16213e",
        "accent": "#e94560",
        "text": "#ffffff",
        "text_secondary": "#cccccc",
    },
    "fonts": {
        "title": "Cairo-Bold",
        "body": "Tajawal-Regular",
        "overlay": "Cairo-SemiBold",
    },
    "watermark": {
        "enabled": True,
        "position": "bottom_right",
        "opacity": 0.3,
        "size_pct": 5,
    },
    "intro": {"enabled": True, "duration_sec": 4},
    "outro": {"enabled": True, "duration_sec": 6},
    "overlay_style": {
        "background_blur": True,
        "background_opacity": 0.7,
        "corner_radius": 8,
        "padding": 20,
    },
}


class BrandKitAgent:
    """
    Loads and enforces channel brand identity across all visual outputs.
    Validates consistency of colors, fonts, watermark, intro/outro.
    """

    def __init__(self, db: FactoryDB, brands_dir: str = "config/brands"):
        self.db = db
        self.brands_dir = Path(brands_dir)

    def run(self, channel_id: str) -> dict:
        """
        Load and return the full brand kit for a channel.

        Returns: Complete brand config dict with paths to assets.
        """
        brand = self._load_brand(channel_id)

        # Validate all assets exist
        validation = self.validate(channel_id, brand)
        if validation["errors"]:
            logger.warning(f"Brand kit issues for {channel_id}: {validation['errors']}")
        brand["validation"] = validation

        logger.info(f"Brand kit loaded for {channel_id}: {len(validation['errors'])} errors, {len(validation['warnings'])} warnings")
        return brand

    def validate(self, channel_id: str, brand: Optional[dict] = None) -> dict:
        """
        Validate brand kit completeness and consistency.

        Returns: {"valid": bool, "errors": [...], "warnings": [...]}
        """
        if brand is None:
            brand = self._load_brand(channel_id)

        errors = []
        warnings = []
        channel_dir = self.brands_dir / channel_id

        # Check required assets
        if brand.get("intro", {}).get("enabled"):
            intro_path = channel_dir / "intro.mp4"
            if not intro_path.exists():
                warnings.append(f"Intro video missing: {intro_path}")

        if brand.get("outro", {}).get("enabled"):
            outro_path = channel_dir / "outro.mp4"
            if not outro_path.exists():
                warnings.append(f"Outro video missing: {outro_path}")

        if brand.get("watermark", {}).get("enabled"):
            wm_path = channel_dir / "watermark.png"
            if not wm_path.exists():
                warnings.append(f"Watermark missing: {wm_path}")

        logo_path = channel_dir / "logo.png"
        if not logo_path.exists():
            warnings.append(f"Logo missing: {logo_path}")

        # Validate colors are valid hex
        colors = brand.get("colors", {})
        for name, color in colors.items():
            if isinstance(color, str) and not color.startswith("#"):
                errors.append(f"Invalid color '{name}': {color} (must be hex)")
            elif isinstance(color, str) and len(color) not in (4, 7):
                errors.append(f"Invalid hex color '{name}': {color}")

        # Validate fonts exist
        fonts = brand.get("fonts", {})
        font_dirs = list(Path("config/fonts").glob("*")) if Path("config/fonts").exists() else []
        available_fonts = [f.name for f in font_dirs]
        for role, font_name in fonts.items():
            font_family = font_name.split("-")[0] if "-" in font_name else font_name
            if available_fonts and font_family not in available_fonts:
                warnings.append(f"Font '{font_name}' for '{role}' may not be installed")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def get_colors(self, channel_id: str) -> dict:
        """Get channel brand colors."""
        brand = self._load_brand(channel_id)
        return brand.get("colors", DEFAULT_BRAND["colors"])

    def get_fonts(self, channel_id: str) -> dict:
        """Get channel brand fonts."""
        brand = self._load_brand(channel_id)
        return brand.get("fonts", DEFAULT_BRAND["fonts"])

    def get_watermark_config(self, channel_id: str) -> dict:
        """Get watermark configuration with resolved path."""
        brand = self._load_brand(channel_id)
        wm = brand.get("watermark", DEFAULT_BRAND["watermark"]).copy()
        wm["path"] = str(self.brands_dir / channel_id / "watermark.png")
        return wm

    def get_intro_path(self, channel_id: str) -> Optional[str]:
        """Get intro video path if enabled."""
        brand = self._load_brand(channel_id)
        if brand.get("intro", {}).get("enabled"):
            path = self.brands_dir / channel_id / "intro.mp4"
            return str(path) if path.exists() else None
        return None

    def get_outro_path(self, channel_id: str) -> Optional[str]:
        """Get outro video path if enabled."""
        brand = self._load_brand(channel_id)
        if brand.get("outro", {}).get("enabled"):
            path = self.brands_dir / channel_id / "outro.mp4"
            return str(path) if path.exists() else None
        return None

    def get_overlay_style(self, channel_id: str) -> dict:
        """Get text overlay style config."""
        brand = self._load_brand(channel_id)
        return brand.get("overlay_style", DEFAULT_BRAND["overlay_style"])

    def format_for_prompt(self, channel_id: str) -> str:
        """Format brand info for injection into image/video generation prompts."""
        brand = self._load_brand(channel_id)
        colors = brand.get("colors", {})
        return (
            f"Brand colors: primary={colors.get('primary', '#1a1a2e')}, "
            f"accent={colors.get('accent', '#e94560')}. "
            f"Style: cinematic documentary, consistent visual identity."
        )

    def _load_brand(self, channel_id: str) -> dict:
        """Load brand kit from YAML config. Falls back to defaults."""
        brand_file = self.brands_dir / channel_id / "brand_kit.yaml"
        if brand_file.exists():
            try:
                with open(brand_file, "r", encoding="utf-8") as f:
                    brand = yaml.safe_load(f) or {}
                # Merge with defaults for missing keys
                merged = DEFAULT_BRAND.copy()
                for key in merged:
                    if key in brand:
                        if isinstance(merged[key], dict) and isinstance(brand[key], dict):
                            merged[key] = {**merged[key], **brand[key]}
                        else:
                            merged[key] = brand[key]
                return merged
            except Exception as e:
                logger.warning(f"Failed to load brand kit for {channel_id}: {e}")

        return DEFAULT_BRAND.copy()
