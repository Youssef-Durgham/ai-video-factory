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
│  │  Intelligence                       │  │   ├─ ACE-Step 1.5     │      │  │
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
LLM:            Qwen 3.5 Q4 (via Ollama)
Vision LLM:     Qwen 3.5-27B (unified vision) (via Ollama)
Image Gen:      FLUX.1-dev (via ComfyUI)
Video Gen:      LTX-2.3 (via ComfyUI)
Voice Clone:    Fish Audio S2 Pro (local)
Music Gen:      ACE-Step 1.5 (via audiocraft)
SFX Gen:        MOSS-SoundEffect (via audiocraft)
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
│   │   ├── telegram_bot.py         # Telegram bot core (§12.6)
│   │   ├── telegram_handlers.py    # Callback handlers for inline buttons (§12.6)
│   │   ├── telegram_conversations.py # Multi-step conversation flows (§12.6)
│   │   ├── job_queue.py            # Job queue + priority + concurrency (§12.7)
│   │   ├── retry_engine.py         # Per-service retry + backoff (§12.5.2)
│   │   ├── asset_versioner.py      # Asset version control (§12.5.3)
│   │   ├── quota_tracker.py        # YouTube API quota tracking (§12.5.4)
│   │   ├── storage_manager.py      # Disk cleanup + archival (§12.5.1)
│   │   ├── watchdog.py             # Service health monitor (§12.5.5)
│   │   └── db_backup.py            # SQLite backup + integrity (§12.9)
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
│   │   ├── writer.py               # Script writer (Qwen 3.5)
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
│   │   ├── music_gen.py            # ACE-Step 1.5 background music
│   │   ├── sfx_gen.py              # MOSS-SoundEffect sound effects
│   │   ├── content_id_guard.py     # Audio fingerprint protection
│   │   ├── upscaler.py             # Real-ESRGAN 4K upscale
│   │   ├── text_animator.py        # Animated Arabic text overlay system
│   │   ├── font_selector.py        # AI font + animation selection (Qwen 3.5)
│   │   ├── color_grader.py         # Color grading + LUT application
│   │   ├── transition_engine.py    # AI-driven scene transitions
│   │   ├── music_scene_sync.py     # Per-mood-zone music generation
│   │   ├── intro_outro.py          # Dynamic intro/outro per content type
│   │   ├── luts/                   # Cinematic LUT files (.cube)
│   │   │   ├── documentary_neutral.cube
│   │   │   ├── dramatic_teal_orange.cube
│   │   │   ├── historical_sepia_warm.cube
│   │   │   ├── military_cold_steel.cube
│   │   │   ├── islamic_warm_gold.cube
│   │   │   ├── tech_cyberpunk.cube
│   │   │   ├── editorial_clean.cube
│   │   │   └── storytelling_warm.cube
│   │   └── fonts/                  # Arabic font library (OTF/TTF files)
│   │       ├── IBM_Plex_Sans_Arabic/
│   │       ├── Noto_Naskh_Arabic/
│   │       ├── Amiri/
│   │       ├── Aref_Ruqaa/
│   │       ├── Cairo/
│   │       ├── Tajawal/
│   │       ├── Scheherazade_New/
│   │       ├── Readex_Pro/
│   │       ├── El_Messiri/
│   │       └── Lemonada/
│   │
│   ├── phase6_visual_qa/
│   │   ├── __init__.py
│   │   ├── image_checker.py        # Vision LLM: image vs script
│   │   ├── style_checker.py        # Style consistency
│   │   ├── sequence_checker.py     # Visual flow check
│   │   ├── audio_qa.py             # Voice/Music/SFX/Mix QA (§4.9)
│   │   ├── overlay_checker.py      # Text overlay QA (§Phase 6C)
│   │   └── regen_comparator.py     # Before/after comparison (§4.14)
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
    script: "qwen3.5:27b"
    vision: "qwen3.5:27b"
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
  engine: "fish_audio_s2_pro"             # "fish_audio_s2_pro" | "openaudios1" | "xtts"
  model_path: "models/fish_audio_s2_pro"
  fallback_engine: "elevenlabs"     # API fallback
  elevenlabs_api_key: "${ELEVENLABS_API_KEY}"  # from .env

# ─── Audio Generation ─────────────────────
audio:
  music_model: "facebook/ACE-Step 1.5"
  sfx_model: "facebook/MOSS-SoundEffect"
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
    IMAGE_QA      = "image_qa"         # 6A: Qwen 3.5-27B verifies images vs script
    IMAGE_REGEN   = "image_regen"      # Regenerate failed images
    VIDEO         = "video"            # LTX-2.3 video generation
    VIDEO_QA      = "video_qa"         # 6B: Qwen 3.5-27B verifies video clips vs script
    VIDEO_REGEN   = "video_regen"      # Regenerate failed clips (or Ken Burns fallback)
    VOICE         = "voice"
    MUSIC         = "music"
    SFX           = "sfx"
    COMPOSE       = "compose"
    OVERLAY_QA    = "overlay_qa"       # Verify Arabic text overlays are readable/positioned
    
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
    JobStatus.COMPOSE:       [JobStatus.OVERLAY_QA, JobStatus.BLOCKED],
    JobStatus.OVERLAY_QA:    [JobStatus.FINAL_QA, JobStatus.COMPOSE, JobStatus.BLOCKED],  # fail → re-compose
    
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
    JobStatus.RESEARCH:     "qwen3.5:27b",
    JobStatus.SEO:          "qwen3.5:27b",
    JobStatus.SCRIPT:       "qwen3.5:27b",
    JobStatus.COMPLIANCE:   "qwen3.5:27b",
    JobStatus.IMAGES:       "flux",
    JobStatus.IMAGE_QA:     "Qwen 3.5-27B:72b",      # Vision verification
    JobStatus.IMAGE_REGEN:  "flux",
    JobStatus.VIDEO:        "ltx",
    JobStatus.VIDEO_QA:     "Qwen 3.5-27B:72b",      # Vision verification
    JobStatus.VIDEO_REGEN:  "ltx",                  # Or Ken Burns (CPU)
    JobStatus.VOICE:        "fish_audio_s2_pro",
    JobStatus.MUSIC:        "ACE-Step 1.5",
    JobStatus.SFX:          "MOSS-SoundEffect",
    JobStatus.COMPOSE:      None,             # CPU only (FFmpeg)
    JobStatus.OVERLAY_QA:   "Qwen 3.5-27B:72b",   # Verify text overlays
    JobStatus.FINAL_QA:     "Qwen 3.5-27B:72b",   # Vision for frame analysis + text for compliance
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
        """
        Phase 7.5: Should this job go to manual review?
        
        ⚠️ CRITICAL DESIGN DECISION: Manual Review is the MOST IMPORTANT phase.
        ════════════════════════════════════════════════════════════════════════
        
        YouTube in 2026 is extremely sophisticated at detecting:
        - Low-effort AI content → demonetization, reduced reach
        - Policy violations → strikes, channel termination
        - Misleading content → community guideline strikes
        
        No matter how good Vision QA is, it CANNOT replace human judgment for:
        - "Does this video feel right?"
        - "Would I be embarrassed if this went public?"
        - "Is this actually good enough for my channel?"
        
        MODES:
        ├── "all" (RECOMMENDED for first 50 videos)
        │   → Every video gets manual review. No exceptions.
        │   → This builds your intuition for what the system produces.
        │   
        ├── "selective" (after 50+ videos with consistent quality)
        │   → Auto-publish ONLY if ALL conditions met:
        │     ├── QA scores > 8.5 (not 8.0 — be strict)
        │     ├── Topic is NOT in sensitive_categories
        │     ├── No human flags from ANY QA phase
        │     ├── Channel has >20 videos published (established)
        │     ├── No YouTube strikes in last 90 days
        │     └── Not a "first video" on a new topic category
        │   → Everything else → manual review
        │   
        └── "off" (NEVER RECOMMENDED)
            → ⚠️ Config accepts this but logs a CRITICAL warning every time
            → "Manual review disabled — publishing without human verification"
            → If you use this, you accept the risk of strikes/demonetization
        
        IMPORTANT: Even in "selective" mode, certain videos ALWAYS get reviewed:
        ├── Political content (any mention of politics, leaders, conflicts)
        ├── Religious content (any mention of religion, sects, beliefs)
        ├── Historical claims (wars, massacres, disputed events)
        ├── Content about real living people
        ├── Content about ongoing legal matters
        ├── First video in a new topic category
        └── Any video where ANY QA phase flagged something
        """
        review_config = config["settings"]["manual_review"]
        
        # Mode: off (STRONGLY discouraged)
        if not review_config["enabled"] or review_config["mode"] == "off":
            logger.critical(
                "⚠️ MANUAL REVIEW DISABLED — publishing without human verification. "
                "This is risky. YouTube strikes can terminate your channel."
            )
            return False
        
        # Mode: all (recommended for first 50 videos)
        if review_config["mode"] == "all":
            return True
        
        # Mode: selective — STRICT conditions for auto-publish
        # ═══ ALWAYS REVIEW (non-negotiable) ═══
        always_review_categories = [
            "politics", "political_analysis", "geopolitics",
            "religion", "islamic", "sectarian",
            "war", "military_conflict", "terrorism",
            "legal", "crime", "human_rights",
            "biography_living_person",
        ]
        if job.get("topic_category") in always_review_categories:
            return True  # ALWAYS review sensitive content
        
        # Check if any QA phase flagged anything
        flags = self.db.get_job_flags(job["id"])
        if any(f["severity"] in ("warn", "error") for f in flags):
            return True  # Any flag → review
        
        # Check QA scores — ALL must be above STRICT threshold
        min_score = review_config.get("auto_publish_min_score", 8.5)
        rubric_stats = self.db.get_rubric_stats(job["id"])
        for stat in rubric_stats:
            if stat["avg_score"] < min_score:
                return True  # Below threshold → review
        
        # Check channel maturity
        channel_video_count = self.db.count_published_videos(job["channel_id"])
        if channel_video_count < 20:
            return True  # New channel → review everything
        
        # Check for recent strikes
        recent_strikes = self.db.get_recent_strikes(job["channel_id"], days=90)
        if recent_strikes:
            return True  # Recent trouble → review
        
        # Check if first video in this topic category
        category_count = self.db.count_videos_in_category(
            job["channel_id"], job["topic_category"]
        )
        if category_count == 0:
            return True  # First in category → review
        
        # ALL conditions passed → safe to auto-publish
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
        if model_name in ("qwen3.5:27b", "Qwen 3.5-27B:72b"):
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
    
    # Operational
    SERVICE_UNHEALTHY     = "ops.service_unhealthy"
    SERVICE_RESTARTED     = "ops.service_restarted"
    QUOTA_LOW             = "ops.quota_low"
    QUOTA_EXHAUSTED       = "ops.quota_exhausted"
    DISK_LOW              = "ops.disk_low"
    STORAGE_CLEANED       = "ops.storage_cleaned"
    ASSET_VERSIONED       = "ops.asset_versioned"
    ASSET_ROLLED_BACK     = "ops.asset_rolled_back"
    RETRY_ATTEMPTED       = "ops.retry_attempted"
    RETRY_EXHAUSTED       = "ops.retry_exhausted"


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
Persists all events to SQLite for audit trail, TRACING, and replay.

⚠️ CRITICAL: With 40 agents + EventBus, debugging is a nightmare
without proper tracing. Every event MUST carry trace context.
"""

import uuid


@dataclass
class Event:
    """Enhanced Event with distributed tracing fields."""
    type: EventType
    job_id: str = ""
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    # ─── TRACING FIELDS (mandatory for debugging) ───
    trace_id: str = ""          # Unique per job run (all events in one job share this)
    span_id: str = ""           # Unique per event
    parent_span_id: str = ""    # Links child events to parent (phase → sub-step)
    source: str = ""            # Which component emitted: "phase6a.image_checker", "gpu_manager"
    severity: str = "info"      # "debug" | "info" | "warn" | "error" | "critical"
    duration_ms: int = 0        # How long the operation took (for perf analysis)


class EventStore:
    """
    Persistent event log with FULL tracing support.
    
    Why tracing matters:
    ├── 40 agents + 9 phases + sub-phases = hundreds of events per job
    ├── Without trace_id: "which events belong to this job run?"
    ├── Without span_id: "in what order did things happen?"
    ├── Without parent_span: "image_checker failed, but WHO called it?"
    ├── Without source: "which of the 40 agents emitted this?"
    └── Without duration_ms: "what's slow? where's the bottleneck?"
    
    DEBUGGING WORKFLOW:
    ─────────────────
    1. Job fails → get trace_id from job table
    2. SELECT * FROM events WHERE trace_id = ? ORDER BY timestamp
    3. See COMPLETE history: every phase, every check, every retry, every decision
    4. parent_span_id shows call hierarchy:
       
       pipeline_runner.run_job (span: abc)
       ├── phase_executor.execute:IMAGE_QA (span: def, parent: abc)
       │   ├── image_checker.verify (span: ghi, parent: def)
       │   │   ├── deterministic.ocr (span: jkl, parent: ghi) → 45ms
       │   │   ├── deterministic.nsfw (span: mno, parent: ghi) → 12ms
       │   │   └── vision.rubric (span: pqr, parent: ghi) → 3400ms ← SLOW
       │   ├── image_checker.verify (span: stu, parent: def) → scene 2
       │   └── style_checker.check (span: vwx, parent: def)
       └── resource_coordinator.unload (span: yz1, parent: abc)
    
    5. Instantly see: vision rubric took 3.4s per image × 15 = 51s total
    
    TELEGRAM DEBUG COMMAND:
    /trace job_20260315_120000
    → Returns: summary of all events, highlighting errors and slow steps
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        job_id TEXT,
        trace_id TEXT NOT NULL,           -- Groups all events in one job run
        span_id TEXT NOT NULL,            -- Unique per event
        parent_span_id TEXT,              -- Parent event (call hierarchy)
        source TEXT,                      -- Component that emitted
        severity TEXT DEFAULT 'info',     -- debug/info/warn/error/critical
        duration_ms INTEGER DEFAULT 0,   -- Operation duration
        data JSON,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
    CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
    CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
    CREATE INDEX IF NOT EXISTS idx_events_parent ON events(parent_span_id);
    CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp);
    CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
    CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
    """
    
    def __init__(self, db):
        self.db = db
        self.db.conn.executescript(self.SCHEMA)
    
    def store(self, event: Event):
        """Store event with full tracing context."""
        if not event.span_id:
            event.span_id = str(uuid.uuid4())[:8]
        
        self.db.conn.execute("""
            INSERT INTO events (event_type, job_id, trace_id, span_id, parent_span_id,
                source, severity, duration_ms, data, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.type.value, event.job_id, event.trace_id, event.span_id,
            event.parent_span_id, event.source, event.severity,
            event.duration_ms, json.dumps(event.data), event.timestamp
        ))
        self.db.conn.commit()
    
    def get_job_trace(self, job_id: str) -> list[dict]:
        """Get complete trace for a job — THE primary debugging tool."""
        rows = self.db.conn.execute("""
            SELECT * FROM events WHERE job_id = ? 
            ORDER BY timestamp ASC
        """, (job_id,)).fetchall()
        return [dict(r) for r in rows]
    
    def get_trace_tree(self, trace_id: str) -> dict:
        """Build hierarchical trace tree from flat events."""
        events = self.db.conn.execute(
            "SELECT * FROM events WHERE trace_id = ? ORDER BY timestamp",
            (trace_id,)
        ).fetchall()
        
        # Build tree: parent_span_id → children
        by_span = {e["span_id"]: dict(e) for e in events}
        roots = []
        for e in events:
            e_dict = by_span[e["span_id"]]
            parent = e["parent_span_id"]
            if parent and parent in by_span:
                by_span[parent].setdefault("children", []).append(e_dict)
            else:
                roots.append(e_dict)
        return roots
    
    def get_errors(self, job_id: str = None, hours: int = 24) -> list[dict]:
        """Get recent errors/criticals — for /health command."""
        query = """
            SELECT * FROM events 
            WHERE severity IN ('error', 'critical')
            AND timestamp > datetime('now', ?)
        """
        params = [f"-{hours} hours"]
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY timestamp DESC LIMIT 50"
        return [dict(r) for r in self.db.conn.execute(query, params).fetchall()]
    
    def get_slow_operations(self, job_id: str, threshold_ms: int = 5000) -> list[dict]:
        """Find operations that took longer than threshold — bottleneck finder."""
        rows = self.db.conn.execute("""
            SELECT source, event_type, duration_ms, span_id, data
            FROM events 
            WHERE job_id = ? AND duration_ms > ?
            ORDER BY duration_ms DESC
        """, (job_id, threshold_ms)).fetchall()
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

### 4.5.1 Tracing Context (`src/core/tracing.py`)

