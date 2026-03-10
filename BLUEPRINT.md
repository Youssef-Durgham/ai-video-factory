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
- **Uses Qwen 2.5 72B (local)** — strongest open-source Arabic model
- Writes full Arabic script in documentary/narration style (reference: channels like الفاتورة المرعبة، وثائقيات سياسية/تاريخية)
- Style: dramatic hooks, suspenseful pacing, rhetorical questions, cinematic narration
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
    "text_overlay": {"text": "١٩٦٩", "style": "fact_date", "position": "bottom_right"},
    "expected_visual_elements": ["astronaut", "moon_surface", "earth_in_background"]
  }
  ```
- `expected_visual_elements` — used by Phase 6 (Visual QA) to verify images
- **Output:** JSON array of 40-80 scenes

### Tech Stack
- LLM: Qwen 2.5 72B (local via Ollama) — all script tasks
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
  - **⚠️ Images must NOT contain any text/writing** — all text is added as overlay in post-production (Phase 5.6)
  - Resolution: 1920x1080 (16:9)
  - Style consistency: Use consistent style LoRA per channel
  - Character consistency: Use IP-Adapter for recurring characters/figures
  - Negative prompt always includes: "text, writing, letters, words, watermark, subtitle"
- **Auto-select:** LLM picks best image based on scene context
- **Time:** ~15-30 sec/image on RTX 3090
- **Output:** Best image per scene saved as PNG
- ⚡ **IMPORTANT:** Images go to Phase 6 (Visual QA) before video generation

#### 5.2 Video Generator (LTX-2.3)
- **Model:** LTX-2.3 (local, via ComfyUI) — latest version, superior motion quality & consistency
- **VRAM:** ~12GB
- **ONLY runs after Phase 6 approves images**
- **Per scene:**
  - Input: Approved image from 5.1 + visual_prompt + camera_movement
  - Generate 5-10 second video clip
  - Image-to-Video mode (starts from the FLUX image, adds realistic motion)
  - Apply camera movement (zoom, pan, parallax, cinematic drift)
- **Fallback:** If LTX-2.3 quality is poor for a scene → use FLUX image with Ken Burns effect (FFmpeg)
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

#### 5.4.1 Content ID Protection System 🛡️⚠️
- **Problem:** YouTube Content ID يكتشف تشابه موسيقي حتى مع مقاطع AI-generated. خوارزمية Shorts أشد حساسية من الفيديوهات العادية. Claim واحد = demonetization أو حذف.
- **Protection layers:**

  **Layer 1: Generation Safeguards (قبل التوليد)**
  - Negative prompts إجبارية:
    ```
    ALWAYS INCLUDE in MusicGen prompt:
    "original composition, no covers, no samples, no existing melodies,
     no copyrighted material, unique musical arrangement"
    
    NEVER INCLUDE:
    - اسم أي فنان أو فرقة
    - اسم أي أغنية معروفة
    - "style of [artist]" أو "like [song]"
    - أي مرجع لموسيقى محمية بحقوق نشر
    ```
  - MusicGen temperature: 0.8-1.0 (أعلى = أكثر originality, أقل تشابه)
  - Seed عشوائي لكل generation (لا يتكرر pattern)

  **Layer 2: Audio Fingerprint Check (بعد التوليد — قبل الاستخدام)**
  - **أداة:** `audfprint` (open-source audio fingerprinting) أو Chromaprint/AcoustID
  - **Process:**
    1. توليد الموسيقى → حفظ WAV مؤقت
    2. استخراج audio fingerprint
    3. مقارنة مع قاعدة بيانات محلية:
       - أرشيف كل الموسيقى المولّدة سابقاً (لا نكرر أنفسنا)
       - عينات من أشهر 10,000 أغنية عربية (top Arabic songs fingerprints)
       - عينات من أشهر الموسيقى الغربية المستخدمة بالـ documentaries
    4. **Similarity score:**
       ```
       Score < 0.15  → ✅ SAFE — مختلف تماماً
       Score 0.15-0.30 → ⚠️ WARNING — يعيد التوليد بـ seed مختلف
       Score > 0.30  → ❌ REJECT — يعيد التوليد بـ prompt مختلف كلياً
       ```
  - **خاص بالـ Shorts:** threshold أشد (< 0.10) لأن خوارزمية Shorts أكثر حساسية

  **Layer 3: Spectral Analysis (طبقة إضافية)**
  - تحليل الـ spectrogram للمقطع المولّد
  - كشف أي melodic patterns متكررة تشبه أغاني مشهورة
  - يركّز على:
    - Melody contour (شكل اللحن — أخطر عنصر بالـ Content ID)
    - Chord progressions (بعض التسلسلات مشهورة جداً)
    - Rhythmic patterns (إيقاعات مميزة لأغاني معينة)
  - **أداة:** `librosa` (Python) لاستخراج:
    ```python
    # استخراج الـ melody contour
    pitches, magnitudes = librosa.piptrack(y=audio, sr=sr)
    # استخراج الـ chroma features (chord detection)
    chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
    # مقارنة مع قاعدة البيانات
    similarity = compare_contours(generated_contour, known_contours_db)
    ```

  **Layer 4: YouTube Pre-check (اختياري — طبقة أخيرة)**
  - قبل النشر العام: رفع الفيديو كـ **unlisted** على YouTube
  - انتظار 10-30 دقيقة → YouTube يفحص Content ID
  - التحقق عبر YouTube API:
    ```python
    # Check for copyright claims on uploaded video
    claims = youtube_api.videos().list(
        part="contentDetails,status",
        id=video_id
    ).execute()
    
    if claims['items'][0]['contentDetails'].get('contentRating'):
        # Has claim → don't publish
        alert_yusif("⚠️ Content ID claim detected on music")
        # Re-generate music → re-compose → re-upload
    else:
        # Clean → change to public/scheduled
        youtube_api.videos().update(
            part="status",
            body={"id": video_id, "status": {"privacyStatus": "scheduled"}}
        )
    ```
  - **هذي أقوى طبقة** — تستخدم نفس نظام YouTube الفعلي

  **Layer 5: Music Variation & Manipulation (تعديلات ما بعد التوليد)**
  - حتى بعد التوليد، نعدّل المقطع ليبتعد أكثر عن أي تشابه:
    ```
    - Pitch shift: ±1-2 semitones (تغيير طبقة الصوت بشكل طفيف)
    - Time stretch: ±5-10% (تغيير السرعة بدون تغيير الـ pitch)
    - Reverb/Echo: إضافة صدى خفيف (يغيّر الـ fingerprint)
    - EQ adjustment: تعديل الترددات (يبعد عن الـ original fingerprint)
    - Layer mixing: دمج 2 مقطع مولّد مع بعض (creates unique hybrid)
    ```
  - هذي التعديلات تصعّب على Content ID الكشف حتى لو كان تشابه أصلي

- **Database: `data/audio_fingerprints.db`**
  ```sql
  CREATE TABLE fingerprints (
    id INTEGER PRIMARY KEY,
    source TEXT,          -- 'generated', 'arabic_top', 'western_top', 'documentary_common'
    title TEXT,
    artist TEXT,
    fingerprint BLOB,
    melody_contour BLOB,
    chroma_features BLOB,
    created_at TIMESTAMP
  );
  
  CREATE TABLE content_id_results (
    video_id TEXT,
    music_track_id TEXT,
    youtube_claim BOOLEAN,
    claim_details TEXT,
    checked_at TIMESTAMP
  );
  ```

- **Initialization (one-time setup):**
  1. تنزيل fingerprints لأشهر 10K أغنية عربية (via AcoustID database)
  2. تنزيل fingerprints لأشهر documentary music tracks
  3. بناء الـ local comparison database
  4. تقدير: ~2GB database, ~1 hour setup

#### 5.5 SFX Generator (AudioCraft)
- **Model:** AudioGen (part of AudioCraft) — local
- **VRAM:** ~4GB (shared with MusicGen)
- **Per scene:** Generate sound effects from `sfx` tags
  - Example: `"crowd cheering"` → generates crowd audio
  - Example: `"explosion in distance"` → generates explosion SFX
- **Fallback library:** Pre-downloaded SFX from Freesound.org for common sounds
- **Content ID note:** SFX أقل خطورة من الموسيقى، لكن نفس الـ fingerprint check يطبّق عليها
- **Output:** WAV SFX files per scene

#### 5.6 Video Composer (FFmpeg + Python)
- **No GPU needed** — CPU-based
- **Steps:**
  1. **Sequence video clips** in scene order
  2. **Overlay narration audio** on video timeline (volume: 100%)
  3. **Mix background music** (volume: 20-30%, auto-duck under narration)
  4. **Add SFX** at appropriate timestamps (volume: 40-60%)
  5. **Apply transitions** between scenes (crossfade, cut, dissolve)
  6. **Add Arabic text overlays (post-production — NOT in AI images):**
     - All visible text is rendered via FFmpeg/Pillow OVER the video
     - Title card at start
     - Section headers
     - Key facts/dates/statistics on screen
     - Highlighted quotes or key phrases
     - Subscribe reminder at end
     - Style: bold Arabic font (Cairo/Tajawal), with background blur/darken strip for readability
     - Text animations: fade-in, slide-in, typewriter effect
  7. **Add intro/outro** templates (per channel branding)
  8. **Render final video:**
     - Resolution: 1920x1080 or 4K
     - Codec: H.264/H.265
     - Audio: AAC 320kbps
     - Format: MP4
- **Output:** Final video MP4 → goes to Phase 7

### GPU Memory Management System (CRITICAL) 🧠

**Problem:** Single RTX 3090 (24GB VRAM). Models cannot coexist in memory:
| Model | VRAM Usage | RAM Offload |
|-------|-----------|-------------|
| Qwen 72B Q4 | ~12-16GB | + ~26GB system RAM |
| FLUX.1-dev | ~12GB | — |
| LTX-2.3 | ~12GB | — |
| Llama 3.2 Vision | ~7GB | — |
| Fish Speech | ~4GB | — |
| MusicGen | ~4GB | — |
| AudioGen | ~4GB | — |
| SadTalker | ~4GB | — |
| Real-ESRGAN | CPU only | ~2GB RAM |

**Solution: GPU Slot System — one model at a time, full VRAM flush between each.**

#### Memory Manager (`src/utils/gpu_manager.py`)
```python
class GPUMemoryManager:
    """
    Ensures only ONE model occupies VRAM at any time.
    Full cache clear between model swaps.
    """
    
    def load_model(self, model_name):
        # 1. Unload current model completely
        self.unload_current()
        # 2. Force VRAM flush
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
        gc.collect()
        # 3. Verify VRAM is actually free
        free_vram = torch.cuda.mem_get_info()[0] / 1e9
        assert free_vram > 20, f"VRAM not freed: {free_vram}GB free"
        # 4. Load new model
        self.current = self._load(model_name)
        
    def unload_current(self):
        if self.current:
            del self.current
            self.current = None
            # Kill Ollama server if LLM was loaded
            if self.current_type == "llm":
                subprocess.run(["ollama", "stop", self.current_name])
            # Clear ComfyUI pipeline if image/video model
            if self.current_type == "comfyui":
                comfyui_api.free_memory()
            torch.cuda.empty_cache()
            gc.collect()
            # Wait for VRAM to fully release
            time.sleep(2)
            self._verify_vram_free()
