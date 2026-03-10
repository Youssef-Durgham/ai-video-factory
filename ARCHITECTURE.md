# AI Video Factory — System Architecture (Build Guide)

> **هذا الملف للـ AI Builder.** يحتوي على كل التفاصيل التقنية اللازمة لبناء النظام.
> اقرأ `BLUEPRINT.md` أولاً لفهم المنتج، ثم ارجع هنا للبناء.

---

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          AI VIDEO FACTORY                                │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  ORCHESTRATION LAYER                                               │  │
│  │  PipelineRunner │ JobStateManager │ GateEvaluator │ EventBus      │  │
│  └────────────────────────────┬───────────────────────────────────────┘  │
│                               │ events                                   │
│  ┌────────────────────────────▼───────────────────────────────────────┐  │
│  │  PHASE EXECUTION LAYER (PhaseExecutor)                             │  │
│  │                                                                    │  │
│  │  Phase 1    Phase 2    Phase 3    Phase 4 ✅                       │  │
│  │  Research → SEO      → Script   → Compliance                      │  │
│  │                                       │ PASS                       │  │
│  │  Phase 8    Phase 7 ✅  Phase 6 ✅     Phase 5 (sub-pipeline)      │  │
│  │  Publish ← Final QA ← Visual QA ← ┌──────────────────────┐      │  │
│  │     │                               │ AssetCoordinator     │      │  │
│  │     │       Phase 7.5 ✅             │  ├─ ImageGen         │      │  │
│  │     │       Manual Review            │  ├─ VideoGen         │      │  │
│  │     ▼                               │  ├─ AudioCoordinator │      │  │
│  │  Phase 9 ← (cron)                  │  │   ├─ VoiceGen     │      │  │
│  │  Intelligence                       │  │   ├─ MusicGen     │      │  │
│  │                                     │  │   └─ SFXGen       │      │  │
│  │                                     │  └─ VideoComposer    │      │  │
│  │                                     └──────────────────────┘      │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  INFRASTRUCTURE LAYER                                              │  │
│  │  ResourceCoordinator (GPU) │ FactoryDB │ EventStore │ TelegramBot │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  AGENTS LAYER                                                      │  │
│  │  core_agents/          │ optimization_agents/  │ experimental/     │  │
│  │  (anti_repetition,     │ (watch_optimizer,     │ (sponsorship,     │  │
│  │   content_calendar,    │  revenue_optimizer,   │  cross_promo,     │  │
│  │   community)           │  algo_tracker)        │  dubbing)         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
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
│   │   ├── pipeline_runner.py      # Thin coordinator (see §4.6)
│   │   ├── phase_executor.py       # Phase → handler mapping (see §4.7)
│   │   ├── job_state_machine.py    # Formal FSM + transitions (see §4.2)
│   │   ├── gate_evaluator.py       # QA gate evaluation (see §4.3)
│   │   ├── resource_coordinator.py # GPU lifecycle orchestration (see §4.4)
│   │   ├── event_bus.py            # In-process pub/sub events (see §4.5)
│   │   ├── event_store.py          # Persistent event log (see §4.5)
│   │   ├── gpu_manager.py          # Low-level GPU memory (see §6)
│   │   ├── gpu_logger.py           # GPU precision logging (see §6)
│   │   ├── scheduler.py            # Job scheduler (APScheduler)
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
│   │   ├── __init__.py             # Exports: AssetCoordinator, AudioCoordinator, VideoComposer
│   │   ├── asset_coordinator.py    # Visual sub-pipeline: images + video
│   │   ├── audio_coordinator.py    # Audio sub-pipeline: voice + music + SFX
│   │   ├── video_composer.py       # FFmpeg assembly sub-pipeline
│   │   ├── image_gen.py            # FLUX image generation
│   │   ├── image_prompt.py         # Arabic content prompt enhancement
│   │   ├── video_gen.py            # LTX-2.3 video generation
│   │   ├── voice_clone.py          # Voice cloning (one-time setup)
│   │   ├── voice_gen.py            # TTS with cloned voice
│   │   ├── voice_selector.py       # Smart voice selection agent
│   │   ├── music_gen.py            # MusicGen background music
│   │   ├── sfx_gen.py              # AudioGen sound effects
│   │   ├── content_id_guard.py     # Audio fingerprint protection
│   │   └── upscaler.py             # Real-ESRGAN 4K upscale
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
│   ├── agents/
│   │   ├── __init__.py
│   │   │
│   │   ├── core_agents/            # 🔴 Production-critical (Sprint 6-7)
│   │   │   ├── __init__.py
│   │   │   ├── anti_repetition.py  # Prevents pattern fatigue
│   │   │   ├── content_calendar.py # Weekly planning
│   │   │   ├── community.py       # Comment engagement
│   │   │   ├── emotional_arc.py   # Script emotion mapping
│   │   │   ├── narrative_styles.py # Style library + selection
│   │   │   ├── dynamic_length.py  # Optimal video length
│   │   │   ├── brand_kit.py       # Visual identity enforcement
│   │   │   ├── voice_emotion.py   # Per-scene TTS emotion
│   │   │   └── sound_design.py    # Cinematic audio layering
│   │   │
│   │   ├── optimization_agents/    # 🟡 Improves performance (Sprint 8-10)
│   │   │   ├── __init__.py
│   │   │   ├── watch_optimizer.py  # Retention analysis → feedback
│   │   │   ├── revenue_optimizer.py# RPM tracking + adjustments
│   │   │   ├── algo_tracker.py    # YouTube algorithm monitoring
│   │   │   ├── ad_placement.py    # Smart mid-roll positions
│   │   │   ├── template_evolver.py # Script template learning
│   │   │   ├── playlist_agent.py  # Series clustering
│   │   │   ├── competitor_alert.py # Real-time monitoring
│   │   │   ├── trending_hijack.py # Breaking news fast-track
│   │   │   └── micro_test.py      # Hook testing before publish
│   │   │
│   │   └── experimental_agents/    # 🟢 Future/nice-to-have (Sprint 11-12)
│   │       ├── __init__.py
│   │       ├── dubbing_agent.py   # Multi-language dubbing
│   │       ├── cross_promo.py     # Cross-channel promotion
│   │       ├── sponsorship.py     # Sponsor integration
│   │       ├── repurpose.py       # Multi-platform repurposing
│   │       ├── audience_intel.py  # Audience profiling
│   │       ├── presenter.py       # AI virtual presenter
│   │       ├── disaster_recovery.py # Backup + strike protocol
│   │       └── ab_testing.py      # A/B script testing
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

## 4. Orchestration Layer (Decomposed — NOT God Object)

> **Problem:** A single `Pipeline` class handling sequencing, GPU, state, gates, notifications, and resume
> is a God Orchestrator. Hard to test, maintain, and extend.
>
> **Solution:** Decompose into 5 focused components + an event system.

### 4.1 Component Decomposition

```
src/core/
├── pipeline_runner.py       # High-level: "run this job"
├── phase_executor.py        # Executes a single phase
├── gate_evaluator.py        # Evaluates QA gates (pass/fail/block)
├── job_state_machine.py     # Formal state machine for job status
├── resource_coordinator.py  # GPU model loading/unloading orchestration
├── event_bus.py             # Internal event system
└── event_store.py           # Persistent event log (SQLite table)
```

```
┌─────────────────────────────────────────────────────────────┐
│                     PipelineRunner                           │
│  "Run job X" — thin coordinator, delegates everything        │
│                                                             │
│  Uses:                                                      │
│  ├── JobStateMachine    → "what's the next valid state?"    │
│  ├── PhaseExecutor      → "execute phase Y for job X"      │
│  ├── GateEvaluator      → "did the gate pass?"             │
│  ├── ResourceCoordinator → "load/unload GPU model"          │
│  └── EventBus           → "emit PHASE_COMPLETED event"     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Job State Machine (`src/core/job_state_machine.py`)

**Formal finite state machine — prevents invalid transitions.**

```python
"""
Formal state machine for job lifecycle.
Every status transition must be explicitly defined here.
Invalid transitions raise StateError — prevents bugs.
"""

