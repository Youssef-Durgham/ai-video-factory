# AI Video Factory — Full Blueprint

## Overview

Automated AI-powered video production pipeline that generates, produces, and publishes high-quality Arabic documentary/educational/entertainment videos to YouTube — fully autonomous with minimal human intervention.

**Owner:** Yusif
**Status:** Planning
**Hardware Target:** i9-14900K, 128GB RAM, RTX 3090 (24GB) — single GPU to start

---

## Architecture Overview — 8 Phases

```
PHASE 1          PHASE 2          PHASE 3          PHASE 4
Research &  ───▶ Keyword &   ───▶ Script      ───▶ QA: Script
Trends           SEO Analysis     Engine           Compliance
                                                      │
                                                  PASS ▼ FAIL → fix/block
                                                      │
PHASE 8          PHASE 7          PHASE 6          PHASE 5
Publish     ◀─── QA: Final  ◀─── QA: Visual  ◀─── Production
Engine           Video Check      Verify           Engine

COMPLIANCE AGENT gates Phase 4 + 6 + 7 — can BLOCK and alert user
```

### Phase Summary

| # | Phase | Purpose | Gate? |
|---|-------|---------|-------|
| 1 | Research & Trends | Find trending topics on YouTube + web + news | — |
| 2 | Keyword & SEO Analysis | Find best keywords, titles, tags for the topic on YouTube | — |
| 3 | Script Engine | Write, review, fact-check, split script into scenes | — |
| 4 | **QA: Script Compliance** | Verify script is NOT violating YouTube ToS before production | ✅ GATE |
| 5 | Production Engine | Generate images, videos, voice, music, SFX, compose | — |
| 6 | **QA: Visual Verification** | Verify generated images match script before video generation | ✅ GATE |
| 7 | **QA: Final Video Check** | Verify FFmpeg composed correctly — A/V sync, duration, quality | ✅ GATE |
| 8 | Publishing Engine | Thumbnail, SEO metadata, YouTube upload, scheduling | — |

---

## Phase 1: Research & Trend Discovery

### Purpose
Find trending topics across YouTube, news, social media — and present them to the user for selection.

### Components

#### 1.1 YouTube Trend Scanner
- **YouTube Trending API:** What's trending in Arabic YouTube right now
- **YouTube Search:** Most-viewed recent videos by category
- **Competitor Analysis:** What are top Arabic documentary/news channels posting about?
  - Track 20-50 competitor channels
  - What topics got the most views in the last 7 days?
  - What topics are getting sudden view spikes?
- **Output:** Top trending YouTube topics with view counts

#### 1.2 Web & News Trend Scanner
- **Sources:**
  - Google Trends API (Arabic regions: Iraq, Saudi, Egypt, UAE, Morocco)
  - Twitter/X trending hashtags (Arabic)
  - Reddit trending (r/worldnews, r/science, r/todayilearned)
  - News RSS feeds (Al Jazeera, BBC Arabic, Reuters Arabic, Sky News Arabia)
- **Output:** Top trending web topics with search volume

#### 1.3 Topic Ranker
- Combines YouTube trends + web trends
- Scores each topic:
  - YouTube search volume (high = good)
  - Competition (low = good — fewer videos on this topic)
  - Trend velocity (rising fast = good)
  - Category match (fits our channels)
- **Output:** Ranked list of 10-20 topics

#### 1.4 Topic Presenter
- Sends curated ranked list to Yusif via Telegram
- Includes: topic, score, suggested channel, suggested angle
- Yusif selects topic + confirms channel
- Stores selection in job queue

### Tech Stack
- `pytrends` (Google Trends)
- YouTube Data API v3 (trending + search)
- Twitter API v2 or scraping
- `feedparser` (RSS)
- LLM for summarization and angle suggestion

---

## Phase 2: Keyword & SEO Analysis

### Purpose
BEFORE writing the script — research the best keywords, title style, and tags that will maximize YouTube discoverability for this topic.

### Components

#### 2.1 YouTube Keyword Research
- **YouTube Search Suggest API:** Type the topic → get autocomplete suggestions (= what people actually search)
- **YouTube Search Results Analysis:**
  - Search the topic on YouTube
  - Analyze top 20 results:
    - What titles do they use? (patterns, power words, length)
    - What tags do they have? (via `ytdl` or API)
    - What descriptions? (keywords, structure)
    - View count vs. subscriber ratio (= how well did it perform?)
    - Thumbnail style (text? faces? colors?)
  - **Output:** Keyword report

#### 2.2 Title Generator
- Based on keyword research, generate 10 title options
- Scoring criteria:
  - Contains high-volume keywords
  - Emotional hook (curiosity gap, shock, question)
  - Length < 60 characters
  - Arabic-optimized (reads well right-to-left)