```

#### Model Loading Strategy
```
Strategy 1: Ollama for LLMs (Qwen, Llama Vision)
  → ollama run qwen2.5:72b → processes tasks → ollama stop qwen2.5:72b
  → VRAM freed → next model loads

Strategy 2: ComfyUI for Image/Video (FLUX, LTX-2.3)
  → ComfyUI API: load workflow → generate → unload model → free memory
  → ComfyUI supports model unloading via API

Strategy 3: Direct Python for Audio (Fish Speech, MusicGen, AudioGen)
  → Load model → process all scenes → del model → torch.cuda.empty_cache()

Strategy 4: CPU-only (Real-ESRGAN, FFmpeg)
  → No VRAM needed → can run parallel with GPU tasks
```

#### Swap Optimization: Batch by Model
```
❌ BAD: Load/unload per scene (swap 80 times)
   Scene 1: load FLUX → generate → unload → load LTX → generate → unload → ...
   Scene 2: load FLUX → generate → unload → load LTX → generate → unload → ...

✅ GOOD: Batch all work per model (swap 7 times total)
   FLUX:        load once → generate ALL 60 images → unload     (~30 min)
   Vision LLM:  load once → check ALL 60 images → unload        (~5 min)
   FLUX:        load again → regenerate failed images → unload   (~5 min, if needed)
   LTX-2.3:    load once → generate ALL 60 videos → unload      (~90 min)
   Fish Speech: load once → narrate ALL 60 scenes → unload      (~10 min)
   MusicGen:    load once → generate ALL tracks → unload         (~10 min)
   AudioGen:    load once → generate ALL SFX → unload            (~5 min)
   FFmpeg:      CPU only → compose final video                   (~10 min)
   Qwen 72B:    load once → all QA checks → unload              (~10 min)
```

#### VRAM Monitoring & Safety
```python
class VRAMMonitor:
    """Runs in background thread, monitors VRAM health."""
    
    THRESHOLDS = {
        "warning": 0.90,   # 90% VRAM used → log warning
        "critical": 0.95,  # 95% VRAM used → force cleanup
        "oom_prevention": 0.98  # 98% → kill current process
    }
    
    def monitor_loop(self):
        while True:
            used, total = torch.cuda.mem_get_info()
            usage_pct = 1 - (used / total)
            
            if usage_pct > self.THRESHOLDS["oom_prevention"]:
                self.force_kill_and_flush()  # prevent OOM crash
                self.alert_telegram("⚠️ VRAM OOM prevented — flushed GPU")
                
            elif usage_pct > self.THRESHOLDS["critical"]:
                torch.cuda.empty_cache()
                gc.collect()
                
            time.sleep(5)  # check every 5 seconds
```

#### Ollama Configuration for VRAM Control
```yaml
# ~/.ollama/config.yaml (or environment variables)
OLLAMA_NUM_PARALLEL: 1          # Only 1 request at a time
OLLAMA_MAX_LOADED_MODELS: 1     # Only 1 model in VRAM
OLLAMA_KEEP_ALIVE: "0"          # Unload model immediately after use (no idle caching)
OLLAMA_GPU_OVERHEAD: "500MB"    # Reserve 500MB for system
```
- `KEEP_ALIVE=0` is critical — default Ollama keeps model in VRAM for 5 min
- Without this, Qwen stays in VRAM and blocks FLUX from loading

#### ComfyUI Memory Configuration
```python
# ComfyUI API: force model unload after generation
def generate_and_free(workflow, images_needed):
    results = comfyui_api.queue_prompt(workflow)
    # Wait for completion
    comfyui_api.wait_for_prompt(results['prompt_id'])
    # Force unload ALL models from VRAM
    comfyui_api.free_memory(unload_models=True)
    # Verify
    time.sleep(2)
    assert get_free_vram() > 20  # GB
    return results
```

#### Swap Time Budget
| Swap | Time | Notes |
|------|------|-------|
| Unload any model | ~2-5 sec | del + cache clear + gc |
| Load Qwen 72B Q4 | ~30-45 sec | 42GB from disk → GPU+RAM |
| Load FLUX | ~10-15 sec | 12GB from disk → VRAM |
| Load LTX-2.3 | ~10-15 sec | 8GB from disk → VRAM |
| Load Fish Speech | ~5 sec | 2GB → VRAM |
| Load MusicGen | ~5 sec | 3.3GB → VRAM |
| **Total swap overhead** | **~3-5 min** | **7 swaps per video** |

#### Error Recovery
```
IF VRAM OOM during generation:
  1. Kill current process
  2. torch.cuda.empty_cache() + gc.collect()
  3. Verify VRAM free
  4. Retry current batch
  5. If OOM again → reduce batch size (e.g., 1 image at a time instead of 3)
  6. If still failing → alert Yusif: "GPU memory issue"