from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    PENDING       = "pending"
    RESEARCH      = "research"
    SEO           = "seo"
    SCRIPT        = "script"
    COMPLIANCE    = "compliance"
    
    # Phase 5+6 sub-states (asset generation + verification)
    IMAGES        = "images"           # FLUX image generation
    IMAGE_QA      = "image_qa"         # 6A: Qwen2.5-VL verifies images vs script
    IMAGE_REGEN   = "image_regen"      # Regenerate failed images
    VIDEO         = "video"            # LTX-2.3 video generation
    VIDEO_QA      = "video_qa"         # 6B: Qwen2.5-VL verifies video clips vs script
    VIDEO_REGEN   = "video_regen"      # Regenerate failed clips (or Ken Burns fallback)
    VOICE         = "voice"
    MUSIC         = "music"
    SFX           = "sfx"
    COMPOSE       = "compose"
    
    FINAL_QA      = "final_qa"
    MANUAL_REVIEW = "manual_review"
    PUBLISH       = "publish"
    PUBLISHED     = "published"
    
    # Terminal / special states
    BLOCKED       = "blocked"
    CANCELLED     = "cancelled"
    
    # Phase 9 tracking states
    TRACKING_24H  = "tracking_24h"
    TRACKING_7D   = "tracking_7d"
    TRACKING_30D  = "tracking_30d"
    COMPLETE      = "complete"


# ═══ TRANSITION MAP ═══
# Only these transitions are allowed. Anything else = bug.
TRANSITIONS: dict[JobStatus, list[JobStatus]] = {
    JobStatus.PENDING:       [JobStatus.RESEARCH],
    JobStatus.RESEARCH:      [JobStatus.SEO, JobStatus.BLOCKED],
    JobStatus.SEO:           [JobStatus.SCRIPT, JobStatus.BLOCKED],
    JobStatus.SCRIPT:        [JobStatus.COMPLIANCE, JobStatus.BLOCKED],
    JobStatus.COMPLIANCE:    [JobStatus.IMAGES, JobStatus.BLOCKED],
    
    # Phase 5+6 sub-pipeline (interleaved generation + verification)
    JobStatus.IMAGES:        [JobStatus.IMAGE_QA, JobStatus.BLOCKED],
    JobStatus.IMAGE_QA:      [JobStatus.VIDEO, JobStatus.IMAGE_REGEN, JobStatus.BLOCKED],
    JobStatus.IMAGE_REGEN:   [JobStatus.IMAGE_QA],   # Re-verify after regen
    JobStatus.VIDEO:         [JobStatus.VIDEO_QA, JobStatus.BLOCKED],
    JobStatus.VIDEO_QA:      [JobStatus.VOICE, JobStatus.VIDEO_REGEN, JobStatus.BLOCKED],
    JobStatus.VIDEO_REGEN:   [JobStatus.VIDEO_QA],   # Re-verify after regen
    JobStatus.VOICE:         [JobStatus.MUSIC, JobStatus.BLOCKED],
    JobStatus.MUSIC:         [JobStatus.SFX, JobStatus.BLOCKED],
    JobStatus.SFX:           [JobStatus.COMPOSE, JobStatus.BLOCKED],
    JobStatus.COMPOSE:       [JobStatus.FINAL_QA, JobStatus.BLOCKED],
    
    JobStatus.FINAL_QA:      [JobStatus.MANUAL_REVIEW, JobStatus.PUBLISH, JobStatus.BLOCKED],
    JobStatus.MANUAL_REVIEW: [JobStatus.PUBLISH, JobStatus.BLOCKED, JobStatus.CANCELLED],
    JobStatus.PUBLISH:       [JobStatus.PUBLISHED, JobStatus.BLOCKED],
    JobStatus.PUBLISHED:     [JobStatus.TRACKING_24H],
    
    # Phase 9 tracking
    JobStatus.TRACKING_24H:  [JobStatus.TRACKING_7D],
    JobStatus.TRACKING_7D:   [JobStatus.TRACKING_30D],
    JobStatus.TRACKING_30D:  [JobStatus.COMPLETE],
    
    # Blocked can be unblocked → resume from blocked_phase
    JobStatus.BLOCKED:       [
        JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT, 
        JobStatus.COMPLIANCE, JobStatus.IMAGES, JobStatus.VISUAL_QA,
        JobStatus.VIDEO, JobStatus.VOICE, JobStatus.MUSIC,
        JobStatus.COMPOSE, JobStatus.FINAL_QA, JobStatus.PUBLISH,
        JobStatus.CANCELLED
    ],
    
    # Terminal states — no transitions out
    JobStatus.CANCELLED:     [],
    JobStatus.COMPLETE:      [],
}

# Which states require which GPU model
GPU_REQUIREMENTS: dict[JobStatus, Optional[str]] = {
    JobStatus.RESEARCH:     "qwen2.5:72b",
    JobStatus.SEO:          "qwen2.5:72b",
    JobStatus.SCRIPT:       "qwen2.5:72b",
    JobStatus.COMPLIANCE:   "qwen2.5:72b",
    JobStatus.IMAGES:       "flux",
    JobStatus.IMAGE_QA:     "qwen2.5-vl:72b",      # Vision verification
    JobStatus.IMAGE_REGEN:  "flux",
    JobStatus.VIDEO:        "ltx",
    JobStatus.VIDEO_QA:     "qwen2.5-vl:72b",      # Vision verification
    JobStatus.VIDEO_REGEN:  "ltx",                  # Or Ken Burns (CPU)
    JobStatus.VOICE:        "fish_speech",
    JobStatus.MUSIC:        "musicgen",
    JobStatus.SFX:          "audiogen",
    JobStatus.COMPOSE:      None,             # CPU only
    JobStatus.FINAL_QA:     "qwen2.5-vl:72b",   # Vision for frame analysis + text for compliance
    JobStatus.MANUAL_REVIEW: None,            # Waiting for human
    JobStatus.PUBLISH:      "flux",           # Thumbnails
}

# Consecutive states that use the SAME model (batch without unload)
GPU_BATCHES = [
    [JobStatus.RESEARCH, JobStatus.SEO, JobStatus.SCRIPT, JobStatus.COMPLIANCE],  # All Qwen
]


class StateError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class JobStateMachine:
    """
    Enforces valid state transitions.
    Every status change in the system MUST go through this class.
    """
    
    def __init__(self, db):
        self.db = db
    
    def transition(self, job_id: str, to_status: JobStatus) -> None:
        """
        Transition job to new status.
        Raises StateError if transition is invalid.
        """
        job = self.db.get_job(job_id)
        current = JobStatus(job["status"])
        
        if to_status not in TRANSITIONS.get(current, []):
            raise StateError(
                f"Invalid transition: {current.value} → {to_status.value}. "
                f"Allowed: {[s.value for s in TRANSITIONS.get(current, [])]}"
            )
        
        self.db.update_job_status(job_id, to_status.value)
        return current  # Return previous status for logging
    
    def get_next_status(self, current: JobStatus) -> Optional[JobStatus]:
        """Get the default next status (first in transition list)."""
        options = TRANSITIONS.get(current, [])
        if options and options[0] != JobStatus.BLOCKED:
            return options[0]
        return None
    
    def get_required_gpu(self, status: JobStatus) -> Optional[str]:
        """What GPU model does this status need?"""
        return GPU_REQUIREMENTS.get(status)
    
    def can_batch_with_next(self, current: JobStatus, next_status: JobStatus) -> bool:
        """Can we keep the same GPU model loaded for the next status?"""
        for batch in GPU_BATCHES:
            if current in batch and next_status in batch:
                return True
        return False
    
    def get_resume_status(self, job_id: str) -> JobStatus:
        """After crash, where should this job resume?"""
        job = self.db.get_job(job_id)
        status = JobStatus(job["status"])
        
        # If blocked, resume from the phase that blocked it
        if status == JobStatus.BLOCKED:
            blocked_phase = job.get("blocked_phase")
            if blocked_phase:
                return JobStatus(blocked_phase)
        
        return status