```python
"""
Tracing context — passed through the entire pipeline.
Every component uses this to emit properly-linked events.
"""

class TracingContext:
    """
    Created once per job run. Passed to every phase/coordinator/checker.
    
    Usage:
        trace = TracingContext(job_id="job_20260315_120000")
        
        # In PipelineRunner:
        with trace.span("pipeline_runner.run_job") as span:
            # In PhaseExecutor:
            with trace.span("phase6a.image_qa", parent=span) as child:
                # In ImageChecker:
                with trace.span("image_checker.verify_scene_5", parent=child) as leaf:
                    result = check_image(...)
                    # leaf auto-records duration_ms on exit
    """
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.trace_id = str(uuid.uuid4())[:12]  # Shared across all events in this run
        self.event_bus = None  # Set by PipelineRunner
    
    def span(self, source: str, parent=None):
        """Create a tracing span (context manager)."""
        return Span(
            trace_id=self.trace_id,
            job_id=self.job_id,
            source=source,
            parent_span_id=parent.span_id if parent else None,
            event_bus=self.event_bus
        )


class Span:
    """Individual tracing span — tracks one operation."""
    
    def __init__(self, trace_id, job_id, source, parent_span_id, event_bus):
        self.trace_id = trace_id
        self.job_id = job_id
        self.source = source
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_span_id = parent_span_id
        self.event_bus = event_bus
        self._start_time = None
    
    def __enter__(self):
        self._start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self._start_time) * 1000)
        severity = "error" if exc_type else "info"
        
        self.event_bus.emit(Event(
            type=EventType.PHASE_COMPLETED if not exc_type else EventType.PHASE_FAILED,
            job_id=self.job_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            source=self.source,
            severity=severity,
            duration_ms=duration_ms,
            data={"error": str(exc_val)} if exc_type else {}
        ))
    
    def emit(self, event_type: EventType, data: dict = None, severity: str = "info"):
        """Emit an event within this span's context."""
        self.event_bus.emit(Event(
            type=event_type,
            job_id=self.job_id,
            trace_id=self.trace_id,
            span_id=str(uuid.uuid4())[:8],
            parent_span_id=self.span_id,
            source=self.source,
            severity=severity,
            data=data or {}
        ))
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
Combines: video clips + voice + music + SFX + ANIMATED text overlays + intro/outro.
"""

class VideoComposer:
    def run(self, job_id: str) -> PhaseResult:
        # ... FFmpeg assembly logic
        pass


# ═══ src/phase5_production/text_animator.py ═══
"""
Animated Arabic Text Overlay System.

NOT static drawtext! Renders animated text as transparent video layers (MOV/WebM + alpha),
then composites with FFmpeg. This enables cinematic text animations.

Architecture:
┌───────────────────────────────────────────────────────────────────┐
│                     TEXT ANIMATION PIPELINE                        │
│                                                                   │
│  1. AI Font Selector (Qwen 3.5)                                  │
│     Script mood + topic → selects font + animation style          │
│                                                                   │
│  2. Text Renderer (Pillow + Cairo)                                │
│     Renders each frame of the animation as PNG with alpha         │
│                                                                   │
│  3. Animation Encoder (FFmpeg)                                    │
│     PNGs → transparent video overlay (ProRes 4444 or VP9+alpha)   │
│                                                                   │
│  4. Compositor (FFmpeg)                                           │
│     Base video + overlay video → final composed video             │
└───────────────────────────────────────────────────────────────────┘
"""

from dataclasses import dataclass
from enum import Enum


# ═══════════════════════════════════════════════════════════════
# ARABIC FONT LIBRARY
# ═══════════════════════════════════════════════════════════════

class FontCategory(str, Enum):
    FORMAL_NEWS     = "formal_news"       # أخبار رسمية، تحليل سياسي
    DRAMATIC        = "dramatic"          # وثائقي درامي، جرائم، ألغاز
    HISTORICAL      = "historical"        # تاريخي، حضارات، حروب قديمة
    MODERN_TECH     = "modern_tech"       # تكنولوجيا، علوم، مستقبل
    ISLAMIC         = "islamic"           # ديني، إسلامي، تراث
    MILITARY        = "military"          # عسكري، جيوسياسي، حروب حديثة
    EDITORIAL       = "editorial"         # رأي، تعليق، تحليل
    STORYTELLING    = "storytelling"      # قصص، سرد، حكايات


# Font library — curated Arabic fonts (all free/open-source)
FONT_LIBRARY = {
    FontCategory.FORMAL_NEWS: {
        "primary": "IBM Plex Sans Arabic",      # نظيف، رسمي، مقروء
        "accent": "Noto Naskh Arabic",           # للعناوين
        "fallback": "Cairo",
        "weight_range": [400, 700],
        "style_notes": "Clean, authoritative. No decorations."
    },
    FontCategory.DRAMATIC: {
        "primary": "Aref Ruqaa",                 # درامي، مشوّق
        "accent": "Lemonada",                     # للتأثير
        "fallback": "Tajawal",
        "weight_range": [700, 900],
        "style_notes": "Bold, high contrast. Shadows allowed."
    },
    FontCategory.HISTORICAL: {
        "primary": "Amiri",                       # كلاسيكي، تراثي
        "accent": "Scheherazade New",             # للاقتباسات التاريخية
        "fallback": "Noto Naskh Arabic",
        "weight_range": [400, 700],
        "style_notes": "Elegant, classical. Ornamental accents OK."
    },
    FontCategory.MODERN_TECH: {
        "primary": "IBM Plex Sans Arabic",        # حديث، تقني
        "accent": "Readex Pro",                   # هندسي
        "fallback": "Cairo",
        "weight_range": [300, 600],
        "style_notes": "Geometric, minimal. Thin weights for futuristic feel."
    },
    FontCategory.ISLAMIC: {
        "primary": "Scheherazade New",            # نسخ تقليدي
        "accent": "Amiri Quran",                  # للآيات
        "fallback": "Amiri",
        "weight_range": [400, 700],
        "style_notes": "Traditional Naskh. Respectful, ornate headers."
    },
    FontCategory.MILITARY: {
        "primary": "Cairo",                       # قوي، مباشر
        "accent": "Tajawal",                      # للأرقام والإحصائيات
        "fallback": "IBM Plex Sans Arabic",
        "weight_range": [600, 900],
        "style_notes": "Heavy weight, all-caps feel. Stark, impactful."
    },
    FontCategory.EDITORIAL: {
        "primary": "Noto Sans Arabic",            # نظيف، محايد
        "accent": "El Messiri",                   # للعناوين
        "fallback": "Cairo",
        "weight_range": [400, 700],
        "style_notes": "Neutral, readable. Let the content speak."
    },
    FontCategory.STORYTELLING: {
        "primary": "Tajawal",                     # دافئ، ودود
        "accent": "Lemonada",                     # مرح
        "fallback": "Noto Sans Arabic",
        "weight_range": [300, 600],
        "style_notes": "Warm, inviting. Slightly rounded."
    },
}


# ═══════════════════════════════════════════════════════════════
# ANIMATION STYLES
# ═══════════════════════════════════════════════════════════════

class AnimationStyle(str, Enum):
    # ─── Entry Animations (text appears) ───
    TYPEWRITER      = "typewriter"       # حرف حرف (character by character RTL)
    WORD_BY_WORD    = "word_by_word"     # كلمة كلمة مع الصوت
    FADE_IN         = "fade_in"          # تظهر تدريجياً (alpha 0→1)
    SLIDE_RIGHT     = "slide_right"      # تنزلق من اليمين (RTL natural direction)
    SLIDE_UP        = "slide_up"         # تطلع من تحت
    SCALE_UP        = "scale_up"         # تكبر من صغير
    BLUR_REVEAL     = "blur_reveal"      # من ضبابي لواضح
    GLITCH_IN       = "glitch_in"        # تأثير تشويش (للتقني/الدرامي)
    LETTER_CASCADE  = "letter_cascade"   # كل حرف يسقط بمكانه
    
    # ─── Exit Animations (text disappears) ───
    FADE_OUT        = "fade_out"
    SLIDE_LEFT      = "slide_left"
    SCALE_DOWN      = "scale_down"
    
    # ─── Persistent Effects (while text is visible) ───
    SUBTLE_FLOAT    = "subtle_float"     # حركة خفيفة للأعلى/أسفل
    GLOW_PULSE      = "glow_pulse"       # نبض خفيف بالإضاءة
    SHADOW_DRIFT    = "shadow_drift"     # الظل يتحرك ببطء


# Animation presets per content type
ANIMATION_PRESETS = {
    FontCategory.FORMAL_NEWS: {
        "entry": AnimationStyle.SLIDE_RIGHT,
        "exit": AnimationStyle.FADE_OUT,
        "persistent": None,
        "duration_entry_ms": 400,
        "duration_exit_ms": 300,
        "easing": "ease_out_cubic",
    },
    FontCategory.DRAMATIC: {
        "entry": AnimationStyle.BLUR_REVEAL,
        "exit": AnimationStyle.FADE_OUT,
        "persistent": AnimationStyle.GLOW_PULSE,
        "duration_entry_ms": 600,
        "duration_exit_ms": 400,
        "easing": "ease_in_out_quad",
    },
    FontCategory.HISTORICAL: {
        "entry": AnimationStyle.TYPEWRITER,
        "exit": AnimationStyle.FADE_OUT,
        "persistent": None,
        "duration_entry_ms": 800,       # Slower = more elegant
        "duration_exit_ms": 500,
        "easing": "linear",
    },
    FontCategory.MODERN_TECH: {
        "entry": AnimationStyle.GLITCH_IN,
        "exit": AnimationStyle.SCALE_DOWN,
        "persistent": AnimationStyle.SUBTLE_FLOAT,
        "duration_entry_ms": 350,       # Fast = techy
        "duration_exit_ms": 250,
        "easing": "ease_out_expo",
    },
    FontCategory.ISLAMIC: {
        "entry": AnimationStyle.FADE_IN,
        "exit": AnimationStyle.FADE_OUT,
        "persistent": None,
        "duration_entry_ms": 700,       # Gentle, respectful
        "duration_exit_ms": 700,
        "easing": "ease_in_out_sine",
    },
    FontCategory.MILITARY: {
        "entry": AnimationStyle.SLIDE_UP,
        "exit": AnimationStyle.SLIDE_LEFT,
        "persistent": None,
        "duration_entry_ms": 300,       # Sharp, decisive
        "duration_exit_ms": 200,
        "easing": "ease_out_quart",
    },
    FontCategory.EDITORIAL: {
        "entry": AnimationStyle.WORD_BY_WORD,
        "exit": AnimationStyle.FADE_OUT,
        "persistent": None,
        "duration_entry_ms": 500,
        "duration_exit_ms": 300,
        "easing": "ease_out_cubic",
    },
    FontCategory.STORYTELLING: {
        "entry": AnimationStyle.LETTER_CASCADE,
        "exit": AnimationStyle.FADE_OUT,
        "persistent": AnimationStyle.SUBTLE_FLOAT,
        "duration_entry_ms": 600,
        "duration_exit_ms": 400,
        "easing": "ease_out_back",       # Slight overshoot = playful
    },
}


# ═══════════════════════════════════════════════════════════════
# AI FONT + ANIMATION SELECTOR
# ═══════════════════════════════════════════════════════════════

class FontAnimationSelector:
    """
    Uses Qwen 3.5 to analyze script and select optimal font + animation.
    Runs during Phase 3 (Script) — decision stored in DB for Phase 5 (Compose).
    
    Why AI selection:
    - Same "military" topic can be tense thriller or calm analysis
    - Script TONE matters more than just topic category
    - AI reads the actual script and picks the best match
    """
    
    def select(self, script: dict, channel_config: dict) -> FontAnimationConfig:
        """
        Qwen 3.5 prompt:
        ┌──────────────────────────────────────────────────────────┐
        │ You are a professional Arabic video typographer.          │
        │                                                          │
        │ VIDEO SCRIPT:                                            │
        │ Title: "{title}"                                         │
        │ Topic: {topic_category}                                  │
        │ Tone: {emotional_arc}                                    │
        │ Sample narration: "{first_3_scenes_narration}"           │
        │ Channel style: {channel_brand_kit}                       │
        │                                                          │
        │ Available font categories:                               │
        │ {list FontCategory with descriptions}                    │
        │                                                          │
        │ Select:                                                  │
        │ 1. font_category: Which category best fits this video?   │
        │ 2. primary_weight: Font weight (300-900)                 │
        │ 3. accent_usage: Where to use accent font?               │
        │    "titles_only" | "quotes" | "statistics" | "none"      │
        │ 4. text_color: Hex color for primary text                │
        │ 5. accent_color: Hex color for accent/highlight          │
        │ 6. background_style: "none" | "box" | "gradient" | "blur"│
        │ 7. animation_override: null (use preset) or specific     │
        │    animation if the preset doesn't fit                   │
        │ 8. reasoning: Why this combination?                      │
        │                                                          │
        │ Return JSON.                                             │
        └──────────────────────────────────────────────────────────┘
        """
        pass
    
    # Falls back to rule-based selection if LLM fails
    def _fallback_select(self, topic_category: str) -> FontAnimationConfig:
        """Direct category → font mapping. No AI needed."""
        pass


@dataclass
class FontAnimationConfig:
    """Stored in DB: jobs.font_animation_config (JSON)"""
    font_category: FontCategory
    primary_font: str
    accent_font: str
    primary_weight: int
    accent_usage: str       # "titles_only" | "quotes" | "statistics" | "none"
    text_color: str         # "#FFFFFF"
    accent_color: str       # "#FFD700"
    background_style: str   # "none" | "box" | "gradient" | "blur"
    background_color: str   # "#00000080" (semi-transparent black)
    animation_preset: dict  # From ANIMATION_PRESETS
    animation_override: dict = None  # AI can override specific animations
    reasoning: str = ""


# ═══════════════════════════════════════════════════════════════
# TEXT ANIMATION RENDERER
# ═══════════════════════════════════════════════════════════════

class TextAnimationRenderer:
    """
    Renders animated Arabic text as transparent video overlays.
    
    Method: Frame-by-frame rendering → transparent video layer
    
    Pipeline per text overlay:
    1. Calculate total frames needed (entry + hold + exit)
    2. For each frame:
       a. Calculate animation state (position, alpha, scale, etc.)
       b. Render text with Pillow/PyCairo on transparent canvas
       c. Apply effects (shadow, glow, background box)
       d. Save as PNG with alpha channel
    3. Encode PNGs → transparent video (FFmpeg ProRes 4444 or VP9+alpha)
    4. Overlay onto base video at correct timestamp
    
    Why not FFmpeg drawtext?
    ├── drawtext CAN do fade/slide but NOT:
    │   ├── Typewriter (character by character)
    │   ├── Word-by-word sync
    │   ├── Blur reveal
    │   ├── Glitch effects
    │   ├── Letter cascade
    │   ├── Complex easing curves
    │   └── Per-character animations
    ├── Pillow/Cairo gives FULL control over every pixel per frame
    └── Pre-rendered overlays = predictable quality (no FFmpeg font issues)
    """
    
    def render_overlay(self, text: str, config: FontAnimationConfig,
                       scene_duration_sec: float, fps: int = 30,
                       resolution: tuple = (1920, 1080)) -> str:
        """
        Renders animated text overlay as transparent video file.
        Returns: path to overlay video (ProRes 4444 with alpha)
        """
        preset = config.animation_override or config.animation_preset
        
        # Calculate frame counts
        entry_frames = int(preset["duration_entry_ms"] / 1000 * fps)
        exit_frames = int(preset["duration_exit_ms"] / 1000 * fps)
        hold_frames = int(scene_duration_sec * fps) - entry_frames - exit_frames
        total_frames = entry_frames + hold_frames + exit_frames
        
        frames = []
        for i in range(total_frames):
            # Determine animation phase
            if i < entry_frames:
                phase = "entry"
                progress = self._ease(i / entry_frames, preset["easing"])
            elif i < entry_frames + hold_frames:
                phase = "hold"
                progress = 1.0
            else:
                phase = "exit"
                exit_progress = (i - entry_frames - hold_frames) / exit_frames
                progress = 1.0 - self._ease(exit_progress, preset["easing"])
            
            # Render frame
            frame = self._render_frame(
                text=text,
                config=config,
                animation_style=preset[phase] if phase != "hold" else preset.get("persistent"),
                progress=progress,
                resolution=resolution
            )
            frames.append(frame)
        
        # Encode frames → transparent video
        return self._encode_overlay(frames, fps)
    
    def _render_frame(self, text, config, animation_style, progress, resolution):
        """
        Render single frame using PyCairo (better Arabic shaping than Pillow).
        
        PyCairo advantages for Arabic:
        ├── Proper HarfBuzz text shaping (ligatures, marks)
        ├── Pango layout for complex RTL text
        ├── Sub-pixel rendering
        └── Gradient fills, shadows, outlines natively
        """
        # 1. Create transparent canvas
        # 2. Apply animation transform (position, alpha, scale based on progress)
        # 3. Render text with font, color, shadow
        # 4. Apply background box/gradient if configured
        # 5. Return as PIL Image (RGBA)
        pass
    
    def _ease(self, t: float, easing: str) -> float:
        """Easing functions for smooth animations."""
        if easing == "linear": return t
        elif easing == "ease_out_cubic": return 1 - (1-t)**3
        elif easing == "ease_out_expo": return 1 - 2**(-10*t) if t > 0 else 0
        elif easing == "ease_in_out_quad": return 2*t*t if t < 0.5 else 1-(-2*t+2)**2/2
        elif easing == "ease_in_out_sine": return -(math.cos(math.pi*t)-1)/2
        elif easing == "ease_out_quart": return 1 - (1-t)**4
        elif easing == "ease_out_back": c1=1.70158; return 1+c1*((t-1)**3)+c1*((t-1)**2)
        return t
    
    def _encode_overlay(self, frames: list, fps: int) -> str:
        """
        Encode PNG frames → transparent video.
        
        Option A: ProRes 4444 (best quality, large files)
        ffmpeg -framerate 30 -i frame_%04d.png -c:v prores_ks -profile:v 4444 
               -pix_fmt yuva444p10le overlay.mov
        
        Option B: VP9 + alpha (smaller files, good quality)
        ffmpeg -framerate 30 -i frame_%04d.png -c:v libvpx-vp9 
               -pix_fmt yuva420p overlay.webm
        
        We use ProRes 4444 (quality > size for intermediate files).
        """
        pass


# ═══════════════════════════════════════════════════════════════
# SPECIAL ANIMATIONS (complex ones that need custom rendering)
# ═══════════════════════════════════════════════════════════════

class TypewriterAnimation:
    """
    Character-by-character reveal, RTL direction.
    Arabic-aware: reveals full ligature groups, not broken characters.
    
    Uses python-bidi + arabic-reshaper to handle:
    ├── Connected letters (لا as one unit, not ل + ا)
    ├── Diacritics (تشكيل) appear with their letter
    └── RTL cursor position
    """
    pass

class WordByWordAnimation:
    """
    Syncs word appearance with narration audio.
    
    Method:
    1. Get word-level timestamps from voice generation (Fish Audio S2 Pro outputs these)
    2. Each word fades/slides in at exactly its spoken timestamp
    3. Creates "karaoke-style" text that follows the narrator
    
    Perfect for: quotes, poetry, Quranic verses, key statements
    """
    pass

class GlitchAnimation:
    """
    Digital glitch effect — text appears with distortion then stabilizes.
    
    Method per frame:
    1. Render text normally
    2. Random horizontal slice displacement (RGB channel shift)
    3. Random scanline noise
    4. Decreasing intensity over entry_frames → clean text at end
    
    Perfect for: tech topics, hacking, conspiracy, dystopia
    """
    pass
```