IF model fails to load:
  1. Verify VRAM is actually free (previous model leaked?)
  2. Force: nvidia-smi --gpu-reset (last resort)
  3. Retry load
  4. If still failing → skip to next phase, alert Yusif
```

### Production Pipeline Order (with GPU Swaps)
```
Single RTX 3090 — one model at a time, full VRAM flush between each:

Phase 1-4: SCRIPT & QA (Qwen 72B)
  🧠 Load Qwen 72B ──────────────────────── (~45 sec)
  ├── Phase 1: Research analysis            (~5 min)
  ├── Phase 2: SEO + titles + tags          (~5 min)
  ├── Phase 3: Script + review + split      (~15 min)
  └── Phase 4: Compliance QA                (~5 min)
  🗑️ Unload Qwen ─────────────────────────── (~3 sec)
  ⏱️ Subtotal: ~30 min

Phase 5a: IMAGES (FLUX)
  🎨 Load FLUX ────────────────────────────── (~15 sec)
  └── Generate ALL scene images (60×)       (~30 min)
  🗑️ Unload FLUX ──────────────────────────── (~3 sec)

Phase 6: VISUAL QA (Llama Vision)
  👁️ Load Llama 3.2 Vision ────────────────── (~10 sec)
  └── Check ALL images vs script            (~5 min)
  🗑️ Unload Vision ─────────────────────────── (~3 sec)

  [If images need regeneration → reload FLUX → fix → unload]

Phase 5b: VIDEO (LTX-2.3)
  🎥 Load LTX-2.3 ─────────────────────────── (~15 sec)
  └── Generate ALL video clips (60×)        (~90 min)
  🗑️ Unload LTX ───────────────────────────── (~3 sec)

Phase 5c: VOICE (Fish Speech)
  🎙️ Load Fish Speech ─────────────────────── (~5 sec)
  └── Narrate ALL scenes (60×)              (~10 min)
  🗑️ Unload Fish Speech ───────────────────── (~3 sec)

Phase 5d: MUSIC (MusicGen)
  🎵 Load MusicGen ─────────────────────────── (~5 sec)
  └── Generate 3-4 music tracks             (~10 min)
  🗑️ Unload MusicGen ──────────────────────── (~3 sec)

Phase 5e: SFX (AudioGen)
  🔊 Load AudioGen ─────────────────────────── (~5 sec)
  └── Generate ALL SFX                      (~5 min)
  🗑️ Unload AudioGen ──────────────────────── (~3 sec)

Phase 5f: COMPOSE (CPU — no GPU needed)
  🎬 FFmpeg + Pillow ───────────────────────── (CPU)
  └── Assemble final video                  (~10 min)

Phase 7: FINAL QA (Qwen 72B)
  🧠 Load Qwen 72B ──────────────────────────  (~45 sec)
  └── Technical + content + compliance check (~10 min)
  🗑️ Unload Qwen ──────────────────────────── (~3 sec)

Phase 8: PUBLISH (FLUX for thumbnails)
  🎨 Load FLUX ────────────────────────────── (~15 sec)
  └── Generate 3 thumbnails                 (~2 min)
  🗑️ Unload FLUX ──────────────────────────── (~3 sec)

  📤 Upload + SRT + metadata (network only) (~5 min)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total GPU swaps: 9 (+ ~5 min overhead)
Total production time: ~3-3.5 hours per video
VRAM peak: never exceeds 16GB (single model)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
- **A/B Testing (Local AI Agent):**
  1. FLUX generates 3 thumbnail variants with different styles (composition, colors, text placement)
  2. Local Qwen 2.5 72B scores & selects the 3 most different variants
  3. Upload all 3 to YouTube "Test & Compare" feature via API
  4. After 7 days: agent pulls CTR analytics per thumbnail
  5. Feeds winning style patterns back into future thumbnail generation prompts
  6. Over time: learns which styles work per channel/topic category

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

#### 8.2.5 Subtitle Generator (SRT) — Local AI Agent
- **Auto-generate SRT** from the original script text (already have exact narration per scene)
- Sync timestamps from scene durations + voice audio timing
- Arabic subtitles (MSA) — clean, accurate, already written
- Optional: English translated subtitles (via local Qwen 2.5 72B translation)
- **All processing local** — no API calls needed (text already exists, just formatting + timing)
- Upload as closed captions to YouTube — **massive SEO boost** (YouTube Arabic auto-captions are poor)
- Embed burn-in subtitles option for social media clips (Shorts, Reels)

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
| **LLM (Script + QA)** | Qwen 2.5 72B (Q4, local via Ollama) — strong Arabic, used for ALL tasks: script writing, review, SEO, compliance, splitting |
| **Vision LLM (Phase 6)** | LLaVA / Llama 3.2 Vision (local) or API |
| **Image Gen** | ComfyUI + FLUX.1-dev |
| **Video Gen** | ComfyUI + LTX-2.3 |
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
| Qwen 2.5 72B Q4_K_M | ~42GB | ALL LLM tasks: script writing, review, SEO, compliance, splitting (strongest local Arabic model) |
| Llama 3.2 Vision 11B | ~7GB | Visual QA (Phase 6) |
| FLUX.1-dev | ~12GB | Image generation |
| LTX-2.3 | ~8GB | Video generation (image-to-video with realistic motion) |
| Fish Speech / OpenAudio S1 | ~2GB | Arabic TTS |
| MusicGen-large | ~3.3GB | Music generation |
| AudioGen-medium | ~1.5GB | SFX generation |
| Real-ESRGAN | ~0.1GB | 4K image/video upscaling (CPU) |
| SadTalker / MuseTalk | ~2GB | AI virtual presenter (lip sync) |

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
│   │   ├── thumbnail.py        # Thumbnail generation + smart text positioning
│   │   ├── seo_assembler.py    # Assemble final SEO metadata
│   │   ├── subtitle_gen.py     # SRT subtitle generator (Arabic + English)
│   │   ├── uploader.py         # YouTube upload + A/B thumbnail test
│   │   ├── tracker.py          # Performance tracking + feedback loop
│   │   └── shorts_gen.py       # YouTube Shorts auto-generator
│   ├── agents/
│   │   ├── content_calendar.py # Weekly/monthly content planning
│   │   ├── watch_optimizer.py  # Retention analysis + script feedback
│   │   ├── community.py        # Comment engagement + moderation
│   │   ├── trending_hijack.py  # Breaking news fast-track detector
│   │   ├── playlist_agent.py   # Series clustering + playlist management
│   │   ├── dubbing_agent.py    # Multi-language dubbing pipeline
│   │   ├── anti_repetition.py  # Pattern tracking + diversity enforcer
│   │   ├── ad_placement.py     # Smart mid-roll ad positioning
│   │   ├── sponsorship.py      # Sponsor integration + tracking
│   │   ├── repurpose.py        # Multi-platform content repurposing
│   │   ├── audience_intel.py   # Audience profiling + comment mining
│   │   ├── cross_promo.py      # Cross-channel promotion network
│   │   ├── template_evolver.py # Script template learning + evolution
│   │   ├── revenue_optimizer.py# Revenue dashboard + optimization
│   │   ├── disaster_recovery.py# Backup + strike protocol
│   │   ├── competitor_alert.py # Real-time competitor monitoring
│   │   ├── emotional_arc.py    # Emotional arc mapping + validation
│   │   ├── voice_emotion.py    # Per-scene TTS emotion control
│   │   ├── sound_design.py     # Cinematic sound layering
│   │   ├── presenter.py        # AI virtual presenter (SadTalker/MuseTalk)
│   │   ├── upscaler.py         # 4K Real-ESRGAN upscaling
│   │   ├── seasonal_bank.py    # Pre-production for predictable events
│   │   ├── narrative_styles.py # Story style selection + enforcement
│   │   ├── micro_test.py       # Hook testing before full publish
│   │   ├── dynamic_length.py   # Optimal video length calculator
│   │   ├── brand_kit.py        # Brand identity management + versioning
│   │   ├── algo_tracker.py     # YouTube algorithm change detection
│   │   └── ab_testing.py       # A/B script testing framework
│   └── utils/
│       ├── gpu_manager.py      # VRAM memory manager (load/unload/flush/monitor)
│       ├── content_id_guard.py # Audio fingerprint + Content ID protection
│       ├── gpu_scheduler.py    # GPU task queue (sequential, batched by model)
│       ├── database.py         # SQLite operations
│       ├── telegram_bot.py     # Notifications
│       ├── logger.py           # Logging
│       └── retry.py            # Retry logic for failed steps
├── data/
│   ├── jobs.db                 # SQLite database
│   ├── audio_fingerprints.db   # Content ID protection fingerprint database
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
       LTX-2.3 video clips from approved images (~90 min)
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