```

### 4.3 Gate Evaluator (`src/core/gate_evaluator.py`)

```python
"""
Evaluates QA gate results.
Decides: PASS (continue) | RETRY (regenerate) | BLOCK (alert human)
Separated from phase logic for testability.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GateResult:
    passed: bool
    action: str            # "continue" | "retry" | "block" | "manual_review"
    reason: str = ""
    retry_phase: Optional[str] = None   # Which phase to re-run
    failed_items: list = None           # e.g., failed scene indices
    score: float = 0.0


class GateEvaluator:
    """Evaluates results from QA phases and decides next action."""
    
    def evaluate_compliance(self, check_results: list[dict]) -> GateResult:
        """Phase 4: Script compliance gate."""
        blocked = [r for r in check_results if r["status"] == "block"]
        warnings = [r for r in check_results if r["status"] == "warn"]
        
        if blocked:
            return GateResult(
                passed=False, action="block",
                reason=f"Compliance violation: {blocked[0]['details']}"
            )
        
        if len(warnings) > 2:
            return GateResult(
                passed=False, action="block",
                reason=f"Too many warnings ({len(warnings)}): {warnings[0]['details']}"
            )
        
        avg_score = sum(r["score"] for r in check_results) / len(check_results)
        return GateResult(passed=True, action="continue", score=avg_score)
    
    def evaluate_visual_qa(self, image_scores: list[dict]) -> GateResult:
        """Phase 6: Visual QA gate."""
        failed = [s for s in image_scores if s["score"] < 7]
        total = len(image_scores)
        pass_rate = (total - len(failed)) / total
        
        if pass_rate >= 0.9:
            return GateResult(passed=True, action="continue", score=pass_rate)
        elif pass_rate >= 0.7:
            return GateResult(
                passed=False, action="retry",
                retry_phase="image_regen",
                failed_items=[s["scene_index"] for s in failed],
                reason=f"{len(failed)}/{total} images below quality threshold"
            )
        else:
            return GateResult(
                passed=False, action="block",
                reason=f"Image quality too low: {len(failed)}/{total} failed"
            )
    
    def evaluate_final_qa(self, technical: dict, content: dict) -> GateResult:
        """Phase 7: Final video QA gate."""
        if technical.get("av_sync_drift_ms", 0) > 100:
            return GateResult(
                passed=False, action="retry", retry_phase="compose",
                reason=f"A/V sync drift: {technical['av_sync_drift_ms']}ms"
            )
        
        content_score = content.get("score", 0)
        if content_score < 7:
            return GateResult(
                passed=False, action="block",
                reason=f"Content coherence too low: {content_score}/10"
            )
        
        return GateResult(passed=True, action="continue", score=content_score)
    
    def evaluate_manual_review_needed(self, job: dict, config: dict) -> bool:
        """Phase 7.5: Should this job go to manual review?"""
        review_config = config["settings"]["manual_review"]
        
        if not review_config["enabled"] or review_config["mode"] == "off":
            return False
        
        if review_config["mode"] == "all":
            return True
        
        # Selective mode
        if job.get("topic_category") in review_config.get("sensitive_categories", []):
            return True
        
        # Check QA scores
        min_score = review_config.get("auto_publish_min_score", 8.0)
        # ... check all QA scores against min_score
        
        return False
```

### 4.4 Resource Coordinator (`src/core/resource_coordinator.py`)

```python
"""
Manages GPU model lifecycle.
Wraps GPUMemoryManager with state-machine awareness.
Knows which model each status needs and handles batching.
"""

from src.core.gpu_manager import GPUMemoryManager
from src.core.gpu_logger import GPULogger
from src.core.job_state_machine import JobStatus, GPU_REQUIREMENTS


class ResourceCoordinator:
    """
    High-level GPU orchestration.
    Knows: which model is loaded, which model the next phase needs,
    whether to batch or swap.
    """
    
    def __init__(self, gpu_manager: GPUMemoryManager):
        self.gpu = gpu_manager
        self.current_model = None
        self.logger = None
    
    def set_logger(self, logger: GPULogger):
        self.logger = logger
    
    def prepare_for_status(self, status: JobStatus):
        """
        Ensure the correct GPU model is loaded for this status.
        Handles: no-op (already loaded), swap, or skip (CPU-only).
        """
        required = GPU_REQUIREMENTS.get(status)
        
        if required is None:
            # CPU-only phase — unload GPU if anything loaded
            if self.current_model:
                self.gpu.unload_model(logger=self.logger)
                self.current_model = None
            return
        
        if required == self.current_model:
            # Already loaded — no swap needed (batching)
            return
        
        # Need to swap
        if self.current_model:
            self.gpu.unload_model(logger=self.logger)
        
        model_type = self._get_model_type(required)
        self.gpu.load_model(required, model_type=model_type, logger=self.logger)
        self.current_model = required
    
    def release_all(self):
        """Release GPU at end of pipeline or on error."""
        if self.current_model:
            self.gpu.unload_model(logger=self.logger)
            self.current_model = None
    
    def emergency_release(self):
        """Nuclear option — force free everything."""
        self.gpu.emergency_cleanup(logger=self.logger)
        self.current_model = None
    
    def _get_model_type(self, model_name: str) -> str:
        if model_name in ("qwen2.5:72b", "qwen2.5-vl:72b"):
            return "ollama"
        elif model_name in ("flux", "ltx"):
            return "comfyui"
        else:
            return "python"
```

### 4.5 Event Bus + Event Store (`src/core/event_bus.py`, `src/core/event_store.py`)

```python
# ═══ src/core/event_bus.py ═══
"""
Internal event system.
Decouples phases from side effects (notifications, logging, analytics).
Not a message broker — just a simple in-process pub/sub.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Job lifecycle
    JOB_CREATED           = "job.created"
    JOB_STATUS_CHANGED    = "job.status_changed"
    JOB_BLOCKED           = "job.blocked"
    JOB_UNBLOCKED         = "job.unblocked"
    JOB_CANCELLED         = "job.cancelled"
    JOB_PUBLISHED         = "job.published"
    
    # Phase events
    PHASE_STARTED         = "phase.started"
    PHASE_COMPLETED       = "phase.completed"
    PHASE_FAILED          = "phase.failed"
    
    # Gate events
    GATE_PASSED           = "gate.passed"
    GATE_FAILED           = "gate.failed"
    GATE_BLOCKED          = "gate.blocked"
    
    # Production events
    IMAGE_GENERATED       = "production.image_generated"
    IMAGE_REGENERATED     = "production.image_regenerated"
    VIDEO_GENERATED       = "production.video_generated"
    VOICE_GENERATED       = "production.voice_generated"
    MUSIC_GENERATED       = "production.music_generated"
    COMPOSE_COMPLETED     = "production.compose_completed"
    
    # GPU events
    GPU_MODEL_LOADED      = "gpu.model_loaded"
    GPU_MODEL_UNLOADED    = "gpu.model_unloaded"
    GPU_OOM               = "gpu.oom"
    GPU_VRAM_LEAK         = "gpu.vram_leak"
    
    # Human interaction
    TOPIC_SELECTED        = "human.topic_selected"
    MANUAL_REVIEW_REQUESTED = "human.review_requested"
    MANUAL_REVIEW_APPROVED  = "human.review_approved"
    MANUAL_REVIEW_REJECTED  = "human.review_rejected"
    
    # Intelligence
    ANALYTICS_CAPTURED    = "intel.analytics_captured"
    RULE_DISCOVERED       = "intel.rule_discovered"
    REPORT_GENERATED      = "intel.report_generated"
    
    # Content ID
    CONTENT_ID_SAFE       = "content_id.safe"
    CONTENT_ID_CLAIMED    = "content_id.claimed"


@dataclass
class Event:
    type: EventType
    job_id: str = ""
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """
    Simple in-process event bus.
    Phases emit events → subscribers react.
    
    Example subscribers:
    - TelegramBot listens to JOB_BLOCKED → sends alert
    - GPULogger listens to GPU_OOM → logs critical
    - EventStore listens to ALL → persists to DB
    """
    
    def __init__(self):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._global_subscribers: list[Callable] = []
    
    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe to a specific event type."""
        self._subscribers.setdefault(event_type, []).append(handler)
    
    def subscribe_all(self, handler: Callable):
        """Subscribe to ALL events (for logging/persistence)."""
        self._global_subscribers.append(handler)
    
    def emit(self, event: Event):
        """Emit an event to all subscribers."""
        logger.debug(f"Event: {event.type.value} | job={event.job_id} | {event.data}")
        
        # Global subscribers first (logging)
        for handler in self._global_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
        
        # Type-specific subscribers
        for handler in self._subscribers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")


# ═══ src/core/event_store.py ═══
"""
Persists all events to SQLite for audit trail and replay.
"""

class EventStore:
    """
    Persistent event log.
    Every event emitted by EventBus is stored here.
    Used for: audit trail, debugging, crash analysis, analytics.
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        job_id TEXT,
        data JSON,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        -- Indexes for common queries
        CONSTRAINT idx_event_type CHECK(event_type IS NOT NULL)
    );
    CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
    CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
    CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp);
    """
    
    def __init__(self, db):
        self.db = db
        self.db.conn.executescript(self.SCHEMA)
    
    def store(self, event: Event):
        """Store event — called as global subscriber on EventBus."""
        self.db.conn.execute(
            "INSERT INTO events (event_type, job_id, data, timestamp) VALUES (?, ?, ?, ?)",
            (event.type.value, event.job_id, json.dumps(event.data), event.timestamp)
        )
        self.db.conn.commit()
    
    def get_job_events(self, job_id: str) -> list[dict]:
        """Get all events for a job — for debugging/audit."""
        rows = self.db.conn.execute(
            "SELECT * FROM events WHERE job_id = ? ORDER BY timestamp", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    
    def get_recent(self, event_type: str = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM events"
        params = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.db.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
```

### 4.6 Pipeline Runner (`src/core/pipeline_runner.py`) — Thin Coordinator

```python
"""
PipelineRunner — the THIN orchestrator.
Does NOT contain phase logic. Only coordinates the other components.

