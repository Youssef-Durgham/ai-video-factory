"""
Phase 5 — AI Font + Animation Selection (Qwen 3.5).

Analyzes script mood/topic to select optimal:
  • FontCategory (from text_animator.py FONT_LIBRARY)
  • Colors (text + accent)
  • Animation preset (from text_animator.py ANIMATION_PRESETS)

Uses Qwen 3.5 via Ollama for intelligent selection,
with rule-based fallback if LLM is unavailable.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Import from text_animator
from .text_animator import (
    FontCategory,
    FONT_LIBRARY,
    ANIMATION_PRESETS,
)

# ════════════════════════════════════════════════════════════════
# TOPIC → FONT CATEGORY FALLBACK MAP
# ════════════════════════════════════════════════════════════════

TOPIC_FONT_MAP: dict[str, FontCategory] = {
    "documentary":   FontCategory.FORMAL_NEWS,
    "historical":    FontCategory.HISTORICAL,
    "military":      FontCategory.MILITARY,
    "political":     FontCategory.FORMAL_NEWS,
    "scientific":    FontCategory.MODERN_TECH,
    "technology":    FontCategory.MODERN_TECH,
    "crime":         FontCategory.DRAMATIC,
    "mystery":       FontCategory.DRAMATIC,
    "islamic":       FontCategory.ISLAMIC,
    "biography":     FontCategory.STORYTELLING,
    "economic":      FontCategory.EDITORIAL,
    "social":        FontCategory.EDITORIAL,
    "entertainment": FontCategory.STORYTELLING,
}

# Default colors per category
CATEGORY_COLORS: dict[FontCategory, dict] = {
    FontCategory.FORMAL_NEWS:  {"text": "#FFFFFF", "accent": "#4A90D9", "bg": "#000000B0"},
    FontCategory.DRAMATIC:     {"text": "#FFFFFF", "accent": "#FF4444", "bg": "#000000C0"},
    FontCategory.HISTORICAL:   {"text": "#F5E6C8", "accent": "#C8A96E", "bg": "#1A0F00B0"},
    FontCategory.MODERN_TECH:  {"text": "#E0E0E0", "accent": "#00D4FF", "bg": "#0A0A2080"},
    FontCategory.ISLAMIC:      {"text": "#FFFFFF", "accent": "#FFD700", "bg": "#0D2818B0"},
    FontCategory.MILITARY:     {"text": "#E0E0E0", "accent": "#8B9DC3", "bg": "#1C2833C0"},
    FontCategory.EDITORIAL:    {"text": "#FFFFFF", "accent": "#F0A030", "bg": "#000000A0"},
    FontCategory.STORYTELLING: {"text": "#FFFFFF", "accent": "#FFB347", "bg": "#2C1810B0"},
}

# Fonts directory
FONTS_BASE = Path("src/phase5_production/fonts")


@dataclass
class FontAnimationConfig:
    """Complete font + animation configuration for a video."""
    font_category: str = "formal_news"
    primary_font: str = "IBM Plex Sans Arabic"
    accent_font: str = "Noto Naskh Arabic"
    font_path: str = ""
    font_size: int = 56
    primary_weight: int = 400
    accent_usage: str = "titles_only"
    text_color: str = "#FFFFFF"
    accent_color: str = "#4A90D9"
    background_style: str = "box"
    background_color: str = "#000000B0"
    entry_animation: str = "fade_in"
    exit_animation: str = "fade_out"
    animation_preset: dict = field(default_factory=dict)
    animation_override: Optional[dict] = None
    reasoning: str = ""


# ════════════════════════════════════════════════════════════════
# LLM PROMPT TEMPLATE
# ════════════════════════════════════════════════════════════════

FONT_SELECTION_PROMPT = """You are a professional Arabic video typographer.

VIDEO SCRIPT:
Title: "{title}"
Topic: {topic_category}
Tone: {emotional_arc}
Sample narration: "{sample_narration}"
Channel style: {channel_style}

