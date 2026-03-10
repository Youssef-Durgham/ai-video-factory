# AI Video Factory — System Architecture (Build Guide)

> **هذا الملف للـ AI Builder.** يحتوي على كل التفاصيل التقنية اللازمة لبناء النظام.
> اقرأ `BLUEPRINT.md` أولاً لفهم المنتج، ثم ارجع هنا للبناء.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI VIDEO FACTORY                             │
│                                                                     │
│  Python 3.11+ Orchestrator                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Phase 1  │→│ Phase 2  │→│ Phase 3  │→│ Phase 4  │          │
│  │ Research │  │ SEO      │  │ Script   │  │ QA       │          │
│  └──────────┘  └──────────┘  └──────────┘  └────┬─────┘          │
│                                                   │ PASS           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────▼─────┐          │
│  │ Phase 8  │←│ Phase 7  │←│ Phase 6  │←│ Phase 5  │          │
│  │ Publish  │  │ Final QA │  │ Visual QA│  │Production│          │
│  └────┬─────┘  └──────────┘  └──────────┘  └──────────┘          │
│       │                                                            │
│  ┌────▼─────┐                                                      │
│  │ Phase 9  │ ← Performance Intelligence (continuous loop)         │
│  └──────────┘                                                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ INFRASTRUCTURE                                               │   │
│  │ SQLite DB │ GPU Manager │ GPU Logger │ Telegram Bot │ Cron  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Hardware Target
```
CPU:  Intel i9-14900K (24 cores)
RAM:  128GB DDR5
GPU:  1x NVIDIA RTX 3090 (24GB VRAM)
Disk: 2TB+ NVMe SSD
OS:   Linux (Ubuntu 22.04) or Windows 11
```

### Tech Stack
```
Language:       Python 3.11+
LLM:            Qwen 2.5 72B Q4 (via Ollama)
Vision LLM:     Llama 3.2 Vision 11B (via Ollama)
Image Gen:      FLUX.1-dev (via ComfyUI)
Video Gen:      LTX-2.3 (via ComfyUI)
Voice Clone:    Fish Speech 1.5 (local)
Music Gen:      MusicGen-large (via audiocraft)
SFX Gen:        AudioGen-medium (via audiocraft)
Upscaling:      Real-ESRGAN (CPU)
Presenter:      SadTalker / MuseTalk (optional)
Video Compose:  FFmpeg + MoviePy + Pillow
Database:       SQLite (WAL mode)
Scheduling:     APScheduler
Notification:   Telegram Bot API
API:            YouTube Data API v3
Dashboard:      FastAPI + React (optional)
```

---

## 2. Project Structure

```
ai-video-factory/
│
├── BLUEPRINT.md                    # Product spec (what to build)
├── ARCHITECTURE.md                 # This file (how to build it)
├── requirements.txt                # Python dependencies
├── setup.py                        # Package setup
├── .env.example                    # Environment variables template
├── docker-compose.yml              # Optional containerized setup
│
├── config/
│   ├── settings.yaml               # Global settings (see §3)
│   ├── channels.yaml               # Channel definitions (see §3)
│   ├── youtube_policies.md         # YouTube ToS summary for compliance
│   ├── voices/                     # Human voice recordings (input)
│   │   ├── male_authoritative_01.wav
│   │   ├── male_energetic_01.wav
│   │   ├── male_mysterious_01.wav
│   │   ├── male_narrator_01.wav
│   │   ├── female_educational_01.wav
│   │   ├── female_dramatic_01.wav
│   │   ├── young_male_01.wav
│   │   ├── embeddings/             # AI clone embeddings (generated)
│   │   │   └── *.pt
│   │   └── voice_library.yaml      # Voice metadata
│   ├── brands/                     # Per-channel brand kits
│   │   └── [channel_id]/
│   │       ├── logo.png
│   │       ├── watermark.png
│   │       ├── intro.mp4
│   │       ├── outro.mp4
│   │       └── brand_kit.yaml
│   ├── templates/                  # Intro/outro video templates
│   ├── fonts/                      # Arabic fonts (Cairo, Tajawal)
│   └── loras/                      # FLUX LoRA models
│       ├── middle_east_architecture.safetensors
│       ├── photojournalism.safetensors
│       └── cinematic_lighting.safetensors
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # Main orchestrator (see §4)
│   ├── cli.py                      # CLI entry point
│   │
│   ├── core/                       # Core infrastructure
│   │   ├── __init__.py
│   │   ├── config.py               # Config loader (see §3)
│   │   ├── database.py             # FactoryDB class (see §5)
│   │   ├── gpu_manager.py          # GPU memory manager (see §6)
│   │   ├── gpu_logger.py           # GPU precision logging (see §6)
│   │   ├── scheduler.py            # Job scheduler
│   │   ├── telegram_bot.py         # Telegram notifications + interactive
│   │   └── retry.py                # Retry/backoff logic
│   │
│   ├── phase1_research/
│   │   ├── __init__.py
│   │   ├── youtube_trends.py       # YouTube Data API v3 trending
│   │   ├── web_trends.py           # Google Trends + RSS + Reddit
│   │   ├── topic_ranker.py         # Score and rank topics
│   │   └── topic_presenter.py      # Telegram topic selection UI
│   │
│   ├── phase2_seo/
│   │   ├── __init__.py
│   │   ├── keyword_research.py     # YouTube keyword analysis
│   │   ├── competitor_analysis.py  # Analyze top videos
│   │   ├── title_generator.py      # LLM-powered title generation
│   │   └── tag_planner.py          # Tags + description template
│   │
│   ├── phase3_script/
│   │   ├── __init__.py
│   │   ├── researcher.py           # Web research agent
│   │   ├── writer.py               # Script writer (Qwen 72B)
│   │   ├── reviewer.py             # Script reviewer + fact checker
│   │   └── splitter.py             # Scene splitter → JSON
│   │
│   ├── phase4_compliance/
│   │   ├── __init__.py
│   │   ├── youtube_policy.py       # YouTube ToS check
│   │   ├── ai_content_check.py     # Anti-low-effort check
│   │   ├── copyright_check.py      # Plagiarism detection
│   │   ├── fact_checker.py         # Fact verification
│   │   └── arabic_quality.py       # MSA grammar + pronunciation
│   │
│   ├── phase5_production/
│   │   ├── __init__.py
│   │   ├── image_gen.py            # FLUX image generation
│   │   ├── image_prompt.py         # Arabic content prompt enhancement
│   │   ├── video_gen.py            # LTX-2.3 video generation
│   │   ├── voice_clone.py          # Voice cloning (one-time setup)
│   │   ├── voice_gen.py            # TTS with cloned voice
│   │   ├── voice_selector.py       # Smart voice selection agent
│   │   ├── music_gen.py            # MusicGen background music
│   │   ├── sfx_gen.py              # AudioGen sound effects
│   │   ├── content_id_guard.py     # Audio fingerprint protection
│   │   ├── upscaler.py             # Real-ESRGAN 4K upscale
│   │   └── composer.py             # FFmpeg video assembly
│   │
│   ├── phase6_visual_qa/
│   │   ├── __init__.py
│   │   ├── image_checker.py        # Vision LLM: image vs script
│   │   ├── style_checker.py        # Style consistency
│   │   └── sequence_checker.py     # Visual flow check
│   │
│   ├── phase7_video_qa/
│   │   ├── __init__.py
│   │   ├── technical_check.py      # A/V sync, duration, resolution
│   │   ├── content_check.py        # Narration-visual alignment
│   │   └── final_compliance.py     # Last compliance sweep
│   │
│   ├── phase7_5_review/
│   │   ├── __init__.py
│   │   └── manual_review.py        # Telegram interactive review gate
│   │
│   ├── phase8_publish/
│   │   ├── __init__.py
│   │   ├── thumbnail_gen.py        # FLUX thumbnail + text overlay
│   │   ├── thumbnail_validator.py  # Vision LLM readability check
│   │   ├── seo_assembler.py        # Final SEO metadata
│   │   ├── subtitle_gen.py         # SRT generator (Arabic + English)
│   │   ├── uploader.py             # YouTube API upload
│   │   ├── shorts_gen.py           # YouTube Shorts auto-generator
│   │   └── ab_test.py              # Thumbnail A/B testing
│   │
│   ├── phase9_intelligence/
│   │   ├── __init__.py
│   │   ├── ctr_analyzer.py         # CTR pattern analysis
│   │   ├── watchtime_analyzer.py   # Watch time optimization
│   │   ├── retention_analyzer.py   # Second-by-second retention
│   │   ├── revenue_intel.py        # Revenue pattern discovery
│   │   ├── cross_video.py          # Cross-video pattern mining
│   │   └── reporter.py             # Weekly/monthly reports
│   │
│   ├── agents/                     # Advanced feature agents
│   │   ├── __init__.py
│   │   ├── content_calendar.py
│   │   ├── watch_optimizer.py
│   │   ├── community.py
│   │   ├── trending_hijack.py
│   │   ├── playlist_agent.py
│   │   ├── dubbing_agent.py
│   │   ├── anti_repetition.py
│   │   ├── emotional_arc.py
│   │   ├── voice_emotion.py
│   │   ├── sound_design.py
│   │   ├── presenter.py
│   │   ├── narrative_styles.py
│   │   ├── micro_test.py
│   │   ├── dynamic_length.py
│   │   ├── brand_kit.py
│   │   ├── algo_tracker.py
│   │   ├── ad_placement.py
│   │   ├── sponsorship.py
│   │   ├── repurpose.py
│   │   ├── audience_intel.py
│   │   ├── cross_promo.py
│   │   ├── template_evolver.py
│   │   ├── revenue_optimizer.py
│   │   ├── disaster_recovery.py
│   │   ├── competitor_alert.py
│   │   └── ab_testing.py
│   │
│   └── models/                     # Data models (Pydantic)
│       ├── __init__.py
│       ├── job.py                  # Job model
│       ├── scene.py                # Scene model
│       ├── script.py               # Script model
│       └── analytics.py            # Analytics models
│
├── data/
│   ├── factory.db                  # Main SQLite database
│   ├── audio_fingerprints.db       # Content ID fingerprints
│   ├── seo_cache/                  # Cached keyword research
│   ├── sfx_library/                # Pre-downloaded SFX
│   ├── ambient_library/            # Pre-generated ambient tracks
│   ├── competitor_data/            # Competitor channel cache
│   └── performance_rules/          # Learned optimization rules
│
├── output/                         # Generated content (per job)
│   ├── [job_id]/
│   │   ├── research.json           # Phase 1 output
│   │   ├── seo.json                # Phase 2 output
│   │   ├── script_v1.txt           # Phase 3 output (versions)
│   │   ├── script_v2.txt
│   │   ├── script_approved.txt
│   │   ├── scenes.json             # Scene definitions
│   │   ├── compliance.json         # Phase 4 results
│   │   ├── images/                 # Phase 5a: FLUX images
│   │   │   ├── scene_001.png
│   │   │   ├── scene_001_4k.png    # Upscaled
│   │   │   └── ...
│   │   ├── videos/                 # Phase 5b: LTX clips
│   │   │   ├── scene_001.mp4
│   │   │   └── ...
│   │   ├── audio/
│   │   │   ├── voice/              # Phase 5c: Narration
│   │   │   │   ├── scene_001.wav
│   │   │   │   └── ...
│   │   │   ├── music/              # Phase 5d: Background music
│   │   │   │   ├── intro.wav
│   │   │   │   ├── background.wav
│   │   │   │   ├── tension.wav
│   │   │   │   └── outro.wav
│   │   │   └── sfx/               # Phase 5e: Sound effects
│   │   │       ├── scene_005_explosion.wav
│   │   │       └── ...
│   │   ├── visual_qa.json          # Phase 6 results
│   │   ├── final.mp4               # Phase 5f: Composed video
│   │   ├── final_qa.json           # Phase 7 results
│   │   ├── thumbnails/             # Phase 8: Thumbnails
│   │   │   ├── thumb_A.png
│   │   │   ├── thumb_B.png
│   │   │   └── thumb_C.png
│   │   ├── subtitles/
│   │   │   ├── arabic.srt
│   │   │   └── english.srt
│   │   ├── shorts/                 # Auto-generated Shorts
│   │   │   ├── short_01.mp4
│   │   │   └── ...
│   │   └── metadata.json           # Final YouTube metadata
│   └── seasonal_bank/              # Pre-produced seasonal videos
│
├── logs/
│   ├── gpu/                        # Per-job GPU logs
│   │   ├── [session]_[job].log
│   │   ├── [session]_[job]_events.jsonl
│   │   └── [session]_[job]_vram.csv
│   ├── pipeline/                   # Phase-level logs
│   └── alerts/                     # Critical events
│
└── tests/
    ├── test_database.py
    ├── test_gpu_manager.py
    ├── test_image_gen.py
    ├── test_voice_clone.py
    ├── test_composer.py
    └── test_pipeline_e2e.py
```