- **Output:** Top 3 title options with keyword density score

#### 2.3 Tag & Description Planner
- Generate 20-30 tags (Arabic + English mix):
  - Primary keyword tags (exact match)
  - Related keyword tags (semantic)
  - Trending tags (currently hot)
  - Channel-level tags (branding)
- Plan description structure:
  - First 2 lines (visible before "show more") — keyword-rich hook
  - Timestamps (added after video is composed)
  - Sources section
  - Social links
  - Hashtags (3-5)
- **Output:** Tag list + description template

#### 2.4 Competitor Gap Analysis
- What angle are competitors NOT covering?
- What questions are unanswered in existing videos?
- Feed unique angles to the Script Writer
- **Output:** Unique angle recommendation

### Tech Stack
- YouTube Data API v3
- YouTube Search Suggest (unofficial endpoint)
- LLM for title generation and analysis
- `yt-dlp` for metadata extraction

---

## Phase 3: Script Engine

### Purpose
Write a complete, reviewed, fact-checked script divided into timed scenes. Uses SEO data from Phase 2 to optimize for keywords.

### Components

#### 3.1 Research Agent
- Takes the selected topic + unique angle from Phase 2
- Searches multiple sources for information:
  - Web search (Brave/Google)
  - Wikipedia
  - News articles
  - Academic sources when relevant
- Compiles raw research document with sources cited
- **Output:** Research document (2000-5000 words) with citations

#### 3.2 Script Writer
- **Inputs:**
  - Research document
  - Channel tone guidelines
  - SEO keywords from Phase 2 (must naturally include top keywords)
  - Selected title from Phase 2
  - Unique angle from Phase 2
- Writes full Arabic script in documentary/narration style
- Structure:
  ```
  - Hook (0:00-0:15) — grab attention, match title promise
  - Introduction (0:15-0:45) — set context
  - Main Content (0:45-8:00) — 3-5 main sections
  - Conclusion (8:00-9:30) — summary + perspective
  - Outro (9:30-10:00) — subscribe CTA
  ```
- Target length: 1200-1800 words (≈ 8-12 minutes spoken)
- **Must include top keywords naturally** (for YouTube closed captions SEO)

#### 3.3 Script Reviewer
- **Separate LLM pass** — reviews the script for:
  - Factual accuracy (cross-reference with sources)
  - Arabic grammar and eloquence (MSA)
  - Engagement level (is the hook strong? is it boring anywhere?)
  - Keyword inclusion (are SEO keywords present?)
  - Pacing (not too fast, not too slow)
- Returns: approved / revision needed + specific notes
- If revision needed → sends back to Writer (max 3 iterations)

#### 3.4 Scene Splitter
- Takes approved script
- Splits into scenes, each 5-15 seconds
- For each scene, generates:
  ```json
  {
    "scene_id": 1,
    "duration_seconds": 10,
    "narration_text": "في عام 1969، خطا الإنسان أول خطوة على سطح القمر...",
    "visual_prompt": "Astronaut stepping onto moon surface, dramatic lighting, cinematic, photorealistic, 1969 space mission",
    "visual_style": "photorealistic_cinematic",
    "camera_movement": "slow_zoom_in",
    "music_mood": "epic_dramatic",
    "sfx": ["footstep_on_gravel", "radio_static"],
    "transition_to_next": "crossfade",
    "text_overlay": null,
    "expected_visual_elements": ["astronaut", "moon_surface", "earth_in_background"]
  }
  ```
- `expected_visual_elements` — used by Phase 6 (Visual QA) to verify images
- **Output:** JSON array of 40-80 scenes

### Tech Stack
- LLM: Local (Llama 3.1 70B via Ollama) or API (Claude/GPT)
- Web search for research
- Structured JSON output with validation

---

## Phase 4: QA — Script Compliance Check ✅ GATE

### Purpose
**MUST PASS before any production begins.** Ensures the script will NOT cause YouTube strikes, demonetization, or bans.

### Checks

#### 4.1 YouTube Community Guidelines Check
- LLM reviews entire script against YouTube's policies:
  - ❌ Hate speech or discrimination
  - ❌ Violence glorification or graphic descriptions
  - ❌ Harassment or bullying of specific individuals
  - ❌ Dangerous or harmful activities
  - ❌ Misleading medical/scientific claims
  - ❌ Election misinformation
  - ❌ Child safety violations
  - ❌ Spam or deceptive practices
- For **political content** specifically:
  - Must present facts, not propaganda
  - Must cite sources for claims
  - Must not call for violence
  - Must not target protected groups
  - Controversial claims must be attributed ("according to X...")

#### 4.2 Copyright Check
- Script text: no plagiarized paragraphs (check against source documents)
- No copyrighted quotes without attribution
- No song lyrics, movie scripts, or book excerpts