---

### 4.9 Audio QA System (`src/phase6_visual_qa/audio_qa.py`)

> **The missing QA layer.** Images/video have 3-layer verification. Audio has NOTHING.
> Audio = 50% of video quality (voice, music, SFX). Must be verified.

```python
"""
Audio QA — 3-layer verification for all audio assets.
Runs after each audio generation step (VOICE, MUSIC, SFX).

Architecture:
  VOICE → Audio QA (voice) → MUSIC → Audio QA (music) → SFX → Audio QA (sfx)
  
Audio QA runs INLINE (not a separate phase) — lightweight checks after each generation.
Heavy checks (full mix analysis) run after COMPOSE.
"""

# ═══════════════════════════════════════════════════════════════
# VOICE QA
# ═══════════════════════════════════════════════════════════════

class VoiceQA:
    """
    Verify Fish Audio S2 Pro voice output quality.
    
    LAYER 1: DETERMINISTIC (signal processing)
    ├── Silence detection
    │   → librosa.effects.split() — find silent gaps
    │   → Gap > 2s in middle of narration = FAIL
    │   → No audio at all = FAIL
    ├── Clipping detection  
    │   → Samples hitting ±1.0 for > 10ms = clipping
    │   → > 5 clip events = FAIL
    ├── Duration check
    │   → Actual vs expected (from script word count × WPM)
    │   → Off by > 20% = suspect (too fast/slow)
    ├── SNR (Signal-to-Noise Ratio)
    │   → SNR < 20dB = poor quality
    ├── Spectral analysis
    │   → Frequency range 80Hz-8kHz (human speech)
    │   → Energy outside this range = artifacts
    └── Consistent volume (RMS)
        → Scene-to-scene RMS variation > 6dB = inconsistent
    
    LAYER 2: WHISPER STT VERIFICATION (CPU — no GPU needed)
    ├── Run Whisper (tiny/base) on generated audio
    │   → Compare transcription vs original script text
    │   → Word Error Rate (WER) calculation
    │   → WER > 15% = pronunciation problems
    ├── Arabic-specific checks
    │   → Common Fish Audio S2 Pro Arabic errors:
    │     - ع vs أ confusion
    │     - ح vs ه confusion  
    │     - Tashkeel (diacritics) pronunciation
    │     - Names/places pronunciation
    └── Timing extraction
        → Word-level timestamps for word-by-word text animation sync
    
    LAYER 3: PROSODY ANALYSIS
    ├── Pitch contour (F0 tracking via CREPE/pYIN)
    │   → Monotone detection: pitch std < threshold = robotic
    │   → Pitch matches scene emotion? (sad=lower, exciting=higher)
    ├── Speaking rate variation
    │   → Constant WPM throughout = unnatural
    │   → Should vary with content (faster for action, slower for emphasis)
    └── Emotion match
        → Scene emotion tag vs detected audio emotion
        → Basic classifier: energy + pitch + rate → calm/excited/tense/sad
    
    Returns: VoiceQAResult(
        silence_gaps: list,
        clipping_events: int,
        duration_ratio: float,       # actual/expected
        snr_db: float,
        wer: float,                  # Word Error Rate
        misheard_words: list[dict],  # [{expected, heard, timestamp}]
        pitch_monotone: bool,
        emotion_match: float,        # 0-1
        word_timestamps: list,       # For text animation sync
        verdict: str,                # pass | regen | flag_human
    )
    """
    pass


# ═══════════════════════════════════════════════════════════════
# MUSIC QA
# ═══════════════════════════════════════════════════════════════

class MusicQA:
    """
    Verify ACE-Step 1.5 output + scene mood alignment.
    
    LAYER 1: DETERMINISTIC
    ├── Duration match (expected vs actual)
    ├── Content ID check (already exists — audio fingerprint)
    ├── Clipping / distortion detection
    ├── Silence detection (should be continuous)
    └── Volume level appropriate for background (target: -18 to -24 LUFS)
    
    LAYER 2: MOOD ANALYSIS
    ├── Extract audio features (librosa)
    │   → Tempo (BPM), key, energy, danceability
    ├── Compare vs scene mood tag
    │   → "tense" scene should have: minor key, low tempo, sparse arrangement
    │   → "hopeful" scene: major key, moderate tempo, fuller arrangement
    │   → "dramatic" scene: variable tempo, dynamic range, crescendos
    └── Transition smoothness
        → If music changes between scenes, check for abrupt cuts
        → Auto-crossfade if cut detected
    
    Returns: MusicQAResult(
        content_id_safe: bool,
        mood_match: float,           # 0-1
        volume_lufs: float,
        tempo_bpm: float,
        verdict: str
    )
    """
    pass


# ═══════════════════════════════════════════════════════════════
# MIX QA (after COMPOSE — full audio mix analysis)
# ═══════════════════════════════════════════════════════════════

class MixQA:
    """
    After FFmpeg mixes voice + music + SFX → verify the MIX is correct.
    
    Checks:
    ├── Voice intelligibility
    │   → Run Whisper on MIXED audio (not isolated voice)
    │   → WER should be close to isolated voice WER
    │   → If WER increased > 5% → music/SFX too loud
    ├── Music ducking verification
    │   → During narration: music volume should drop
    │   → Measure music-to-voice ratio during speech segments
    │   → Ratio should be -12dB to -18dB
    ├── SFX timing
    │   → SFX should not overlap with key narration words
    │   → SFX volume should not exceed voice
    ├── Overall loudness
    │   → LUFS measurement (YouTube target: -14 LUFS)
    │   → True peak < -1 dBTP
    └── Audio-video sync drift
        → Compare voice onset with scene transition timing
        → Drift > 100ms = problem
    
    Returns: MixQAResult(
        voice_intelligibility_wer: float,
        ducking_correct: bool,
        overall_lufs: float,
        true_peak_dbtp: float,
        av_sync_drift_ms: float,
        verdict: str
    )
    """
    pass
```

### 4.10 Color Grading System (`src/phase5_production/color_grader.py`)

> **Problem:** FLUX generates each image independently → inconsistent colors across scenes.
> A documentary needs unified visual identity.

```python
"""
Automatic color grading — ensures visual consistency across all scenes.
Runs AFTER all images generated, BEFORE video generation (LTX).

Pipeline:
  FLUX images → Color Grader → graded images → LTX video → ...

Method: Reference-based color transfer + LUT application.
CPU only — no GPU needed.
"""

class ColorGrader:
    """
    Two approaches (AI selects which):
    
    APPROACH 1: LUT-Based (fast, predictable)
    ├── Library of cinematic LUTs categorized by mood:
    │   ├── documentary_neutral.cube    — clean, slightly desaturated
    │   ├── dramatic_teal_orange.cube   — Hollywood blockbuster look
    │   ├── historical_sepia_warm.cube  — warm, aged feel
    │   ├── military_cold_steel.cube    — blue-grey, high contrast
    │   ├── islamic_warm_gold.cube      — warm, golden tones
    │   ├── tech_cyberpunk.cube         — high saturation, neon accents
    │   ├── editorial_clean.cube        — minimal color shift
    │   └── storytelling_warm.cube      — warm, inviting
    │
    ├── AI selects LUT based on font_category (already chosen in Phase 3)
    │   → Same AI decision drives: font + animation + color grade = unified look
    │
    └── Apply LUT to all images uniformly (OpenCV / Pillow)
    
    APPROACH 2: Reference-Based Transfer (adaptive)
    ├── Pick "hero image" — the best-scored image from Phase 6A
    ├── Transfer its color palette to all other images
    │   → Method: Reinhard color transfer (mean/std matching in LAB space)
    │   → Or: histogram matching per channel
    └── Preserves scene-specific details while unifying the palette
    
    COMBINED (recommended):
    1. Apply mood-appropriate LUT to all images
    2. Then Reinhard-normalize to reduce remaining outliers
    3. Result: all images share a consistent cinematic look
    
    Stored in DB: jobs.color_grade_config (JSON)
    """
    
    # LUT mapping — same categories as fonts
    LUT_MAP = {
        "formal_news":   "documentary_neutral.cube",
        "dramatic":      "dramatic_teal_orange.cube",
        "historical":    "historical_sepia_warm.cube",
        "modern_tech":   "tech_cyberpunk.cube",
        "islamic":       "islamic_warm_gold.cube",
        "military":      "military_cold_steel.cube",
        "editorial":     "editorial_clean.cube",
        "storytelling":  "storytelling_warm.cube",
    }
    
    def grade_all_images(self, job_id: str) -> list[str]:
        """
        1. Get font_category from job config
        2. Select LUT
        3. Apply to all scene images
        4. Reinhard normalize to hero image
        5. Save graded images (preserve originals)
        """
        pass
    
    def grade_thumbnail(self, thumbnail_path: str, job_id: str) -> str:
        """Apply same grade to thumbnails — brand consistency."""
        pass
```

### 4.11 Intelligent Transition System (`src/phase5_production/transition_engine.py`)

```python
"""
AI-driven transition selection between scenes.
NOT just crossfade everywhere — transitions convey meaning.

Runs during Phase 3 (Script) — Qwen 3.5 analyzes scene pairs
and assigns transitions. Stored in scenes.transition_type (already in DB).
"""

# Transition library
TRANSITIONS = {
    # ─── Hard cuts ───
    "cut":              {"ffmpeg": "-filter_complex '[0][1]concat'",
                         "when": "same location, continuous action, tension"},
    "smash_cut":        {"ffmpeg": "instant cut + audio spike",
                         "when": "sudden contrast, shock, humor"},
    
    # ─── Soft transitions ───
    "crossfade":        {"ffmpeg": "xfade=transition=fade:duration=0.5",
                         "when": "gentle scene change, related topics"},
    "dissolve":         {"ffmpeg": "xfade=transition=dissolve:duration=1.0",
                         "when": "time passing, dream-like, memory"},
    
    # ─── Directional ───
    "wipe_left":        {"ffmpeg": "xfade=transition=wipeleft:duration=0.5",
                         "when": "geographic movement, timeline progression"},
    "slide_up":         {"ffmpeg": "xfade=transition=slideup:duration=0.4",
                         "when": "escalation, revelation, new chapter"},
    
    # ─── Dramatic ───
    "fade_black":       {"ffmpeg": "fade=out → black 1s → fade=in",
                         "when": "major time skip, chapter break, death/ending"},
    "fade_white":       {"ffmpeg": "fade=out:color=white → fade=in",
                         "when": "flashback, divine/spiritual, revelation"},
    
    # ─── Modern/Dynamic ───
    "zoom_in":          {"ffmpeg": "zoompan + xfade",
                         "when": "focusing on detail, narrowing scope"},
    "zoom_out":         {"ffmpeg": "zoompan reverse + xfade",
                         "when": "revealing bigger picture, broadening scope"},
    "glitch_cut":       {"ffmpeg": "RGB shift frames + cut",
                         "when": "tech content, conspiracy, digital theme"},
}


class TransitionSelector:
    """
    Qwen 3.5 analyzes adjacent scene pairs → selects optimal transition.
    
    Prompt per scene pair:
    ┌────────────────────────────────────────────────────┐
    │ Scene {N}: "{narration_summary}" — mood: {mood}   │
    │ Scene {N+1}: "{narration_summary}" — mood: {mood} │
    │                                                    │
    │ Relationship: {same_topic|new_topic|time_skip|     │
    │               flashback|contrast|escalation}       │
    │                                                    │
    │ Select transition and duration (0.3s-2.0s).       │
    │ Available: {list transitions with 'when' hints}    │
    └────────────────────────────────────────────────────┘
    
    Fallback rules (if LLM fails):
    ├── Same mood → crossfade 0.5s
    ├── Mood change → dissolve 1.0s  
    ├── Time skip → fade_black 1.5s
    ├── Tension build → cut (instant)
    └── Chapter break → fade_black 2.0s
    """
    pass
```

### 4.12 Music-Scene Sync System (`src/phase5_production/music_scene_sync.py`)

```python
"""
Dynamic music that adapts to scene moods.
Instead of ONE track for the whole video → segmented music per mood zone.

Pipeline:
1. Phase 3 (Script): Group consecutive scenes by mood → "mood zones"
2. Phase 5 (Music): Generate one ACE-Step 1.5 track per mood zone
3. Phase 5 (Compose): Crossfade between music tracks at zone transitions
"""

class MusicSceneSync:
    """
    Step 1: Mood Zone Detection (during Script phase)
    ─────────────────────────────────────────────────
    Group consecutive scenes with same/similar mood:
    
    Scene 1: tense     ┐
    Scene 2: tense     ├── Zone A: "tense" (45s)
    Scene 3: dramatic  ┘
    Scene 4: hopeful   ┐
    Scene 5: hopeful   ├── Zone B: "hopeful" (30s)
    Scene 6: calm      ┘
    Scene 7: dramatic  ┐
    Scene 8: climax    ├── Zone C: "dramatic_climax" (50s)
    Scene 9: dramatic  ┘
    Scene 10: reflective ── Zone D: "reflective" (20s)
    
    Mood compatibility groups (can share one track):
    ├── {tense, dramatic, suspenseful}
    ├── {hopeful, inspiring, triumphant}
    ├── {calm, reflective, peaceful}
    ├── {sad, somber, melancholy}
    └── {exciting, energetic, climactic}
    
    Step 2: Per-Zone Music Generation
    ─────────────────────────────────
    ACE-Step 1.5 prompt per zone:
    - Zone A: "tense documentary background music, minor key, sparse, 45 seconds"
    - Zone B: "hopeful uplifting background, major key, gentle strings, 30 seconds"
    - Zone C: "dramatic climax orchestral, building intensity, 50 seconds"
    - Zone D: "reflective calm piano, peaceful outro, 20 seconds"
    
    Step 3: Zone Crossfades (during Compose)
    ─────────────────────────────────────────
    Between zones: 2-3 second crossfade
    FFmpeg: amerge + volume automation
    Music ducking still applies during narration.
    
    DB: mood_zones table
    ├── job_id, zone_index, mood, start_scene, end_scene
    ├── duration_sec, music_prompt, music_path
    └── crossfade_in_sec, crossfade_out_sec
    """
    pass
```

### 4.13 Pacing Analyzer (`src/phase3_script/pacing_analyzer.py`)

```python
"""
Analyzes and optimizes video pacing/rhythm.
Runs during Phase 3 (Script) — adjusts scene durations BEFORE production.

Problem: Uniform scene durations = boring. Viewers feel the monotony.
Solution: Vary duration based on content complexity + emotional arc.
"""

class PacingAnalyzer:
    """
    RULES (based on documentary editing best practices):
    
    1. SCENE DURATION GUIDELINES:
    ├── Hook/intro: 3-5s (fast, grab attention)
    ├── Context/setup: 8-12s (establish the topic)
    ├── Complex explanation: 12-20s (give time to absorb)
    ├── Emotional peak: 5-8s (intense, impactful)
    ├── Visual showcase: 6-10s (let visuals breathe)
    ├── Transition/bridge: 3-5s (connecting scenes)
    └── Conclusion/reflection: 10-15s (slow, thoughtful)
    
    2. RHYTHM PATTERNS (tempo mapping):
    ├── Start: medium pace → hook the viewer
    ├── Build: gradually longer scenes → establish depth  
    ├── Peak: short, rapid scenes → climax energy
    ├── Valley: longer scenes → emotional breathing room
    └── End: medium → conclusion, satisfying close
    
    3. ANTI-MONOTONY RULES:
    ├── No 3+ consecutive scenes with same duration (±2s)
    ├── Duration ratio between adjacent scenes: max 3:1
    ├── Every 2-3 minutes: at least one "pace change" (±50% duration shift)
    └── Total video pacing score: variance of durations should be > threshold
    
    4. CONTENT-BASED ADJUSTMENTS (Qwen 3.5):
    ├── Scene has statistics/data → +3s (reader needs time)
    ├── Scene has emotional quote → +2s (let it land)
    ├── Scene is visual transition → -3s (keep moving)
    ├── Scene follows a climax → -2s (maintain energy)
    └── Scene introduces new concept → +4s (comprehension time)
    """
    
    def analyze_and_adjust(self, scenes: list[dict]) -> list[dict]:
        """
        Input: scenes with initial durations from script
        Output: scenes with optimized durations + pacing_notes
        
        Process:
        1. Classify each scene type (hook/setup/peak/valley/conclusion)
        2. Apply duration guidelines
        3. Check rhythm patterns
        4. Apply anti-monotony rules
        5. Content-based fine-tuning (Qwen 3.5)
        6. Validate total duration within target range
        """
        pass
    
    def get_pacing_score(self, scene_durations: list[float]) -> float:
        """
        Score 0-10 for pacing quality.
        Based on: duration variance, rhythm patterns, anti-monotony compliance.
        """
        pass
```

### 4.14 Vision Before/After Comparison (`src/phase6_visual_qa/regen_comparator.py`)