---

## 3. Configuration System

### `config/settings.yaml` — Global Settings
```yaml
# ═══════════════════════════════════════════
# AI Video Factory — Global Configuration
# ═══════════════════════════════════════════

factory:
  name: "AI Video Factory"
  version: "1.0.0"
  timezone: "Asia/Baghdad"
  language: "ar"                    # Primary language

# ─── Hardware ──────────────────────────────
gpu:
  device: "cuda:0"
  vram_gb: 24
  safety_margin_gb: 2               # Reserve 2GB for system
  max_temperature_c: 85             # Throttle warning
  monitor_interval_sec: 5

# ─── Ollama (LLM) ─────────────────────────
ollama:
  host: "http://localhost:11434"
  models:
    script: "qwen2.5:72b-instruct-q4_K_M"
    vision: "llama3.2-vision:11b"
  keep_alive: "0"                   # Unload immediately after use
  num_parallel: 1
  timeout_sec: 600                  # 10 min max per LLM call

# ─── ComfyUI (Image/Video Gen) ────────────
comfyui:
  host: "http://localhost:8188"
  workflows_dir: "config/comfyui_workflows/"
  models:
    flux: "flux1-dev.safetensors"
    ltx: "ltx-video-2.3.safetensors"
  loras:
    - "middle_east_architecture.safetensors"
    - "photojournalism.safetensors"
    - "cinematic_lighting.safetensors"

# ─── Voice Cloning ────────────────────────
voice:
  engine: "fish_speech"             # "fish_speech" | "openaudios1" | "xtts"
  model_path: "models/fish_speech_1.5"
  fallback_engine: "elevenlabs"     # API fallback
  elevenlabs_api_key: "${ELEVENLABS_API_KEY}"  # from .env

# ─── Audio Generation ─────────────────────
audio:
  music_model: "facebook/musicgen-large"
  sfx_model: "facebook/audiogen-medium"
  sample_rate: 44100
  music_temperature: 0.9            # Higher = more original
  
# ─── Content ID Protection ────────────────
content_id:
  fingerprint_db: "data/audio_fingerprints.db"
  similarity_threshold_music: 0.15   # < 0.15 = safe
  similarity_threshold_shorts: 0.10  # Stricter for Shorts
  youtube_precheck: true             # Upload unlisted first
  precheck_wait_min: 15

# ─── YouTube API ──────────────────────────
youtube:
  api_key: "${YOUTUBE_API_KEY}"
  client_secrets_file: "config/youtube_client_secret.json"
  quota_daily: 10000
  quota_reserve: 3000                # Keep 3K units in reserve
  
# ─── Telegram ─────────────────────────────
telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  admin_chat_id: "${TELEGRAM_CHAT_ID}"  # Yusif's chat ID
  
# ─── Database ─────────────────────────────
database:
  path: "data/factory.db"
  wal_mode: true
  busy_timeout_ms: 5000

# ─── Pipeline Defaults ────────────────────
pipeline:
  default_target_length_min: 10
  max_script_revisions: 3
  max_image_regenerations: 2
  max_voice_retries: 3
  scene_duration_range: [5, 15]      # seconds
  image_resolution: [1920, 1080]
  video_fps: 24
  video_codec: "h264"
  audio_codec: "aac"
  audio_bitrate: "320k"

# ─── Manual Review ────────────────────────
manual_review:
  enabled: true
  mode: "selective"                  # "all" | "selective" | "off"
  auto_publish_min_score: 8.0
  auto_publish_after_n_videos: 20
  sensitive_categories: ["politics"]
  timeout_hours: 24
  timeout_action: "hold"             # "auto_publish" | "hold" | "cancel"

# ─── Scheduling ───────────────────────────
schedule:
  daily_run_time: "06:00"            # UTC+3
  analytics_intervals: [24, 48, 168, 720]  # hours: 24h, 48h, 7d, 30d
  weekly_report_day: "sunday"
  monthly_report_day: 1
```