#### 4.3 Fact Verification
- Cross-reference key claims with 2+ independent sources
- Flag any claim with only 1 source as "unverified" → add qualifier in script
- Dates, names, statistics → must be verified
- **Output:** Fact-check report with confidence scores

#### 4.4 Arabic Quality Check
- MSA (Modern Standard Arabic) consistency
- No dialect mixing (unless intentional)
- Grammar validation
- Pronunciation-friendly text (avoid ambiguous words for TTS)

### Gate Logic
```
IF all checks pass → proceed to Phase 5
IF minor issues → auto-fix and re-check (max 2 iterations)
IF major issues (policy violation) → BLOCK + alert Yusif via Telegram
   "⚠️ Script blocked: [reason]. Review needed."
   Yusif can: approve override / request rewrite / cancel
```

---

## Phase 5: Production Engine

### Purpose
Generate all media assets — images, video clips, voice, music, SFX — and compose the final video.

### Components

#### 5.1 Image Generator (FLUX)
- **Model:** FLUX.1-dev (local, via ComfyUI or diffusers)
- **VRAM:** ~12GB
- **Per scene:**
  - Generate 2-3 image variations from `visual_prompt`
  - Resolution: 1920x1080 (16:9)
  - Style consistency: Use consistent style LoRA per channel
  - Character consistency: Use IP-Adapter for recurring characters/figures
- **Auto-select:** LLM picks best image based on scene context
- **Time:** ~15-30 sec/image on RTX 3090
- **Output:** Best image per scene saved as PNG
- ⚡ **IMPORTANT:** Images go to Phase 6 (Visual QA) before video generation

#### 5.2 Video Generator (LTX-2)
- **Model:** LTX-2 (local, via ComfyUI)
- **VRAM:** ~12GB
- **ONLY runs after Phase 6 approves images**
- **Per scene:**
  - Input: Approved image from 5.1 + visual_prompt + camera_movement
  - Generate 5-10 second video clip
  - Image-to-Video mode (starts from the FLUX image, adds motion)
  - Apply camera movement (zoom, pan, Ken Burns)
- **Fallback:** If LTX-2 quality is poor for a scene → use FLUX image with Ken Burns effect (FFmpeg)
- **Time:** ~30-90 sec/clip on RTX 3090
- **Output:** MP4 clips per scene (5-10 sec each)

#### 5.3 Voice Generator (Fish Speech)
- **Model:** Fish Speech / OpenAudio S1 (local)
- **VRAM:** ~4GB
- **Setup:**
  - Clone a high-quality Arabic male voice (news anchor style)
  - Each channel can have its own voice profile
  - Voice profiles stored as reference audio files
- **Per scene:**
  - Input: `narration_text` + voice profile
  - Output: WAV audio clip
  - Auto-adjust speed to match target `duration_seconds`
- **Quality checks:**
  - Arabic pronunciation validation
  - No glitches/artifacts detection
  - Re-generate if quality score < threshold
- **Time:** ~5-10 sec/clip on RTX 3090
- **Output:** WAV audio per scene

#### 5.4 Music Generator (MusicGen / AudioCraft)
- **Model:** MusicGen-large (Meta) — local
- **VRAM:** ~4GB
- **Strategy:**
  - Generate 3-4 music tracks per video:
    ```
    - Intro music: epic/dramatic (15 sec)
    - Main background: matches content mood (3-4 min, loopable)
    - Tension/climax: for dramatic moments (30 sec)
    - Outro music: calm/reflective (15 sec)
    ```
  - Prompt based on `music_mood` from scene data
  - Example prompts:
    - `"dramatic orchestral documentary music, arabic influence, cinematic"`
    - `"calm ambient background music, middle eastern oud, gentle"`
    - `"tense suspenseful music, news documentary style"`
- **Output:** WAV tracks for different sections

#### 5.5 SFX Generator (AudioCraft)
- **Model:** AudioGen (part of AudioCraft) — local
- **VRAM:** ~4GB (shared with MusicGen)
- **Per scene:** Generate sound effects from `sfx` tags
  - Example: `"crowd cheering"` → generates crowd audio
  - Example: `"explosion in distance"` → generates explosion SFX
- **Fallback library:** Pre-downloaded SFX from Freesound.org for common sounds
- **Output:** WAV SFX files per scene

#### 5.6 Video Composer (FFmpeg + Python)
- **No GPU needed** — CPU-based
- **Steps:**
  1. **Sequence video clips** in scene order
  2. **Overlay narration audio** on video timeline (volume: 100%)
  3. **Mix background music** (volume: 20-30%, auto-duck under narration)
  4. **Add SFX** at appropriate timestamps (volume: 40-60%)
  5. **Apply transitions** between scenes (crossfade, cut, dissolve)
  6. **Add text overlays:**
     - Title card at start
     - Section headers
     - Key facts/dates on screen
     - Subscribe reminder at end
  7. **Add intro/outro** templates (per channel branding)
  8. **Render final video:**
     - Resolution: 1920x1080 or 4K
     - Codec: H.264/H.265
     - Audio: AAC 320kbps
     - Format: MP4