```python
"""
When Phase 6 regenerates an image/video, send BOTH versions to Telegram
for comparison. Yusif sees the improvement (or lack thereof).
"""

class RegenComparator:
    """
    Triggers when: image or video is regenerated (attempt_number > 1)
    
    Telegram output:
    ┌──────────────────────────────────────────────────────┐
    │ 🔄 Scene 5 — Regenerated (attempt 2)                │
    │                                                      │
    │ [BEFORE image]        [AFTER image]                  │
    │ Score: 4.2/10         Score: 8.1/10                  │
    │                                                      │
    │ ❌ Before issues:     ✅ After improvements:         │
    │ - Extra fingers       - Clean anatomy                │
    │ - Low semantic match  - Matches narration            │
    │ - Text detected       - No text                      │
    │                                                      │
    │ 📝 Prompt changes:                                   │
    │ - Added: "five fingers on each hand"                 │
    │ - Removed: "crowded scene"                           │
    │ - Negative added: "deformed hands, extra digits"     │
    │                                                      │
    │ [✅ Accept] [🔄 Try Again] [✏️ Edit Prompt]         │
    └──────────────────────────────────────────────────────┘
    
    For videos:
    - Send both clips side-by-side (or sequential with labels)
    - Include keyframe comparison
    
    Stored in qa_rubrics: both attempts are already stored,
    this just presents them comparatively.
    """
    
    def send_comparison(self, job_id: str, scene_index: int, 
                        asset_type: str) -> None:
        """
        1. Get rubric for attempt N-1 and attempt N
        2. Build side-by-side comparison
        3. Send via Telegram with inline buttons
        """
        pass
```

### 4.15 Dynamic Intro/Outro System (`src/phase5_production/intro_outro.py`)

```python
"""
Dynamic intro/outro that adapts to video content.
NOT a static template — varies per video type.

Method: Pre-rendered intro/outro TEMPLATES with customizable elements.
Templates are transparent video layers (like text animations).
"""

class IntroOutroEngine:
    """
    INTRO VARIANTS (by content type — matched to font_category):
    
    formal_news:
    ├── Style: News broadcast open — logo + title slide + date
    ├── Animation: Clean slide-in, professional
    ├── Duration: 3-4s
    └── Music: Short news sting (pre-made, stored in assets/)
    
    dramatic:
    ├── Style: Dark reveal — smoke/particles + logo emerge from darkness
    ├── Animation: Slow fade from black, dramatic lighting
    ├── Duration: 5-6s
    └── Music: Low drone → hit
    
    historical:
    ├── Style: Parchment/aged paper unfold → title appears in classical font
    ├── Animation: Paper texture, ink writing effect
    ├── Duration: 4-5s
    └── Music: Classical oud or piano
    
    modern_tech:
    ├── Style: Digital grid/HUD → logo glitch-in
    ├── Animation: Matrix-style, circuit board patterns
    ├── Duration: 3-4s
    └── Music: Electronic pulse
    
    islamic:
    ├── Style: Geometric Islamic pattern → expands to reveal title
    ├── Animation: Arabesque pattern growth, elegant
    ├── Duration: 4-5s
    └── Music: Gentle nasheed or oud
    
    military:
    ├── Style: Tactical map → zoom to title, military stencil font
    ├── Animation: Sharp, decisive movements
    ├── Duration: 3-4s
    └── Music: Military drum cadence
    
    OUTRO (universal structure, styled per category):
    ├── Subscribe CTA (animated, language-matched)
    ├── Next video suggestion (from content_calendar)
    ├── Channel logo + social links
    ├── Duration: 8-12s (YouTube end screen compatible)
    └── End screen zones: 2 video suggestions + subscribe button
    
    IMPLEMENTATION:
    ├── Templates: After Effects → export as PNG sequences + JSON config
    │   OR: Generated programmatically (PyCairo, same as text animations)
    ├── Customization per video:
    │   → Title text (rendered in matching font)
    │   → Date (for news)
    │   → Episode number (for series)
    │   → Colors (from brand_kit)
    └── Composited by VideoComposer (FFmpeg overlay at start/end)
    """
    pass
```

### 4.16 Scene Duration Optimizer (`src/phase3_script/scene_duration_optimizer.py`)

```python
"""
Adjusts individual scene durations based on visual complexity + narration length.
Companion to PacingAnalyzer — this handles per-scene optimization.

Runs AFTER voice generation (we now know exact narration duration per scene).
"""

class SceneDurationOptimizer:
    """
    INPUTS:
    ├── Narration audio duration per scene (from Fish Audio S2 Pro)
    ├── Visual complexity score (from FLUX prompt analysis)
    ├── Scene type (action, dialogue, visual showcase, data display)
    ├── Text overlay amount (more text = more reading time needed)
    └── Emotional weight (from emotional_arc agent)
    
    RULES:
    1. Scene duration ≥ narration duration + 0.5s (breathing room)
    2. Scenes with text overlay: add (word_count / 3) seconds reading time
    3. Data/statistics scenes: add 3s minimum for comprehension
    4. After emotional peak: add 1-2s "landing" time (let it sink in)
    5. Visual showcase (beautiful landscape): can extend 2-3s beyond narration
    6. Rapid montage scenes: can be shorter than narration (audio continues over next scene)
    
    OUTPUT:
    Updated scene durations → affects:
    ├── LTX video clip length
    ├── Text overlay timing
    ├── Music zone durations
    └── Transition timing
    """
    pass
```

### 4.17 Subtitle Style Matching (`src/phase8_publish/subtitle_styler.py`)

```python
"""
SRT subtitles styled to match the video's font + color selection.
YouTube supports styled subtitles via .ass (Advanced SubStation Alpha) format.

Currently: plain SRT → YouTube default white text.
After: .ass with matching font, colors, and positioning.
"""

class SubtitleStyler:
    """
    Takes: SRT content + FontAnimationConfig (from Phase 3 AI selection)
    Produces: .ass file with styled subtitles
    
    .ass file structure:
    ├── [Script Info]: resolution, title
    ├── [V4+ Styles]: font name, size, colors, outline, shadow
    └── [Events]: timed subtitle lines with style reference
    
    Style mapping:
    ├── Font: same primary_font as text overlays
    ├── Size: 52px (readable at 1080p)
    ├── Primary color: white or text_color from config
    ├── Outline: 2px black (readability)
    ├── Shadow: 1px (depth)
    ├── Position: bottom-center (YouTube standard)
    ├── Margin: 30px from bottom (above YouTube controls)
    └── Alignment: center (or right-aligned for Arabic if RTL mode)
    
    BONUS — Accent styling:
    ├── Key words/names: accent_color from config
    ├── Quotes: italic + accent_color
    ├── Numbers/statistics: bold
    └── Foreign words: different style tag
    
    Output: .ass file uploaded to YouTube as closed captions
    (fallback: .srt if .ass upload fails)
    """
    pass
```

### 4.18 Thumbnail Font Matching (`src/phase8_publish/thumbnail_gen.py`)

```python
"""
Thumbnail text uses the SAME font_category selected for the video.
Visual brand consistency: video overlays + subtitles + thumbnail = unified look.

ALREADY in thumbnail_gen.py — this is the integration note:
"""

class ThumbnailGenerator:
    """
    Enhancement: Font consistency across all text elements.
    
    When generating thumbnail text:
    ├── Load FontAnimationConfig from job
    ├── Use accent_font (not primary — thumbnails need bolder fonts)
    ├── Use accent_color for emphasis text
    ├── Apply same background_style (box/gradient/blur)
    └── Apply same color_grade LUT to thumbnail
    
    Result: Viewer sees thumbnail → clicks → video has same visual identity
    = professional, branded, trustworthy
    
    Implementation:
    ├── FLUX generates base image (no text in FLUX prompt)
    ├── Apply color grade LUT
    ├── PyCairo renders text in accent_font + accent_color
    ├── Add background treatment (same as video overlays)
    └── Final: thumbnail matches video aesthetic perfectly
    """
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
        model_used TEXT,                     -- 'Qwen 3.5-27B:72b'
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
                    flags: list, hard_fail: str = None, model: str = "Qwen 3.5-27B:72b",
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
        "qwen3.5:27b":         16.0,   # GB (GPU portion, rest offloads to RAM)
        "qwen3.5:27b":  7.0,
        "flux":                 12.0,
        "ltx":                  12.0,
        "fish_audio_s2_pro":           4.0,
        "ACE-Step 1.5":              4.0,
        "MOSS-SoundEffect":              4.0,
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
LLM:    Qwen 3.5 (already loaded in GPU Slot 1)
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
│       Uses: Qwen 3.5 to analyze + score
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
LLM:    Qwen 3.5 (still loaded from Phase 1)
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
│       Uses: Qwen 3.5 analyzes competitor titles/descriptions
│       Returns: {unique_angles: [...], unanswered_questions: [...]}
│
├── title_generator.py
│   └── generate_titles(topic, keywords, gap_analysis) → list[dict]
│       Uses: Qwen 3.5 generates 10 titles
│       Scoring: keyword_density * 0.3 + emotional_hook * 0.3 + 
│                length_optimal * 0.2 + uniqueness * 0.2
│       Returns: [{title, score, keywords_included}]  # sorted by score
│
└── tag_planner.py
    └── plan_tags_description(topic, keywords, title) → dict
        Uses: Qwen 3.5
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
LLM:    Qwen 3.5 (still loaded)

Files to build:
├── researcher.py
│   └── research_topic(topic: str, angle: str) → str
│       Uses: Brave Search API (or web_search tool) → gather 5-10 sources
│       Uses: Qwen 3.5 to synthesize into research document
│       Returns: research_text (2000-5000 words with citations)
│
├── writer.py
│   └── write_script(research: str, seo: dict, channel: dict, rules: list) → str
│       Uses: Qwen 3.5 with structured prompt
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
│       Uses: Qwen 3.5 (separate prompt — acts as critic)
│       Checks: factual accuracy, engagement, keywords, pacing, grammar
│       Returns: ReviewResult(approved: bool, notes: str, scores: dict)
│       
│       If not approved → returns to writer with notes (max 3 iterations)
│
└── splitter.py
    └── split_to_scenes(script: str, channel: dict) → list[dict]
        Uses: Qwen 3.5
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
LLM:    Qwen 3.5 (still loaded)
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
│       Uses: Fish Audio S2 Pro
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
│       Uses: Fish Audio S2 Pro + clone embedding
│       Per scene: narration_text + voice_emotion → WAV
│       Quality check: pronunciation + glitch detection
│       Saves: scene voice paths to DB
│
├── music_gen.py
│   └── generate_music(job_id: str, scenes: list) → None
│       Uses: audiocraft.ACE-Step 1.5
│       Generates: intro, background, tension, outro tracks
│       CRITICAL: negative prompts for originality (see BLUEPRINT §5.4)
│       Saves: track paths to DB: audio_tracks table
│
├── sfx_gen.py
│   └── generate_sfx(job_id: str, scenes: list) → None
│       Uses: audiocraft.MOSS-SoundEffect
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

> **Vision Model: Qwen 3.5-27B** (not Llama Vision 11B)
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
LLM:    Qwen 3.5-27B (via Ollama) — JUDGE role only
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
│       │ LAYER 2: VISION LLM RUBRIC (Qwen 3.5-27B — judge role)  │
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
│       Send ALL images to Qwen 3.5-27B:
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
        1. Load Qwen 3.5-27B
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
│       │ LAYER 2: VISION RUBRIC (Qwen 3.5-27B — judge role)      │
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
        STEP 1: Load Qwen 3.5-27B
        
        STEP 2: IMAGE QA (Stage 6A)
          a. Verify each image vs script
          b. Check style consistency
          c. Check sequence flow
          d. Send image gallery to Telegram
          e. Gate: >90% pass → continue; 70-90% → regen; <70% → block
        
        STEP 3: Unload Qwen 3.5-27B → Load FLUX (if regen needed)
          a. Regenerate failed images
          b. Unload FLUX → Load Qwen 3.5-27B → Re-verify
        
        STEP 4: Unload Qwen 3.5-27B → (PipelineRunner handles LTX loading)
          → VIDEO GENERATION HAPPENS (Phase 5b)
          → Return to Phase 6 Stage 6B
        
        STEP 5: VIDEO QA (Stage 6B)
          a. Load Qwen 3.5-27B again
          b. Extract keyframes from each clip
          c. Verify each video vs script
          d. Handle fallbacks (regen/ken burns)
          e. Send video gallery to Telegram
          f. Gate: >85% pass → continue; else → regen or block
        
        STEP 6: Unload Qwen 3.5-27B
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
Updated state machine transitions:
```
IMAGES → IMAGE_QA → VIDEO_GEN → VIDEO_QA → VOICE → MUSIC → SFX → COMPOSE → OVERLAY_QA → FINAL_QA → ...
```

#### Phase 6C: Text Overlay QA (`src/phase6_visual_qa/overlay_checker.py`)

> **After FFmpeg composes video with Arabic text overlays — verify they're correct.**
> This catches: unreadable text, bad positioning, timing mismatches, color clashes.

```
Input:  Composed video with text overlays (output/[job_id]/composed.mp4)
Output: Overlay QA results → DB: qa_rubrics (asset_type='overlay')
LLM:    Qwen 3.5-27B
STATUS: OVERLAY_QA (between COMPOSE and FINAL_QA)

Files to build:
├── overlay_checker.py
│   └── check_overlays(video_path, scenes) → OverlayQAResult
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 1: DETERMINISTIC (no LLM)                        │
│       │                                                         │
│       │ For each scene with text_overlay:                       │
│       │ ├── Extract frame at overlay timestamp (FFmpeg)          │
│       │ ├── OCR the frame (EasyOCR Arabic mode)                 │
│       │ │   → Compare OCR output vs expected overlay text       │
│       │ │   → Match rate < 80% = text unreadable                │
│       │ ├── Text region contrast analysis                       │
│       │ │   → Extract text bounding box                         │
│       │ │   → Calculate contrast ratio vs background            │
│       │ │   → WCAG AA minimum: 4.5:1 (fail below this)         │
│       │ ├── Text position check                                 │
│       │ │   → Not in top 5% (YouTube title bar zone)            │
│       │ │   → Not in bottom 10% (YouTube controls zone)         │
│       │ │   → Not clipped by edges                              │
│       │ ├── Timing verification                                 │
│       │ │   → Overlay appears when narration starts (±0.5s)     │
│       │ │   → Overlay disappears when narration ends (±0.5s)    │
│       │ │   → Minimum display time: 2 seconds                   │
│       │ └── Arabic text direction check                         │
│       │     → Verify RTL rendering is correct                   │
│       │     → No reversed characters or mixed direction          │
│       └─────────────────────────────────────────────────────────┘
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 2: VISION LLM (Qwen 3.5-27B — supplementary)      │
│       │                                                         │
│       │ Send frame with overlay to Qwen 3.5-27B:                  │
│       │ "This documentary frame has Arabic text overlay.         │
│       │  Expected text: '{expected_text}'                        │
│       │                                                         │
│       │  Check:                                                  │
│       │  A. Readability (1-10): Is the text clearly readable?   │
│       │     Consider: font size, contrast, background clutter   │
│       │  B. Positioning (1-10): Is the text well-placed?        │
│       │     Not covering important visual elements?             │
│       │  C. Visual Integration (1-10): Does the text style      │
│       │     match the documentary aesthetic?                    │
│       │  D. Occlusion (1-10): Does the text block key content? │
│       │     Faces, actions, important objects?                  │
│       │                                                         │
│       │  Each axis: score + reasoning + confidence"             │
│       └─────────────────────────────────────────────────────────┘
│       
│       ┌─────────────────────────────────────────────────────────┐
│       │ LAYER 3: COMBINED VERDICT                               │
│       │                                                         │
│       │ HARD FAILS (auto re-compose):                           │
│       │ ├── OCR match < 80% → text unreadable, adjust style     │
│       │ ├── contrast ratio < 4.5:1 → add/darken background box  │
│       │ ├── text in YouTube dead zones → reposition              │
│       │ ├── RTL rendering broken → fix font/renderer             │
│       │ └── timing off > 1.0s → re-sync                         │
│       │                                                         │
│       │ On fail: auto-fix parameters → re-compose → re-check   │
│       │ Max 2 re-compose attempts before BLOCK                   │
│       └─────────────────────────────────────────────────────────┘
│       
│       Returns: OverlayQAResult(
│           per_scene: list[OverlayCheck],  # each scene's results
│           overall_pass: bool,
│           auto_fixable: bool,             # Can FFmpeg fix it?
│           fix_instructions: list[dict],   # {scene_index, fix_type, params}
│       )
│
├── overlay_auto_fixer.py
│   └── apply_fixes(video_path, fix_instructions) → str (new video path)
│       Automated fixes (re-run FFmpeg with adjusted params):
│       ├── "contrast" → Add semi-transparent dark box behind text
│       ├── "position" → Move text to safe zone
│       ├── "timing" → Adjust overlay start/end timestamps
│       ├── "font_size" → Increase/decrease font
│       └── "rtl_fix" → Switch to known-good Arabic font (Noto Naskh)
│
└── Stored in qa_rubrics with:
    asset_type = 'overlay'
    check_phase = 'phase6c'
```

#### Phase 7: Final QA (`src/phase7_video_qa/`)
```
Input:  Composed video (output/[job_id]/final.mp4) — FULL assembled video
Output: Pass/Fail → DB: compliance_checks table
LLM:    Qwen 3.5-27B (vision) + Qwen 3.5 (text compliance)
GATE:   Can block

Files to build:
├── technical_check.py    → A/V sync, duration, resolution, bitrate, file integrity
│   Uses: ffprobe (part of FFmpeg) — no GPU needed
│
├── content_check.py      → Extract 1 frame per scene from FINAL video
│   Uses: Qwen 3.5-27B
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
├── final_compliance.py   → One last YouTube policy sweep (Qwen 3.5 text)
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
        2. Load Qwen 3.5-27B → content_check (vision)
        3. Swap to Qwen 3.5 → final_compliance (text)
        4. Send final preview to Telegram
        5. Return aggregate result + gate decision