Responsibilities:
1. Get next status from StateMachine
2. Ask ResourceCoordinator to prepare GPU
3. Ask PhaseExecutor to run the phase
4. Ask GateEvaluator to evaluate gates
5. Emit events via EventBus
6. Handle errors gracefully
"""

import logging
from src.core.config import load_config
from src.core.database import FactoryDB
from src.core.job_state_machine import JobStateMachine, JobStatus, StateError
from src.core.gate_evaluator import GateEvaluator
from src.core.resource_coordinator import ResourceCoordinator
from src.core.gpu_manager import GPUMemoryManager
from src.core.gpu_logger import GPULogger
from src.core.event_bus import EventBus, Event, EventType
from src.core.event_store import EventStore
from src.core.telegram_bot import TelegramBot
from src.core.phase_executor import PhaseExecutor

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Thin coordinator. Runs a job through the pipeline
    by delegating to specialized components.
    
    Compare to old monolithic Pipeline class:
    - No phase logic here
    - No GPU management here
    - No gate evaluation here
    - No state manipulation here
    Just coordination.
    """
    
    def __init__(self):
        config = load_config()
        db = FactoryDB(config["settings"]["database"]["path"])
        gpu = GPUMemoryManager(config["settings"]["gpu"])
        
        self.config = config
        self.db = db
        self.state = JobStateMachine(db)
        self.gates = GateEvaluator()
        self.resources = ResourceCoordinator(gpu)
        self.executor = PhaseExecutor(config, db)
        self.events = EventBus()
        self.telegram = TelegramBot(config["settings"]["telegram"])
        
        # Wire up event subscribers
        event_store = EventStore(db)
        self.events.subscribe_all(event_store.store)                         # Persist all
        self.events.subscribe(EventType.JOB_BLOCKED, self._on_blocked)       # Alert
        self.events.subscribe(EventType.GPU_OOM, self._on_gpu_oom)           # Emergency
        self.events.subscribe(EventType.JOB_PUBLISHED, self._on_published)   # Notify
        self.events.subscribe(EventType.MANUAL_REVIEW_REQUESTED, self._on_review)
    
    def run_job(self, job_id: str):
        """Run a job through all phases until completion or pause."""
        gpu_logger = GPULogger(job_id)
        self.resources.set_logger(gpu_logger)
        
        try:
            while True:
                job = self.db.get_job(job_id)
                current = JobStatus(job["status"])
                
                # Terminal states — done
                if current in (JobStatus.PUBLISHED, JobStatus.CANCELLED, 
                               JobStatus.COMPLETE, JobStatus.BLOCKED):
                    break
                
                # Waiting for human — pause
                if current == JobStatus.MANUAL_REVIEW:
                    break
                
                # 1. Prepare GPU for this phase
                self.resources.prepare_for_status(current)
                
                # 2. Execute the phase
                self.events.emit(Event(EventType.PHASE_STARTED, job_id, {"phase": current.value}))
                result = self.executor.execute(current, job_id)
                self.events.emit(Event(EventType.PHASE_COMPLETED, job_id, {
                    "phase": current.value, "score": result.score
                }))
                
                # 3. Evaluate gate (if this phase has one)
                if result.is_gate:
                    gate_result = self.gates.evaluate(current, result)
                    
                    if gate_result.action == "block":
                        self.state.transition(job_id, JobStatus.BLOCKED)
                        self.events.emit(Event(EventType.GATE_BLOCKED, job_id, {
                            "phase": current.value, "reason": gate_result.reason
                        }))
                        break
                    
                    elif gate_result.action == "retry":
                        retry_status = JobStatus(gate_result.retry_phase)
                        self.state.transition(job_id, retry_status)
                        continue  # Loop back to retry phase
                    
                    elif gate_result.action == "manual_review":
                        self.state.transition(job_id, JobStatus.MANUAL_REVIEW)
                        self.events.emit(Event(EventType.MANUAL_REVIEW_REQUESTED, job_id))
                        break  # Pause for human
                
                # 4. Transition to next state
                next_status = self.state.get_next_status(current)
                if next_status:
                    # Check if we can keep GPU (batching)
                    if not self.state.can_batch_with_next(current, next_status):
                        required_now = self.state.get_required_gpu(current)
                        required_next = self.state.get_required_gpu(next_status)
                        if required_now != required_next:
                            self.resources.release_all()
                    
                    self.state.transition(job_id, next_status)
                else:
                    break  # No next state — done
        
        except StateError as e:
            logger.error(f"State machine error: {e}")
            self.events.emit(Event(EventType.PHASE_FAILED, job_id, {"error": str(e)}))
            raise
        
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            self.resources.emergency_release()
            self.events.emit(Event(EventType.PHASE_FAILED, job_id, {"error": str(e)}))
            self.telegram.alert(f"🚨 Pipeline error: {job_id}\n{str(e)[:200]}")
            raise
        
        finally:
            self.resources.release_all()
    
    def resume_all(self):
        """Resume interrupted jobs after crash."""
        for job in self.db.get_active_jobs():
            resume_status = self.state.get_resume_status(job["id"])
            logger.info(f"Resuming {job['id']} from {resume_status.value}")
            self.run_job(job["id"])
    
    # ─── Event Handlers ────────────────────────────────
    
    def _on_blocked(self, event: Event):
        self.telegram.alert(f"⚠️ Job blocked: {event.job_id}\n{event.data.get('reason', '')}")
    
    def _on_gpu_oom(self, event: Event):
        self.resources.emergency_release()
        self.telegram.alert(f"💥 GPU OOM: {event.job_id}")
    
    def _on_published(self, event: Event):
        self.telegram.send(f"✅ Published: {event.data.get('topic', '')}")
    
    def _on_review(self, event: Event):
        # Trigger Telegram interactive review UI
        pass
```

### 4.7 Phase Executor (`src/core/phase_executor.py`)

```python
"""
Executes individual phases.
Maps JobStatus → Phase class → result.
Knows nothing about GPU, state, or gates.
"""

from src.core.job_state_machine import JobStatus
from src.core.database import FactoryDB

# Phase imports
from src.phase1_research import ResearchPhase
from src.phase2_seo import SEOPhase
from src.phase3_script import ScriptPhase
from src.phase4_compliance import CompliancePhase
from src.phase5_production import (
    AssetCoordinator, AudioCoordinator, VideoComposer
)
from src.phase6_visual_qa import VisualQAPhase
from src.phase7_video_qa import VideoQAPhase
from src.phase7_5_review import ManualReviewPhase
from src.phase8_publish import PublishPhase


class PhaseExecutor:
    """
    Maps status → phase → execute.
    Each phase is a self-contained module that reads from DB and writes to DB.
    """
    
    def __init__(self, config: dict, db: FactoryDB):
        self.config = config
        self.db = db
        
        # Initialize phases (lazy or upfront)
        self._phases = {
            JobStatus.RESEARCH:     ResearchPhase(config, db),
            JobStatus.SEO:          SEOPhase(config, db),
            JobStatus.SCRIPT:       ScriptPhase(config, db),
            JobStatus.COMPLIANCE:   CompliancePhase(config, db),
            JobStatus.IMAGES:       AssetCoordinator(config, db),     # Sub-pipeline
            JobStatus.VISUAL_QA:    VisualQAPhase(config, db),
            JobStatus.IMAGE_REGEN:  AssetCoordinator(config, db),     # Regen mode
            JobStatus.VIDEO:        AssetCoordinator(config, db),     # Video mode
            JobStatus.VOICE:        AudioCoordinator(config, db),     # Sub-pipeline
            JobStatus.MUSIC:        AudioCoordinator(config, db),
            JobStatus.SFX:          AudioCoordinator(config, db),
            JobStatus.COMPOSE:      VideoComposer(config, db),
            JobStatus.FINAL_QA:     VideoQAPhase(config, db),
            JobStatus.PUBLISH:      PublishPhase(config, db),
        }
    
    def execute(self, status: JobStatus, job_id: str):
        """Execute the phase for current status."""
        phase = self._phases.get(status)
        if not phase:
            raise ValueError(f"No phase handler for status: {status}")
        
        return phase.run(job_id)