| Phase | Timeline | Channels | Videos/Day | Shorts/Day | Features | Hardware |
|-------|----------|----------|-----------|------------|----------|----------|
| MVP | Month 1-2 | 1 | 1 | 3-5 | Core 8 phases | 1x RTX 3090 |
| Growth | Month 3-4 | 2-3 | 2-3 | 6-15 | + Shorts, Engagement, Watch Optimizer | 1x RTX 3090 |
| Scale | Month 5-6 | 3-5 | 3-5 | 15-25 | + Calendar, Playlists, Revenue, Repurposing | 2x RTX 3090 |
| Premium | Month 6-8 | 3-5 | 3-5 | 15-25 | + Emotional Arc, Voice Emotion, Sound Design, 4K | 2x RTX 3090 |
| Global | Month 9+ | 5-10 | 5-10 | 25-50 | + Multi-Language, AI Presenter, Full Intelligence | 2x 3090 + Cloud |

---

## Quality Targets

| Metric | Target | How |
|--------|--------|-----|
| Video resolution | 1080p minimum | FLUX + LTX-2.3 output settings |
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
- [ ] Install ComfyUI + FLUX + LTX-2.3
- [ ] Install Fish Speech + MusicGen + AudioCraft
- [ ] Install Ollama + Qwen 2.5 72B + Llama 3.2 Vision
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
- [ ] Build LTX-2.3 video generation pipeline
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
- [ ] Build thumbnail generator (with A/B testing support)
- [ ] Build SEO metadata assembler
- [ ] Build SRT subtitle generator (Arabic + optional English)
- [ ] Build YouTube uploader (with subtitle upload)
- [ ] Build performance tracker (with thumbnail A/B analytics)
- [ ] Build Telegram notification bot
- [ ] Test: full pipeline topic → published video

### Sprint 6: Multi-Channel + Polish (Week 8)
- [ ] Channel configuration system
- [ ] Per-channel voice profiles + visual styles (Voice Cloning Library)
- [ ] Daily scheduling system
- [ ] Error handling + retry logic everywhere
- [ ] Logging + monitoring dashboard
- [ ] Test: 2 channels, 1 video each per day

### Sprint 7: Growth Agents (Week 9-10)
- [ ] YouTube Shorts auto-generator (crop + subtitle + upload)
- [ ] Community Engagement Agent (auto-reply + pin + moderation)
- [ ] Watch Time Optimizer (retention analysis + script feedback loop)
- [ ] Smart Thumbnail Text Positioning (Vision LLM validation)
- [ ] Anti-Repetition System (pattern tracking + diversity enforcement)
- [ ] Test: full cycle with Shorts + engagement for 1 week

### Sprint 8: Scale Agents (Week 11-12)
- [ ] Content Calendar Agent (weekly planning + Telegram approval)
- [ ] Playlist Strategy Agent (series detection + auto-grouping)
- [ ] Trending Hijack Mode (fast-track pipeline + alerts)
- [ ] Multi-Language Dubbing pipeline (translate + re-voice + re-overlay)
- [ ] Performance dashboard (all agents + analytics in one view)
- [ ] Test: 3 channels, daily output, full automation

### Sprint 9: Revenue & Intelligence (Week 13-14)
- [ ] Smart Ad Placement (mid-roll optimizer)
- [ ] Content Repurposing Engine (Twitter, Instagram, Blog, Podcast, Telegram)
- [ ] Revenue Dashboard & Optimizer (RPM tracking + auto-adjustments)
- [ ] Audience Intelligence System (demographics + comment mining)
- [ ] Auto-Chapters & Smart Timestamps
- [ ] Disaster Recovery & Channel Protection (backup + strike protocol)
- [ ] Test: full revenue tracking for 2 weeks

### Sprint 10: Network & Growth (Week 15-16)
- [ ] Cross-Channel Promotion Network
- [ ] Competitor Alert System (real-time monitoring)
- [ ] Script Template Evolution (learning from top performers)
- [ ] Sponsorship Detector & Integrator (placeholder slots)
- [ ] Test: all revenue + network features integrated

### Sprint 11: Production Quality (Week 17-18)
- [ ] Emotional Arc Engine (arc mapping + validation + music linking)
- [ ] Voice Emotion Control (per-scene TTS parameters)
- [ ] Cinematic Sound Design (6-layer audio mixing)
- [ ] Narrative Style Library (5 styles + auto-selection)
- [ ] Dynamic Video Length (topic-based + revenue-adjusted)
- [ ] Brand Kit Management System (versioned assets + enforcement)
- [ ] Test: produce 5 videos with full quality features

### Sprint 12: Intelligence & Testing (Week 19-20)
- [ ] 4K AI Upscaling (Real-ESRGAN pipeline)
- [ ] AI Virtual Presenter (SadTalker/MuseTalk integration)
- [ ] Seasonal Content Bank (calendar + pre-production pipeline)
- [ ] Micro-Testing / Hook Testing (Short → test → proceed)
- [ ] YouTube Algorithm Tracker (signal monitoring + auto-adaptation)
- [ ] Automated A/B Script Testing (monthly test framework)
- [ ] Final integration: all 40 features running together
- [ ] Full documentation + monitoring dashboard + alerting

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
| LLM (local Qwen 2.5 72B) | $0 (electricity only) |
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
| 5 - Video | LTX-2.3 fails | Fallback: Ken Burns on FLUX image |
| 5 - Voice | Fish Speech glitch | Re-generate. Fallback: ElevenLabs API |
| 5 - Music | MusicGen fails | Fallback: pre-made royalty-free tracks |
| 5 - Music | Content ID claim detected | Re-generate with different seed/prompt + pitch shift + re-check |
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

## Advanced Features (Post-MVP)

### 9. YouTube Shorts Pipeline 🎬
- **Trigger:** Runs automatically after every long-form video is published
- **Process:**
  1. Qwen 2.5 72B analyzes the script → selects 3-5 strongest moments (hooks, shocking facts, dramatic reveals)
  2. FFmpeg extracts the corresponding video segments
  3. Auto-crop 16:9 → 9:16 (vertical) with smart framing (center on subject)
  4. Add large Arabic subtitles (burned-in, bold, centered — Shorts style)
  5. Add channel branding watermark
  6. Trim to 30-60 seconds max
- **Upload:** Separate upload as YouTube Short with its own title/tags
- **SEO:** Hashtags + trending tags specific to Shorts algorithm
- **Output:** 3-5 Shorts per long-form video — **free extra reach, zero production cost**