```

#### Phase 8: Publish (`src/phase8_publish/`)
```
Input:  Final video + SEO data + scenes
Output: YouTube upload + Shorts + SRT
APIs:   YouTube Data API v3

Files to build:
├── thumbnail_gen.py       → FLUX generates 3 variants + font matching (§4.18)
├── thumbnail_qa.py        → Full 3-layer QA on thumbnails (see below)
├── subtitle_styler.py     → .ass styled subtitles matching video font (§4.17)
├── seo_assembler.py       → Combine: title + desc + tags + timestamps + hashtags
├── subtitle_gen.py        → SRT from scene narration text + timing
├── uploader.py            → YouTube API: upload video, set metadata, add captions
├── shorts_gen.py          → Extract 3-5 best moments → crop 9:16 → add subtitles
└── ab_test.py             → Upload 3 thumbnails to YouTube Test & Compare
```

##### Thumbnail QA (`src/phase8_publish/thumbnail_qa.py`)

> Thumbnail = most important single image in the video (drives CTR).
> Gets the SAME 3-layer treatment as scene images, PLUS thumbnail-specific checks.

```
Input:  3 generated thumbnail variants
Output: Ranked thumbnails → best goes to YouTube, all 3 to A/B test
LLM:    Qwen 3.5-27B

┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: DETERMINISTIC                                      │
│                                                             │
│ ├── Resolution check: exactly 1280x720 (YouTube standard)   │
│ ├── File size: < 2MB (YouTube limit)                        │
│ ├── Face detection (if applicable): face clearly visible?   │
│ │   → dlib/RetinaFace: face size > 15% of thumbnail area   │
│ ├── Text overlay OCR (thumbnail text is intentional!)       │
│ │   → But must be readable: OCR match > 90%                │
│ │   → Font size check: text region > 8% of image area      │
│ ├── Mobile readability simulation                           │
│ │   → Downscale to 168x94 (YouTube mobile thumbnail size)  │
│ │   → OCR on downscaled version — text still readable?     │
│ │   → Key visual elements still distinguishable?            │
│ ├── Color vibrancy: saturation/contrast above threshold     │
│ │   → Thumbnails need to POP against white background       │
│ ├── YouTube dead zone check                                 │
│ │   → Bottom-right: video duration badge covers this area   │
│ │   → No critical elements there                            │
│ └── Competitor similarity check                             │
│     → CLIP embedding vs recent thumbnails in same niche     │
│     → Too similar = won't stand out                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: VISION RUBRIC (Qwen 3.5-27B)                       │
│                                                             │
│ A. Click Appeal (1-10)                                      │
│    "Would you click this thumbnail on YouTube?"             │
│    Curiosity gap, emotional hook, visual intrigue.          │
│                                                             │
│ B. Topic Relevance (1-10)                                   │
│    "Does this thumbnail match: '{video_title}'?"            │
│    Misleading thumbnails = high CTR but low retention.      │
│                                                             │
│ C. Mobile Readability (1-10)                                │
│    "At phone screen size, is everything clear?"             │
│    Text, faces, key objects all distinguishable.            │
│                                                             │
│ D. Emotional Impact (1-10)                                  │
│    "What emotion does this evoke?"                          │
│    Must match the video's emotional hook.                   │
│                                                             │
│ E. Professionalism (1-10)                                   │
│    "Does this look professionally made?"                    │
│    Not cluttered, not amateurish, consistent brand.         │
│                                                             │
│ F. Differentiation (1-10)                                   │
│    "Would this stand out among similar videos?"             │
│    Show 3-5 competitor thumbnails alongside for comparison. │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: RANKING (not just pass/fail)                       │
│                                                             │
│ All 3 variants scored → ranked by weighted formula.         │
│ weighted = click_appeal(0.30) + relevance(0.20) +           │
│            mobile(0.20) + emotion(0.15) + pro(0.10) +       │
│            diff(0.05)                                       │
│                                                             │
│ Best thumbnail → primary                                    │
│ All 3 → YouTube Test & Compare (A/B test)                   │
│ If ALL 3 < 6.0 → regenerate with different prompts          │
│                                                             │
│ Stored in qa_rubrics: asset_type='thumbnail'                │
└─────────────────────────────────────────────────────────────┘
```

---

##### Vision QA Calibration System (`src/core/rubric_calibrator.py`)

> **Problem:** Rubric weights (semantic_match * 0.25, etc.) are initially arbitrary.
> **Solution:** After enough Phase 9 data, auto-calibrate weights based on real performance.

```
The calibration loop:
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  Phase 6 QA rubric scores ──┐                                  │
│                              ├──→ Correlation Analysis         │
│  Phase 9 YouTube metrics ───┘    (after 20+ videos)            │
│  (CTR, retention, watch time)                                  │
│                                                                │
│  Questions we answer:                                          │
│  ├── Which rubric axes correlate with HIGH retention?           │
│  │   → Increase their weight                                   │
│  ├── Which axes don't correlate with anything?                  │
│  │   → Decrease their weight (or remove)                       │
│  ├── Is our threshold (7.0) too high or too low?               │
│  │   → Videos that scored 6.5 but performed well = lower it    │
│  │   → Videos that scored 8.0 but performed poorly = raise it  │
│  └── Are regen decisions correct?                               │
│      → Regenerated images: did regen improve final performance? │
│      → If not: wasted GPU time, adjust regen threshold          │
│                                                                │
│  Output: Updated weights + thresholds in calibration config     │
│  Frequency: After every 20 new videos (enough statistical data) │
│  Storage: calibration_history table (track weight evolution)     │
└────────────────────────────────────────────────────────────────┘

Files to build:
├── rubric_calibrator.py
│   └── class RubricCalibrator:
│       
│       def calibrate(self, min_videos: int = 20) → CalibrationResult:
│           """
│           1. Pull all qa_rubrics + youtube_analytics for published videos
│           2. For each rubric axis, calculate Pearson correlation with:
│              - avg_view_percentage (retention)
│              - ctr (click-through rate) [thumbnails only]
│              - watch_time_hours (engagement)
│           3. Normalize correlations → new weights (sum = 1.0)
│           4. Analyze threshold: find optimal cutoff via ROC curve
│              (maximize: high-performing videos PASS, low-performing FAIL)
│           5. Save new weights to config + calibration_history
│           """
│           pass
│       
│       def should_calibrate(self) → bool:
│           """True if 20+ new videos since last calibration."""
│           pass
│       
│       def get_current_weights(self) → dict:
│           """Return active weights (default or calibrated)."""
│           pass
│
├── calibration config in settings.yaml:
│   rubric_calibration:
│     mode: "default"              # "default" | "calibrated" | "manual"
│     min_videos_for_calibration: 20
│     
│     # Default weights (used until first calibration)
│     image_weights:
│       semantic_match: 0.25
│       element_presence: 0.20
│       composition: 0.15
│       style_fit: 0.10
│       artifact_severity: 0.15
│       cultural: 0.05
│       emotion: 0.10
│     
│     # Will be auto-populated after calibration
│     calibrated_weights: null
│     calibrated_threshold: null
│     last_calibration: null
│     calibration_confidence: null    # How strong the correlations are
│
└── DB table:
    CREATE TABLE IF NOT EXISTS calibration_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calibration_type TEXT,       -- 'image' | 'video' | 'thumbnail'
        videos_analyzed INTEGER,
        old_weights JSON,
        new_weights JSON,
        old_threshold REAL,
        new_threshold REAL,
        correlations JSON,           -- {axis: pearson_r, ...}
        confidence REAL,             -- Overall calibration confidence
        notes TEXT,                   -- "composition weight increased 0.15→0.22"
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
```

---

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
audiocraft>=1.3           # ACE-Step 1.5 + MOSS-SoundEffect
# fish-audio-s2-pro             # Install separately from GitHub

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
8. Install Ollama + Qwen 3.5 Q4
9. Install ComfyUI + FLUX + LTX-2.3
10. Install Fish Audio S2 Pro
11. Install audiocraft (ACE-Step 1.5 + MOSS-SoundEffect)

TEST:
- Ollama: generate Arabic text ✓
- ComfyUI: generate 1 image ✓
- Fish Audio S2 Pro: clone 1 voice + generate 1 sentence ✓
- ACE-Step 1.5: generate 15 sec music ✓

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
13. src/phase3_script/pacing_analyzer.py
14. src/phase3_script/scene_duration_optimizer.py

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
ollama pull qwen3.5:27b
ollama pull qwen3.5:27b

# 6. Install ComfyUI (separate process)
# Follow: https://github.com/comfyanonymous/ComfyUI
# Download FLUX.1-dev + LTX-2.3 models into ComfyUI/models/

# 7. Install Fish Audio S2 Pro
# Follow: https://github.com/fishaudio/fish-audio-s2-pro

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
| Voice | Fish Audio S2 Pro clone from real recordings | Human recordings cloned = natural Arabic pronunciation |
| Phase 5 | Sub-pipeline (3 coordinators, not 1 phase) | AssetCoordinator + AudioCoordinator + VideoComposer — most complex phase deserves structure |
| Agents | 3 tiers: core / optimization / experimental | Clear priority. Won't confuse production-critical with nice-to-have |
| Config | YAML (not JSON/TOML) | Readable, supports comments, good for multi-line strings |
| Error handling | Checkpoint + resume via FSM | 3-hour pipeline — FSM ensures correct resume point after any crash |
| Notifications | Telegram (not email/SMS) | Instant, interactive (inline buttons), free, Yusif already uses it |
| Phase 9 | Cron-based (not inline) | Analytics data isn't available immediately — needs 24h+ delay |
| Manual review | Selective (not always) | High-quality videos auto-publish; only flag edge cases |

---

## 12.5 Operational Infrastructure

### 12.5.1 Storage Manager (`src/core/storage_manager.py`)

> **Problem:** Each video produces ~5-10GB intermediate files. 10 videos = 50-100GB.
> Without cleanup, disk fills in days.

```python
"""
Manages disk space across the entire pipeline.
Policies: what to keep, what to archive, what to delete, and when.
"""

class StorageManager:
    """
    STORAGE LAYOUT PER JOB:
    output/
    └── job_20260315_120000/
        ├── images/                    # FLUX outputs
        │   ├── scene_001_v1.png       # Version 1 (original)
        │   ├── scene_001_v2.png       # Version 2 (regen)
        │   ├── scene_001_final.png    # Symlink → best version
        │   └── ...
        ├── images_graded/             # After color grading
        ├── videos/                    # LTX clips
        │   ├── scene_001_v1.mp4
        │   └── scene_001_final.mp4
        ├── audio/
        │   ├── voice/                 # Fish Audio S2 Pro outputs
        │   ├── music/                 # ACE-Step 1.5 per mood zone
        │   └── sfx/                   # MOSS-SoundEffect outputs
        ├── overlays/                  # Animated text layers (ProRes)
        ├── compose/                   # FFmpeg intermediate
        │   ├── composed_v1.mp4        # Before overlay QA fix
        │   └── composed_final.mp4
        ├── thumbnails/                # 3 variants
        ├── subtitles/                 # .ass + .srt
        ├── final/
        │   ├── final.mp4              # THE published video
        │   └── final_metadata.json    # YouTube metadata
        ├── qa/                        # QA artifacts
        │   ├── keyframes/             # Extracted for vision QA
        │   └── reports/               # Per-scene QA JSONs
        └── logs/                      # Job-specific logs
    
    CLEANUP POLICIES:
    ─────────────────
    """
    
    # What to keep permanently
    KEEP_FOREVER = [
        "final/final.mp4",            # The published video
        "final/final_metadata.json",   # Metadata
        "thumbnails/*_final.*",        # Winning thumbnail
        "subtitles/*.ass",             # Subtitles
    ]
    
    # What to archive (compress → cold storage) after 7 days
    ARCHIVE_AFTER_7D = [
        "images/*_final.png",          # Final scene images (useful for repurpose)
        "audio/voice/*.wav",           # Voice tracks (re-composable)
        "qa/reports/*.json",           # QA data (for Phase 9 learning)
    ]
    
    # What to delete after 3 days (post-publish, QA passed)
    DELETE_AFTER_3D = [
        "images/*_v[0-9]*.png",        # Non-final image versions
        "images_graded/",              # Graded intermediates
        "videos/*_v[0-9]*.mp4",        # Non-final video versions
        "overlays/",                   # Text animation layers
        "compose/*_v[0-9]*.mp4",       # Non-final compositions
        "qa/keyframes/",               # Vision QA keyframes
    ]
    
    # What to delete immediately after compose
    DELETE_AFTER_COMPOSE = [
        "overlays/*.mov",              # ProRes text layers (huge files, 500MB+)
    ]
    
    def cleanup_job(self, job_id: str, policy: str = "post_publish"):
        """
        Run cleanup for a job.
        Policies: 'post_compose' | 'post_publish' | 'archive' | 'full_clean'
        
        Called by:
        - PipelineRunner after COMPOSE → delete overlay MOVs
        - Cron job daily → apply 3-day and 7-day policies
        - Manual → full_clean (keeps only KEEP_FOREVER)
        """
        pass
    
    def get_disk_usage(self) -> dict:
        """
        Returns: {
            total_gb: float,
            by_job: {job_id: size_gb},
            by_type: {images: gb, videos: gb, audio: gb, overlays: gb},
            oldest_uncleaned_job: str,
            estimated_days_until_full: float
        }
        """
        pass
    
    def emergency_cleanup(self, target_free_gb: float = 50):
        """
        When disk is critically low:
        1. Delete all DELETE_AFTER_3D for ALL jobs (not just old ones)
        2. Archive all ARCHIVE_AFTER_7D immediately
        3. If still not enough → alert Yusif via Telegram
        """
        pass


# ═══ SETTINGS.YAML ═══
# storage:
#   output_dir: "output/"
#   archive_dir: "archive/"           # Compressed archives
#   max_disk_usage_gb: 500            # Alert threshold
#   emergency_free_gb: 50             # Emergency cleanup trigger
#   cleanup_schedule: "0 3 * * *"     # Daily at 3 AM
#   archive_compression: "zstd"       # Fast compression
#   keep_versions: 2                  # Keep last N versions of regen assets
```

### 12.5.2 Retry & Backoff Strategy (`src/core/retry_engine.py`)

```python
"""
Comprehensive retry strategy for every external dependency.
Each service has its own failure mode → needs its own retry policy.
"""

from dataclasses import dataclass
from enum import Enum


class FailureType(str, Enum):
    TIMEOUT      = "timeout"          # Service didn't respond in time
    OOM          = "oom"              # GPU out of memory
    CRASH        = "crash"            # Service crashed/exited
    BAD_OUTPUT   = "bad_output"       # Service responded but output is garbage
    HUNG         = "hung"             # Service is alive but not responding
    RATE_LIMIT   = "rate_limit"       # API quota exceeded
    NETWORK      = "network"          # Network/connection error


@dataclass
class RetryPolicy:
    max_retries: int
    initial_delay_sec: float
    backoff_multiplier: float        # Exponential backoff
    max_delay_sec: float
    timeout_sec: float               # Per-attempt timeout
    on_exhaust: str                   # "block" | "skip" | "fallback" | "alert"
    fallback_action: str = None      # What to do if retries exhausted


# ═══ PER-SERVICE RETRY POLICIES ═══

RETRY_POLICIES = {
    # ─── Ollama (Qwen 3.5, Qwen 3.5-27B) ───
    "ollama": RetryPolicy(
        max_retries=3,
        initial_delay_sec=10,
        backoff_multiplier=2.0,        # 10s → 20s → 40s
        max_delay_sec=60,
        timeout_sec=300,               # 5 min per generation
        on_exhaust="block",
        # Recovery: restart Ollama service
        # subprocess.run(["systemctl", "restart", "ollama"])
    ),
    
    # ─── ComfyUI (FLUX, LTX) ───
    "comfyui": RetryPolicy(
        max_retries=3,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=30,
        timeout_sec=180,               # 3 min per image, 5 min per video
        on_exhaust="block",
        # Recovery: restart ComfyUI, clear queue
        # POST http://localhost:8188/queue {"clear": true}
    ),
    
    # ─── Fish Audio S2 Pro ───
    "fish_audio_s2_pro": RetryPolicy(
        max_retries=2,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=20,
        timeout_sec=120,               # 2 min per scene narration
        on_exhaust="block",
    ),
    
    # ─── ACE-Step 1.5 / MOSS-SoundEffect ───
    "ACE-Step 1.5": RetryPolicy(
        max_retries=2,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=20,
        timeout_sec=180,               # 3 min per music zone
        on_exhaust="fallback",
        fallback_action="use_stock_music",  # Fallback: pre-made royalty-free tracks
    ),
    
    # ─── FFmpeg ───
    "ffmpeg": RetryPolicy(
        max_retries=2,
        initial_delay_sec=2,
        backoff_multiplier=1.5,
        max_delay_sec=10,
        timeout_sec=600,               # 10 min for full compose
        on_exhaust="block",            # FFmpeg failure = critical
    ),
    
    # ─── YouTube API ───
    "youtube_api": RetryPolicy(
        max_retries=5,
        initial_delay_sec=60,          # YouTube rate limits need patience
        backoff_multiplier=2.0,
        max_delay_sec=900,             # Up to 15 min
        timeout_sec=120,
        on_exhaust="alert",            # Don't block — alert and retry later
    ),
    
    # ─── Whisper (Audio QA STT) ───
    "whisper": RetryPolicy(
        max_retries=2,
        initial_delay_sec=5,
        backoff_multiplier=2.0,
        max_delay_sec=15,
        timeout_sec=120,
        on_exhaust="skip",             # QA — skip if STT fails, note in rubric
    ),
}