### `config/channels.yaml` — Channel Definitions
```yaml
channels:
  - id: "documentary_ar"
    name: "وثائقيات"
    youtube_channel_id: "UC_REPLACE_ME"
    category: "documentary"
    topics: ["history", "science", "culture", "mysteries", "geopolitics"]
    
    voice:
      default_voice_id: "v_male_auth_01"
      allow_voice_switch: false       # Lock to one voice = branding
    
    style:
      visual: "cinematic_photorealistic"
      color_palette: ["#1a1a2e", "#16213e", "#0f3460", "#e94560"]
      lora: "photojournalism.safetensors"
      font_title: "Cairo Bold"
      font_body: "Tajawal Regular"
    
    content:
      tone: "educational, engaging, slightly dramatic"
      target_length_min: [8, 12]      # Range
      language: "MSA"
      narrative_styles: ["investigative", "storytelling", "explainer"]
      script_guidelines: |
        - Use dramatic hooks with rhetorical questions
        - Include surprising facts
        - End with thought-provoking conclusion
        - Minimum 2 emotional peaks per script
    
    brand:
      logo: "config/brands/documentary_ar/logo.png"
      intro: "config/brands/documentary_ar/intro.mp4"
      outro: "config/brands/documentary_ar/outro.mp4"
      watermark: "config/brands/documentary_ar/watermark.png"
      lower_third_style: "glass_blur"
      text_animation: "fade_slide_right"
    
    schedule:
      videos_per_day: 1
      posting_time: "18:00"
      timezone: "Asia/Baghdad"
      shorts_per_video: 3
    
    # More channels follow same structure...
```

### Config Loader (`src/core/config.py`)
```python
"""
Configuration loader.
Reads YAML configs + .env variables.
All other modules import config from here.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

CONFIG_DIR = Path("config")

def load_config() -> dict:
    """Load and merge all config files."""
    # Load global settings
    with open(CONFIG_DIR / "settings.yaml") as f:
        settings = yaml.safe_load(f)
    
    # Load channel definitions
    with open(CONFIG_DIR / "channels.yaml") as f:
        channels = yaml.safe_load(f)
    
    # Load voice library
    with open(CONFIG_DIR / "voices" / "voice_library.yaml") as f:
        voices = yaml.safe_load(f)
    
    # Resolve environment variables (${VAR} → actual value)
    settings = _resolve_env_vars(settings)
    
    return {
        "settings": settings,
        "channels": channels["channels"],
        "voices": voices["voice_library"]
    }

def get_channel_config(channel_id: str) -> dict:
    """Get config for a specific channel."""
    config = load_config()
    for ch in config["channels"]:
        if ch["id"] == channel_id:
            return ch
    raise ValueError(f"Channel not found: {channel_id}")

def _resolve_env_vars(obj):
    """Recursively replace ${VAR} with os.environ[VAR]."""
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        var = obj[2:-1]
        return os.environ.get(var, "")
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    return obj
```

---

## 4. Main Orchestrator (`src/main.py`)

