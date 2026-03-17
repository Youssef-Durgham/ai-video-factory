"""
Configuration loader.
Reads YAML configs + .env variables.
All other modules import config from here — NO hardcoded paths.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Resolve project root (ai-video-factory/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def load_config(config_dir: Optional[Path] = None) -> dict:
    """
    Load and merge all config files.
    Returns merged dict with keys: settings, channels, voices (if available).
    """
    cdir = Path(config_dir) if config_dir else CONFIG_DIR

    # Load global settings (required)
    settings_path = cdir / "settings.yaml"
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    with open(settings_path, encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}

    # Resolve environment variables (${VAR} → actual value)
    settings = _resolve_env_vars(settings)

    result = {"settings": settings}

    # Load channel definitions (optional)
    channels_path = cdir / "channels.yaml"
    if channels_path.exists():
        with open(channels_path, encoding="utf-8") as f:
            channels_data = yaml.safe_load(f) or {}
        result["channels"] = channels_data.get("channels", [])
    else:
        result["channels"] = []

    # Load voice library (optional)
    voice_lib_path = cdir / "voices" / "voice_library.yaml"
    if voice_lib_path.exists():
        with open(voice_lib_path, encoding="utf-8") as f:
            voices_data = yaml.safe_load(f) or {}
        result["voices"] = voices_data.get("voice_library", {})
    else:
        result["voices"] = {}

    return result


def get_channel_config(channel_id: str, config: Optional[dict] = None) -> dict:
    """Get config for a specific channel."""
    if config is None:
        config = load_config()
    for ch in config.get("channels", []):
        if ch.get("id") == channel_id:
            return ch
    raise ValueError(f"Channel not found: {channel_id}")


def get_setting(path: str, config: Optional[dict] = None, default=None):
    """
    Get a nested setting by dot-path.
    Example: get_setting("pipeline.max_script_revisions") → 3
    """
    if config is None:
        config = load_config()
    settings = config.get("settings", {})
    keys = path.split(".")
    current = settings
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def resolve_path(relative_path: str) -> Path:
    """Resolve a path relative to project root."""
    p = Path(relative_path)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def _resolve_env_vars(obj):
    """Recursively replace ${VAR} with os.environ[VAR]."""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            var = obj[2:-1]
            return os.environ.get(var, "")
        return obj
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    return obj