class RetryEngine:
    """
    Wraps any service call with retry logic.
    
    Usage:
        retry = RetryEngine("ollama")
        result = retry.execute(lambda: ollama.generate(...))
    
    On each failure:
    1. Log failure type + attempt number
    2. Emit event (EventBus: SERVICE_RETRY)
    3. Wait (exponential backoff)
    4. Try recovery action if available
    5. Retry or exhaust
    
    On exhaust:
    - "block" → block job + alert Telegram
    - "skip" → skip this step, note in DB
    - "fallback" → execute fallback_action
    - "alert" → alert Telegram, keep job active for manual retry
    """
    
    def __init__(self, service: str):
        self.policy = RETRY_POLICIES[service]
        self.service = service
    
    def execute(self, fn, *args, **kwargs):
        for attempt in range(1, self.policy.max_retries + 1):
            try:
                return self._run_with_timeout(fn, *args, **kwargs)
            except Exception as e:
                failure_type = self._classify_failure(e)
                delay = self._calculate_delay(attempt)
                
                logger.warning(
                    f"Retry {attempt}/{self.policy.max_retries} for {self.service}: "
                    f"{failure_type} — waiting {delay}s"
                )
                
                self._attempt_recovery(failure_type)
                time.sleep(delay)
        
        # Exhausted
        return self._handle_exhaustion()
    
    def _classify_failure(self, error) -> FailureType:
        """Classify error into FailureType for appropriate handling."""
        if "timeout" in str(error).lower():
            return FailureType.TIMEOUT
        elif "CUDA out of memory" in str(error):
            return FailureType.OOM
        elif "Connection refused" in str(error):
            return FailureType.CRASH
        # ... etc
    
    def _attempt_recovery(self, failure_type: FailureType):
        """Service-specific recovery actions."""
        if self.service == "ollama" and failure_type in (FailureType.CRASH, FailureType.HUNG):
            subprocess.run(["ollama", "stop"], capture_output=True)
            time.sleep(5)
            # Ollama auto-restarts via systemd/service
        
        elif self.service == "comfyui" and failure_type == FailureType.HUNG:
            # Clear ComfyUI queue
            requests.post("http://localhost:8188/queue", json={"clear": True})
            time.sleep(3)
        
        elif failure_type == FailureType.OOM:
            # Emergency GPU cleanup
            gpu_manager.emergency_cleanup()
            time.sleep(10)
    
    def _calculate_delay(self, attempt: int) -> float:
        delay = self.policy.initial_delay_sec * (self.policy.backoff_multiplier ** (attempt - 1))
        return min(delay, self.policy.max_delay_sec)
```

### 12.5.3 Asset Versioning (`src/core/asset_versioner.py`)

```python
"""
Keeps all versions of regenerated assets.
Yusif can say "go back to version 1" — system can comply.

Naming: scene_001_v1.png, scene_001_v2.png, scene_001_final.png (symlink)
"""

class AssetVersioner:
    """
    Every time an asset is generated or regenerated:
    1. Save with version suffix: scene_{idx}_v{attempt}.{ext}
    2. Update 'final' symlink to point to latest/best version
    3. Record version metadata in DB
    
    DB table: asset_versions
    ├── job_id, scene_index, asset_type ('image'|'video'|'voice'|'music')
    ├── version (1, 2, 3...)
    ├── file_path
    ├── file_size_bytes
    ├── qa_score (from rubric)
    ├── is_active (which version is 'final')
    ├── creation_reason ('initial'|'regen_qa_fail'|'regen_manual'|'regen_prompt_edit')
    └── created_at
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS asset_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        scene_index INTEGER,
        asset_type TEXT NOT NULL,
        version INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        file_size_bytes INTEGER,
        qa_score REAL,
        is_active BOOLEAN DEFAULT TRUE,
        creation_reason TEXT,
        prompt_used TEXT,              -- The prompt that generated this version
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (job_id) REFERENCES jobs(id),
        UNIQUE(job_id, scene_index, asset_type, version)
    );
    CREATE INDEX IF NOT EXISTS idx_versions_job ON asset_versions(job_id, scene_index);
    CREATE INDEX IF NOT EXISTS idx_versions_active ON asset_versions(is_active);
    """
    
    def save_version(self, job_id: str, scene_index: int, asset_type: str,
                     file_path: str, qa_score: float = None,
                     reason: str = "initial", prompt: str = None) -> int:
        """
        Save new version. Returns version number.
        Deactivates previous versions, activates this one.
        Creates/updates 'final' symlink.
        """
        # Get next version number
        current_max = self.db.execute(
            "SELECT MAX(version) FROM asset_versions WHERE job_id=? AND scene_index=? AND asset_type=?",
            (job_id, scene_index, asset_type)
        ).fetchone()[0] or 0
        
        new_version = current_max + 1
        
        # Deactivate old versions
        self.db.execute(
            "UPDATE asset_versions SET is_active=FALSE WHERE job_id=? AND scene_index=? AND asset_type=?",
            (job_id, scene_index, asset_type)
        )
        
        # Save new version
        versioned_path = self._version_path(file_path, new_version)
        shutil.copy2(file_path, versioned_path)
        
        self.db.execute("""
            INSERT INTO asset_versions (job_id, scene_index, asset_type, version,
                file_path, file_size_bytes, qa_score, is_active, creation_reason, prompt_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, ?, ?)
        """, (job_id, scene_index, asset_type, new_version,
              versioned_path, os.path.getsize(versioned_path), qa_score, reason, prompt))
        
        # Update 'final' symlink
        final_path = self._final_path(file_path)
        if os.path.exists(final_path):
            os.remove(final_path)
        os.symlink(versioned_path, final_path)
        
        self.db.commit()
        return new_version
    
    def rollback(self, job_id: str, scene_index: int, asset_type: str, 
                 to_version: int) -> str:
        """
        Rollback to a previous version.
        Called when Yusif says "use the first image".
        Returns: path to restored version.
        """
        # Deactivate all
        self.db.execute(
            "UPDATE asset_versions SET is_active=FALSE WHERE job_id=? AND scene_index=? AND asset_type=?",
            (job_id, scene_index, asset_type)
        )
        # Activate target version
        self.db.execute(
            "UPDATE asset_versions SET is_active=TRUE WHERE job_id=? AND scene_index=? AND asset_type=? AND version=?",
            (job_id, scene_index, asset_type, to_version)
        )
        
        # Update symlink
        row = self.db.execute(
            "SELECT file_path FROM asset_versions WHERE job_id=? AND scene_index=? AND asset_type=? AND version=?",
            (job_id, scene_index, asset_type, to_version)
        ).fetchone()
        
        final_path = self._final_path(row["file_path"])
        os.symlink(row["file_path"], final_path)
        
        self.db.commit()
        return row["file_path"]
    
    def get_versions(self, job_id: str, scene_index: int, 
                     asset_type: str) -> list[dict]:
        """Get all versions for an asset — for Telegram display."""
        pass
```

### 12.5.4 YouTube API Quota Tracker (`src/core/quota_tracker.py`)

```python
"""
YouTube Data API v3 quota: 10,000 units per day (resets midnight PT).
Without tracking, quota exhaustion = silent failures.

Quota costs (official):
├── videos.insert (upload)     = 1,600 units
├── videos.update (metadata)   = 50 units
├── videos.list               = 1 unit
├── captions.insert           = 400 units
├── channels.list             = 1 unit
├── search.list               = 100 units
├── thumbnails.set            = 50 units
├── youtube.analytics (read)  = 1-5 units
└── playlistItems.insert      = 50 units

One full publish cycle:
├── upload video              = 1,600
├── set thumbnail             = 50
├── upload 2 caption tracks   = 800
├── add to playlist           = 50
├── verify upload (list)      = 1
└── Total per video           ≈ 2,501 units

→ Max 4 videos per day with quota to spare for analytics.
"""

class QuotaTracker:
    """
    Tracks YouTube API quota usage in real-time.
    Prevents operations that would exceed quota.
    
    DB table: api_quota_log
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS api_quota_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,                    -- Pacific Time date
        operation TEXT NOT NULL,                -- 'videos.insert', 'thumbnails.set', etc.
        units_used INTEGER NOT NULL,
        job_id TEXT,
        response_status INTEGER,               -- HTTP status code
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_quota_date ON api_quota_log(date);
    """
    
    DAILY_LIMIT = 10_000
    
    OPERATION_COSTS = {
        "videos.insert":        1600,
        "videos.update":        50,
        "videos.list":          1,
        "captions.insert":      400,
        "captions.list":        1,
        "channels.list":        1,
        "search.list":          100,
        "thumbnails.set":       50,
        "playlistItems.insert": 50,
        "playlistItems.list":   1,
        "analytics.query":      5,      # Approximate
    }
    
    def can_afford(self, operation: str) -> bool:
        """Check if we have enough quota for this operation."""
        cost = self.OPERATION_COSTS.get(operation, 10)
        used_today = self._get_today_usage()
        remaining = self.DAILY_LIMIT - used_today
        
        if remaining < cost:
            logger.warning(f"Quota insufficient: need {cost}, have {remaining}")
            return False
        return True
    
    def record_usage(self, operation: str, job_id: str = None, 
                     status: int = 200):
        """Record an API call."""
        cost = self.OPERATION_COSTS.get(operation, 10)
        today = self._pacific_today()
        
        self.db.execute(
            "INSERT INTO api_quota_log (date, operation, units_used, job_id, response_status) VALUES (?, ?, ?, ?, ?)",
            (today, operation, cost, job_id, status)
        )
        self.db.commit()
        
        remaining = self.DAILY_LIMIT - self._get_today_usage()
        if remaining < 2000:
            self.telegram.alert(f"⚠️ YouTube quota low: {remaining}/10,000 remaining")
    
    def get_status(self) -> dict:
        """Current quota status."""
        used = self._get_today_usage()
        return {
            "date": self._pacific_today(),
            "used": used,
            "remaining": self.DAILY_LIMIT - used,
            "percent_used": round(used / self.DAILY_LIMIT * 100, 1),
            "max_videos_remaining": (self.DAILY_LIMIT - used) // 2501,
            "reset_time": "midnight Pacific Time"
        }
    
    def schedule_if_needed(self, operation: str, job_id: str) -> str:
        """
        If quota insufficient now, schedule for after midnight PT reset.
        Returns: 'now' | 'scheduled:YYYY-MM-DDTHH:MM:SS'
        """
        if self.can_afford(operation):
            return "now"
        
        # Schedule for 00:05 PT (5 min after reset, safety margin)
        reset_time = self._next_reset_time()
        self.db.schedule_deferred_operation(operation, job_id, reset_time)
        self.telegram.send(
            f"⏳ YouTube quota exhausted. {operation} for job {job_id} "
            f"scheduled at {reset_time} (after quota reset)"
        )
        return f"scheduled:{reset_time}"
    
    def _get_today_usage(self) -> int:
        row = self.db.execute(
            "SELECT COALESCE(SUM(units_used), 0) FROM api_quota_log WHERE date = ?",
            (self._pacific_today(),)
        ).fetchone()
        return row[0]
    
    def _pacific_today(self) -> str:
        """YouTube quota resets at midnight Pacific Time."""
        from datetime import timezone, timedelta
        pt = timezone(timedelta(hours=-8))
        return datetime.now(pt).strftime("%Y-%m-%d")
```

### 12.5.5 Service Watchdog (`src/core/watchdog.py`)

```python
"""
Monitors all external services the pipeline depends on.
Detects: hangs, crashes, unresponsive services, resource exhaustion.
Recovers: restart, alert, pause pipeline.

Runs as a background thread alongside the pipeline.
"""

import threading
import time
import subprocess
import requests
import psutil


class ServiceWatchdog(threading.Thread):
    """
    Background monitor — checks service health every 30 seconds.
    
    Monitored services:
    ├── Ollama          — HTTP health check + process alive
    ├── ComfyUI         — HTTP health check + queue status
    ├── GPU             — nvidia-smi: temp, VRAM, utilization
    ├── Disk            — Free space check
    ├── RAM             — Available memory
    └── Pipeline        — Is PipelineRunner making progress?
    """
    
    daemon = True  # Dies when main process exits
    
    def __init__(self, config: dict, event_bus, telegram):
        super().__init__(name="Watchdog")
        self.config = config
        self.events = event_bus
        self.telegram = telegram
        self.check_interval = 30        # seconds
        self.running = True
        
        # Pipeline progress tracking
        self._last_status_change = time.time()
        self._last_job_status = None
    
    def run(self):
        while self.running:
            try:
                self._check_all()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            time.sleep(self.check_interval)
    
    def _check_all(self):
        results = {
            "ollama": self._check_ollama(),
            "comfyui": self._check_comfyui(),
            "gpu": self._check_gpu(),
            "disk": self._check_disk(),
            "ram": self._check_ram(),
            "pipeline": self._check_pipeline_progress(),
        }
        
        for service, status in results.items():
            if status["healthy"] is False:
                self._handle_unhealthy(service, status)
    
    # ─── Service Checks ────────────────────────────────
    
    def _check_ollama(self) -> dict:
        """
        1. HTTP GET http://localhost:11434/api/tags → should respond
        2. If no response in 5s → unhealthy
        3. Check if ollama process exists
        """
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            return {"healthy": r.status_code == 200, "detail": "OK"}
        except:
            # Check if process is running
            alive = any(p.name() == "ollama" for p in psutil.process_iter())
            return {
                "healthy": False,
                "detail": "process_alive_but_unresponsive" if alive else "process_dead",
                "recovery": "restart"
            }
    
    def _check_comfyui(self) -> dict:
        """
        1. HTTP GET http://localhost:8188/system_stats → should respond
        2. Check queue: GET http://localhost:8188/queue → pending count
        3. If queue stuck (same items for > 10 min) → hung
        """
        try:
            r = requests.get("http://localhost:8188/system_stats", timeout=5)
            queue = requests.get("http://localhost:8188/queue", timeout=5).json()
            
            pending = len(queue.get("queue_pending", []))
            running = len(queue.get("queue_running", []))
            
            return {
                "healthy": True,
                "pending": pending,
                "running": running,
                "detail": "OK"
            }
        except:
            return {"healthy": False, "detail": "unreachable", "recovery": "restart"}
    
    def _check_gpu(self) -> dict:
        """
        nvidia-smi checks:
        ├── Temperature > 85°C → WARNING (throttling imminent)
        ├── Temperature > 90°C → CRITICAL (pause pipeline)
        ├── VRAM > 95% when no model loading → LEAK
        └── GPU utilization 0% for > 5 min during generation → HUNG
        """
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu,memory.used,memory.total,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            temp, vram_used, vram_total, util = result.stdout.strip().split(", ")
            temp, vram_used, vram_total, util = int(temp), int(vram_used), int(vram_total), int(util)
            
            healthy = True
            detail = "OK"
            
            if temp > 90:
                healthy = False
                detail = f"CRITICAL: GPU temp {temp}°C — PAUSE PIPELINE"
            elif temp > 85:
                detail = f"WARNING: GPU temp {temp}°C — throttling likely"
            
            if vram_used / vram_total > 0.95:
                healthy = False
                detail = f"VRAM LEAK: {vram_used}/{vram_total}MB used"
            
            return {
                "healthy": healthy,
                "temp_c": temp,
                "vram_used_mb": vram_used,
                "vram_total_mb": vram_total,
                "utilization": util,
                "detail": detail
            }
        except:
            return {"healthy": False, "detail": "nvidia-smi failed"}
    
    def _check_disk(self) -> dict:
        """Alert if <50GB free. Emergency if <20GB."""
        usage = psutil.disk_usage(self.config["settings"]["storage"]["output_dir"])
        free_gb = usage.free / (1024**3)
        
        if free_gb < 20:
            return {"healthy": False, "detail": f"CRITICAL: {free_gb:.1f}GB free", 
                    "recovery": "emergency_cleanup"}
        elif free_gb < 50:
            return {"healthy": True, "detail": f"WARNING: {free_gb:.1f}GB free"}
        return {"healthy": True, "free_gb": round(free_gb, 1), "detail": "OK"}
    
    def _check_ram(self) -> dict:
        """Alert if <8GB available (Qwen 3.5 needs ~26GB system RAM)."""
        available_gb = psutil.virtual_memory().available / (1024**3)
        if available_gb < 8:
            return {"healthy": False, "detail": f"LOW RAM: {available_gb:.1f}GB available"}
        return {"healthy": True, "available_gb": round(available_gb, 1), "detail": "OK"}
    
    def _check_pipeline_progress(self) -> dict:
        """
        If job status hasn't changed in > 30 minutes → something is stuck.
        Exception: MANUAL_REVIEW (waiting for human is expected).
        """
        current_job = self.db.get_active_jobs()
        if not current_job:
            return {"healthy": True, "detail": "no active jobs"}
        
        job = current_job[0]
        if job["status"] == "manual_review":
            return {"healthy": True, "detail": "waiting for human review"}
        
        if job["status"] != self._last_job_status:
            self._last_job_status = job["status"]
            self._last_status_change = time.time()
        
        stuck_minutes = (time.time() - self._last_status_change) / 60
        
        if stuck_minutes > 30:
            return {
                "healthy": False,
                "detail": f"Pipeline stuck in '{job['status']}' for {stuck_minutes:.0f}min",
                "recovery": "alert"
            }
        return {"healthy": True, "detail": f"Progress OK ({job['status']})", 
                "minutes_in_state": round(stuck_minutes, 1)}
    
    # ─── Recovery Actions ──────────────────────────────
    
    def _handle_unhealthy(self, service: str, status: dict):
        """Take recovery action based on service and failure type."""
        recovery = status.get("recovery", "alert")
        
        if recovery == "restart":
            self._restart_service(service)
        elif recovery == "emergency_cleanup":
            StorageManager(self.config).emergency_cleanup()
        elif recovery == "alert":
            pass  # Just alert below
        
        # Always alert
        self.telegram.alert(
            f"🚨 Watchdog: {service} unhealthy\n"
            f"Detail: {status['detail']}\n"
            f"Action: {recovery}"
        )
        self.events.emit(Event(
            EventType.SERVICE_UNHEALTHY,
            data={"service": service, "status": status}
        ))
    
    def _restart_service(self, service: str):
        """Attempt service restart."""
        if service == "ollama":
            subprocess.run(["ollama", "stop"], capture_output=True, timeout=10)
            time.sleep(5)
            subprocess.Popen(["ollama", "serve"])
            time.sleep(10)
        
        elif service == "comfyui":
            # Kill ComfyUI process and restart
            for p in psutil.process_iter():
                if "comfyui" in p.name().lower() or "main.py" in " ".join(p.cmdline()):
                    p.kill()
            time.sleep(5)
            subprocess.Popen(
                ["python", "main.py", "--listen", "0.0.0.0"],
                cwd=self.config["settings"]["comfyui"]["path"]
            )
            time.sleep(15)
        
        logger.info(f"Watchdog: restarted {service}")