```python
"""
Main Pipeline Orchestrator.
Runs jobs through all 9 phases sequentially.
Handles GPU model swapping, checkpointing, and error recovery.
"""

import logging
from datetime import datetime
from src.core.config import load_config
from src.core.database import FactoryDB
from src.core.gpu_manager import GPUMemoryManager
from src.core.gpu_logger import GPULogger
from src.core.telegram_bot import TelegramBot

# Phase imports
from src.phase1_research import ResearchPhase
from src.phase2_seo import SEOPhase
from src.phase3_script import ScriptPhase
from src.phase4_compliance import CompliancePhase
from src.phase5_production import ProductionPhase
from src.phase6_visual_qa import VisualQAPhase
from src.phase7_video_qa import VideoQAPhase
from src.phase7_5_review import ManualReviewPhase
from src.phase8_publish import PublishPhase
from src.phase9_intelligence import IntelligencePhase

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Main orchestrator. Runs a job through all phases.
    
    Key responsibilities:
    1. Phase sequencing (1 → 2 → 3 → 4 → 5 → 6 → 7 → 7.5 → 8 → 9)
    2. GPU model swapping between phases
    3. Checkpoint/resume on crash
    4. Gate handling (PASS/FAIL/BLOCK)
    5. Telegram notifications
    """
    
    def __init__(self):
        self.config = load_config()
        self.db = FactoryDB(self.config["settings"]["database"]["path"])
        self.gpu = GPUMemoryManager(self.config["settings"]["gpu"])
        self.telegram = TelegramBot(self.config["settings"]["telegram"])
        
    def run_job(self, job_id: str):
        """
        Run a single job through the full pipeline.
        Resumes from last completed phase if previously interrupted.
        """
        job = self.db.get_job(job_id)
        gpu_logger = GPULogger(job_id)
        
        try:
            # ═══════════════════════════════════════════
            # GPU SLOT 1: Qwen 72B (Phases 1-4)
            # ═══════════════════════════════════════════
            if job["status"] in ["pending", "research", "seo", "script", "compliance"]:
                self.gpu.load_model("qwen2.5:72b", model_type="ollama", logger=gpu_logger)
                
                # Phase 1: Research
                if job["status"] in ["pending", "research"]:
                    self.db.update_job_status(job_id, "research")
                    research = ResearchPhase(self.config, self.db)
                    research.run(job_id)
                    
                    # Present topics to user, wait for selection
                    # (handled by topic_presenter → Telegram)
                
                # Phase 2: SEO
                if job["status"] in ["research", "seo"]:
                    self.db.update_job_status(job_id, "seo")
                    seo = SEOPhase(self.config, self.db)
                    seo.run(job_id)
                
                # Phase 3: Script
                if job["status"] in ["seo", "script"]:
                    self.db.update_job_status(job_id, "script")
                    script = ScriptPhase(self.config, self.db)
                    script.run(job_id)  # Write → Review → Split (up to 3 iterations)
                
                # Phase 4: Compliance QA (GATE)
                if job["status"] in ["script", "compliance"]:
                    self.db.update_job_status(job_id, "compliance")
                    compliance = CompliancePhase(self.config, self.db)
                    result = compliance.run(job_id)
                    
                    if result.blocked:
                        self.db.block_job(job_id, "phase4", result.reason)
                        self.telegram.alert(f"⚠️ Script blocked: {result.reason}")
                        return  # Stop — requires human intervention
                
                self.gpu.unload_model(logger=gpu_logger)
            
            # ═══════════════════════════════════════════
            # GPU SLOT 2: FLUX (Phase 5a - Images)
            # ═══════════════════════════════════════════
            if job["status"] in ["compliance", "images"]:
                self.db.update_job_status(job_id, "images")
                self.gpu.load_model("flux", model_type="comfyui", logger=gpu_logger)
                
                production = ProductionPhase(self.config, self.db, self.gpu, gpu_logger)
                production.generate_images(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
            
            # ═══════════════════════════════════════════
            # GPU SLOT 3: Llama Vision (Phase 6 - Visual QA)
            # ═══════════════════════════════════════════
            if job["status"] in ["images", "visual_qa"]:
                self.db.update_job_status(job_id, "visual_qa")
                self.gpu.load_model("llama3.2-vision:11b", model_type="ollama", logger=gpu_logger)
                
                visual_qa = VisualQAPhase(self.config, self.db)
                result = visual_qa.run(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
                
                if result.needs_regeneration:
                    # Reload FLUX, regenerate failed images
                    self.gpu.load_model("flux", model_type="comfyui", logger=gpu_logger)
                    production.regenerate_failed_images(job_id, result.failed_scenes)
                    self.gpu.unload_model(logger=gpu_logger)
                    
                    # Re-check
                    self.gpu.load_model("llama3.2-vision:11b", model_type="ollama", logger=gpu_logger)
                    result = visual_qa.run(job_id)
                    self.gpu.unload_model(logger=gpu_logger)
                
                if result.blocked:
                    self.db.block_job(job_id, "phase6", result.reason)
                    self.telegram.alert(f"⚠️ Visual QA failed: {result.reason}")
                    return
            
            # ═══════════════════════════════════════════
            # GPU SLOT 4: LTX-2.3 (Phase 5b - Video)
            # ═══════════════════════════════════════════
            if job["status"] in ["visual_qa", "video"]:
                self.db.update_job_status(job_id, "video")
                self.gpu.load_model("ltx", model_type="comfyui", logger=gpu_logger)
                
                production.generate_videos(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
            
            # ═══════════════════════════════════════════
            # GPU SLOT 5: Fish Speech (Phase 5c - Voice)
            # ═══════════════════════════════════════════
            if job["status"] in ["video", "voice"]:
                self.db.update_job_status(job_id, "voice")
                self.gpu.load_model("fish_speech", model_type="python", logger=gpu_logger)
                
                production.generate_voice(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
            
            # ═══════════════════════════════════════════
            # GPU SLOT 6: MusicGen (Phase 5d - Music)
            # ═══════════════════════════════════════════
            if job["status"] in ["voice", "music"]:
                self.db.update_job_status(job_id, "music")
                self.gpu.load_model("musicgen", model_type="python", logger=gpu_logger)
                
                production.generate_music(job_id)
                # Content ID check runs here (CPU-based fingerprinting)
                
                self.gpu.unload_model(logger=gpu_logger)
            
            # ═══════════════════════════════════════════
            # GPU SLOT 7: AudioGen (Phase 5e - SFX)
            # ═══════════════════════════════════════════
            if job["status"] in ["music", "sfx"]:
                self.db.update_job_status(job_id, "sfx")
                self.gpu.load_model("audiogen", model_type="python", logger=gpu_logger)
                
                production.generate_sfx(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
            
            # ═══════════════════════════════════════════
            # CPU ONLY: FFmpeg Compose (Phase 5f)
            # ═══════════════════════════════════════════
            if job["status"] in ["sfx", "compose"]:
                self.db.update_job_status(job_id, "compose")
                # No GPU needed
                production.compose_video(job_id)
            
            # ═══════════════════════════════════════════
            # GPU SLOT 8: Qwen 72B (Phase 7 - Final QA)
            # ═══════════════════════════════════════════
            if job["status"] in ["compose", "final_qa"]:
                self.db.update_job_status(job_id, "final_qa")
                self.gpu.load_model("qwen2.5:72b", model_type="ollama", logger=gpu_logger)
                
                final_qa = VideoQAPhase(self.config, self.db)
                result = final_qa.run(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
                
                if result.blocked:
                    self.db.block_job(job_id, "phase7", result.reason)
                    self.telegram.alert(f"⚠️ Final QA failed: {result.reason}")
                    return
            
            # ═══════════════════════════════════════════
            # Phase 7.5: Manual Review (if required)
            # ═══════════════════════════════════════════
            if job["status"] in ["final_qa", "manual_review"]:
                review = ManualReviewPhase(self.config, self.db, self.telegram)
                if review.is_required(job_id):
                    self.db.update_job_status(job_id, "manual_review")
                    review.request_review(job_id)
                    return  # Pauses here — resumes when Yusif responds
            
            # ═══════════════════════════════════════════
            # GPU SLOT 9: FLUX (Phase 8 - Thumbnails)
            # ═══════════════════════════════════════════
            if job["status"] in ["manual_review", "final_qa", "publish"]:
                self.db.update_job_status(job_id, "publish")
                self.gpu.load_model("flux", model_type="comfyui", logger=gpu_logger)
                
                publisher = PublishPhase(self.config, self.db)
                publisher.generate_thumbnails(job_id)
                
                self.gpu.unload_model(logger=gpu_logger)
                
                # CPU: SRT, metadata, upload
                publisher.generate_subtitles(job_id)
                publisher.assemble_metadata(job_id)
                publisher.upload_to_youtube(job_id)
                publisher.generate_shorts(job_id)
                
                self.db.update_job_status(job_id, "published")
                self.telegram.send(f"✅ Published: {job['topic']}")
            
            # ═══════════════════════════════════════════
            # Phase 9: Performance Intelligence (scheduled)
            # ═══════════════════════════════════════════
            # Phase 9 runs on a cron schedule, not inline
            # See: src/phase9_intelligence/
            
        except Exception as e:
            logger.error(f"Pipeline error on job {job_id}: {e}", exc_info=True)
            self.gpu.emergency_cleanup(logger=gpu_logger)
            self.telegram.alert(f"🚨 Pipeline error: {job_id}\n{str(e)[:200]}")
            raise


    def resume_all(self):
        """Resume any interrupted jobs (after crash/restart)."""
        active_jobs = self.db.get_active_jobs()
        for job in active_jobs:
            logger.info(f"Resuming job: {job['id']} from status: {job['status']}")
            self.run_job(job["id"])
```

---

## 5. Database (`src/core/database.py`)

```python
"""
Central database for all agents.
SQLite with WAL mode for concurrent reads.

All 9 phases + 40 feature agents read/write through this class.
See BLUEPRINT.md "Central Database Schema" for full table definitions.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class FactoryDB:
    def __init__(self, db_path: str = "data/factory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        
        self._create_tables()
    
    def _create_tables(self):
        """Create all tables if they don't exist."""
        # Read schema from BLUEPRINT.md or define inline
        # All CREATE TABLE statements from BLUEPRINT.md §Database Schema
        self.conn.executescript(SCHEMA_SQL)
    
    # ─── Job Management ────────────────────────────────
    
    def create_job(self, channel_id: str, topic: str, **kwargs) -> str:
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.conn.execute(
            "INSERT INTO jobs (id, channel_id, topic, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (job_id, channel_id, topic, datetime.now())
        )
        self.conn.commit()
        return job_id
    
    def get_job(self, job_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    
    def update_job_status(self, job_id: str, status: str):
        phase_col = f"phase{status}_completed_at" if status.isdigit() else None
        self.conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(), job_id)
        )
        self.conn.commit()
    
    def block_job(self, job_id: str, phase: str, reason: str):
        self.conn.execute(
            "UPDATE jobs SET status = 'blocked', blocked_at = ?, blocked_phase = ?, blocked_reason = ? WHERE id = ?",
            (datetime.now(), phase, reason, job_id)
        )
        self.conn.commit()
    
    def get_active_jobs(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status NOT IN ('published', 'blocked', 'cancelled') ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
    
    # ─── Scene Management ──────────────────────────────
    
    def save_scenes(self, job_id: str, scenes: list):
        for i, scene in enumerate(scenes):
            self.conn.execute("""
                INSERT INTO scenes (job_id, scene_index, narration_text, duration_sec,
                    visual_prompt, visual_style, camera_movement, expected_elements,
                    music_mood, sfx_tags, text_overlay, presenter_mode, transition_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, i, scene["narration_text"], scene["duration_seconds"],
                scene["visual_prompt"], scene.get("visual_style"),
                scene.get("camera_movement"), json.dumps(scene.get("expected_visual_elements", [])),
                scene.get("music_mood"), json.dumps(scene.get("sfx", [])),
                json.dumps(scene.get("text_overlay")), scene.get("presenter_mode", "none"),
                scene.get("transition_to_next", "crossfade")
            ))
        self.conn.commit()
    
    def get_scenes(self, job_id: str) -> list:
        rows = self.conn.execute(
            "SELECT * FROM scenes WHERE job_id = ? ORDER BY scene_index", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    
    def update_scene_asset(self, job_id: str, scene_index: int, **kwargs):
        """Update generated asset paths for a scene."""
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id, scene_index]
        self.conn.execute(
            f"UPDATE scenes SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE job_id = ? AND scene_index = ?",
            vals
        )
        self.conn.commit()
    
    # ─── Analytics ─────────────────────────────────────
    
    def save_analytics(self, job_id: str, period: str, metrics: dict):
        self.conn.execute("""
            INSERT INTO youtube_analytics (job_id, youtube_video_id, snapshot_period,
                views, watch_time_hours, avg_view_duration_sec, avg_view_percentage,
                likes, comments, shares, impressions, ctr,
                estimated_revenue, rpm, retention_curve, top_countries, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, metrics.get("video_id"), period,
            metrics.get("views"), metrics.get("watch_hours"),
            metrics.get("avg_duration"), metrics.get("avg_percentage"),
            metrics.get("likes"), metrics.get("comments"), metrics.get("shares"),
            metrics.get("impressions"), metrics.get("ctr"),
            metrics.get("revenue"), metrics.get("rpm"),
            json.dumps(metrics.get("retention_curve")),
            json.dumps(metrics.get("countries")),
            datetime.now()
        ))
        self.conn.commit()
    
    # ─── Performance Rules (Phase 9) ──────────────────
    
    def get_active_rules(self, channel_id: str = None) -> list:
        """Get all active performance rules for script/production guidance."""
        query = "SELECT * FROM performance_rules WHERE active = 1"
        params = []
        if channel_id:
            query += " AND (applies_to_channel IS NULL OR applies_to_channel = ?)"
            params.append(channel_id)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    
    # ─── Anti-Repetition ──────────────────────────────
    
    def get_recent_patterns(self, channel_id: str, last_n: int = 10) -> list:
        rows = self.conn.execute(
            "SELECT * FROM anti_repetition WHERE channel_id = ? ORDER BY published_at DESC LIMIT ?",
            (channel_id, last_n)
        ).fetchall()
        return [dict(r) for r in rows]
```