```

### 4.8 Phase 5 Decomposition — Sub-Pipeline

```python
# ═══ src/phase5_production/__init__.py ═══
"""
Phase 5 is NOT a single phase — it's a sub-pipeline with 3 coordinators:

AssetCoordinator:    Images + Video (visual assets)
AudioCoordinator:    Voice + Music + SFX (audio assets)
VideoComposer:       FFmpeg assembly (final composition)

Each coordinator manages its own generation logic.
GPU model loading is handled by ResourceCoordinator (external).
"""

from src.phase5_production.asset_coordinator import AssetCoordinator
from src.phase5_production.audio_coordinator import AudioCoordinator
from src.phase5_production.video_composer import VideoComposer


# ═══ src/phase5_production/asset_coordinator.py ═══
"""
Coordinates visual asset generation: images + videos.
Handles: image generation, prompt enhancement, video generation, fallback to Ken Burns.
"""

class AssetCoordinator:
    """
    Manages visual asset pipeline.
    Called at different stages:
    - status=IMAGES → generate all images
    - status=IMAGE_REGEN → regenerate failed images only
    - status=VIDEO → generate all video clips
    """
    
    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        status = JobStatus(job["status"])
        
        if status == JobStatus.IMAGES:
            return self._generate_all_images(job_id)
        elif status == JobStatus.IMAGE_REGEN:
            return self._regenerate_failed(job_id)
        elif status == JobStatus.VIDEO:
            return self._generate_all_videos(job_id)
    
    def _generate_all_images(self, job_id):
        scenes = self.db.get_scenes(job_id)
        for scene in scenes:
            prompt, negative = enhance_prompt(scene["visual_prompt"], ...)
            image_path = self.image_gen.generate(prompt, negative)
            self.db.update_scene_asset(job_id, scene["scene_index"], image_path=image_path)
        return PhaseResult(success=True)
    
    # ... etc


# ═══ src/phase5_production/audio_coordinator.py ═══
"""
Coordinates all audio generation: voice, music, SFX.
Each runs in sequence (different GPU models).
"""

class AudioCoordinator:
    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        status = JobStatus(job["status"])
        
        if status == JobStatus.VOICE:
            return self._generate_voice(job_id)
        elif status == JobStatus.MUSIC:
            return self._generate_music(job_id)
        elif status == JobStatus.SFX:
            return self._generate_sfx(job_id)


# ═══ src/phase5_production/video_composer.py ═══
"""
FFmpeg assembly — CPU only.
Combines: video clips + voice + music + SFX + text overlays + intro/outro.
"""

class VideoComposer:
    def run(self, job_id: str) -> PhaseResult:
        # ... FFmpeg assembly logic
        pass
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
    """
    SQLite Scaling Strategy:
    ─────────────────────────
    NOW (v1):   Single factory.db — all tables.
                Perfect for single machine, <1000 jobs.
    
    LATER (v2): Split heavy tables to separate DBs:
                ├── factory.db          — jobs, scenes, scripts (core)
                ├── analytics.db        — youtube_analytics, revenue (heavy reads)
                ├── intelligence.db     — performance_rules, patterns (ML)
                └── events.db           — event_store (audit, append-only)
                
                OR: migrate analytics to Parquet files (columnar, fast aggregation)
                OR: migrate to Postgres when multi-machine
    
    TRIGGER: When factory.db > 500MB or analytics queries > 1 sec
    """
    
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
    
    # ─── QA Rubric Storage ─────────────────────────────
    # Stores FULL rubric output for every QA check — not just final score.
    # Enables: post-mortem analysis, template improvement, Phase 9 learning.
    
    QA_RUBRICS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS qa_rubrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        scene_index INTEGER,                -- NULL for job-level checks
        asset_type TEXT NOT NULL,            -- 'image' | 'video' | 'thumbnail' | 'final_video'
        check_phase TEXT NOT NULL,           -- 'phase6a' | 'phase6b' | 'phase7' | 'phase8'
        attempt_number INTEGER DEFAULT 1,    -- Which try (1st, 2nd after regen...)
        
        -- Deterministic layer results
        deterministic_results JSON,          -- {text_detected, nsfw_score, blur_score, ...}
        deterministic_pass BOOLEAN,          -- Did it pass hard rules?
        hard_fail_reason TEXT,               -- NULL if passed, else reason
        
        -- Vision rubric (per-axis)
        rubric_scores JSON,                  -- {axis: {score, reasoning, confidence}, ...}
        -- Example: {
        --   "semantic_match": {"score": 8.5, "reasoning": "Image shows...", "confidence": "high"},
        --   "composition": {"score": 7.0, "reasoning": "Good framing...", "confidence": "medium"},
        --   ...
        -- }
        
        -- Combined verdict
        weighted_score REAL,                 -- Calculated from rubric_scores
        final_verdict TEXT NOT NULL,          -- 'pass' | 'regen_adjust' | 'regen_new' | 'fail' | 'flag_human'
        flags JSON,                          -- ["low_confidence_composition", "near_threshold", ...]
        
        -- Metadata
        model_used TEXT,                     -- 'qwen2.5-vl:72b'
        inference_time_ms INTEGER,           -- How long the vision check took
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (job_id) REFERENCES jobs(id)
    );
    CREATE INDEX IF NOT EXISTS idx_rubrics_job ON qa_rubrics(job_id);
    CREATE INDEX IF NOT EXISTS idx_rubrics_scene ON qa_rubrics(job_id, scene_index);
    CREATE INDEX IF NOT EXISTS idx_rubrics_verdict ON qa_rubrics(final_verdict);
    CREATE INDEX IF NOT EXISTS idx_rubrics_phase ON qa_rubrics(check_phase);
    """
    
    def save_rubric(self, job_id: str, scene_index: int, asset_type: str,
                    check_phase: str, attempt: int, deterministic: dict,
                    rubric_scores: dict, weighted_score: float, verdict: str,
                    flags: list, hard_fail: str = None, model: str = "qwen2.5-vl:72b",
                    inference_ms: int = 0):
        """Save complete QA rubric for a scene/asset."""
        self.conn.execute("""
            INSERT INTO qa_rubrics (job_id, scene_index, asset_type, check_phase,
                attempt_number, deterministic_results, deterministic_pass, hard_fail_reason,
                rubric_scores, weighted_score, final_verdict, flags, model_used, inference_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, scene_index, asset_type, check_phase, attempt,
            json.dumps(deterministic), hard_fail is None, hard_fail,
            json.dumps(rubric_scores), weighted_score, verdict,
            json.dumps(flags), model, inference_ms
        ))
        self.conn.commit()
    
    def get_rubrics(self, job_id: str, scene_index: int = None,
                    asset_type: str = None) -> list[dict]:
        """Get rubrics for analysis. Filter by scene/type."""
        query = "SELECT * FROM qa_rubrics WHERE job_id = ?"
        params = [job_id]
        if scene_index is not None:
            query += " AND scene_index = ?"
            params.append(scene_index)
        if asset_type:
            query += " AND asset_type = ?"
            params.append(asset_type)
        query += " ORDER BY scene_index, attempt_number"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]
    
    def get_rubric_stats(self, job_id: str) -> dict:
        """Aggregate rubric stats for a job — for Phase 9 learning."""
        rows = self.conn.execute("""
            SELECT asset_type, check_phase,
                   COUNT(*) as total,
                   AVG(weighted_score) as avg_score,
                   SUM(CASE WHEN final_verdict = 'pass' THEN 1 ELSE 0 END) as pass_count,
                   SUM(CASE WHEN hard_fail_reason IS NOT NULL THEN 1 ELSE 0 END) as hard_fails,
                   SUM(CASE WHEN final_verdict = 'flag_human' THEN 1 ELSE 0 END) as human_flags,
                   AVG(attempt_number) as avg_attempts
            FROM qa_rubrics WHERE job_id = ?
            GROUP BY asset_type, check_phase
        """, (job_id,)).fetchall()
        return [dict(r) for r in rows]
    
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