### 10. Voice Cloning Library 🎙️
- **Purpose:** Each channel gets its own unique voice = stronger branding
- **Voice profiles:**
  ```yaml
  voices:
    documentary_male:
      file: "voices/arabic_male_deep.wav"
      tone: "authoritative, calm, cinematic"
      channels: ["documentary_ar"]
    news_male:
      file: "voices/arabic_male_news.wav"
      tone: "urgent, clear, professional"
      channels: ["politics_ar"]
    sports_male:
      file: "voices/arabic_male_energetic.wav"
      tone: "excited, fast-paced, passionate"
      channels: ["sports_ar"]
    female_narrator:
      file: "voices/arabic_female_calm.wav"
      tone: "warm, educational, engaging"
      channels: ["science_ar"]
  ```
- **Setup:** Record 1-3 minutes reference audio per voice → Fish Speech clones it
- **Consistency:** Same voice across all videos on a channel builds audience trust

### 11. Content Calendar Agent 📅
- **Purpose:** Reduce daily manual input — Yusif approves once per week instead of daily
- **Process:**
  1. Every Sunday: agent analyzes trends + channel gaps + upcoming events
  2. Generates weekly plan: 7 topics × assigned channels
  3. Considers:
     - Topic diversity (no 3 politics videos in a row)
     - Upcoming events (Ramadan, elections, sports tournaments)
     - Seasonal trends (summer topics, back-to-school)
     - Previous performance data (what topics worked)
  4. Sends plan to Yusif via Telegram as interactive list
  5. Yusif approves / swaps / adds topics
  6. Agent queues the approved plan → auto-executes daily
- **Override:** Yusif can always inject a manual topic mid-week
- **Monthly view:** Optional 30-day content roadmap

### 12. Watch Time Optimizer 📈
- **Purpose:** Learn from audience behavior to improve future scripts
- **Data source:** YouTube Analytics API — retention curve per video
- **Analysis (local Qwen 2.5 72B):**
  - Where do viewers drop off? (timestamp → which scene/section)
  - Which hooks retain >90% viewers past 30 seconds?
  - Which section types lose viewers? (long explanations? slow pacing?)
  - Average watch duration vs. video length
- **Feedback rules (auto-learned):**
  ```
  IF intro > 30 sec → viewers drop 40% → RULE: keep intros < 20 sec
  IF no visual change > 15 sec → viewers drop → RULE: max 10 sec per static scene
  IF rhetorical question at 3:00 → retention spike → RULE: add question every 2-3 min
  ```
- **Applied to:** Phase 3 (Script Writer) — rules injected into writing prompt
- **Dashboard:** Weekly retention report to Yusif

### 13. Multi-Language Dubbing 🌍
- **Purpose:** Same video → multiple languages → multiple channels → multiplied revenue
- **Target languages:** English, Turkish, Urdu, French, Spanish
- **Process:**
  1. Qwen 2.5 72B translates Arabic script → target language
  2. Fish Speech generates voice in target language (with language-specific voice profile)
  3. FFmpeg swaps audio track + updates text overlays
  4. Update thumbnails with translated title text
  5. New SEO metadata per language (Phase 2 re-runs for target language)
  6. Upload to separate channel per language
- **No re-rendering video:** Same visuals, just new audio + text overlays
- **Timeline:** Start after Arabic channel hits 10K subscribers
- **Revenue multiplier:** Same production cost × 3-5 languages

### 14. Community Engagement Agent 💬
- **Purpose:** Boost algorithm ranking via early engagement (first 2 hours critical)
- **After publishing:**
  1. **Pin a comment** with a discussion question related to the video topic
  2. **Reply to first 20-50 comments** intelligently:
     - Qwen reads comment → generates contextual reply (not generic "thanks!")
     - Asks follow-up questions to encourage threads
     - Likes positive comments
  3. **Flag management:**
     - Detect spam/hate comments → hide + report
     - Detect constructive criticism → save for improvement feedback
  4. **Heart comments** that add value to the discussion
- **Timing:** Most active in first 2 hours, then checks every 6 hours for 48h
- **Safety:** Never argues, never political opinions, always respectful
- **Tone per channel:** Documentary = thoughtful, Sports = enthusiastic, etc.

### 15. Trending Hijack Mode ⚡
- **Purpose:** Capitalize on breaking news/events for massive views
- **Detection:**
  - Phase 1 trend scanner runs every 2 hours (not just daily)
  - Detects sudden spikes: topic went from 0 → trending in < 6 hours
  - Filters: must match channel categories
- **Alert:** Sends Telegram notification to Yusif:
  ```
  ⚡ TRENDING ALERT: [topic]
  Search volume: +500% in 3 hours
  Competition: only 2 videos so far
  Suggested channel: politics_ar
  Estimated window: 6-12 hours
  
  [🚀 Fast-track] [⏭️ Skip] [📋 Queue normally]
  ```
- **Fast-track pipeline (if approved):**
  - Shorter script: 800 words (5-6 min video)
  - Reduced QA: Phase 4 compliance only (skip Phase 6 style consistency)
  - Lower image count: 25-30 scenes instead of 40-80
  - Skip music generation → use pre-made tracks
  - **Total time: ~60-90 minutes instead of 3-4 hours**
- **Goal:** Be among first 5 videos on a trending topic

### 16. Playlist Strategy Agent 📚
- **Purpose:** Organize content into binge-worthy series for multiplied views
- **Auto-detection:**
  - After 10+ videos: agent clusters videos by topic similarity
  - Suggests playlist groupings:
    ```
    "انهيار الدول" → فنزويلا, لبنان, الأرجنتين, سريلانكا
    "ألغاز لم تُحل" → خامنئي, MH370, DB Cooper
    "حروب المال" → sanctions, oil wars, crypto wars
    ```
- **Series planning:**
  - When creating a video on "Venezuela collapse" → agent suggests:
    "This fits the 'Nation Collapse' series. Next suggested: Lebanon, Argentina"
  - Adds end-screen cards linking to previous/next in series
  - Playlist description optimized for SEO
- **YouTube algorithm benefit:** Playlist views count toward watch time, and YouTube auto-plays next video

### 17. Smart Thumbnail Text Positioning 🖼️
- **Problem:** YouTube overlays timestamp (bottom-right) and duration (bottom-left) on thumbnails
- **Rules:**
  - ❌ No text in bottom-right 15% (timestamp covers it)
  - ❌ No text in bottom-left 10% (duration covers it)
  - ✅ Best zones: top-third, center, right-center
  - Max 3-5 Arabic words (large, bold, readable at mobile size)
  - High contrast: white text + dark stroke, or colored text + blur background
- **Vision LLM check:** After thumbnail generation, Llama 3.2 Vision verifies:
  - Is the text readable at 320x180 (mobile thumbnail size)?
  - Does the text overlap with YouTube UI elements?
  - Is the composition eye-catching?
- **Auto-reject:** If text fails readability → regenerate with adjusted position

### 18. Anti-Repetition System 🔄
- **Purpose:** Prevent AI from falling into patterns that bore the audience
- **Tracking database (SQLite):**
  ```sql
  -- Tracks all past content patterns
  titles          → title structure, power words used
  hooks           → opening style (question? fact? shock?)
  visual_styles   → color palettes, composition types
  music_moods     → what moods were used recently
  angles          → perspective taken on similar topics
  ```
- **Rules:**
  - Same hook style max 2 times in 10 videos
  - Same visual palette max 3 times in 10 videos
  - Same title structure (e.g., "كيف...؟") max 2 times in 7 videos
  - Force style refresh every 10 videos (new visual approach)
- **Injection:** Anti-repetition constraints fed to Qwen during script + image prompting
- **Monthly report:** Diversity score to Yusif

---

## Revenue & Intelligence Features (Post-Growth)