- **Output:** Final video MP4 → goes to Phase 7

### Production Pipeline Order (GPU Scheduling)
```
Since single GPU, run sequentially:

1. FLUX images (all scenes)       → ~20-40 min
   ── Phase 6: Visual QA ──      → ~2-5 min (LLM check)
   (re-generate failed images)    → ~5-10 min if needed
2. LTX-2 videos (all scenes)     → ~60-120 min
3. Fish Speech (all scenes)       → ~5-10 min
4. MusicGen (3-4 tracks)          → ~5-10 min
5. AudioCraft SFX (all scenes)    → ~5-10 min
6. FFmpeg compose (CPU)           → ~5-10 min
   ── Phase 7: Final QA ──       → ~2-5 min
                                    ─────────
                         Total:    ~2-3 hours per video
```

---

## Phase 6: QA — Visual Verification ✅ GATE

### Purpose
**BEFORE generating video clips (expensive)**, verify that the generated images actually match the script scenes.

### Components

#### 6.1 Image-Script Alignment Check
- **Vision LLM** (local or API) analyzes each generated image:
  - Does it match the `visual_prompt`?
  - Does it contain the `expected_visual_elements`?
  - Is it appropriate (no accidental NSFW, offensive content)?
  - Is the quality acceptable (not blurry, artifacts)?
  - Is the style consistent with previous scenes?
- **Scoring:** Each image gets 1-10 score
  - Score ≥ 7 → PASS
  - Score 4-6 → regenerate with adjusted prompt (1 retry)
  - Score < 4 → regenerate with completely new prompt (1 retry)

#### 6.2 Style Consistency Check
- Compare all scene images side by side:
  - Color palette consistency
  - Art style consistency
  - Character appearance consistency (if recurring)
- Flag outlier images for regeneration

#### 6.3 Sequence Flow Check
- View all images in order — does the visual story flow?
- No jarring jumps between scenes
- Transitions make visual sense

### Gate Logic
```
IF >90% images pass (score ≥ 7) → proceed to video generation
IF 70-90% pass → regenerate failed ones (1 round)
IF <70% pass → BLOCK + alert Yusif
   "⚠️ Image quality issue: [X] of [Y] scenes failed visual check"
```

---

## Phase 7: QA — Final Video Check ✅ GATE

### Purpose
After FFmpeg composes the final video — verify it's correct before publishing.

### Components

#### 7.1 Technical Quality Check (automated)
- **Audio-Video Sync:**
  - Narration aligns with correct scenes
  - No audio drift over time
  - Music doesn't overpower narration
- **Duration Check:**
  - Total video length matches expected (8-12 min)
  - No scenes too short (<2s) or too long (>20s)
  - No black frames or frozen frames
- **Resolution & Bitrate:**
  - Minimum 1080p
  - Bitrate adequate (no compression artifacts)
  - Audio quality (no clipping, no silence gaps)
- **File Integrity:**
  - MP4 is valid and playable
  - No corruption
  - File size reasonable (expect 200MB-1GB for 10min 1080p)

#### 7.2 Content Coherence Check
- **LLM reviews** (using extracted frames + audio transcript):
  - Does the narration match what's shown on screen?
  - Are text overlays readable and correctly timed?
  - Is the intro/outro present and correct?
  - Does it flow well as a complete video?

#### 7.3 Final Compliance Re-check
- One last check on the composed video:
  - Any accidental inappropriate visual content?
  - Audio: any artifacts that sound like copyrighted content?
  - Overall: would this pass YouTube's automated review?

### Gate Logic
```
IF all technical checks pass + content coherence > 7/10 → proceed to publish
IF minor issues (timing off, audio level) → auto-fix with FFmpeg and re-check
IF major issues → BLOCK + alert Yusif
   "⚠️ Video QA failed: [reason]. Review needed."
```

---

## Phase 8: Publishing Engine

### Purpose
Optimize and publish videos to YouTube with maximum discoverability.

### Components

#### 8.1 Thumbnail Generator
- **Model:** FLUX (same as 5.1)
- **Strategy:**
  - Generate 3 thumbnail options per video
  - Style: Bold, high contrast, Arabic text overlay
  - Include: Dramatic image + large Arabic title text + emotional element
  - Resolution: 1280x720
  - Use channel-specific templates/style
  - **Uses best-performing title from Phase 2**