#### Phase 6: Visual QA — Deep Verification (`src/phase6_visual_qa/`)

> **Vision Model: Qwen2.5-VL 72B** (not Llama Vision 11B)
> Reason: Arabic text understanding, complex scene analysis, much higher accuracy.
> GPU: Runs via Ollama, same slot as Qwen text (already have 72B quantized).
>
> ⚠️ **CRITICAL DESIGN PRINCIPLE: Vision = Judge, NOT Source of Truth**
> The Vision LLM is a SCORING + FLAGGING tool. It can:
>   ✅ Score quality, detect artifacts, flag problems, add notes
>   ❌ NOT make final pass/fail decisions alone
> 
> Why: Vision LLMs can hallucinate confidence, miss subtle errors,
> or over-approve. All decisions combine Vision scores + deterministic
> checks + script constraints + thresholds.
>
> For historical/political content: Vision CANNOT verify historical
> accuracy (correct uniforms, flags, eras). That's enforced via
> prompt engineering constraints + HistoricalContextValidator (Phase 3).

```
Input:  Generated images + video clips + script scenes
Output: Structured rubric scores per asset → DB: scenes.image_rubric (JSON), scenes.video_rubric (JSON)
LLM:    Qwen2.5-VL 72B (via Ollama) — JUDGE role only
GATE:   Combined score (vision + deterministic) → block, regen, or human review

═══════════════════════════════════════════════════════════════
STAGE 6A: IMAGE ↔ SCRIPT VERIFICATION (after FLUX, before LTX)
═══════════════════════════════════════════════════════════════

Files to build:
├── image_script_verifier.py
│   └── verify_image_against_script(image_path, scene) → ImageVerification
│       
│       TWO-LAYER VERIFICATION:
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 1: DETERMINISTIC CHECKS (no LLM — runs first)    │
│       │                                                         │
│       │ These are hard rules — LLM opinion doesn't override:    │
│       │ ├── OCR text detection (Tesseract/EasyOCR)              │
│       │ │   → Any text found = AUTOMATIC FAIL                   │
│       │ ├── NSFW classifier (NudeNet or similar, local)         │
│       │ │   → NSFW score > 0.5 = AUTOMATIC FAIL                │
│       │ ├── Image technical quality                              │
│       │ │   → Resolution check, blur detection (Laplacian)      │
│       │ │   → Black/white frame detection                        │
│       │ ├── AI artifact detector                                 │
│       │ │   → Extra fingers/limbs heuristic (hand region crop)  │
│       │ │   → Face distortion check (dlib landmarks)            │
│       │ └── File integrity (valid image, not corrupt)            │
│       └─────────────────────────────────────────────────────────┘
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 2: VISION LLM RUBRIC (Qwen2.5-VL — judge role)  │
│       │                                                         │
│       │ Structured rubric — NOT a vague "score 1-10":           │
│       │                                                         │
│       │ RUBRIC AXES (each scored 1-10 with mandatory reasoning):│
│       │                                                         │
│       │ A. Semantic Match                                       │
│       │    "Does image convey the MEANING of the narration?"    │
│       │    Narration: "{narration_text}"                        │
│       │    NOT asking if it's a literal match — conceptual fit. │
│       │                                                         │
│       │ B. Visual Element Presence                              │
│       │    "Which expected elements are visible?"               │
│       │    Expected: {expected_elements}                        │
│       │    Return: {element: "present"|"absent"|"uncertain"}    │
│       │                                                         │
│       │ C. Composition Quality                                  │
│       │    "Is the image well-composed for a documentary?"      │
│       │    Lighting, framing, depth, focus, not cluttered.      │
│       │                                                         │
│       │ D. Style Fit                                            │
│       │    "Does this look like a {style} documentary frame?"   │
│       │    style = cinematic|editorial|archival|illustrated     │
│       │                                                         │
│       │ E. Artifact Severity                                    │
│       │    "Rate visible AI generation artifacts"               │
│       │    10=clean, 1=obviously AI-generated mess              │
│       │    List specific artifacts found.                       │
│       │                                                         │
│       │ F. Cultural/Regional Appropriateness                    │
│       │    "Is this visually appropriate for {region} audience?"│
│       │    NOT historical accuracy (that's prompt engineering). │
│       │                                                         │
│       │ G. Emotional Tone Match                                 │
│       │    "Does visual mood match {emotion}?"                  │
│       │    dramatic|informative|tense|hopeful|somber            │
│       │                                                         │
│       │ IMPORTANT: For each axis, provide:                      │
│       │ - Score (1-10)                                          │
│       │ - One-line reasoning                                    │
│       │ - Confidence level (high|medium|low)                    │
│       │                                                         │
│       │ If confidence = "low" on any axis → FLAG for human.    │
│       └─────────────────────────────────────────────────────────┘
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 3: COMBINED VERDICT (deterministic formula)       │
│       │                                                         │
│       │ NOT the LLM's verdict — calculated from scores:         │
│       │                                                         │
│       │ weighted_score = (                                      │
│       │     semantic_match * 0.25 +                             │
│       │     element_presence * 0.20 +                           │
│       │     composition * 0.15 +                                │
│       │     style_fit * 0.10 +                                  │
│       │     artifact_severity * 0.15 +                          │
│       │     cultural * 0.05 +                                   │
│       │     emotion * 0.10                                      │
│       │ )                                                       │
│       │                                                         │
│       │ HARD FAILS (override score):                            │
│       │ ├── deterministic_text_detected = True → FAIL           │
│       │ ├── deterministic_nsfw = True → FAIL                    │
│       │ ├── deterministic_corrupt = True → FAIL                 │
│       │ ├── any axis confidence = "low" → FLAG_HUMAN            │
│       │ └── extra_limbs/face_distortion = True → FAIL           │
│       │                                                         │
│       │ SOFT THRESHOLDS:                                        │
│       │ ├── weighted_score ≥ 7.0 → PASS                        │
│       │ ├── weighted_score 4.0-6.9 → REGEN (adjust prompt)     │
│       │ └── weighted_score < 4.0 → REGEN (new prompt)          │
│       └─────────────────────────────────────────────────────────┘
│       
│       Returns: ImageVerification(
│           # Deterministic layer
│           text_detected: bool,        # OCR result
│           nsfw_score: float,          # classifier result
│           blur_score: float,          # Laplacian variance
│           artifact_flags: list[str],  # detected AI artifacts
│           
│           # Vision rubric (7 axes)
│           rubric: dict[str, RubricScore],  # axis → {score, reasoning, confidence}
│           
│           # Combined
│           weighted_score: float,      # calculated, NOT from LLM
│           hard_fail: Optional[str],   # reason if hard-failed
│           verdict: str,               # "pass" | "regen_adjust" | "regen_new" | "fail" | "flag_human"
│           flags: list[str]            # all issues found
│       )
│
├── style_checker.py
│   └── check_consistency(image_paths: list) → StyleResult
│       
│       TWO-LAYER approach:
│       
│       LAYER 1: DETERMINISTIC (no LLM):
│       ├── Color histogram comparison (OpenCV)
│       │   → Extract dominant colors per image
│       │   → Calculate pairwise histogram distance
│       │   → Outlier = distance > 2 std deviations from mean
│       ├── Brightness/contrast distribution
│       │   → Flag images with drastically different exposure
│       └── Aspect ratio / resolution consistency
│       
│       LAYER 2: VISION LLM (supplementary):
│       Send ALL images to Qwen2.5-VL:
│       "These are scenes from the same documentary.
│        For each image, note:
│        - Art style (photorealistic/illustrated/painted)
│        - Color temperature (warm/cool/neutral)
│        - Lighting style (cinematic/flat/dramatic)
│        Which images break consistency? List them with reasons."
│       
│       COMBINED: deterministic outliers ∩ LLM outliers = high confidence
│                 deterministic only = medium (still flag)
│                 LLM only = low (note but don't fail)
│       
│       Returns: StyleResult(
│           consistency_score: float,       # 0-1, from histogram analysis
│           outlier_indices: list[int],     # combined
│           deterministic_outliers: list,   # from histogram
│           llm_outliers: list,             # from vision
│           confidence: str                 # high|medium|low
│       )
│
├── sequence_checker.py
│   └── check_flow(image_paths: list, scenes: list) → FlowResult
│       
│       ⚠️ HARD PROBLEM — sequence evaluation is genuinely difficult.
│       Approach: Conservative scoring — only flag OBVIOUS breaks.
│       
│       LAYER 1: DETERMINISTIC:
│       ├── Scene-to-scene color shift magnitude
│       │   → Large shift between adjacent scenes = potential jarring cut
│       ├── Subject continuity (if same person/place across scenes)
│       │   → CLIP embeddings similarity between adjacent scenes
│       └── Brightness flow (no sudden dark→bright→dark)
│       
│       LAYER 2: VISION LLM (conservative):
│       Send images in ORDER, 3 at a time (sliding window):
│       "These 3 consecutive documentary frames play in this order.
│        Scene N-1: '{narration_n1}'
│        Scene N:   '{narration_n}'
│        Scene N+1: '{narration_n1}'
│        
│        Is the visual transition from N-1→N and N→N+1 jarring?
│        Only flag transitions that would confuse a viewer.
│        Minor style differences are OK for documentaries."
│       
│       ⚠️ Sliding window (3 images) is more reliable than
│       sending all 15 images at once (LLM loses focus).
│       
│       VERDICT LOGIC:
│       ├── Both layers agree "jarring" → FLAG (high confidence)
│       ├── Deterministic only → NOTE (don't fail)
│       ├── LLM only → NOTE (don't fail)
│       └── Neither → PASS
│       
│       Returns: FlowResult(
│           score: float,                    # 0-1
│           jarring_transitions: list[tuple], # [(scene_i, scene_j, reason, confidence)]
│           methodology: str                  # "sliding_window_3"
│       )
│
├── telegram_gallery.py     ← NEW: Send images+script to Yusif
│   └── send_image_gallery(job_id) → None
│       Sends Telegram album: each image captioned with its narration text
│       Format per image:
│       ┌──────────────────────────────────┐
│       │ 🎬 Scene 3/15                    │
│       │ 📝 "النص اللي يقرأه المعلق..."  │
│       │ 🎯 Score: 8.5/10                 │
│       │ ⚠️ Missing: mosque in background │
│       │ [📷 IMAGE ATTACHED]              │
│       └──────────────────────────────────┘
│       
│       After all images:
│       Summary message:
│       "✅ 13/15 images passed (avg 8.2/10)
│        ⚠️ 2 images need review: Scene 5, Scene 11
│        [Approve All] [Regenerate Failed] [View Details]"
│
└── image_qa_coordinator.py  ← Orchestrates 6A
    └── run_image_qa(job_id) → ImageQAResult
        1. Load Qwen2.5-VL 72B
        2. Run image_script_verifier on EACH scene
        3. Run style_checker on ALL images
        4. Run sequence_checker on ALL images in order
        5. Send telegram_gallery to Yusif
        6. Return aggregate result

═══════════════════════════════════════════════════════════════
STAGE 6B: VIDEO CLIP ↔ SCRIPT VERIFICATION (after LTX, before voice)
═══════════════════════════════════════════════════════════════

├── video_script_verifier.py    ← Verify LTX video clips
│   └── verify_video_against_script(video_path, scene) → VideoVerification
│       
│       Method: Extract 5 keyframes → deterministic + vision rubric
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 1: DETERMINISTIC VIDEO CHECKS (no LLM)           │
│       │                                                         │
│       │ ├── Frame-to-frame optical flow analysis                │
│       │ │   → Detect frozen frames (zero flow)                  │
│       │ │   → Detect sudden jumps (flow magnitude spike)        │
│       │ ├── Temporal consistency (SSIM between adjacent frames) │
│       │ │   → SSIM drop > 0.3 between adjacent = glitch        │
│       │ ├── OCR on all keyframes (text detection)               │
│       │ │   → Any text found = AUTOMATIC FAIL                   │
│       │ ├── Black/white/corrupt frame detection                  │
│       │ ├── Duration check vs expected                           │
│       │ └── FPS consistency check                                │
│       └─────────────────────────────────────────────────────────┘
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 2: VISION RUBRIC (Qwen2.5-VL — judge role)      │
│       │                                                         │
│       │ Send 5 keyframes with timestamps + script context:      │
│       │                                                         │
│       │ RUBRIC AXES:                                            │
│       │ A. Motion Plausibility (1-10)                           │
│       │    "Do the keyframes show believable motion?"           │
│       │    Smooth progression, no teleporting objects.           │
│       │                                                         │
│       │ B. Script Motion Match (1-10)                           │
│       │    "Motion prompt: '{motion_prompt}'"                   │
│       │    "Do keyframes show this type of movement?"           │
│       │                                                         │
│       │ C. Temporal Coherence (1-10)                            │
│       │    "Do frames show logical time progression?"           │
│       │    No objects appearing/disappearing between frames.    │
│       │                                                         │
│       │ D. AI Artifact Severity (1-10)                          │
│       │    "List specific artifacts: morphing, warping,         │
│       │    flickering, extra limbs, melting objects"             │
│       │    10=clean, 1=severe artifacts                         │
│       │                                                         │
│       │ E. Source Image Fidelity (1-10)                         │
│       │    "Does the video preserve the source image quality?"  │
│       │    Or did LTX degrade/distort the original?             │
│       │                                                         │
│       │ Each axis: score + reasoning + confidence               │
│       └─────────────────────────────────────────────────────────┘
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 3: COMBINED VERDICT (deterministic formula)       │
│       │                                                         │
│       │ weighted_score = (                                      │
│       │     motion_plausibility * 0.25 +                        │
│       │     script_match * 0.25 +                               │
│       │     temporal_coherence * 0.20 +                         │
│       │     artifact_severity * 0.20 +                          │
│       │     source_fidelity * 0.10                              │
│       │ )                                                       │
│       │                                                         │
│       │ HARD FAILS:                                             │
│       │ ├── text_detected = True → FAIL                         │
│       │ ├── frozen_frames > 30% → FAIL                          │
│       │ ├── ssim_glitches > 2 → FAIL                            │
│       │ └── any axis confidence = "low" → FLAG_HUMAN            │
│       │                                                         │
│       │ FALLBACK LOGIC (on FAIL):                               │
│       │ ├── artifact_severity < 4 AND source_fidelity > 7       │
│       │ │   → "regen_video" (retry LTX, different motion)       │
│       │ ├── source_fidelity < 5                                 │
│       │ │   → "regen_image" (source image was bad)              │
│       │ ├── motion_plausibility < 4 AND 2+ retries done         │
│       │ │   → "ken_burns" (LTX can't handle this, use fallback) │
│       │ └── else → "regen_video" (default retry)                │
│       └─────────────────────────────────────────────────────────┘
│       
│       Returns: VideoVerification(
│           # Deterministic
│           text_detected: bool,
│           frozen_frames: int,
│           ssim_glitches: int,
│           optical_flow_anomalies: list,
│           
│           # Vision rubric (5 axes)
│           rubric: dict[str, RubricScore],
│           
│           # Combined
│           weighted_score: float,
│           hard_fail: Optional[str],
│           verdict: str,          # "pass"|"regen_video"|"regen_image"|"ken_burns"|"flag_human"
│           fallback_reason: str,
│           flags: list[str]
│       )
│
├── video_keyframe_extractor.py  ← NEW
│   └── extract_keyframes(video_path, count=5) → list[str]
│       Uses FFmpeg: ffmpeg -i clip.mp4 -vf "select='eq(pict_type,I)'" -frames:v 5
│       Returns: list of temp image paths
│
├── telegram_video_gallery.py    ← NEW: Send video clips+script to Yusif
│   └── send_video_gallery(job_id) → None
│       Sends each LTX clip as Telegram video with caption:
│       ┌──────────────────────────────────────────────────────┐
│       │ 🎬 Scene 3/15 — Video Clip                          │
│       │ 📝 "النص اللي يقرأه المعلق هنا..."                 │
│       │ 🎥 Motion: "slow pan across ancient ruins"           │
│       │ 🎯 Vision Score: 8.0/10                             │
│       │ ⚠️ Minor: slight warping at 2.1s                    │
│       │ [🎬 VIDEO ATTACHED]                                  │
│       └──────────────────────────────────────────────────────┘
│       
│       Summary:
│       "🎬 Video Clips Review:
│        ✅ 12/15 clips passed
│        ⚠️ 2 clips regenerated (Ken Burns fallback)
│        ❌ 1 clip needs manual review: Scene 8
│        [Approve All] [View Flagged] [Reject & Regen]"
│
└── visual_qa_coordinator.py   ← Master coordinator for Phase 6
    └── run(job_id) → Phase6Result
        
        EXECUTION ORDER:
        ─────────────────
        STEP 1: Load Qwen2.5-VL 72B
        
        STEP 2: IMAGE QA (Stage 6A)
          a. Verify each image vs script
          b. Check style consistency
          c. Check sequence flow
          d. Send image gallery to Telegram
          e. Gate: >90% pass → continue; 70-90% → regen; <70% → block
        
        STEP 3: Unload Qwen2.5-VL → Load FLUX (if regen needed)
          a. Regenerate failed images
          b. Unload FLUX → Load Qwen2.5-VL → Re-verify
        
        STEP 4: Unload Qwen2.5-VL → (PipelineRunner handles LTX loading)
          → VIDEO GENERATION HAPPENS (Phase 5b)
          → Return to Phase 6 Stage 6B
        
        STEP 5: VIDEO QA (Stage 6B)
          a. Load Qwen2.5-VL 72B again
          b. Extract keyframes from each clip
          c. Verify each video vs script
          d. Handle fallbacks (regen/ken burns)
          e. Send video gallery to Telegram
          f. Gate: >85% pass → continue; else → regen or block
        
        STEP 6: Unload Qwen2.5-VL
```