### 19. Smart Ad Placement (Mid-Roll) 💰
- **Purpose:** Maximize ad revenue without hurting viewer experience
- **Process:**
  1. Qwen analyzes script → identifies natural pause points between sections
  2. Places ad breaks AFTER cliffhangers/questions (viewer stays to see answer)
  3. Never places ads mid-sentence or during climactic moments
  4. Learns from retention data: if ad at 3:20 causes 15% drop → move it to 3:45
- **Rules:**
  - First ad: never before 2:00
  - Spacing: minimum 2 minutes between ads
  - Max ads: 3-4 per 10-minute video
  - Always after a section transition, never mid-section
- **Impact:** +30-50% revenue vs. YouTube auto-placement

### 20. Sponsorship Detector & Integrator 🤝
- **Purpose:** Prepare for and manage sponsorships as channels grow
- **Pre-sponsor (< 50K subs):**
  - Tracks channel niche + audience demographics
  - Builds list of potential sponsors matching the niche
  - Reserves a 15-30 sec "sponsor slot" in every script (skippable placeholder)
- **Post-sponsor (> 50K subs):**
  - Integrates sponsor brief into script naturally (not jarring)
  - Generates sponsor segment: visual + narration + CTA
  - Tracks sponsor segment performance: skip rate, click-through
  - A/B tests sponsor placement: beginning vs. middle vs. end
- **Database:** Sponsor history, rates, performance per channel

### 21. Content Repurposing Engine 🔄
- **Purpose:** One video → 10+ content pieces across 6+ platforms
- **Auto-generated from each video:**
  ```
  📹 YouTube Long-form     ← (original)
  📱 YouTube Shorts ×3-5   ← (Phase 9 - already built)
  🐦 Twitter/X Thread      ← Top 5 points as Arabic thread + video link
  📸 Instagram Reels ×3-5  ← Same as Shorts, different hashtags/format
  📝 Blog Post             ← Script → SEO-optimized Arabic article
  🎧 Podcast Episode       ← Narration audio extracted as standalone podcast
  📢 Telegram Post         ← Summary + key facts + video link
  📌 Pinterest Pins ×3     ← Best scene images + Arabic text overlay
  ```
- **Platform-specific formatting:**
  - Twitter: 280 char limit per tweet, thread format
  - Instagram: 30 hashtags, different caption style
  - Blog: headings, paragraphs, internal links, schema markup
  - Podcast: intro jingle + narration + outro (no visual references)
- **Scheduling:** Each platform has optimal posting time
- **Impact:** 6x content reach, minimal extra cost

### 22. Audience Intelligence System 🧠
- **Data sources:**
  - YouTube Analytics API (demographics, geography, device)
  - Comment analysis (Qwen reads + categorizes comments)
  - Search terms that lead to videos
  - Traffic sources (browse, search, suggested, external)
- **Audience profile (auto-built):**
  ```yaml
  channel: documentary_ar
  top_countries: [Iraq, Saudi, Egypt, Morocco, Algeria]
  age_range: 18-34 (65%), 35-44 (20%)
  gender: male 72%, female 28%
  peak_hours: 18:00-23:00 UTC+3
  device: mobile 68%, desktop 25%, TV 7%
  top_requests: ["فيديو عن كوريا الشمالية", "سلسلة عن الحرب الباردة"]
  ```
- **Comment mining:**
  - Extracts topic requests: "سووا فيديو عن..." → adds to topic suggestions
  - Sentiment analysis: positive/negative ratio per video
  - FAQ detection: common questions → future video ideas
- **Applied to:** Phase 1 (topic selection), Phase 3 (script tone), Phase 8 (posting time)

### 23. Cross-Channel Promotion Network 🔗
- **Trigger:** Activates when 3+ channels are running
- **Process:**
  1. Agent maps topic relationships between channels:
     ```
     politics_ar: "انهيار فنزويلا" ←→ documentary_ar: "لعنة النفط"
     science_ar: "الطاقة النووية" ←→ politics_ar: "إيران والملف النووي"
     ```
  2. Auto-inserts cross-references in scripts:
     "شوفوا تحليلنا المفصّل على قناة [X]..."
  3. End-screen cards link to related videos on sister channels
  4. Pinned comments mention related content on other channels
- **Rules:**
  - Max 1 cross-promo per video (not spammy)
  - Only when genuinely relevant (not forced)
  - Tracks: how many viewers actually migrate between channels
- **Impact:** Network effect — 1 viewer becomes viewer of 3 channels

### 24. Script Template Evolution 📖
- **Learning cycle:**
  1. After 30 days: agent ranks all scripts by watch time retention
  2. Top 20% scripts → extracts structural patterns:
     - Hook type (question? shocking fact? mystery?)
     - Section count and length
     - Transition style between sections
     - Conclusion type (open-ended? call-to-action? philosophical?)
  3. Bottom 20% scripts → extracts anti-patterns (what to avoid)
  4. Builds evolving template library:
     ```yaml
     templates:
       high_retention_v3:
         hook: "shocking_fact + rhetorical_question"
         hook_length: "< 15 seconds"
         sections: 4
         section_length: "90-120 seconds each"
         transitions: "cliffhanger_question"
         conclusion: "open_ended_philosophical"
         avg_retention: "62%"
         based_on: ["vid_034", "vid_041", "vid_052"]
     ```
  5. Script Writer uses best template as structural guide
- **Monthly refresh:** Re-evaluates and updates templates
- **Per-channel templates:** Documentary style ≠ Sports style ≠ Entertainment style

### 25. Revenue Dashboard & Optimizer 📊
- **Tracks per video:**
  - Revenue (AdSense), RPM, CPM
  - Views, watch hours, subscribers gained
  - Revenue per topic category
  - Revenue per video length
  - Revenue per posting day/time
- **Discovers patterns:**
  ```
  "12-min videos earn 2.1x more than 8-min" → adjust target length
  "Technology topics: RPM $3.20 vs Politics: RPM $1.80" → prioritize tech
  "Thursday 6PM posts earn 25% more than Sunday 10AM" → optimize schedule
  "Videos with 4 mid-rolls earn 40% more than 2 mid-rolls" → adjust ad count
  ```
- **Auto-adjustments:**
  - Feeds optimal video length to Phase 3 (Script Writer)
  - Feeds optimal posting time to Phase 8 (Publisher)
  - Feeds high-RPM topics to Phase 1 (Topic Ranker) with bonus score
- **Weekly report to Yusif:** Revenue summary + optimization suggestions

### 26. Disaster Recovery & Channel Protection 🛡️
- **Daily backup:**
  - All configs, voice profiles, templates, style LoRAs
  - SQLite database (jobs, analytics, patterns)
  - Best-performing scripts + scene JSONs (for reference)
  - Backup location: separate drive + optional cloud (encrypted)
- **Channel strike protocol:**
  ```
  STRIKE DETECTED:
  1. ⏸️ PAUSE all publishing immediately
  2. 🔍 Identify which video caused the strike
  3. 📊 Analyze: what policy was violated?
  4. 🔧 Tighten Phase 4 compliance rules for that violation type
  5. 📱 Alert Yusif with full report + action plan
  6. ✅ Resume only after Yusif approves
  ```
- **Shadow channel:**
  - Pre-created backup channel per main channel
  - Same branding, description, links
  - If main channel gets terminated → redirect audience
  - Community post on related channels: "we moved to..."
- **Content archive:**
  - Every published video saved locally (full quality)
  - Metadata + SEO data preserved
  - Can re-upload entire library to new channel if needed

### 27. Competitor Alert System 🔔
- **Real-time monitoring (every 2 hours):**
  - Tracks 20-50 competitor channels per niche
  - Detects: new uploads, view velocity, viral spikes
- **Alerts:**
  ```
  🔔 SAME TOPIC: Competitor "قناة X" posted about [your queued topic] 2h ago
     → Options: [Change angle] [Speed up] [Cancel & swap]
  
  🔥 VIRAL ALERT: "قناة Y" got 500K views in 12h on [topic]
     → Analysis: [why it went viral] [suggested response video]
  
  📉 COMPETITOR DOWN: "قناة Z" hasn't posted in 14 days
     → Opportunity: grab their audience with similar content
  ```