- **Text overlay:** Pillow/PIL for Arabic text rendering
- **Selection:** LLM scores thumbnails based on click-appeal
- **Learn from data:** After Phase 8.4 tracks performance, feed back which thumbnail styles get highest CTR

#### 8.2 SEO Metadata Assembly
- **Uses all data from Phase 2:**
  - Title: best-ranked title from Phase 2
  - Description: keyword-rich, timestamped (timestamps auto-generated from scene data)
  - Tags: 20-30 from Phase 2 analysis
  - Hashtags: 3-5 trending
- **Adds:**
  - Auto-generated timestamps from scene durations
  - Sources section (from research phase)
  - Standard channel links and branding text

#### 8.3 YouTube Publisher
- **YouTube Data API v3:**
  - Upload video to correct channel
  - Set title, description, tags, thumbnail
  - Set category, language (Arabic), default audio language
  - Set visibility: public (or scheduled for optimal time)
  - Add to playlist (auto-create playlists by topic)
  - Add end screen + cards (link to related videos)
  - **AI Disclosure label** (required by YouTube policy)
  - AI disclosure text in description
- **Scheduling:**
  - Optimal posting times per channel (from Phase 2 research)
  - Queue system if multiple videos ready

#### 8.4 Performance Tracker
- After publishing, track (24h, 48h, 7d, 30d):
  - Views, CTR, average watch time, retention curve
  - Compare with previous videos on same channel
  - **Feed data back to improve:**
    - Phase 2: Which keywords/titles perform best
    - Phase 3: Which script structures retain viewers
    - Phase 8.1: Which thumbnail styles get highest CTR
- Weekly analytics report to Yusif via Telegram

---

## Channel Configuration

### Structure
Each channel is defined in a config file:

```yaml
channels:
  - id: "documentary_ar"
    name: "وثائقيات"
    youtube_channel_id: "UC..."
    category: "documentary"
    topics: ["history", "science", "culture", "mysteries"]
    style:
      visual: "cinematic_photorealistic"
      color_palette: ["#1a1a2e", "#16213e", "#0f3460", "#e94560"]
      font: "Cairo"
      intro_template: "templates/documentary_intro.mp4"
      outro_template: "templates/documentary_outro.mp4"
    voice:
      profile: "voices/arabic_male_deep.wav"
      speed: 1.0
      tone: "authoritative, calm, engaging"
    music:
      default_mood: "dramatic_cinematic"
      style_prompt: "orchestral documentary music, arabic instruments"
    content:
      tone: "educational, engaging, slightly dramatic"
      target_length_minutes: 8-12
      language: "MSA"
      script_guidelines: |
        - Use dramatic hooks
        - Include surprising facts
        - End with thought-provoking conclusion
    schedule:
      videos_per_day: 1
      posting_time: "18:00"  # UTC+3
      timezone: "Asia/Baghdad"

  - id: "sports_ar"
    name: "رياضة"
    category: "sports"
    topics: ["football", "olympics", "athletes", "records"]
    style:
      visual: "dynamic_energetic"
    # ... etc

  - id: "entertainment_ar"
    name: "ترفيه"
    category: "entertainment"
    # ... etc

  - id: "politics_ar"
    name: "سياسة"
    category: "politics"
    # ... etc

  - id: "science_ar"
    name: "علوم"
    category: "science"
    # ... etc
```

---

## Technical Requirements

### Hardware
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | 1x RTX 3090 (24GB) | 2x RTX 3090 |
| CPU | i7/i9 (8+ cores) | i9-14900K ✅ |
| RAM | 64GB | 128GB ✅ |
| Storage | 1TB SSD | 2TB+ NVMe |
| PSU | 1000W | 1200W+ |

### Software Stack
| Component | Technology |
|-----------|-----------|
| **Orchestrator** | Python 3.11+ (main pipeline controller) |
| **LLM (Script + QA)** | Ollama + Llama 3.1 70B (Q4) OR API (Claude/GPT) |
| **Vision LLM (Phase 6)** | LLaVA / Llama 3.2 Vision (local) or API |
| **Image Gen** | ComfyUI + FLUX.1-dev |
| **Video Gen** | ComfyUI + LTX-2 |
| **TTS** | Fish Speech / OpenAudio S1 |
| **Music** | MusicGen (via audiocraft library) |
| **SFX** | AudioGen (via audiocraft library) |
| **Video Compose** | FFmpeg + MoviePy |
| **Text on Video** | Pillow (PIL) for Arabic text |
| **YouTube** | YouTube Data API v3 (google-api-python-client) |
| **YouTube SEO** | YouTube Search Suggest + yt-dlp |
| **Scheduling** | APScheduler or system cron |
| **Database** | SQLite (job queue, video metadata, analytics, SEO data) |
| **Notification** | Telegram Bot API |
| **Web Dashboard** | Optional: FastAPI + React (monitor production) |