```

---

### 12.6 Telegram Bot Architecture (`src/core/telegram_bot.py` + handlers + conversations)

> **The human interface.** Yusif controls the entire factory through Telegram.
> This is NOT just "send alerts" — it's a full interactive control panel.

```python
"""
Telegram Bot — built with python-telegram-bot v20+ (async).

Architecture:
┌────────────────────────────────────────────────────────────────┐
│                    TELEGRAM BOT LAYERS                          │
│                                                                │
│  Layer 1: Core Bot (telegram_bot.py)                           │
│  ├── Bot initialization + webhook/polling setup                │
│  ├── Message routing                                           │
│  ├── Media sending (images, videos, albums)                    │
│  └── Rate limiting (Telegram: 30 msgs/sec, 20 msgs/min/chat)  │
│                                                                │
│  Layer 2: Handlers (telegram_handlers.py)                      │
│  ├── Inline button callbacks                                   │
│  ├── Command handlers (/status, /queue, /cancel, etc.)        │
│  └── Notification formatters                                   │
│                                                                │
│  Layer 3: Conversations (telegram_conversations.py)            │
│  ├── Topic selection flow                                      │
│  ├── Manual review flow                                        │
│  ├── Asset regen flow                                          │
│  └── Settings adjustment flow                                  │
└────────────────────────────────────────────────────────────────┘
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)


# ═══════════════════════════════════════════════════════════════
# LAYER 1: CORE BOT
# ═══════════════════════════════════════════════════════════════

class TelegramBot:
    """
    Core bot — handles connection, media, rate limiting.
    
    Config (settings.yaml):
    telegram:
      bot_token: "BOT_TOKEN_HERE"
      chat_id: "YUSIF_CHAT_ID"         # Primary chat for all notifications
      mode: "polling"                    # "polling" | "webhook"
      webhook_url: null                  # Required if mode=webhook
      rate_limit:
        messages_per_second: 25          # Below Telegram's 30/sec limit
        albums_per_minute: 10            # Media groups are heavier
    """
    
    def __init__(self, config: dict):
        self.app = Application.builder().token(config["bot_token"]).build()
        self.chat_id = config["chat_id"]
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all command + callback handlers."""
        # Commands
        self.app.add_handler(CommandHandler("status", handlers.cmd_status))
        self.app.add_handler(CommandHandler("queue", handlers.cmd_queue))
        self.app.add_handler(CommandHandler("cancel", handlers.cmd_cancel))
        self.app.add_handler(CommandHandler("retry", handlers.cmd_retry))
        self.app.add_handler(CommandHandler("quota", handlers.cmd_quota))
        self.app.add_handler(CommandHandler("disk", handlers.cmd_disk))
        self.app.add_handler(CommandHandler("health", handlers.cmd_health))
        self.app.add_handler(CommandHandler("new", handlers.cmd_new_video))
        self.app.add_handler(CommandHandler("settings", handlers.cmd_settings))
        
        # Conversation flows
        self.app.add_handler(conversations.topic_selection_conv)
        self.app.add_handler(conversations.manual_review_conv)
        self.app.add_handler(conversations.asset_regen_conv)
        
        # Inline button callbacks (catch-all)
        self.app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    
    # ─── Media Sending ─────────────────────────────────
    
    async def send(self, text: str, buttons: list = None):
        """Send text message with optional inline buttons."""
        markup = None
        if buttons:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(b["text"], callback_data=b["data"]) for b in row]
                for row in buttons
            ])
        await self.app.bot.send_message(self.chat_id, text, 
                                         reply_markup=markup, parse_mode="HTML")
    
    async def send_image_album(self, images: list[dict]):
        """
        Send up to 10 images as Telegram album.
        images: [{path, caption}]
        Telegram limit: 10 media per album.
        For >10 images: split into multiple albums.
        """
        from telegram import InputMediaPhoto
        
        for chunk in self._chunks(images, 10):
            media = [
                InputMediaPhoto(
                    open(img["path"], "rb"),
                    caption=img.get("caption", "")[:1024],  # Telegram caption limit
                    parse_mode="HTML"
                )
                for img in chunk
            ]
            await self.app.bot.send_media_group(self.chat_id, media)
            await asyncio.sleep(1)  # Rate limiting between albums
    
    async def send_video(self, video_path: str, caption: str, buttons: list = None):
        """Send video with caption and optional buttons."""
        markup = None
        if buttons:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(b["text"], callback_data=b["data"]) for b in row]
                for row in buttons
            ])
        
        # Telegram video limit: 50MB for bots, 2GB with local API server
        file_size = os.path.getsize(video_path)
        if file_size > 50 * 1024 * 1024:
            # Send as document (no preview but no size limit with local API)
            await self.app.bot.send_document(
                self.chat_id, open(video_path, "rb"),
                caption=caption, reply_markup=markup
            )
        else:
            await self.app.bot.send_video(
                self.chat_id, open(video_path, "rb"),
                caption=caption, reply_markup=markup,
                supports_streaming=True
            )
    
    async def alert(self, text: str):
        """Send alert with 🚨 prefix."""
        await self.send(f"🚨 {text}")


# ═══════════════════════════════════════════════════════════════
# LAYER 2: HANDLERS
# ═══════════════════════════════════════════════════════════════

class TelegramHandlers:
    """
    Command handlers and callback processors.
    
    COMMANDS:
    /status     → Current pipeline status (active job, phase, GPU, disk)
    /queue      → Job queue (pending, active, completed today)
    /cancel     → Cancel active job (confirmation required)
    /retry      → Retry blocked job from last checkpoint
    /quota      → YouTube API quota status
    /disk       → Disk usage + cleanup options
    /health     → Full system health (GPU, RAM, services, disk)
    /new        → Start new video (triggers topic selection flow)
    /settings   → View/change settings (channel, quality, auto-publish)
    """
    
    async def cmd_status(self, update: Update, context):
        """
        📊 Pipeline Status
        
        🎬 Active Job: job_20260315_120000
        📋 Topic: "أسرار الحرب العالمية الثانية"
        🔄 Phase: VIDEO_QA (6B — verifying clips)
        ⏱️ Time in phase: 4m 22s
        🎯 Progress: 12/15 scenes verified
        🖥️ GPU: Qwen 3.5-27B loaded (14.2GB VRAM, 68°C)
        💾 Disk: 342GB free
        📊 YouTube Quota: 7,499/10,000 remaining
        
        ⏳ Queue: 2 jobs pending
        """
        pass
    
    async def cmd_queue(self, update: Update, context):
        """
        📋 Job Queue
        
        🟢 Active: "أسرار الحرب العالمية الثانية" (VIDEO_QA)
        ⏳ #2: "مستقبل الذكاء الاصطناعي" (pending)
        ⏳ #3: "أزمة المياه في الشرق الأوسط" (pending)
        ✅ Today: 1 video published
        ❌ Blocked: 0
        
        [▶️ Start #2 Now] [🔀 Reorder] [❌ Remove #3]
        """
        pass
    
    async def handle_callback(self, update: Update, context):
        """
        Routes inline button callbacks by prefix.
        
        Callback data format: "{action}:{job_id}:{extra}"
        
        Actions:
        ├── "approve_images:{job_id}"      → Approve all images, continue pipeline
        ├── "regen_failed:{job_id}"        → Regenerate failed images
        ├── "regen_scene:{job_id}:{idx}"   → Regenerate specific scene
        ├── "approve_videos:{job_id}"      → Approve all video clips
        ├── "approve_final:{job_id}"       → Approve final video, proceed to publish
        ├── "reject_final:{job_id}"        → Reject, block job
        ├── "publish:{job_id}"             → Publish now
        ├── "cancel:{job_id}"              → Cancel job
        ├── "retry:{job_id}"               → Retry from last checkpoint
        ├── "select_topic:{job_id}:{idx}"  → Select topic from research results
        ├── "rollback:{job_id}:{scene}:{v}"→ Rollback asset to version
        ├── "edit_prompt:{job_id}:{scene}" → Enter prompt edit mode
        └── "queue_*"                      → Queue management actions
        """
        query = update.callback_query
        await query.answer()  # Acknowledge button press
        
        data = query.data
        action = data.split(":")[0]
        
        # Route to appropriate handler
        ROUTES = {
            "approve_images":  self._handle_approve_images,
            "regen_failed":    self._handle_regen_failed,
            "regen_scene":     self._handle_regen_scene,
            "approve_videos":  self._handle_approve_videos,
            "approve_final":   self._handle_approve_final,
            "publish":         self._handle_publish,
            "cancel":          self._handle_cancel,
            "retry":           self._handle_retry,
            "select_topic":    self._handle_select_topic,
            "rollback":        self._handle_rollback,
            "edit_prompt":     self._handle_edit_prompt,
        }
        
        handler = ROUTES.get(action)
        if handler:
            await handler(query, data)
    
    async def _handle_approve_images(self, query, data):
        """User approved images → unblock pipeline → continue to LTX."""
        job_id = data.split(":")[1]
        self.state_machine.transition(job_id, JobStatus.VIDEO)
        self.pipeline_runner.resume_job(job_id)
        await query.edit_message_text(f"✅ Images approved. Starting video generation...")
    
    async def _handle_select_topic(self, query, data):
        """User selected a topic from research results."""
        _, job_id, topic_idx = data.split(":")
        topic = self.db.get_research_topics(job_id)[int(topic_idx)]
        self.db.set_selected_topic(job_id, topic)
        self.state_machine.transition(job_id, JobStatus.SEO)
        self.pipeline_runner.resume_job(job_id)
        await query.edit_message_text(f"✅ Topic selected: {topic['title']}\nStarting SEO...")
    
    async def _handle_edit_prompt(self, query, data):
        """Enter prompt editing — wait for user's new prompt text."""
        _, job_id, scene_idx = data.split(":")
        # Store state: waiting for prompt text
        context.user_data["editing_prompt"] = {
            "job_id": job_id,
            "scene_index": int(scene_idx)
        }
        await query.edit_message_text(
            f"✏️ Scene {scene_idx} — Enter new visual prompt:\n"
            f"Current: {self.db.get_scene(job_id, int(scene_idx))['visual_prompt']}"
        )


# ═══════════════════════════════════════════════════════════════
# LAYER 3: CONVERSATION FLOWS
# ═══════════════════════════════════════════════════════════════

class TelegramConversations:
    """
    Multi-step conversation flows for complex interactions.
    Uses python-telegram-bot ConversationHandler.
    """
    
    # ─── Topic Selection Flow ──────────────────────────
    # Triggered by: Phase 1 completion (research done, topics ready)
    # 
    # Step 1: Bot sends 5 topics with descriptions
    #   "🔍 Research complete! Select a topic:
    #    
    #    1️⃣ أسرار الحرب العالمية الثانية المنسية
    #       Score: 8.5 | Trend: ↑ | Competition: Low
    #    
    #    2️⃣ مستقبل الذكاء الاصطناعي في العالم العربي  
    #       Score: 9.1 | Trend: ↑↑ | Competition: Medium
    #    ...
    #    [1️⃣] [2️⃣] [3️⃣] [4️⃣] [5️⃣] [🔄 New Topics]"
    #
    # Step 2: User taps a button → topic selected → pipeline continues
    # Step 3 (optional): User types custom topic → skip research, use this
    
    TOPIC_SELECT, TOPIC_CONFIRM = range(2)
    
    topic_selection_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(
            _topic_entry, pattern="^topics_ready:")
        ],
        states={
            TOPIC_SELECT: [
                CallbackQueryHandler(_topic_selected, pattern="^select_topic:"),
                CallbackQueryHandler(_topic_refresh, pattern="^refresh_topics:"),
                MessageHandler(filters.TEXT, _custom_topic),
            ],
            TOPIC_CONFIRM: [
                CallbackQueryHandler(_topic_confirmed, pattern="^confirm_topic:"),
                CallbackQueryHandler(_topic_back, pattern="^back_to_topics"),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_conversation)],
        per_message=False,
    )
    
    # ─── Manual Review Flow ────────────────────────────
    # Triggered by: Phase 7.5 (job needs human review)
    #
    # Step 1: Bot sends final video + QA scores
    #   "🎬 REVIEW REQUIRED
    #    Topic: {title}
    #    Duration: 10:24
    #    QA: 7.8/10 (below auto-publish threshold)
    #    Reason: Sensitive political topic
    #    [▶️ VIDEO ATTACHED]
    #    
    #    [✅ Approve & Publish] [✏️ Request Changes] [❌ Reject]"
    #
    # Step 2a: Approve → publish
    # Step 2b: Request Changes → bot asks what to change
    #   "What needs changing?
    #    [🖼️ Specific Scene] [📝 Script] [🎵 Audio] [🎬 Full Regen]"
    # Step 3: User specifies → pipeline handles regen → back to review
    
    REVIEW_DECISION, REVIEW_CHANGES, REVIEW_SCENE_SELECT = range(3)
    
    manual_review_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(
            _review_entry, pattern="^review_ready:")
        ],
        states={
            REVIEW_DECISION: [
                CallbackQueryHandler(_review_approve, pattern="^approve_final:"),
                CallbackQueryHandler(_review_changes, pattern="^request_changes:"),
                CallbackQueryHandler(_review_reject, pattern="^reject_final:"),
            ],
            REVIEW_CHANGES: [
                CallbackQueryHandler(_change_scene, pattern="^change_scene:"),
                CallbackQueryHandler(_change_script, pattern="^change_script:"),
                CallbackQueryHandler(_change_audio, pattern="^change_audio:"),
                CallbackQueryHandler(_full_regen, pattern="^full_regen:"),
            ],
            REVIEW_SCENE_SELECT: [
                CallbackQueryHandler(_scene_selected, pattern="^scene_change:"),
                MessageHandler(filters.TEXT, _scene_custom_instruction),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_conversation)],
    )
    
    # ─── Interaction Patterns Summary ──────────────────
    #
    # PATTERN 1: Notification Only (no response needed)
    #   Bot: "✅ Phase 3 complete. Script ready. Starting compliance..."
    #   → No buttons, informational only
    #
    # PATTERN 2: Quick Action (single button press)
    #   Bot: "⚠️ Job blocked: compliance issue"
    #   [🔄 Retry] [❌ Cancel]
    #   → One tap, immediate action
    #
    # PATTERN 3: Gallery Review (media + approval)
    #   Bot: [Album of 15 images with captions]
    #   Bot: "✅ 13/15 passed. [Approve All] [Regen Failed]"
    #   → Review media, then single tap
    #
    # PATTERN 4: Conversation (multi-step)
    #   Topic selection, manual review with changes
    #   → Multiple steps, state tracked
    #
    # PATTERN 5: Text Input (user types response)
    #   Prompt editing: user types new prompt
    #   Custom topic: user types topic
    #   → Freeform text, parsed by bot
```

### 12.7 Job Queue & Concurrency (`src/core/job_queue.py`)

```python
"""
Job queue — manages multiple jobs on a single GPU.
Only ONE job can use the GPU at a time, but multiple jobs
can be in different lifecycle stages.

Key insight: some phases need GPU, some don't.
We can interleave GPU work from different jobs.
"""

class JobQueue:
    """
    QUEUE ARCHITECTURE:
    ┌──────────────────────────────────────────────────────┐
    │                    JOB QUEUE                          │
    │                                                      │
    │  Priority Levels:                                    │
    │  P0 (urgent):    Trending topic hijack (time-sensitive)
    │  P1 (normal):    Scheduled content calendar videos   │
    │  P2 (background): Re-optimization, shorts generation │
    │                                                      │
    │  States:                                             │
    │  ├── queued      → Waiting for GPU                   │
    │  ├── active      → Currently running on GPU          │
    │  ├── paused      → Waiting for human (manual review) │
    │  ├── deferred    → Waiting for quota/time            │
    │  └── completed   → Done (published or cancelled)     │
    │                                                      │
    │  CONCURRENCY MODEL:                                  │
    │  ├── GPU phases: STRICTLY one at a time              │
    │  ├── CPU phases: can run in parallel                 │
    │  ├── Waiting phases: don't block the queue           │
    │  └── Interleaving: if job A is waiting for human,    │
    │      job B can start GPU work                        │
    └──────────────────────────────────────────────────────┘
    
    DB table: job_queue
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS job_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
        priority INTEGER DEFAULT 1,          -- 0=urgent, 1=normal, 2=background
        position INTEGER,                    -- Queue position
        queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        estimated_duration_min INTEGER,       -- Based on historical averages
        
        -- Scheduling
        scheduled_start TIMESTAMP,            -- NULL = start ASAP
        channel_id TEXT,                      -- Which YouTube channel
        
        CONSTRAINT valid_priority CHECK(priority IN (0, 1, 2))
    );
    CREATE INDEX IF NOT EXISTS idx_queue_priority ON job_queue(priority, position);
    """
    
    def enqueue(self, job_id: str, priority: int = 1, 
                scheduled_start: str = None) -> int:
        """Add job to queue. Returns queue position."""
        position = self._next_position(priority)
        self.db.execute("""
            INSERT INTO job_queue (job_id, priority, position, scheduled_start)
            VALUES (?, ?, ?, ?)
        """, (job_id, priority, position, scheduled_start))
        self.db.commit()
        
        self.telegram.send(
            f"📋 Job queued: {job_id}\n"
            f"Priority: {'🔴 Urgent' if priority == 0 else '🟢 Normal' if priority == 1 else '🔵 Background'}\n"
            f"Position: #{position}"
        )
        return position
    
    def get_next_job(self) -> Optional[str]:
        """
        Get the next job that should run.
        Logic:
        1. Check for P0 (urgent) jobs first
        2. Then P1 by position
        3. Then P2 if nothing else
        4. Skip jobs whose scheduled_start is in the future
        5. Skip if YouTube quota insufficient for publish
        """
        row = self.db.execute("""
            SELECT job_id FROM job_queue 
            WHERE job_id NOT IN (
                SELECT id FROM jobs WHERE status IN ('published', 'cancelled', 'complete')
            )
            AND (scheduled_start IS NULL OR scheduled_start <= CURRENT_TIMESTAMP)
            ORDER BY priority ASC, position ASC
            LIMIT 1
        """).fetchone()
        return row["job_id"] if row else None
    
    def can_interleave(self, current_job_id: str) -> Optional[str]:
        """
        If current job is paused (manual_review, blocked), 
        can another job use the GPU?
        
        Returns: job_id of interleave candidate, or None
        """
        current = self.db.get_job(current_job_id)
        if current["status"] not in ("manual_review", "blocked"):
            return None  # Current job is active — no interleave
        
        # Find next queued job
        return self.get_next_job()
    
    def reorder(self, job_id: str, new_position: int):
        """Move job to new position in queue."""
        pass
    
    def promote(self, job_id: str):
        """Promote to P0 (urgent). Used by trending_hijack agent."""
        pass