**⚠️ HISTORICAL/POLITICAL CONTENT — Vision Limitations:**
```
Vision LLM CANNOT reliably verify:
├── Historical accuracy of clothing/uniforms/military ranks
├── Correct flags for specific time periods  
├── Architecture appropriate to the era
├── Weapon/vehicle models matching the described period
└── Cultural details specific to sub-regions

These are enforced UPSTREAM, not by Vision QA:
├── Phase 3 (Script): HistoricalContextValidator
│   → Embeds constraints in visual_prompt: "1990s Iraqi military uniform,
│     NOT modern, earth tones, beret, NO American-style camo"
├── Phase 5 (FLUX): Prompt engineering
│   → Negative prompts include era-inappropriate elements
│   → Regional LoRA selection for cultural accuracy
└── Phase 4 (Compliance): Flags sensitive historical topics
    → Routes to manual review (Phase 7.5) automatically

Vision QA checks: "does this look like a coherent documentary frame?"
Vision QA does NOT check: "is this historically accurate?"
```

**⚠️ CRITICAL: Phase 6 now runs in TWO stages with LTX in between:**
```
Images → 6A (image QA) → LTX video gen → 6B (video QA) → Voice gen
```
This means the state machine needs these transitions:
```
IMAGES → IMAGE_QA → VIDEO_GEN → VIDEO_QA → VOICE → ...
```