---

## 6. GPU Manager (`src/core/gpu_manager.py`)

```python
"""
GPU Memory Manager for single RTX 3090.
Ensures only ONE model in VRAM at any time.
Full VRAM flush between model swaps.

CRITICAL: In single-GPU setup, a VRAM leak = full pipeline crash.
Every operation is logged via GPULogger.
"""

import gc
import time
import subprocess
import torch
import requests
import logging

logger = logging.getLogger(__name__)


class GPUMemoryManager:
    
    # Expected VRAM per model
    MODEL_VRAM = {
        "qwen2.5:72b":         16.0,   # GB (GPU portion, rest offloads to RAM)
        "llama3.2-vision:11b":  7.0,
        "flux":                 12.0,
        "ltx":                  12.0,
        "fish_speech":           4.0,
        "musicgen":              4.0,
        "audiogen":              4.0,
        "sadtalker":             4.0,
    }
    
    def __init__(self, gpu_config: dict):
        self.device = gpu_config["device"]
        self.total_vram = gpu_config["vram_gb"]
        self.safety_margin = gpu_config["safety_margin_gb"]
        self.current_model = None
        self.current_type = None
        self.ollama_host = None
        self.comfyui_host = None
    
    def set_hosts(self, ollama_host: str, comfyui_host: str):
        self.ollama_host = ollama_host
        self.comfyui_host = comfyui_host
    
    def load_model(self, model_name: str, model_type: str, logger=None):
        """
        Load a model into VRAM.
        Steps: unload current → flush → verify free → load new.
        
        model_type: "ollama" | "comfyui" | "python"
        """
        expected_vram = self.MODEL_VRAM.get(model_name, 8.0)
        
        if logger:
            start = logger.log_model_load_start(model_name, model_type, expected_vram)
        
        try:
            # 1. Unload whatever is currently loaded
            if self.current_model:
                self.unload_model(logger=logger)
            
            # 2. Force VRAM flush
            self._flush_vram()
            
            # 3. Verify VRAM is free
            free = self._get_free_vram()
            if free < expected_vram:
                raise RuntimeError(
                    f"Insufficient VRAM: need {expected_vram}GB, only {free:.1f}GB free"
                )
            
            # 4. Load model
            if model_type == "ollama":
                self._load_ollama(model_name)
            elif model_type == "comfyui":
                self._load_comfyui(model_name)
            elif model_type == "python":
                pass  # Python models loaded by the calling phase
            
            self.current_model = model_name
            self.current_type = model_type
            
            if logger:
                logger.log_model_load_end(model_name, start, success=True)
                
        except Exception as e:
            if logger:
                logger.log_model_load_end(model_name, start, success=False)
            raise
    
    def unload_model(self, logger=None):
        """Unload current model and free all VRAM."""
        if not self.current_model:
            return
        
        if logger:
            start = logger.log_model_unload_start(self.current_model)
        
        model_name = self.current_model
        
        # Type-specific unloading
        if self.current_type == "ollama":
            self._unload_ollama(model_name)
        elif self.current_type == "comfyui":
            self._unload_comfyui()
        
        # Force cleanup
        self._flush_vram()
        self.current_model = None
        self.current_type = None
        
        # Wait and verify
        time.sleep(2)
        free = self._get_free_vram()
        
        if logger:
            logger.log_model_unload_end(model_name, start)
            
            # Leak detection
            if free < (self.total_vram - self.safety_margin - 1):
                logger.log_vram_flush("leak_detected_post_unload", 
                                     self.total_vram - free, self._get_free_vram())
    
    def emergency_cleanup(self, logger=None):
        """Nuclear option: kill everything and reset GPU."""
        if logger:
            logger.log_gpu_reset("emergency_cleanup")
        
        self.current_model = None
        self.current_type = None
        
        # Kill Ollama
        subprocess.run(["ollama", "stop"], capture_output=True, timeout=10)
        
        # Flush PyTorch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        gc.collect()
        
        time.sleep(3)
    
    # ─── Internal Methods ──────────────────────────────
    
    def _flush_vram(self):
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        gc.collect()
    
    def _get_free_vram(self) -> float:
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return free / 1e9
        return 0.0
    
    def _load_ollama(self, model_name: str):
        """Warm up Ollama model (loads into VRAM)."""
        resp = requests.post(f"{self.ollama_host}/api/generate", json={
            "model": model_name,
            "prompt": "test",
            "options": {"num_predict": 1}
        }, timeout=120)
        resp.raise_for_status()
    
    def _unload_ollama(self, model_name: str):
        """Tell Ollama to unload model from VRAM."""
        try:
            requests.post(f"{self.ollama_host}/api/generate", json={
                "model": model_name,
                "keep_alive": 0
            }, timeout=30)
        except:
            pass
    
    def _load_comfyui(self, model_name: str):
        """ComfyUI loads models on first prompt — just verify server is up."""
        resp = requests.get(f"{self.comfyui_host}/system_stats", timeout=10)
        resp.raise_for_status()
    
    def _unload_comfyui(self):
        """Tell ComfyUI to free all models from VRAM."""
        try:
            requests.post(f"{self.comfyui_host}/free", json={
                "unload_models": True,
                "free_memory": True
            }, timeout=30)
        except:
            pass
```

---

## 7. Phase Interfaces

Every phase follows the same interface pattern:

```python
"""
Phase Interface — all phases implement this pattern.
"""

from abc import ABC, abstractmethod
from src.core.database import FactoryDB
from dataclasses import dataclass


@dataclass
class PhaseResult:
    success: bool
    blocked: bool = False
    reason: str = ""
    needs_regeneration: bool = False
    failed_scenes: list = None
    score: float = 0.0


class BasePhase(ABC):
    def __init__(self, config: dict, db: FactoryDB):
        self.config = config
        self.db = db
    
    @abstractmethod
    def run(self, job_id: str) -> PhaseResult:
        """Execute this phase for the given job."""
        pass
```

### Phase-by-Phase Build Guide