### AI Models to Download
| Model | Size | Purpose |
|-------|------|---------|
| Llama 3.1 70B Q4_K_M | ~40GB | Script writing + review + SEO + compliance |
| Llama 3.2 Vision 11B | ~7GB | Visual QA (Phase 6) |
| FLUX.1-dev | ~12GB | Image generation |
| LTX-2 | ~8GB | Video generation |
| Fish Speech / OpenAudio S1 | ~2GB | Arabic TTS |
| MusicGen-large | ~3.3GB | Music generation |
| AudioGen-medium | ~1.5GB | SFX generation |

### API Keys Needed
| Service | Purpose | Cost |
|---------|---------|------|
| YouTube Data API | Upload + Analytics + Search | Free (quota limits) |
| Google Trends | Topic research | Free |
| Brave Search API | Research | Free tier |
| Telegram Bot | Notifications | Free |
| ElevenLabs (optional backup) | TTS fallback | $22/mo |

---

## Project Structure

```
ai-video-factory/
├── BLUEPRINT.md                # This file
├── config/
│   ├── channels.yaml           # Channel definitions
│   ├── youtube_policies.md     # YouTube ToS summary for compliance agent
│   ├── voices/                 # Voice reference audio files
│   │   ├── arabic_male_deep.wav
│   │   ├── arabic_male_news.wav
│   │   └── arabic_female_calm.wav
│   └── templates/              # Intro/outro video templates
│       ├── documentary_intro.mp4
│       └── documentary_outro.mp4
├── src/
│   ├── main.py                 # Main orchestrator
│   ├── phase1_research/
│   │   ├── youtube_trends.py   # YouTube trending analysis
│   │   ├── web_trends.py       # Google Trends + news + social
│   │   ├── topic_ranker.py     # Score and rank topics
│   │   └── topic_presenter.py  # Present to user via Telegram
│   ├── phase2_seo/
│   │   ├── keyword_research.py # YouTube keyword analysis
│   │   ├── competitor_analysis.py # Analyze top videos for topic
│   │   ├── title_generator.py  # Generate optimized titles
│   │   └── tag_planner.py      # Generate tags + description template
│   ├── phase3_script/
│   │   ├── researcher.py       # Deep research on topic
│   │   ├── writer.py           # Script writing (uses SEO keywords)
│   │   ├── reviewer.py         # Script review + fact-check
│   │   └── splitter.py         # Split to scenes JSON
│   ├── phase4_compliance/
│   │   ├── youtube_policy.py   # YouTube ToS compliance check
│   │   ├── copyright_check.py  # Plagiarism + copyright check
│   │   ├── fact_checker.py     # Fact verification with sources
│   │   └── arabic_quality.py   # Arabic grammar + MSA check
│   ├── phase5_production/
│   │   ├── image_gen.py        # FLUX image generation
│   │   ├── video_gen.py        # LTX-2 video generation
│   │   ├── voice_gen.py        # Fish Speech TTS
│   │   ├── music_gen.py        # MusicGen background music
│   │   ├── sfx_gen.py          # AudioGen sound effects
│   │   └── composer.py         # FFmpeg video assembly
│   ├── phase6_visual_qa/
│   │   ├── image_checker.py    # Vision LLM checks images vs script
│   │   ├── style_checker.py    # Style consistency across scenes
│   │   └── sequence_checker.py # Visual story flow check
│   ├── phase7_video_qa/
│   │   ├── technical_check.py  # A/V sync, duration, resolution, bitrate
│   │   ├── content_check.py    # Narration-visual alignment
│   │   └── final_compliance.py # Last compliance sweep
│   ├── phase8_publish/
│   │   ├── thumbnail.py        # Thumbnail generation
│   │   ├── seo_assembler.py    # Assemble final SEO metadata
│   │   ├── uploader.py         # YouTube upload
│   │   └── tracker.py          # Performance tracking + feedback loop
│   └── utils/
│       ├── gpu_scheduler.py    # GPU task queue (sequential)
│       ├── database.py         # SQLite operations
│       ├── telegram_bot.py     # Notifications
│       ├── logger.py           # Logging
│       └── retry.py            # Retry logic for failed steps
├── data/
│   ├── jobs.db                 # SQLite database
│   ├── seo_cache/              # Cached keyword research
│   ├── sfx_library/            # Pre-downloaded SFX
│   ├── fonts/                  # Arabic fonts (Cairo, Tajawal, etc.)
│   └── competitor_data/        # Tracked competitor channel data
├── output/
│   ├── research/               # Research documents
│   ├── scripts/                # Written scripts
│   ├── scenes/                 # Scene JSON files
│   ├── images/                 # Generated images
│   ├── videos/                 # Generated video clips
│   ├── audio/                  # Voice + music + SFX
│   ├── thumbnails/             # Generated thumbnails
│   └── final/                  # Final composed videos
├── requirements.txt
└── docker-compose.yml          # Optional: containerized setup
```