- **Competitive intelligence:**
  - Monthly report: competitor growth rates, top-performing content
  - Gap analysis: what topics are underserved
  - Trend prediction: what competitors will likely cover next

### 28. Auto-Chapters & Smart Timestamps ⏱️
- **Auto-generated from scene data:**
  ```
  0:00 المقدمة
  0:15 كيف بدأت القصة
  2:30 نقطة التحول
  5:10 الحقيقة المخفية
  7:45 ماذا يعني هذا للمستقبل
  9:20 الخلاصة
  ```
- **Smart naming (not boring):**
  - ❌ "القسم الأول" ← generic
  - ✅ "اللحظة التي غيّرت كل شيء" ← clickable
  - Qwen generates chapter titles that create curiosity
- **YouTube benefits:**
  - Chapters show in progress bar
  - Google Search shows chapters in results (extra visibility)
  - Viewers can skip to interesting sections (better experience)
- **Auto-inserted:** Into YouTube description by Phase 8 SEO assembler

---

## Production Quality & Intelligence (Advanced)

### 29. Emotional Arc Engine 🎭
- **Purpose:** Every script follows a deliberate emotional wave — not monotone
- **Arc mapping:**
  ```
  😐 ──→ 😲 ──→ 😰 ──→ 🤯 ──→ 😌 ──→ 🔥
  intro   shock   tension  reveal  reflect  CTA
  ```
- **Process:**
  1. Qwen analyzes script → maps emotional intensity per section (1-10 scale)
  2. Validates: must have min 2 peaks and 2 valleys (no flat line)
  3. If flat → rewrites weak sections to add tension/surprise
  4. Links arc to music mood: tension sections = suspenseful music, reveals = epic drop
  5. Links arc to voice emotion (Feature 30): whisper at mystery, strong at reveal
- **Learns from data:** Correlates arc shapes with retention curves
  - "Scripts with peak at 60% mark retain 15% more viewers"
- **Output:** Emotional arc JSON attached to scene data

### 30. Voice Emotion Control 🎙️💫
- **Purpose:** TTS that changes emotion per scene — not robotic monotone
- **Emotion tags per scene:**
  ```json
  {
    "scene_id": 1,
    "emotion": "mysterious",
    "speed": 0.9,
    "pitch_shift": -2,
    "intensity": 0.7
  }
  ```
- **Emotion types:**
  | Emotion | Speed | Pitch | Use case |
  |---------|-------|-------|----------|
  | mysterious | 0.85x | lower | Hooks, mysteries |
  | urgent | 1.2x | higher | Breaking news, danger |
  | dramatic | 0.9x | deep | Reveals, climax |
  | calm | 1.0x | neutral | Explanations |
  | excited | 1.15x | higher | Sports, achievements |
  | whisper | 0.8x | lower | Secrets, tension |
  | reflective | 0.95x | soft | Conclusions |
- **Implementation:** Fish Speech parameters adjusted per scene
- **Fallback:** If emotion control fails → use neutral + rely on music for emotion
- **Impact:** Massive quality difference — sounds like a real narrator, not AI

### 31. Cinematic Sound Design 🎧
- **Purpose:** Professional-grade audio layering beyond basic SFX
- **Layers per scene:**
  ```
  Layer 1: Narration (100% volume)
  Layer 2: Background music (20-30%, auto-ducked)
  Layer 3: Ambient bed (10-15% — city noise, wind, room tone)
  Layer 4: SFX hits (40-60% — specific moments)
  Layer 5: Risers/drops (30% — tension builders before reveals)
  Layer 6: Silence beats (0% — intentional 0.5-1s pauses for impact)
  ```
- **Sound design patterns:**
  ```yaml
  patterns:
    mystery_reveal:
      - riser (3 sec, building tension)
      - silence (0.5 sec)
      - dramatic hit + narration reveal
      - ambient shift (dark → light)
    
    scene_transition:
      - current ambient fade out (1 sec)
      - whoosh/sweep SFX
      - new ambient fade in (1 sec)
    
    emotional_moment:
      - music swells
      - ambient drops to silence
      - voice slows (emotion control)
      - piano note or oud
  ```
- **Ambient library (pre-generated):**
  - City streets, desert wind, rain, ocean, crowd murmur, office, war zone
  - Generated once via AudioGen → reused across videos
- **FFmpeg mixing:** All 6 layers composed with precise timing

### 32. AI Virtual Presenter 🧑‍💻
- **Purpose:** Add human connection — viewers engage more with faces
- **Models:** SadTalker / MuseTalk / LivePortrait (local)
- **VRAM:** ~4GB
- **Setup:**
  - Generate or select a presenter face per channel (FLUX-generated or stock)
  - Each channel has unique presenter: different face, clothing style
  - Presenter image saved as reference
- **Usage modes:**
  ```
  Mode 1: Picture-in-Picture (PiP)
    → Small presenter window in corner
    → Used during: introductions, transitions, opinions
    
  Mode 2: Full-screen presenter
    → Presenter fills screen
    → Used during: hook, conclusion, CTA
    
  Mode 3: No presenter
    → Just B-roll visuals
    → Used during: documentary footage, data, maps
  ```
- **Per scene:** `"presenter_mode": "pip" | "fullscreen" | "none"`
- **Lip sync:** Audio from Fish Speech → SadTalker syncs lips to narration
- **Timeline:** Start after core pipeline is stable (Month 3+)

### 33. 4K AI Upscaling 🔍
- **Model:** Real-ESRGAN (local, CPU-based — no GPU queue conflict)
- **Process:**
  1. FLUX generates 1080p images
  2. Real-ESRGAN upscales to 4K (3840x2160)
  3. Upscaled images → LTX-2.3 for video generation
- **Benefits:**
  - Sharper thumbnails (YouTube compresses heavily — starting higher = better result)
  - YouTube prioritizes 4K content in recommendations
  - Future-proof: 4K TVs becoming standard
- **Time:** ~2-5 sec/image on CPU (parallel with GPU tasks)
- **Optional:** Upscale final video to 4K via FFmpeg + Real-ESRGAN frame-by-frame
  - Slow (~30 min for 10 min video) — optional for premium channels

### 34. Seasonal Content Bank 📅🏦
- **Purpose:** Pre-produce videos for predictable events — be first on trending day
- **Calendar (auto-maintained):**
  ```yaml
  seasonal_events:
    - event: "رمضان"
      prep_start: "Feb 1"
      publish: "first day of Ramadan"
      topics: ["تاريخ رمضان", "أغرب عادات رمضان حول العالم", "اقتصاد رمضان"]
      channels: ["documentary_ar", "entertainment_ar"]
      
    - event: "كأس العالم"
      prep_start: "3 months before"
      publish: "tournament start"
      topics: ["تاريخ كأس العالم", "أغرب أهداف", "فضائح FIFA"]
      channels: ["sports_ar"]
      
    - event: "اليوم الوطني السعودي"
      prep_start: "Aug 1"
      publish: "Sep 23"
      topics: ["تاريخ المملكة", "رؤية 2030", "تحولات السعودية"]
      channels: ["documentary_ar"]
  ```
- **Process:**
  - 2-4 weeks before event: pipeline produces videos
  - Videos stored in `output/seasonal_bank/`
  - Day of event: auto-publish at optimal time
  - **Beat competitors who produce day-of**