class QueueRunner:
    """
    Main loop that manages the queue.
    Replaces the simple resume_all() from PipelineRunner.
    
    Loop:
    1. Get next job from queue
    2. Run it through PipelineRunner
    3. If job pauses (manual_review) → check for interleave
    4. If job completes → get next from queue
    5. If queue empty → sleep and wait for new jobs
    
    INTERLEAVING EXAMPLE:
    ─────────────────────
    Time 00:00 — Job A starts (Phase 1: Research, GPU: Qwen)
    Time 00:15 — Job A: Phase 1 done, topics sent to Telegram
    Time 00:15 — Job A: PAUSED (waiting for Yusif to select topic)
    Time 00:15 — Job B starts (Phase 1: Research, GPU: Qwen)  ← INTERLEAVE
    Time 00:20 — Yusif selects topic for Job A
    Time 00:20 — Job A queued for resume (waits for Job B's GPU phase to finish)
    Time 00:30 — Job B: Phase 1 done, topics sent, PAUSED
    Time 00:30 — Job A resumes (Phase 2: SEO, GPU: Qwen)     ← INTERLEAVE BACK
    ...and so on
    
    This maximizes GPU utilization — GPU is idle only when:
    - All jobs are paused (waiting for human)
    - Queue is empty
    - Service is unhealthy
    """
    
    def run_forever(self):
        """Main queue loop."""
        while True:
            job_id = self.queue.get_next_job()
            
            if job_id is None:
                time.sleep(30)  # Nothing to do — check again in 30s
                continue
            
            try:
                result = self.pipeline.run_job(job_id)
                
                if result == "paused":
                    # Job is waiting for human — try interleave
                    next_job = self.queue.can_interleave(job_id)
                    if next_job:
                        logger.info(f"Interleaving: {job_id} paused, starting {next_job}")
                        self.pipeline.run_job(next_job)
                
                elif result == "completed":
                    logger.info(f"Job {job_id} completed")
                
                elif result == "blocked":
                    logger.warning(f"Job {job_id} blocked — check Telegram")
            
            except Exception as e:
                logger.error(f"Queue runner error: {e}")
                time.sleep(60)  # Wait before retrying
```

### 12.8 Deployment & First Run (`SETUP.md`)

> **This section goes into a separate SETUP.md file** for clarity.
> Linked from ARCHITECTURE.md.

```markdown
# SETUP.md — First Run Guide

## Prerequisites
- OS: Ubuntu 22.04+ or Windows 11 with WSL2
- GPU: NVIDIA RTX 3090 (24GB VRAM) with CUDA 12.x + cuDNN
- CPU: i9-14900K (or equivalent)
- RAM: 128GB
- Disk: 1TB+ SSD (NVMe recommended)
- Python: 3.11+
- NVIDIA Driver: 545+

## Step 1: System Setup

### 1.1 NVIDIA + CUDA
```bash
# Verify GPU
nvidia-smi

# Install CUDA toolkit if not present
# https://developer.nvidia.com/cuda-downloads
```

### 1.2 Python Environment
```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install core dependencies
pip install -r requirements.txt
```

### 1.3 FFmpeg
```bash
# Ubuntu
sudo apt install ffmpeg

# Verify: ffmpeg -version (need 5.0+)
```

## Step 2: Model Downloads (~80GB total)

### 2.1 Ollama + Qwen Models
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Download models
ollama pull qwen3.5:27b    # ~42GB, Arabic text LLM
ollama pull Qwen 3.5-27B:72b-instruct-q4_K_M  # ~42GB, Vision LLM (shares layers with above)

# Configure: keep_alive=0 (free VRAM after each use)
echo 'OLLAMA_KEEP_ALIVE=0' >> /etc/environment
systemctl restart ollama

# Verify
ollama run qwen3.5:27b "مرحبا، كيف حالك؟"
```

### 2.2 ComfyUI + Models
```bash
# Clone ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt

# Download FLUX.1-dev (~12GB)
# Place in: ComfyUI/models/unet/flux1-dev.safetensors
wget https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors \
     -O models/unet/flux1-dev.safetensors

# Download FLUX VAE
wget https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors \
     -O models/vae/flux1-ae.safetensors

# Download FLUX CLIP encoders
wget https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors \
     -O models/clip/clip_l.safetensors
wget https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors \
     -O models/clip/t5xxl_fp8.safetensors

# Download LTX-Video 2.3 (~8GB)
# Check: https://huggingface.co/Lightricks/LTX-Video
wget https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2.3.safetensors \
     -O models/checkpoints/ltx-video-2.3.safetensors

# Start ComfyUI
python main.py --listen 0.0.0.0 --port 8188
# Verify: http://localhost:8188
```

### 2.3 Fish Audio S2 Pro
```bash
git clone https://github.com/fishaudio/fish-audio-s2-pro.git
cd fish-audio-s2-pro
pip install -e .

# Download model
huggingface-cli download fishaudio/fish-audio-s2-pro-1.5 --local-dir checkpoints/fish-audio-s2-pro-1.5

# Verify
python -m tools.api --checkpoint checkpoints/fish-audio-s2-pro-1.5 --listen 0.0.0.0:8080
```

### 2.4 ACE-Step 1.5 + MOSS-SoundEffect
```bash
pip install audiocraft

# Models auto-download on first use (~3GB each)
# Verify:
python -c "from audiocraft.models import ACE-Step 1.5; m = ACE-Step 1.5.get_pretrained('facebook/ACE-Step 1.5-medium'); print('OK')"
```

### 2.5 Whisper (for Audio QA)
```bash
pip install openai-whisper
# Or faster: pip install faster-whisper

# Model auto-downloads on first use (~1GB for 'base')
```

## Step 3: Arabic Fonts
```bash
# Download all fonts to src/phase5_production/fonts/
mkdir -p src/phase5_production/fonts

# Google Fonts (all free)
FONTS=(
    "IBM+Plex+Sans+Arabic"
    "Noto+Naskh+Arabic" 
    "Amiri"
    "Aref+Ruqaa"
    "Cairo"
    "Tajawal"
    "Scheherazade+New"
    "Readex+Pro"
    "El+Messiri"
    "Lemonada"
    "Noto+Sans+Arabic"
)

for font in "${FONTS[@]}"; do
    wget "https://fonts.google.com/download?family=${font}" -O "/tmp/${font}.zip"
    unzip "/tmp/${font}.zip" -d "src/phase5_production/fonts/${font//+/_}/"
done

# Install system-wide (for PyCairo/Pango)
sudo cp -r src/phase5_production/fonts/* /usr/share/fonts/truetype/
fc-cache -f -v
```

## Step 4: Configuration
```bash
# Copy example config
cp settings.example.yaml settings.yaml
cp channels.example.yaml channels.yaml

# Edit settings.yaml:
# - telegram.bot_token
# - telegram.chat_id
# - youtube.client_secret_path
# - paths to ComfyUI, Fish Audio S2 Pro
# - GPU settings

# YouTube API setup:
# 1. Go to https://console.cloud.google.com
# 2. Create project → Enable YouTube Data API v3
# 3. Create OAuth 2.0 credentials
# 4. Download client_secret.json → place in config/
# 5. First run will prompt for browser auth
```

## Step 5: Database Init
```bash
# Initialize database (creates all tables)
python -m src.core.database --init

# Verify
sqlite3 data/factory.db ".tables"
# Should show: jobs, scenes, qa_rubrics, asset_versions, events, ...
```

## Step 6: Verify Everything
```bash
python -m src.core.health_check

# Should output:
# ✅ Ollama: running, qwen3.5:27b available
# ✅ ComfyUI: running on :8188, FLUX loaded
# ✅ Fish Audio S2 Pro: running on :8080
# ✅ FFmpeg: v5.1.2
# ✅ GPU: RTX 3090, 24GB VRAM, driver 545.x
# ✅ RAM: 128GB (112GB available)
# ✅ Disk: 847GB free
# ✅ Telegram: bot connected, chat_id verified
# ✅ YouTube: OAuth valid, quota 10,000/10,000
# ✅ Fonts: 11/11 installed
# ✅ Database: 18 tables, WAL mode
# 
# 🟢 ALL SYSTEMS GO — Ready to produce videos!
```

## Step 7: First Video (test run)
```bash
# Start the factory
python -m src.main

# Or via Telegram:
# Send /new to the bot → follow topic selection → watch it work
```
```

### 12.9 Database Backup (`src/core/db_backup.py`)

```python
"""
SQLite backup strategy.
DB corruption = EVERYTHING lost (jobs, scenes, rubrics, analytics, events, versions).
This is unacceptable.
"""

class DatabaseBackup:
    """
    BACKUP STRATEGY:
    ┌──────────────────────────────────────────────────────────┐
    │                                                          │
    │  LEVEL 1: WAL Checkpointing (automatic, every 5 min)   │
    │  ├── SQLite WAL mode already enabled                     │
    │  ├── PRAGMA wal_checkpoint(PASSIVE) every 5 minutes      │
    │  ├── Ensures WAL file doesn't grow unbounded             │
    │  └── Low overhead, always running                        │
    │                                                          │
    │  LEVEL 2: Hot Backup (hourly)                           │
    │  ├── sqlite3 .backup API (safe, no locking needed)       │
    │  ├── Saves to: backups/hourly/factory_YYYYMMDD_HH.db    │
    │  ├── Keep last 48 hourly backups (2 days)                │
    │  └── Rotate: delete oldest when > 48                     │
    │                                                          │
    │  LEVEL 3: Daily Snapshot (daily, 2 AM)                  │
    │  ├── Full backup + VACUUM into clean copy                │
    │  ├── Saves to: backups/daily/factory_YYYYMMDD.db         │
    │  ├── Compress with zstd → ~60-80% size reduction         │
    │  ├── Keep last 30 daily backups                          │
    │  └── Integrity check: PRAGMA integrity_check on backup   │
    │                                                          │
    │  LEVEL 4: Off-site (optional, weekly)                   │
    │  ├── Copy daily snapshot to external drive / cloud       │
    │  ├── rclone to Google Drive / S3 / etc.                  │
    │  └── Telegram: send compressed DB as document (< 50MB)   │
    │                                                          │
    │  RECOVERY:                                               │
    │  ├── Detect corruption: PRAGMA integrity_check on start  │
    │  ├── Auto-recover: load latest valid backup              │
    │  ├── Alert Yusif with recovery details                   │
    │  └── Resume pipeline from last checkpoint                │
    └──────────────────────────────────────────────────────────┘
    """
    
    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = db_path
        self.backup_dir = backup_dir
        os.makedirs(f"{backup_dir}/hourly", exist_ok=True)
        os.makedirs(f"{backup_dir}/daily", exist_ok=True)
    
    def wal_checkpoint(self):
        """Level 1: WAL checkpoint (every 5 min via scheduler)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn.close()
    
    def hot_backup(self):
        """Level 2: Hourly hot backup using sqlite3 backup API."""
        timestamp = datetime.now().strftime("%Y%m%d_%H")
        backup_path = f"{self.backup_dir}/hourly/factory_{timestamp}.db"
        
        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(backup_path)
        src.backup(dst)
        dst.close()
        src.close()
        
        # Rotate: keep last 48
        self._rotate_backups(f"{self.backup_dir}/hourly", keep=48)
        
        logger.info(f"Hourly backup: {backup_path} ({os.path.getsize(backup_path) / 1024 / 1024:.1f}MB)")
    
    def daily_snapshot(self):
        """Level 3: Daily snapshot with VACUUM + compress + integrity check."""
        timestamp = datetime.now().strftime("%Y%m%d")
        snapshot_path = f"{self.backup_dir}/daily/factory_{timestamp}.db"
        compressed_path = f"{snapshot_path}.zst"
        
        # Backup
        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(snapshot_path)
        src.backup(dst)
        
        # VACUUM the backup (not the live DB)
        dst.execute("VACUUM")
        
        # Integrity check
        result = dst.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            self.telegram.alert(f"🚨 DB integrity check FAILED on daily backup: {result}")
            dst.close()
            src.close()
            return
        
        dst.close()
        src.close()
        
        # Compress
        subprocess.run(["zstd", "-19", "--rm", snapshot_path], check=True)
        
        # Rotate: keep last 30
        self._rotate_backups(f"{self.backup_dir}/daily", keep=30)
        
        size_mb = os.path.getsize(compressed_path) / 1024 / 1024
        logger.info(f"Daily snapshot: {compressed_path} ({size_mb:.1f}MB)")
    
    def check_and_recover(self) -> bool:
        """
        Run on startup. Returns True if DB is healthy.
        If corrupt → auto-recover from latest backup.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            
            if result[0] == "ok":
                return True
            
            # CORRUPT — recover
            logger.error(f"DB CORRUPT: {result}")
            self.telegram.alert("🚨 DATABASE CORRUPTION DETECTED — auto-recovering...")
            
            return self._recover_from_backup()
        
        except Exception as e:
            logger.error(f"DB unreadable: {e}")
            return self._recover_from_backup()
    
    def _recover_from_backup(self) -> bool:
        """Find latest valid backup and restore."""
        # Try hourly backups first (most recent)
        for backup in sorted(
            glob.glob(f"{self.backup_dir}/hourly/*.db"),
            reverse=True
        ):
            try:
                conn = sqlite3.connect(backup)
                result = conn.execute("PRAGMA integrity_check").fetchone()
                conn.close()
                
                if result[0] == "ok":
                    # Valid backup found — restore
                    shutil.copy2(backup, self.db_path)
                    self.telegram.alert(
                        f"✅ DB recovered from: {os.path.basename(backup)}\n"
                        f"Some recent data may be lost (since last hourly backup)."
                    )
                    return True
            except:
                continue
        
        # Try daily snapshots (decompress first)
        for backup in sorted(
            glob.glob(f"{self.backup_dir}/daily/*.db.zst"),
            reverse=True
        ):
            try:
                decompressed = backup.replace(".zst", "")
                subprocess.run(["zstd", "-d", backup, "-o", decompressed], check=True)
                
                conn = sqlite3.connect(decompressed)
                result = conn.execute("PRAGMA integrity_check").fetchone()
                conn.close()
                
                if result[0] == "ok":
                    shutil.copy2(decompressed, self.db_path)
                    os.remove(decompressed)
                    self.telegram.alert(
                        f"✅ DB recovered from daily snapshot: {os.path.basename(backup)}\n"
                        f"⚠️ Data loss: everything since this snapshot."
                    )
                    return True
                
                os.remove(decompressed)
            except:
                continue
        
        # No valid backup found
        self.telegram.alert(
            "🚨🚨 CRITICAL: No valid backup found. Database unrecoverable.\n"
            "Manual intervention required."
        )
        return False
    
    def _rotate_backups(self, directory: str, keep: int):
        """Delete oldest backups, keep last N."""
        files = sorted(glob.glob(f"{directory}/*"), key=os.path.getmtime)
        while len(files) > keep:
            os.remove(files.pop(0))


# ═══ SCHEDULER INTEGRATION ═══
# In main.py startup:
#
# backup = DatabaseBackup("data/factory.db")
# 
# # Check DB integrity on start
# if not backup.check_and_recover():
#     sys.exit("FATAL: Database unrecoverable")
#
# # Schedule backups
# scheduler.add_job(backup.wal_checkpoint, 'interval', minutes=5)
# scheduler.add_job(backup.hot_backup, 'interval', hours=1)
# scheduler.add_job(backup.daily_snapshot, 'cron', hour=2, minute=0)
```

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

### Operational Rules
17. **ALWAYS use AssetVersioner for generated assets.** Never overwrite — version and symlink.
18. **ALWAYS wrap external service calls in RetryEngine.** No bare API calls without retry.
19. **ALWAYS check QuotaTracker.can_afford() before YouTube API calls.** Quota exhaustion = silent failures.
20. **NEVER bypass the job queue.** All jobs go through JobQueue, even manual /new commands.
21. **ALWAYS run DatabaseBackup.check_and_recover() on startup.** Before anything else.
22. **Telegram callbacks MUST acknowledge within 5 seconds** (query.answer()). Slow handlers → background task.