Each phase is a self-contained module. Build and test independently.

#### Phase 1: Research (`src/phase1_research/`)
```
Input:  None (or manual topic from Telegram)
Output: Ranked topic list → DB: research table
LLM:    Qwen 72B (already loaded in GPU Slot 1)
APIs:   YouTube Data API v3, pytrends, feedparser

Files to build:
├── youtube_trends.py
│   ├── get_trending(region_codes: list) → list[dict]
│   │   Uses: youtube.videos().list(chart="mostPopular")
│   │   Returns: [{title, views, channel, category, published_at}]
│   │
│   └── get_competitor_uploads(channel_ids: list, days: int) → list[dict]
│       Uses: youtube.search().list(channelId=..., order="date")
│       Returns: [{title, views, channel_name, topic_extracted}]
│
├── web_trends.py
│   ├── get_google_trends(keywords: list, regions: list) → list[dict]
│   │   Uses: pytrends.interest_over_time()
│   │   Returns: [{keyword, region, interest_score, trend_direction}]
│   │
│   └── get_news_topics(rss_feeds: list) → list[dict]
│       Uses: feedparser.parse(feed_url)
│       Returns: [{title, source, published, summary}]
│
├── topic_ranker.py
│   └── rank_topics(youtube_data, web_data, channel_config) → list[dict]
│       Uses: Qwen 72B to analyze + score
│       Scoring: search_volume * 0.3 + competition_inv * 0.25 + 
│                trend_velocity * 0.25 + category_match * 0.2
│       Returns: [{topic, score, suggested_channel, suggested_angle, sources}]
│
└── topic_presenter.py
    └── present_to_user(ranked_topics: list) → str  # selected topic
        Uses: Telegram Bot — sends inline keyboard with top 10 topics
        Waits: For user to tap a topic button
        Returns: selected topic string
```

#### Phase 2: SEO (`src/phase2_seo/`)
```
Input:  Selected topic (from DB: jobs.topic)
Output: SEO package → DB: seo_data table
LLM:    Qwen 72B (still loaded from Phase 1)
APIs:   YouTube Data API v3, yt-dlp

Files to build:
├── keyword_research.py
│   ├── get_autocomplete(query: str) → list[str]
│   │   Uses: YouTube suggest API (GET http://suggestqueries.google.com/...)
│   │   Returns: ["فنزويلا انهيار", "فنزويلا اقتصاد", ...]
│   │
│   └── analyze_top_results(query: str, limit: int = 20) → dict
│       Uses: youtube.search().list(q=query, order="viewCount")
│       Extracts: titles, tags (via yt-dlp), descriptions, view counts
│       Returns: {keywords: [...], title_patterns: [...], avg_views: int}
│
├── competitor_analysis.py
│   └── find_content_gap(topic: str, competitors: list) → dict
│       Uses: Qwen 72B analyzes competitor titles/descriptions
│       Returns: {unique_angles: [...], unanswered_questions: [...]}
│
├── title_generator.py
│   └── generate_titles(topic, keywords, gap_analysis) → list[dict]
│       Uses: Qwen 72B generates 10 titles
│       Scoring: keyword_density * 0.3 + emotional_hook * 0.3 + 
│                length_optimal * 0.2 + uniqueness * 0.2
│       Returns: [{title, score, keywords_included}]  # sorted by score
│
└── tag_planner.py
    └── plan_tags_description(topic, keywords, title) → dict
        Uses: Qwen 72B
        Returns: {
            tags: [...],  # 30 tags
            description_template: str,
            hashtags: [...]  # 3-5
        }
```

#### Phase 3: Script (`src/phase3_script/`)
```
Input:  SEO data + topic (from DB)
Output: Approved script + scenes JSON → DB: scripts + scenes tables
LLM:    Qwen 72B (still loaded)

Files to build:
├── researcher.py
│   └── research_topic(topic: str, angle: str) → str
│       Uses: Brave Search API (or web_search tool) → gather 5-10 sources
│       Uses: Qwen 72B to synthesize into research document
│       Returns: research_text (2000-5000 words with citations)
│
├── writer.py
│   └── write_script(research: str, seo: dict, channel: dict, rules: list) → str
│       Uses: Qwen 72B with structured prompt
│       Inputs include: performance_rules from Phase 9 (DB)
│       Inputs include: anti_repetition patterns (DB)
│       Inputs include: narrative_style selection
│       Returns: full Arabic script (1200-1800 words)
│       
│       PROMPT STRUCTURE:
│       """
│       أنت كاتب سكربتات وثائقية عربية محترف.
│       
│       الموضوع: {topic}
│       الزاوية: {angle}
│       القناة: {channel.name} — {channel.content.tone}
│       الأسلوب السردي: {narrative_style}
│       الكلمات المفتاحية (يجب تضمينها بشكل طبيعي): {keywords}
│       العنوان المختار: {title}
│       
│       قواعد مستفادة من أداء الفيديوهات السابقة:
│       {performance_rules}
│       
│       البحث المرجعي:
│       {research_text}
│       
│       اكتب سكربت كامل بالعربية الفصحى...
│       """
│
├── reviewer.py
│   └── review_script(script: str, research: str, seo: dict) → ReviewResult
│       Uses: Qwen 72B (separate prompt — acts as critic)
│       Checks: factual accuracy, engagement, keywords, pacing, grammar
│       Returns: ReviewResult(approved: bool, notes: str, scores: dict)
│       
│       If not approved → returns to writer with notes (max 3 iterations)
│
└── splitter.py
    └── split_to_scenes(script: str, channel: dict) → list[dict]
        Uses: Qwen 72B
        Returns: list of scene dicts matching this schema:
        {
            "scene_index": int,
            "narration_text": str,
            "duration_seconds": float,
            "visual_prompt": str,          # English, for FLUX
            "visual_style": str,
            "camera_movement": str,
            "music_mood": str,
            "sfx": list[str],
            "text_overlay": dict | null,
            "expected_visual_elements": list[str],
            "transition_to_next": str,
            "presenter_mode": str,         # "pip" | "fullscreen" | "none"
            "voice_emotion": str           # "dramatic" | "calm" | etc.
        }
        
        IMPORTANT: visual_prompt must be in English (FLUX works best in English)
        IMPORTANT: visual_prompt must include regional accuracy tags
                   (see image_prompt.py for enhancement)
```

#### Phase 4: Compliance (`src/phase4_compliance/`)
```
Input:  Script + scenes (from DB)
Output: Pass/Fail/Block → DB: compliance_checks table
LLM:    Qwen 72B (still loaded)
GATE:   Can BLOCK the job

Files to build:
├── youtube_policy.py     → Check script vs YouTube ToS
├── ai_content_check.py   → Score: is this high-effort content? (min 7/10)
├── copyright_check.py    → Check for plagiarized text
├── fact_checker.py       → Verify claims against sources (2+ sources each)
└── arabic_quality.py     → MSA grammar + TTS pronunciation friendliness
```