### 35. Narrative Style Library 📚✨
- **Purpose:** Vary storytelling approach — prevents audience fatigue
- **Styles:**
  ```yaml
  narrative_styles:
    investigative:
      description: "التحقيق الاستقصائي"
      tone: "من يقف وراء...؟ تابعوا معنا الخيوط"
      structure: [hook_mystery, clue_1, clue_2, evidence, confrontation, reveal, implications]
      music_profile: "suspenseful_noir"
      voice_emotion: ["mysterious", "urgent", "dramatic"]
      best_for: ["politics", "mysteries", "scandals"]
      
    storytelling:
      description: "القصة الدرامية"
      tone: "في يوم بارد من شتاء 1991..."
      structure: [scene_setting, character_intro, rising_action, climax, falling_action, resolution]
      music_profile: "emotional_cinematic"
      voice_emotion: ["calm", "dramatic", "reflective"]
      best_for: ["history", "biography", "human_interest"]
      
    explainer:
      description: "الشرح المبسط"
      tone: "ببساطة، الموضوع هو..."
      structure: [problem_statement, mechanism, examples, impact, what_next]
      music_profile: "calm_educational"
      voice_emotion: ["calm", "excited"]
      best_for: ["science", "technology", "economics"]
      
    countdown:
      description: "القائمة التنازلية"
      tone: "رقم 5... رقم 4..."
      structure: [intro, item_5, item_4, item_3, item_2, honorable_mentions, item_1_reveal]
      music_profile: "building_tension"
      voice_emotion: ["excited", "dramatic"]
      best_for: ["entertainment", "sports", "culture"]
      
    debate:
      description: "وجهات النظر"
      tone: "الفريق الأول يقول... لكن الآخرون يردّون..."
      structure: [question, side_a, evidence_a, side_b, evidence_b, analysis, conclusion]
      music_profile: "balanced_thoughtful"
      voice_emotion: ["calm", "urgent", "reflective"]
      best_for: ["politics", "philosophy", "social_issues"]
  ```
- **Selection:** Qwen picks best style based on topic + anti-repetition rules
- **Enforced:** Script Writer follows the selected style's structure strictly

### 36. Micro-Testing (Hook Testing) 🧪
- **Purpose:** Test the hook before committing to full video production
- **Process:**
  1. After Phase 5 produces first 30 seconds → extract as standalone Short
  2. Upload as unlisted YouTube Short
  3. Share to small test audience (Telegram group, or limited YouTube release)
  4. Monitor for 6 hours: retention %, like ratio, replay rate
  5. **Decision gate:**
     ```
     Retention > 70% at 30 sec → ✅ Proceed with full video
     Retention 50-70% → ⚠️ Rewrite hook (Qwen generates alternative)
     Retention < 50% → ❌ Major rewrite or consider different angle
     ```
  6. If hook rewritten → re-produce only first 30 sec (not entire video)
  7. Swap new hook into full video → publish
- **Cost:** ~15 min extra production time per video
- **Benefit:** Eliminates videos that would fail from weak openings

### 37. Dynamic Video Length 📐
- **Purpose:** Optimal length per topic — not one-size-fits-all
- **Qwen analysis before scripting:**
  ```
  Topic complexity: LOW → 4-6 min
    (simple news, single event, quick explainer)
  
  Topic complexity: MEDIUM → 8-12 min
    (standard documentary, analysis, countdown)
  
  Topic complexity: HIGH → 15-20 min
    (deep investigation, multi-part history, complex geopolitics)
  
  Topic type: BREAKING NEWS → 3-5 min (speed > depth)
  Topic type: EVERGREEN → 12-18 min (depth > speed, long-tail views)
  ```
- **Revenue-adjusted:**
  - Revenue Optimizer (Feature 25) feeds: "12+ min videos earn 2x RPM"
  - Agent adjusts: minimum length = 8 min (for mid-roll eligibility)
- **Retention-adjusted:**
  - Watch Optimizer (Feature 12) feeds: "20+ min videos lose 60% viewers by min 15"
  - Agent adjusts: cap at 18 min unless exceptional topic
- **Output:** Target word count + scene count → fed to Script Writer

### 38. Brand Kit Management System 🎨
- **Purpose:** Consistent visual identity across all outputs, versioned and enforced
- **Per-channel brand kit:**
  ```yaml
  brand_kits:
    documentary_ar:
      version: "2.1"
      logo:
        file: "assets/brands/doc/logo_v2.png"
        position: "top_right"
        opacity: 0.8
        margin: 20px
      colors:
        primary: "#1a1a2e"
        secondary: "#16213e"
        accent: "#e94560"
        text: "#ffffff"
        text_shadow: "#000000"
      fonts:
        title: "Cairo Bold"
        subtitle: "Cairo SemiBold"
        body: "Tajawal Regular"
        stats: "Cairo Black"
      templates:
        intro: "assets/brands/doc/intro_v3.mp4"
        outro: "assets/brands/doc/outro_v2.mp4"
        lower_third: "assets/brands/doc/lower_third.png"
        transition: "assets/brands/doc/transition.mp4"
      watermark:
        file: "assets/brands/doc/watermark.png"
        position: "bottom_left"
        opacity: 0.3
      text_overlay_style:
        background: "blur_dark"  # blur_dark | solid | gradient | none
        animation: "fade_slide_right"  # fade | slide | typewriter | fade_slide_right
        border_radius: 8
      thumbnail_style:
        template: "bold_dramatic"
        text_position: "center_top"
        max_words: 4
        text_color: "#ffffff"
        text_stroke: "#000000"
        stroke_width: 3
  ```
- **Version control:** When branding updates → old version archived, new applied to future videos
- **Consistency enforcer:** Phase 7 (Final QA) validates all outputs match brand kit
- **Asset management:** All brand assets stored in `config/brands/[channel_id]/`

### 39. YouTube Algorithm Tracker 📡
- **Purpose:** Detect and adapt to YouTube algorithm changes in real-time
- **Monitoring signals:**
  ```
  Signal 1: Impression share change
    Normal: 10K impressions/day → Sudden drop to 3K = algorithm shift
    
  Signal 2: CTR anomaly
    Same thumbnails/titles but CTR dropped 30% = algorithm changed ranking
    
  Signal 3: Traffic source shift
    Browse features dropped, Search increased = algorithm de-prioritizing your content
    
  Signal 4: Cross-channel comparison
    Your views dropped but competitors too = global algorithm change
    Your views dropped but competitors stable = content quality issue
  ```
- **Response actions:**
  ```
  Algorithm favoring longer videos → increase target length
  Algorithm favoring Shorts → increase Shorts output
  Algorithm favoring high engagement → boost Community Agent activity
  Algorithm penalizing frequency → reduce from daily to 5/week
  ```
- **Alert to Yusif:**
  ```
  📡 ALGORITHM ALERT:
  Detected: Impression drop -40% across all channels
  Cross-check: 3/5 competitors also dropped
  Diagnosis: Likely global algorithm update
  Recommendation: Hold strategy, monitor 7 days
  Similar past event: March 2025 update (recovered in 10 days)
  ```
- **Monthly report:** Algorithm health score + trend direction

### 40. Automated A/B Script Testing 🔬
- **Purpose:** Scientifically test which script approach works better
- **Process:**
  1. Pick 1 topic per month for A/B test
  2. Qwen writes 2 scripts with different approaches:
     - Version A: investigative style, 12 min
     - Version B: storytelling style, 10 min
  3. Produce both videos (2x production cost — monthly investment)
  4. Publish on same channel, 3 days apart (or on 2 different channels)
  5. After 30 days: compare retention, CTR, watch time, revenue
  6. **Winner's approach → fed to Script Template Evolution (Feature 24)**
- **Variables to test:**
  ```
  Month 1: Hook style (question vs shocking fact)
  Month 2: Video length (8 min vs 14 min)
  Month 3: Narration speed (1.0x vs 0.9x)
  Month 4: Music intensity (subtle vs dramatic)
  Month 5: Visual style (photorealistic vs stylized)
  Month 6: Presenter (with avatar vs without)
  ```
- **Database:** All A/B test results stored → builds knowledge base over time
- **Impact:** Data-driven creative decisions instead of guessing

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