#### Phase 7: Final QA (`src/phase7_video_qa/`)
```
Input:  Composed video (output/[job_id]/final.mp4) — FULL assembled video
Output: Pass/Fail → DB: compliance_checks table
LLM:    Qwen2.5-VL 72B (vision) + Qwen 72B (text compliance)
GATE:   Can block

Files to build:
├── technical_check.py    → A/V sync, duration, resolution, bitrate, file integrity
│   Uses: ffprobe (part of FFmpeg) — no GPU needed
│
├── content_check.py      → Extract 1 frame per scene from FINAL video
│   Uses: Qwen2.5-VL 72B
│   Prompt: "This is the final assembled documentary video.
│            Here are keyframes from {N} scenes with their narration.
│            Check:
│            1. Does each frame match its narration?
│            2. Are text overlays readable and correctly positioned?
│            3. Is the intro/outro present?
│            4. Does it flow as a complete video?
│            5. Any frames that would get the video flagged?"
│   Returns: ContentCheckResult(score, issues: list)
│
├── final_compliance.py   → One last YouTube policy sweep (Qwen 72B text)
│
├── telegram_final_preview.py  ← NEW: Send final video to Yusif
│   └── send_final_preview(job_id) → None
│       Sends the FULL composed video to Telegram with:
│       ┌──────────────────────────────────────────────────────┐
│       │ 🎬 FINAL VIDEO — Ready for Review                   │
│       │ 📋 Topic: "{title}"                                  │
│       │ ⏱️ Duration: 10:24                                   │
│       │ 🎯 QA Scores:                                        │
│       │    Technical: 9.2/10                                 │
│       │    Content Match: 8.7/10                             │
│       │    Compliance: ✅ PASS                                │
│       │ [▶️ VIDEO ATTACHED — full video]                     │
│       │                                                      │
│       │ [✅ Publish] [🔄 Regenerate] [❌ Cancel]             │
│       └──────────────────────────────────────────────────────┘
│
└── video_qa_coordinator.py
    └── run(job_id) → Phase7Result
        1. technical_check (CPU — no GPU needed)
        2. Load Qwen2.5-VL 72B → content_check (vision)
        3. Swap to Qwen 72B → final_compliance (text)
        4. Send final preview to Telegram
        5. Return aggregate result + gate decision
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
| Architecture | Decomposed orchestrator (not God Object) | PipelineRunner + StateMachine + GateEvaluator + ResourceCoordinator = testable, maintainable |
| State management | Formal FSM with transition map | Prevents invalid status jumps, enables safe resume, catches bugs at compile-time |
| Event system | In-process EventBus + EventStore | Decouples phases from side effects. Not a broker — no RabbitMQ overhead |
| Database | SQLite now, split later | Single machine = SQLite. Split analytics to separate DB or Parquet when >500MB |
| GPU scheduling | Sequential with ResourceCoordinator | Single GPU — coordinator handles batching (same model = no swap) |
| LLM hosting | Ollama (not raw transformers) | API interface, memory control via keep_alive=0, easy model switching |
| Image gen | ComfyUI (not diffusers) | Workflow-based, supports LoRA, easy model swapping, web UI for debugging |
| Voice | Fish Speech 1.5 clone from real recordings | Human recordings cloned = natural Arabic pronunciation |
| Phase 5 | Sub-pipeline (3 coordinators, not 1 phase) | AssetCoordinator + AudioCoordinator + VideoComposer — most complex phase deserves structure |
| Agents | 3 tiers: core / optimization / experimental | Clear priority. Won't confuse production-critical with nice-to-have |
| Config | YAML (not JSON/TOML) | Readable, supports comments, good for multi-line strings |
| Error handling | Checkpoint + resume via FSM | 3-hour pipeline — FSM ensures correct resume point after any crash |
| Notifications | Telegram (not email/SMS) | Instant, interactive (inline buttons), free, Yusif already uses it |
| Phase 9 | Cron-based (not inline) | Analytics data isn't available immediately — needs 24h+ delay |
| Manual review | Selective (not always) | High-quality videos auto-publish; only flag edge cases |

---

## 13. Critical Rules for AI Builder

### Architecture Rules
1. **NEVER put phase logic in PipelineRunner.** It's a thin coordinator only. Phase logic goes in PhaseExecutor.
2. **ALWAYS transition status via JobStateMachine.** Direct DB updates bypass validation = bugs.
3. **ALWAYS emit events via EventBus.** Don't call Telegram/logging directly from phases.
4. **NEVER add agents to core_agents/ without explicit approval.** Default to experimental/.
5. **Phase 5 sub-modules report to their Coordinator** (Asset/Audio/Composer), not to PipelineRunner.

### GPU Rules
6. **NEVER load 2 GPU models simultaneously.** ResourceCoordinator handles this — trust it.
7. **ALWAYS check VRAM after unload.** If >15% still used = leak. Log it.
8. **Use ResourceCoordinator.prepare_for_status()** — don't call GPUManager directly from phases.

### Content Rules
9. **ALWAYS use English for FLUX/LTX prompts.** Arabic visual prompts produce garbage.
10. **ALWAYS include negative prompts** for images: "text, writing, letters, watermark"
11. **ALWAYS test voice clone quality** before using in production. Score must be >6/10.
12. **ALWAYS run Content ID check** on generated music before composing into video.
13. **NEVER use unofficial YouTube APIs for data that matters.** Official API only.

### Data Rules
14. **NEVER hardcode paths.** Everything comes from config/settings.yaml.
15. **ALWAYS save intermediate outputs to disk** (not just DB). Pipeline must be resumable.
16. **Status changes → DB + EventStore.** Both must be updated atomically.