#### Phase 5: Production (`src/phase5_production/`)
```
This is the largest phase. Each sub-module handles one media type.
GPU models are swapped between sub-modules (see main.py GPU slots).

├── image_prompt.py
│   └── enhance_prompt(raw_prompt: str, region: str, channel: dict) → tuple[str, str]
│       Adds: regional accuracy tags, style modifiers, LoRA triggers
│       Returns: (enhanced_prompt, negative_prompt)
│
├── image_gen.py
│   └── generate_images(job_id: str, scenes: list) → None
│       Uses: ComfyUI API → FLUX workflow
│       Per scene: generate 2 variations → LLM picks best (via Ollama in next slot)
│       Saves: scene image paths to DB
│       Config: resolution from settings, LoRA from channel config
│
├── video_gen.py
│   └── generate_videos(job_id: str, scenes: list) → None
│       Uses: ComfyUI API → LTX-2.3 workflow (image-to-video)
│       Input: approved image + visual_prompt + camera_movement
│       Fallback: if LTX fails → Ken Burns via FFmpeg
│       Saves: scene video paths to DB
│
├── voice_clone.py  (ONE-TIME SETUP)
│   └── clone_voice(reference_wav: str, voice_id: str) → None
│       Uses: Fish Speech 1.5
│       Steps: denoise → normalize → create embedding → test → save
│       Output: .pt embedding file in config/voices/embeddings/
│
├── voice_selector.py
│   └── select_voice(job: dict, channel: dict) → str
│       Logic: channel default > content match > emotion range > quality score
│       Returns: voice_id
│
├── voice_gen.py
│   └── generate_voice(job_id: str, scenes: list, voice_id: str) → None
│       Uses: Fish Speech 1.5 + clone embedding
│       Per scene: narration_text + voice_emotion → WAV
│       Quality check: pronunciation + glitch detection
│       Saves: scene voice paths to DB
│
├── music_gen.py
│   └── generate_music(job_id: str, scenes: list) → None
│       Uses: audiocraft.MusicGen
│       Generates: intro, background, tension, outro tracks
│       CRITICAL: negative prompts for originality (see BLUEPRINT §5.4)
│       Saves: track paths to DB: audio_tracks table
│
├── sfx_gen.py
│   └── generate_sfx(job_id: str, scenes: list) → None
│       Uses: audiocraft.AudioGen
│       Per scene: generate SFX from sfx tags
│       Fallback: pre-downloaded library in data/sfx_library/
│
├── content_id_guard.py  (runs after music_gen)
│   └── check_audio(track_path: str) → ContentIDResult
│       Layer 1: fingerprint vs local DB
│       Layer 2: spectral analysis (librosa)
│       Layer 3: similarity score threshold
│       If fail → regenerate with different seed
│
├── upscaler.py (CPU — can run parallel)
│   └── upscale_image(input_path: str, output_path: str) → None
│       Uses: Real-ESRGAN (CPU mode)
│       1080p → 4K
│
└── composer.py
    └── compose_video(job_id: str) → str
        Uses: FFmpeg + MoviePy + Pillow
        Steps:
        1. Sequence video clips by scene order
        2. Overlay narration audio (100% vol)
        3. Mix background music (20-30%, auto-duck)
        4. Add SFX at timestamps (40-60%)
        5. Apply transitions (crossfade/cut)
        6. Render Arabic text overlays (Pillow → FFmpeg)
           - Font: Cairo/Tajawal (from config/fonts/)
           - Style: background blur + text animation
        7. Add intro/outro (from channel brand kit)
        8. Render final MP4 (H.264, AAC 320kbps)
        Returns: path to final.mp4
```

#### Phase 6: Visual QA (`src/phase6_visual_qa/`)
```
Input:  Generated images (from DB: scenes.image_path)
Output: Pass/Fail per image → DB: scenes.image_score
LLM:    Llama 3.2 Vision 11B
GATE:   Can block or trigger regeneration

Files to build:
├── image_checker.py
│   └── check_image(image_path: str, scene: dict) → ImageCheckResult
│       Uses: Ollama + llama3.2-vision
│       Prompt: "Does this image match: {visual_prompt}? 
│               Expected elements: {expected_elements}. Score 1-10."
│       Returns: ImageCheckResult(score, matches_prompt, has_nsfw, quality_ok)
│
├── style_checker.py
│   └── check_consistency(image_paths: list) → float
│       Compares color palettes, style across all images
│       Returns: consistency_score (0-1)
│
└── sequence_checker.py
    └── check_flow(image_paths: list, scenes: list) → FlowResult
        Checks: visual story makes sense in order
        Returns: FlowResult(score, jarring_transitions: list)
```

#### Phase 7: Final QA (`src/phase7_video_qa/`)
```
Input:  Composed video (output/[job_id]/final.mp4)
Output: Pass/Fail → DB: compliance_checks table
LLM:    Qwen 72B (for content check)
GATE:   Can block

Files to build:
├── technical_check.py    → A/V sync, duration, resolution, bitrate, file integrity
│   Uses: ffprobe (part of FFmpeg) — no GPU needed
│
├── content_check.py      → Extract frames → Qwen checks narration-visual alignment
└── final_compliance.py   → One last YouTube policy sweep
```

#### Phase 8: Publish (`src/phase8_publish/`)
```
Input:  Final video + SEO data + scenes
Output: YouTube upload + Shorts + SRT
APIs:   YouTube Data API v3

Files to build:
├── thumbnail_gen.py       → FLUX generates 3 variants (GPU Slot 9)
├── thumbnail_validator.py → Vision LLM checks readability at mobile size
├── seo_assembler.py       → Combine: title + desc + tags + timestamps + hashtags
├── subtitle_gen.py        → SRT from scene narration text + timing
├── uploader.py            → YouTube API: upload video, set metadata, add captions
├── shorts_gen.py          → Extract 3-5 best moments → crop 9:16 → add subtitles
└── ab_test.py             → Upload 3 thumbnails to YouTube Test & Compare
```

#### Phase 9: Intelligence (`src/phase9_intelligence/`)
```
Runs on CRON schedule, not inline with pipeline.
Pulls YouTube Analytics API data and feeds back to all phases.

Schedule: 24h, 48h, 7d, 30d after each publish + weekly + monthly

Files to build:
├── ctr_analyzer.py        → Which titles/thumbnails get highest CTR
├── watchtime_analyzer.py  → Optimal video length per category
├── retention_analyzer.py  → Drop-off points → scene-level analysis
├── revenue_intel.py       → RPM patterns → topic/length/time optimization
├── cross_video.py         → Pattern mining across all published videos
└── reporter.py            → Weekly/monthly Telegram reports
```

---

## 8. Data Models (`src/models/`)

```python
# src/models/scene.py
from pydantic import BaseModel, Field
from typing import Optional

class TextOverlay(BaseModel):
    text: str
    style: str = "fact"              # "fact_date" | "section_header" | "quote" | "stat"
    position: str = "bottom_center"  # "top_left" | "center" | "bottom_right" | etc.
    animation: str = "fade_slide"    # "fade" | "slide" | "typewriter"

class Scene(BaseModel):
    scene_index: int
    narration_text: str
    duration_seconds: float = Field(ge=3, le=20)
    visual_prompt: str               # English — for FLUX
    visual_style: str = "photorealistic_cinematic"
    camera_movement: str = "slow_zoom_in"
    music_mood: str = "dramatic"
    sfx: list[str] = []
    text_overlay: Optional[TextOverlay] = None
    expected_visual_elements: list[str] = []
    transition_to_next: str = "crossfade"
    presenter_mode: str = "none"     # "pip" | "fullscreen" | "none"
    voice_emotion: str = "calm"      # "dramatic" | "mysterious" | "urgent" | etc.
    
    # Generated asset paths (filled during production)
    image_path: Optional[str] = None
    image_upscaled_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    voice_path: Optional[str] = None
    image_score: Optional[float] = None


# src/models/job.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Job(BaseModel):
    id: str
    status: str = "pending"
    channel_id: str
    topic: str
    topic_region: str = "global"     # "iraq" | "gulf" | "egypt" | "levant" | "maghreb"
    narrative_style: Optional[str] = None
    selected_voice_id: Optional[str] = None
    target_length_min: Optional[int] = None
    priority: str = "normal"
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None
    created_at: datetime = datetime.now()
```

---

## 9. Dependencies (`requirements.txt`)

```
# ═══ Core ═══
pyyaml>=6.0
pydantic>=2.0
python-dotenv>=1.0
apscheduler>=3.10

# ═══ Database ═══
# sqlite3 is built-in

# ═══ LLM ═══
ollama>=0.3               # Ollama Python client
requests>=2.31            # For ComfyUI API

# ═══ YouTube ═══
google-api-python-client>=2.100
google-auth-oauthlib>=1.1
yt-dlp>=2024.1            # Metadata extraction only

# ═══ Trends & Research ═══
pytrends>=4.9             # Google Trends
feedparser>=6.0           # RSS feeds
praw>=7.7                 # Reddit API (optional)

# ═══ AI Models ═══
torch>=2.1
torchaudio>=2.1
transformers>=4.36
audiocraft>=1.3           # MusicGen + AudioGen
# fish-speech             # Install separately from GitHub

# ═══ Image/Video Processing ═══
Pillow>=10.0              # Arabic text rendering
moviepy>=1.0              # Video editing helper
numpy>=1.24

# ═══ Audio Processing ═══
librosa>=0.10             # Spectral analysis (Content ID)
noisereduce>=3.0          # Voice recording denoising
soundfile>=0.12
chromaprint                # Audio fingerprinting (optional)

# ═══ Upscaling ═══
realesrgan>=0.3           # 4K upscaling (CPU)

# ═══ Telegram ═══
python-telegram-bot>=20.0

# ═══ Logging ═══
rich>=13.0                # Pretty console output

# ═══ Testing ═══
pytest>=7.0
pytest-asyncio>=0.21
```