---

## Workflow — End to End (Daily Cycle)

```
06:00  ═══ PHASE 1: RESEARCH ═══
       Trend Scanner runs → YouTube + web + news
       Topic Ranker scores and ranks
       Sends top 10-20 topics to Yusif via Telegram

       [☝️ Yusif picks topic + channel] (manual, <1 min)

06:10  ═══ PHASE 2: KEYWORD & SEO ═══
       YouTube keyword research for selected topic
       Competitor analysis (top 20 videos)
       Generate 10 title options → rank by SEO score
       Plan tags + description template
       Output: SEO package (title, tags, keywords, angle)

06:25  ═══ PHASE 3: SCRIPT ═══
       Research Agent → gathers info from 5-10 sources
       Script Writer → full Arabic script (using SEO keywords)
       Script Reviewer → quality + fact check (up to 3 iterations)
       Scene Splitter → scene JSON with visual prompts

06:50  ═══ PHASE 4: SCRIPT COMPLIANCE QA ═══
       YouTube policy check
       Copyright check
       Fact verification
       Arabic quality check
       ✅ PASS → continue
       ❌ FAIL → fix or alert Yusif

07:00  ═══ PHASE 5: PRODUCTION (Part 1 — Images) ═══
       FLUX generates images for all scenes (~30 min)

07:30  ═══ PHASE 6: VISUAL QA ═══
       Vision LLM checks all images vs script
       Style consistency check
       Sequence flow check
       ✅ PASS → continue
       ❌ FAIL → regenerate failed images + re-check

07:40  ═══ PHASE 5: PRODUCTION (Part 2 — Video + Audio) ═══
       LTX-2 video clips from approved images (~90 min)
       Fish Speech narration (~10 min)
       MusicGen background music (~10 min)
       AudioGen SFX (~5 min)
       FFmpeg compose final video (~10 min)

09:45  ═══ PHASE 7: FINAL VIDEO QA ═══
       Technical check (A/V sync, duration, resolution)
       Content coherence check
       Final compliance sweep
       ✅ PASS → continue
       ❌ FAIL → auto-fix or alert Yusif

09:55  ═══ PHASE 8: PUBLISH ═══
       Generate 3 thumbnails → pick best
       Assemble SEO metadata (title + desc + tags)
       Upload to YouTube (scheduled for optimal time)
       Send confirmation to Yusif via Telegram
       "✅ [channel] — [title] — scheduled for 18:00"

18:00  Video goes live

NEXT DAY:
       Performance Tracker → analytics report to Yusif
       Feed data back to improve Phases 2, 3, 8
```

---

## Scaling Plan

| Phase | Timeline | Channels | Videos/Day | Hardware |
|-------|----------|----------|-----------|----------|
| MVP | Month 1-2 | 1 | 1 | 1x RTX 3090 |
| Growth | Month 3-4 | 2-3 | 2-3 | 1x RTX 3090 (optimized) |
| Scale | Month 5-6 | 3-5 | 3-5 | 2x RTX 3090 |
| Full | Month 7+ | 5-10 | 5-10 | Cloud GPU overflow |

---

## Quality Targets

| Metric | Target | How |
|--------|--------|-----|
| Video resolution | 1080p minimum | FLUX + LTX-2 output settings |
| Audio quality | Studio-grade narration | Fish Speech + audio normalization |
| Script accuracy | 95%+ factual | Multi-source research + fact-checker |
| Watch retention | >50% average | Strong hooks + pacing + scene variety |
| YouTube CTR | >5% | SEO-optimized titles + A/B thumbnails |
| Publishing consistency | Daily per channel | Automated scheduling |
| Compliance | 0 strikes | 3 QA gates (Phase 4 + 6 + 7) |
| Image-script match | >90% scenes | Phase 6 visual QA |
| A/V sync accuracy | <100ms drift | Phase 7 technical check |

---

## Implementation Order

### Sprint 1: Foundation (Week 1-2)
- [ ] Set up Python project structure
- [ ] Install ComfyUI + FLUX + LTX-2
- [ ] Install Fish Speech + MusicGen + AudioCraft
- [ ] Install Ollama + Llama 3.1 70B + Llama 3.2 Vision
- [ ] Build basic scene JSON schema
- [ ] Build FFmpeg composer (core assembly)
- [ ] Test: manual script → images → video → voice → composed video