Available font categories:
- formal_news: Clean, authoritative (IBM Plex Sans Arabic + Noto Naskh)
- dramatic: Bold, high contrast (Aref Ruqaa + Lemonada)
- historical: Elegant, classical (Amiri + Scheherazade New)
- modern_tech: Geometric, minimal (IBM Plex Sans Arabic + Readex Pro)
- islamic: Traditional Naskh (Scheherazade New + Amiri Quran)
- military: Heavy, impactful (Cairo + Tajawal)
- editorial: Neutral, readable (Noto Sans Arabic + El Messiri)
- storytelling: Warm, inviting (Tajawal + Lemonada)

Select:
1. font_category: Which category best fits this video?
2. primary_weight: Font weight (300-900)
3. accent_usage: "titles_only" | "quotes" | "statistics" | "none"
4. text_color: Hex color for primary text
5. accent_color: Hex color for accent/highlight
6. background_style: "none" | "box" | "gradient" | "blur"
7. animation_override: null (use preset) or specific animation name
8. reasoning: Why this combination? (1 sentence)

Return ONLY valid JSON with these 8 keys. No explanation outside JSON."""


class FontSelector:
    """
    AI-powered font and animation selection using Qwen 3.5.

    Analyzes the script's mood, topic, and tone to select the optimal
    font category, colors, and animation style from the predefined
    FONT_LIBRARY and ANIMATION_PRESETS.

    Falls back to rule-based selection if LLM is unavailable.
    """

    def __init__(
        self,
        db=None,
        ollama_host: str = "http://localhost:11434",
        model: str = "qwen3.5:27b",
    ):
        self.db = db
        self.ollama_host = ollama_host
        self.model = model

    def select(self, job: dict) -> dict:
        """
        Select font + animation config for a job.

        Args:
            job: Job dict with title, topic_category, scenes, etc.

        Returns:
            Dict with font/animation configuration.
        """
        # Try AI selection first
        try:
            config = self._ai_select(job)
            if config:
                return self._config_to_dict(config)
        except Exception as e:
            logger.warning(f"AI font selection failed, using fallback: {e}")

        # Fallback to rules
        config = self._fallback_select(job)
        return self._config_to_dict(config)

    def _ai_select(self, job: dict) -> Optional[FontAnimationConfig]:
        """
        Use Qwen 3.5 to select font + animation based on script analysis.
        """
        import requests

        # Build prompt context
        title = job.get("title", "")
        topic = job.get("topic_category", "documentary")
        emotional_arc = job.get("emotional_arc", "neutral")
        channel_style = job.get("channel_style", "default")

        # Get sample narration from first 3 scenes
        scenes = job.get("scenes", [])
        if isinstance(scenes, list):
            sample = " ".join(
                s.get("narration_text", "")[:100]
                for s in scenes[:3]
                if isinstance(s, dict)
            )
        else:
            sample = ""

        prompt = FONT_SELECTION_PROMPT.format(
            title=title,
            topic_category=topic,
            emotional_arc=emotional_arc,
            sample_narration=sample[:300],
            channel_style=channel_style,
        )

        # Call Ollama
        r = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 500},
            },
            timeout=60,
        )
        r.raise_for_status()
        response_text = r.json().get("response", "")

        # Parse JSON from response
        config = self._parse_llm_response(response_text, topic)
        return config

    def _parse_llm_response(
        self, response: str, topic: str
    ) -> Optional[FontAnimationConfig]:
        """Parse LLM JSON response into FontAnimationConfig."""
        # Extract JSON from response
        try:
            # Find JSON block
            start = response.find("{")
            end = response.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            data = json.loads(response[start:end])
        except json.JSONDecodeError:
            return None

        # Validate font_category
        category_str = data.get("font_category", "formal_news")
        try:
            category = FontCategory(category_str)
        except ValueError:
            category = TOPIC_FONT_MAP.get(topic, FontCategory.FORMAL_NEWS)

        font_info = FONT_LIBRARY.get(category, FONT_LIBRARY[FontCategory.FORMAL_NEWS])
        preset = ANIMATION_PRESETS.get(category, ANIMATION_PRESETS[FontCategory.FORMAL_NEWS])
        colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS[FontCategory.FORMAL_NEWS])

        # Resolve font path
        font_path = self._resolve_font_path(font_info["primary"])

        config = FontAnimationConfig(
            font_category=category_str,
            primary_font=font_info["primary"],
            accent_font=font_info.get("accent", font_info["primary"]),
            font_path=font_path,
            font_size=56,
            primary_weight=data.get("primary_weight", font_info["weight_range"][0]),
            accent_usage=data.get("accent_usage", "titles_only"),
            text_color=data.get("text_color", colors["text"]),
            accent_color=data.get("accent_color", colors["accent"]),
            background_style=data.get("background_style", "box"),
            background_color=colors["bg"],
            entry_animation=preset.get("entry", "fade_in"),
            exit_animation=preset.get("exit", "fade_out"),
            animation_preset=preset,
            animation_override=data.get("animation_override"),
            reasoning=data.get("reasoning", ""),
        )

        return config

    def _fallback_select(self, job: dict) -> FontAnimationConfig:
        """
        Rule-based font selection. No AI needed.

        Maps topic_category directly to FontCategory.
        """
        topic = job.get("topic_category", "documentary")
        category = TOPIC_FONT_MAP.get(topic, FontCategory.FORMAL_NEWS)

        font_info = FONT_LIBRARY.get(category, FONT_LIBRARY[FontCategory.FORMAL_NEWS])
        preset = ANIMATION_PRESETS.get(category, ANIMATION_PRESETS[FontCategory.FORMAL_NEWS])
        colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS[FontCategory.FORMAL_NEWS])

        font_path = self._resolve_font_path(font_info["primary"])

        return FontAnimationConfig(
            font_category=category.value,
            primary_font=font_info["primary"],
            accent_font=font_info.get("accent", font_info["primary"]),
            font_path=font_path,
            font_size=56,
            primary_weight=font_info["weight_range"][0],
            accent_usage="titles_only",
            text_color=colors["text"],
            accent_color=colors["accent"],
            background_style="box",
            background_color=colors["bg"],
            entry_animation=preset.get("entry", "fade_in"),
            exit_animation=preset.get("exit", "fade_out"),
            animation_preset=preset,
            reasoning="Rule-based selection from topic category",
        )

    def _resolve_font_path(self, font_name: str) -> str:
        """Resolve a font name to its file path."""
        # Convert name to directory name
        dir_name = font_name.replace(" ", "_")
        font_dir = FONTS_BASE / dir_name

        if font_dir.exists():
            # Look for .ttf or .otf
            for ext in ("*.ttf", "*.otf"):
                files = list(font_dir.glob(ext))
                if files:
                    # Prefer Regular weight
                    for f in files:
                        if "Regular" in f.name or "regular" in f.name:
                            return str(f)
                    return str(files[0])

        # Fallback — return name and let renderer handle it
        return font_name

    def _config_to_dict(self, config: FontAnimationConfig) -> dict:
        """Convert FontAnimationConfig to dict for storage/use."""
        return {
            "font_category": config.font_category,
            "primary_font": config.primary_font,
            "accent_font": config.accent_font,
            "font_path": config.font_path,
            "font_size": config.font_size,
            "primary_weight": config.primary_weight,
            "accent_usage": config.accent_usage,
            "text_color": config.text_color,
            "accent_color": config.accent_color,
            "background_style": config.background_style,
            "background_color": config.background_color,
            "entry_animation": config.entry_animation,
            "exit_animation": config.exit_animation,
            "animation_preset": config.animation_preset,
            "animation_override": config.animation_override,
            "reasoning": config.reasoning,
        }