---

## 10. Build Order (Sprint-by-Sprint)

### Sprint 1: Foundation (Week 1-2)
```
BUILD IN THIS ORDER:

1. src/core/config.py          — Config loader
2. src/core/database.py        — SQLite schema + FactoryDB class
3. src/core/gpu_manager.py     — GPU memory manager
4. src/core/gpu_logger.py      — GPU logging
5. src/models/*.py             — Pydantic data models
6. src/core/telegram_bot.py    — Basic send/receive
7. src/core/retry.py           — Retry decorator

TEST:
- Load config ✓
- Create DB tables ✓
- GPU load/unload cycle ✓
- Telegram send message ✓

THEN:
8. Install Ollama + Qwen 2.5 72B Q4
9. Install ComfyUI + FLUX + LTX-2.3
10. Install Fish Speech 1.5
11. Install audiocraft (MusicGen + AudioGen)

TEST:
- Ollama: generate Arabic text ✓
- ComfyUI: generate 1 image ✓
- Fish Speech: clone 1 voice + generate 1 sentence ✓
- MusicGen: generate 15 sec music ✓

12. src/phase5_production/composer.py  — FFmpeg assembly
TEST: manual images + manual voice → composed video ✓
```

### Sprint 2: Script + SEO (Week 3)
```
BUILD:
1. src/phase1_research/youtube_trends.py
2. src/phase1_research/web_trends.py
3. src/phase1_research/topic_ranker.py
4. src/phase1_research/topic_presenter.py
5. src/phase2_seo/keyword_research.py
6. src/phase2_seo/competitor_analysis.py
7. src/phase2_seo/title_generator.py
8. src/phase2_seo/tag_planner.py
9. src/phase3_script/researcher.py
10. src/phase3_script/writer.py
11. src/phase3_script/reviewer.py
12. src/phase3_script/splitter.py

TEST: topic → SEO → script → scenes.json ✓
```

### Sprint 3: Production Pipeline (Week 4-5)
```
BUILD:
1. src/phase5_production/image_prompt.py
2. src/phase5_production/image_gen.py
3. src/phase5_production/video_gen.py
4. src/phase5_production/voice_clone.py     (one-time setup)
5. src/phase5_production/voice_selector.py
6. src/phase5_production/voice_gen.py
7. src/phase5_production/music_gen.py
8. src/phase5_production/sfx_gen.py
9. src/phase5_production/composer.py        (enhance from Sprint 1)

TEST: scenes.json → images → videos → voice → music → sfx → final.mp4 ✓
```

### Sprint 4: QA Gates (Week 6)
```
BUILD:
1. src/phase4_compliance/*.py
2. src/phase6_visual_qa/*.py
3. src/phase7_video_qa/*.py
4. src/phase7_5_review/manual_review.py

TEST: bad script → blocked ✓
TEST: bad image → regenerated ✓
TEST: final video → QA pass ✓
TEST: manual review via Telegram ✓
```

### Sprint 5: Publishing (Week 7)
```
BUILD:
1. src/phase8_publish/thumbnail_gen.py
2. src/phase8_publish/thumbnail_validator.py
3. src/phase8_publish/seo_assembler.py
4. src/phase8_publish/subtitle_gen.py
5. src/phase8_publish/uploader.py
6. src/phase8_publish/shorts_gen.py
7. src/phase8_publish/ab_test.py
8. src/main.py                              (full orchestrator)

TEST: full pipeline end-to-end → YouTube upload ✓
```

### Sprint 6-12: Advanced Features
```
See BLUEPRINT.md "Implementation Order" for Sprints 6-12.
Build features in priority order.
Each feature is an independent agent in src/agents/.
```

---

## 11. Environment Setup

### `.env.example`
```bash
# YouTube
YOUTUBE_API_KEY=your_youtube_api_key
YOUTUBE_CLIENT_SECRET=path/to/client_secret.json

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# ElevenLabs (optional fallback)
ELEVENLABS_API_KEY=your_key

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_KEEP_ALIVE=0
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1

# ComfyUI
COMFYUI_HOST=http://localhost:8188
```

### First Run Checklist
```bash
# 1. Clone repo
git clone https://github.com/Youssef-Durgham/ai-video-factory.git
cd ai-video-factory

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env
cp .env.example .env
# Edit .env with your API keys

# 5. Install Ollama + models
ollama pull qwen2.5:72b-instruct-q4_K_M
ollama pull llama3.2-vision:11b

# 6. Install ComfyUI (separate process)
# Follow: https://github.com/comfyanonymous/ComfyUI
# Download FLUX.1-dev + LTX-2.3 models into ComfyUI/models/

# 7. Install Fish Speech 1.5
# Follow: https://github.com/fishaudio/fish-speech

# 8. Create directories
mkdir -p data output logs/gpu logs/pipeline logs/alerts config/voices/embeddings

# 9. Initialize database
python -c "from src.core.database import FactoryDB; FactoryDB()"

# 10. Clone voices (one-time)
python -m src.phase5_production.voice_clone --input config/voices/male_authoritative_01.wav --id v_male_auth_01

# 11. Test pipeline
python -m src.cli test-gpu          # Test GPU load/unload
python -m src.cli test-voice        # Test voice generation
python -m src.cli test-image        # Test image generation
python -m src.cli run --topic "test" --channel documentary_ar  # Full test
```

---

## 12. Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Database | SQLite (not Postgres) | Single machine, no network overhead, WAL handles concurrent reads |
| GPU scheduling | Sequential (not parallel) | Single GPU — can't run 2 models simultaneously |
| LLM hosting | Ollama (not raw transformers) | Easy model management, API interface, memory control via keep_alive=0 |
| Image gen | ComfyUI (not diffusers) | Workflow-based, supports LoRA, easy model swapping, web UI for debugging |
| Voice | Fish Speech 1.5 clone (not from-scratch TTS) | Real human voice recordings cloned = natural Arabic pronunciation |
| Config | YAML (not JSON/TOML) | Readable, supports comments, good for multi-line strings (script guidelines) |
| Error handling | Checkpoint + resume (not restart) | 3-hour pipeline — can't restart from scratch on every error |
| Notifications | Telegram (not email/SMS) | Instant, interactive (inline buttons), free, Yusif already uses it |
| Phase 9 | Cron-based (not inline) | Analytics data isn't available immediately — needs 24h+ delay |
| Manual review | Selective (not always) | High-quality videos auto-publish; only flag edge cases |

---

## 13. Critical Rules for AI Builder

1. **NEVER load 2 GPU models simultaneously.** Always unload → flush → verify → load.
2. **ALWAYS write to DB before starting a phase.** This enables crash recovery.
3. **ALWAYS use English for FLUX/LTX prompts.** Arabic visual prompts produce garbage.
4. **ALWAYS include negative prompts** for images: "text, writing, letters, watermark"
5. **ALWAYS check VRAM after unload.** If >15% still used = leak. Log it.
6. **NEVER hardcode paths.** Everything comes from config/settings.yaml.
7. **NEVER use unofficial YouTube APIs for data that matters.** Official API only.
8. **ALWAYS test voice clone quality** before using in production. Score must be >6/10.
9. **ALWAYS run Content ID check** on generated music before composing into video.
10. **ALWAYS save intermediate outputs to disk** (not just DB). Pipeline must be resumable.