### Sprint 2: Script + SEO Engine (Week 3)
- [ ] Build YouTube keyword research (Phase 2)
- [ ] Build competitor analysis
- [ ] Build title generator
- [ ] Build research agent (Phase 3)
- [ ] Build script writer (uses SEO keywords)
- [ ] Build script reviewer
- [ ] Build scene splitter
- [ ] Test: topic → SEO analysis → script → scenes

### Sprint 3: Production Pipeline (Week 4-5)
- [ ] Build FLUX image generation pipeline
- [ ] Build LTX-2 video generation pipeline
- [ ] Build Fish Speech voice pipeline
- [ ] Build MusicGen music pipeline
- [ ] Build AudioGen SFX pipeline
- [ ] Build GPU scheduler (sequential queue)
- [ ] Test: scenes JSON → full video automatically

### Sprint 4: QA Gates (Week 6)
- [ ] Build Phase 4: Script compliance checker
- [ ] Build Phase 6: Visual QA with vision LLM
- [ ] Build Phase 7: Final video technical check
- [ ] Build gate logic (pass/fail/retry/block)
- [ ] Build Telegram alerts for blocked content
- [ ] Test: intentionally bad content → verify gates catch it

### Sprint 5: Publishing (Week 7)
- [ ] Build thumbnail generator
- [ ] Build SEO metadata assembler
- [ ] Build YouTube uploader
- [ ] Build performance tracker
- [ ] Build Telegram notification bot
- [ ] Test: full pipeline topic → published video

### Sprint 6: Multi-Channel + Polish (Week 8)
- [ ] Channel configuration system
- [ ] Per-channel voice profiles + visual styles
- [ ] Daily scheduling system
- [ ] Error handling + retry logic everywhere
- [ ] Logging + monitoring dashboard
- [ ] Test: 2 channels, 1 video each per day

---

## Cost Estimation

### One-Time
| Item | Cost |
|------|------|
| RTX 3090 (used) | $700-900 |
| PSU upgrade (if needed) | $100-150 |
| Storage (2TB NVMe) | $100-150 |
| **Total** | **$900-$1,200** |

### Monthly Operating
| Item | Cost |
|------|------|
| Electricity (~300W avg, 24/7) | ~$20-40 |
| API calls (backup LLM, if used) | $0-50 |
| ElevenLabs (optional) | $0-22 |
| Domain + hosting (optional dashboard) | $0-10 |
| **Total** | **$20-$120/month** |

### Revenue Target
| Timeline | Monthly Revenue |
|----------|----------------|
| Month 6 | $100-500 |
| Month 12 | $1,000-5,000 |
| Month 18 | $5,000-15,000 |
| Month 24 | $10,000-30,000+ |

---

## Error Handling & Recovery

### Per-Phase Failure Handling
| Phase | Failure | Action |
|-------|---------|--------|
| 1 - Research | API down | Retry 3x, then use cached trends |
| 2 - SEO | YouTube API quota | Use cached data, retry next hour |
| 3 - Script | LLM produces bad output | Retry with different temperature (max 3x) |
| 4 - Compliance | Script blocked | Alert Yusif, pause job |
| 5 - Images | FLUX fails/OOM | Restart GPU, retry. Fallback: lower resolution |
| 5 - Video | LTX-2 fails | Fallback: Ken Burns on FLUX image |
| 5 - Voice | Fish Speech glitch | Re-generate. Fallback: ElevenLabs API |
| 5 - Music | MusicGen fails | Fallback: pre-made royalty-free tracks |
| 5 - Compose | FFmpeg error | Log error, retry with adjusted parameters |
| 6 - Visual QA | Images don't match | Regenerate failed images (max 2 rounds) |
| 7 - Video QA | A/V sync off | Re-compose with adjusted timing |
| 7 - Video QA | Major failure | Alert Yusif, pause job |
| 8 - Upload | YouTube API error | Retry 3x with backoff |
| ANY | GPU crash | Auto-restart, resume from last checkpoint |

### Checkpoint System
- Each phase saves its output to disk
- If pipeline crashes, restart from last completed phase (not from scratch)
- Job status tracked in SQLite: `pending → phase1 → phase2 → ... → published`

---

## Notes

- Start with ONE channel, perfect the quality, then scale
- The human touch: Yusif selects topics — keeps content intentional, not random
- Arabic TTS is improving fast — swap models as better ones release
- Video generation is evolving rapidly — LTX-2 today, better models in 6 months
- Always keep compliance gates strict — one YouTube strike can kill a channel
- Back up all voice profiles, style configs, and channel branding assets
- Monitor YouTube algorithm changes and adapt SEO strategy accordingly
- Phase 2 (SEO) is KEY — the best video with bad SEO gets 0 views
- Phase 6 (Visual QA) saves GPU time — catching bad images before video gen is 10x cheaper
- Phase 7 (Video QA) protects quality — never publish a broken video
