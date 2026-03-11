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
                 PHASE 7.5        PHASE 7          PHASE 6          PHASE 5
PHASE 8     ◀── Manual    ◀──── QA: Final  ◀─── QA: Visual  ◀─── Production
Publish          Review          Video Check      Verify           Engine
   │            (Optional)
   │
   ▼
PHASE 9: Performance Intelligence
   │  Analyzes: CTR, watch time, retention, revenue
   │
   └──▶ Feeds back to: Phase 1 (topics), Phase 2 (SEO), Phase 3 (scripts),
                        Phase 5 (visuals), Phase 8 (thumbnails, posting time)

COMPLIANCE AGENT gates Phase 4 + 6 + 7 — can BLOCK and alert user
MANUAL REVIEW (Phase 7.5) — optional human gate before publish
PERFORMANCE LOOP (Phase 9) — continuous learning from published videos
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
| 7.5 | **Manual Review (Optional)** | Yusif reviews video before publish — can approve/reject/edit | ✅ GATE |
| 8 | Publishing Engine | Thumbnail, SEO metadata, YouTube upload, scheduling | — |
| 9 | **Performance Intelligence** | Analyze CTR, watch time, retention → feed back to all phases | 🔄 LOOP |

---

## Phase 1: Research & Trend Discovery

### Purpose
Find trending topics across YouTube, news, social media — and present them to the user for selection.

### Components

#### 1.1 YouTube Trend Scanner
- **⚠️ OFFICIAL APIs ONLY — No scraping, no unofficial endpoints**
- **YouTube Data API v3 (official, quota: 10,000 units/day):**
  - `videos.list` (chart=mostPopular, regionCode=IQ/SA/EG) — trending videos
  - `search.list` (order=viewCount, publishedAfter=7d) — most-viewed recent by category
  - `channels.list` + `search.list` — competitor channel analysis
- **Competitor Analysis (via official API):**
  - Track 20-50 competitor channels by channel ID
  - What topics got the most views in the last 7 days?
  - What topics are getting sudden view spikes?
- **API Quota Management:**
  ```
  Budget per daily run:
  - Trending fetch: ~200 units (2 regions × 50 results)
  - Competitor scan: ~2000 units (50 channels × search)
  - Keyword research (Phase 2): ~3000 units
  - Upload + metadata: ~1600 units
  - Reserve: ~3200 units
  Total: ~10,000 units/day (fits free quota)
  ```
- **Caching:** Cache results for 6 hours — don't re-fetch same data
- **Output:** Top trending YouTube topics with view counts
- **🚫 NEVER use:** YouTube internal APIs, scraping, browser automation for data extraction
- **Risk mitigation:** If quota exceeded → use cached data + Google Trends only

#### 1.2 Web & News Trend Scanner
- **Sources (all official/public):**
  - Google Trends API via `pytrends` (Arabic regions: Iraq, Saudi, Egypt, UAE, Morocco)
  - Twitter/X API v2 (**official paid tier**, or skip if no API access)
  - Reddit API (**official**, r/worldnews, r/science, r/todayilearned)
  - News RSS feeds (Al Jazeera, BBC Arabic, Reuters Arabic, Sky News Arabia) — **public, no API needed**
  - Google News RSS — public feeds by topic/region
- **⚠️ No scraping:** If a platform doesn't have official API access → skip it, don't scrape
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
- `pytrends` (Google Trends — unofficial but widely used, low risk)
- YouTube Data API v3 (official — trending + search + channels)
- Twitter/X API v2 (official paid tier — or skip)
- Reddit API (official — `praw` library)
- `feedparser` (RSS — public feeds, zero risk)
- LLM for summarization and angle suggestion
- **🚫 No scraping, no unofficial APIs, no browser automation for data**

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
- YouTube Data API v3 (official — search, videos, channels endpoints)
- **⚠️ YouTube Search Suggest:** semi-official autocomplete endpoint (widely used, low risk — but monitor for changes)
- LLM for title generation and analysis
- `yt-dlp` for metadata extraction (**open-source, used for public video metadata only — not downloading copyrighted content**)

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

#### 3.5 Visual Identity Decision (AI — single decision drives everything)
- Qwen 72B reads the complete script and makes ONE unified styling decision:
  - **Font category** → selects from 8 Arabic font families
  - **Animation style** → entry/exit/persistent animations for text overlays
  - **Color grade** → cinematic LUT for all images + thumbnails
  - **Intro/outro style** → matching intro template
  - **Transition defaults** → transition preferences for this content type
  - **Music mood zones** → groups scenes by mood for segmented soundtrack
  - **Subtitle styling** → .ass format with matching font/colors
- This ONE decision creates a **unified visual identity** across:
  - Text overlays, thumbnails, subtitles, intro/outro, color grade, transitions
  - Stored in DB as `FontAnimationConfig` (JSON), referenced by all downstream phases

#### 3.6 Pacing Analyzer
- Classifies each scene type (hook, setup, explanation, peak, conclusion)
- Applies rhythm mapping: medium → build → rapid peak → valley → medium end
- Anti-monotony rules: no 3+ consecutive same-duration scenes
- Output: adjusted scene durations (overrides initial estimates)

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

#### 4.4 YouTube AI Content Policy Compliance ⚠️
- **Problem:** YouTube may classify AI-generated videos as "reused/low-effort content" → limited ads or removal
- **YouTube's criteria for LOW EFFORT:**
  - ❌ AI images with no narration (slideshow)
  - ❌ Generic AI narration with no personality/insight
  - ❌ No original commentary, analysis, or perspective
  - ❌ Repetitive visual patterns (same style every frame)
  - ❌ No storytelling structure (just facts listed)
- **Our defense layers (what makes our content HIGH EFFORT):**
  ```
  ✅ Layer 1: STRONG NARRATION
     - Not just reading facts — emotional arc, rhetorical questions,
       dramatic pacing, personal analysis, "لكن هل تساءلتم...؟"
     - Voice emotion varies per scene (Feature 30)
     - Script reviewer specifically checks for "original insight"
  
  ✅ Layer 2: REAL STORYTELLING
     - Narrative styles (Feature 35): investigative, storytelling, debate
     - Not a list of facts — a STORY with beginning, conflict, resolution
     - Script must have: hook, tension, reveal, reflection
     - Emotional arc engine (Feature 29) enforces this
  
  ✅ Layer 3: VISUAL VARIETY
     - Mix of: AI images, AI video, text overlays, data visualizations
     - Camera movements vary (zoom, pan, parallax — not just static)
     - Style variations within video (not 60 identical-looking scenes)
     - AI Presenter (Feature 32) adds human presence
  
  ✅ Layer 4: PRODUCTION VALUE
     - Cinematic sound design (Feature 31): 6 audio layers
     - **Animated Arabic text overlays** — AI-selected fonts + cinema-grade animations (see below)
     - Intro/outro branding
     - Chapter markers, timestamps
     - Arabic subtitles (SRT)
  
  ✅ Layer 5: DISCLOSURE & TRANSPARENCY
     - YouTube AI disclosure label (REQUIRED)
     - Description includes: "تم إنشاء هذا المحتوى بمساعدة الذكاء الاصطناعي"
     - Sources cited in description
     - This satisfies YouTube's AI content policy
  ```
- **Compliance check (added to Phase 4):**
  ```python
  def check_ai_content_quality(script, scenes):
      score = 0
      
      # Original insight check
      if has_original_analysis(script):     score += 2
      if has_rhetorical_questions(script):  score += 1
      if has_personal_perspective(script):  score += 2
      
      # Storytelling check
      if has_emotional_arc(script):         score += 2
      if has_narrative_structure(script):   score += 1
      
      # Visual variety
      unique_styles = count_unique_visual_styles(scenes)
      if unique_styles >= 3:               score += 1
      
      # Production value
      if has_text_overlays(scenes):         score += 1
      
      # Score: 0-10
      if score >= 7:  return "PASS — high-effort content"
      if score >= 4:  return "WARN — add more original analysis"
      return "BLOCK — too generic, YouTube may flag as low-effort"
  ```

#### 4.5 Arabic Quality Check
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

- **🌍 Arabic/Middle Eastern Content Optimization:**
  ```
  المشكلة: FLUX و LTX مدرّبين أغلب بيانات غربية.
  المحتوى العربي يحتاج prompting دقيق وإلا النتيجة تكون "Hollywood version of Middle East"
  ```
  
  **Prompt Engineering Rules for Arabic Content:**
  ```yaml
  middle_east_prompt_rules:
    # ─── الأماكن والعمارة ──────────────────
    architecture:
      use: "Islamic architecture, arabesque patterns, mashrabiya windows,
            Ottoman architecture, Abbasid-era buildings, modern Gulf skyline,
            Baghdad street scene, Riyadh cityscape, Cairo old town"
      avoid: "generic desert, Aladdin-style, orientalist, fantasy Arabian"
      note: "يحدد البلد بالضبط — عمارة بغداد ≠ عمارة دبي ≠ عمارة القاهرة"
    
    # ─── الأشخاص والملابس ──────────────────
    people:
      use: "Middle Eastern man in thobe/dishdasha, Arab woman in hijab,
            Iraqi businessman in suit, Saudi man in white thobe and ghutra,
            Egyptian street vendor, Moroccan market seller"
      avoid: "stereotypical, orientalist, belly dancer, generic Arab"
      skin_tones: "olive, brown, Mediterranean — specify per region"
      note: "الملابس تختلف بالبلد — دشداشة عراقية ≠ ثوب سعودي ≠ جلابية مصرية"
    
    # ─── المناظر الطبيعية ──────────────────
    landscapes:
      use: "Mesopotamian marshlands, Nile delta farmland, Atlas mountains,
            Arabian desert with specific features, Gulf coast, Levantine hills,
            palm groves, olive orchards"
      avoid: "generic sandy desert, camels only, Lawrence of Arabia style"
      note: "الشرق الأوسط مو بس صحراء — فيه أهوار وجبال وأنهار وغابات"
    
    # ─── السياسة والتاريخ ──────────────────
    politics_history:
      use: "government building, parliament session, diplomatic meeting,
            military equipment (realistic), protest crowd, press conference,
            historical photograph style, documentary still"
      avoid: "violent imagery, gore, graphic war scenes, disrespectful depictions"
      note: "سياسي وواقعي — مو دعائي أو تحريضي"
    
    # ─── الاقتصاد والأعمال ──────────────────
    economy:
      use: "oil refinery, stock market screen with Arabic text, Gulf port,
            construction site Dubai-style, souk/market, modern office"
      avoid: "poverty porn, exaggerated wealth stereotypes"
    
    # ─── Style Modifiers for Authenticity ──────
    style_modifiers:
      lighting: "warm golden hour, dramatic sunset, harsh noon sun"
      color_palette: "warm earth tones, sand gold, deep blue, olive green"
      atmosphere: "dusty atmosphere, heat haze, dramatic shadows"
      photography_style: "photojournalism, documentary photography, cinematic still"
  ```
  
  **LoRA Models for Arabic Content (download/fine-tune):**
  ```
  Recommended LoRAs:
  ├── Middle Eastern Architecture LoRA — enhances Islamic architecture generation
  ├── Arabic Calligraphy LoRA — for decorative elements (NOT text in images)
  ├── Photojournalism LoRA — documentary-style realistic images
  ├── Cinematic Lighting LoRA — dramatic lighting for documentary feel
  └── Regional Face LoRA — better Middle Eastern facial features
  
  Fine-tune options (if needed):
  ├── Collect 500-1000 Middle Eastern documentary stills
  ├── Train FLUX LoRA (~2 hours on RTX 3090)
  └── Result: much better regional accuracy
  ```
  
  **Scene Splitter Prompt Enhancement:**
  ```python
  def enhance_visual_prompt(raw_prompt: str, topic_region: str) -> str:
      """
      Automatically enhances visual prompts with regional accuracy.
      """
      # Add regional context
      if topic_region == "iraq":
          raw_prompt += ", Iraqi setting, Mesopotamian, Tigris river area"
      elif topic_region == "gulf":
          raw_prompt += ", Gulf state setting, modern Arabian architecture"
      elif topic_region == "egypt":
          raw_prompt += ", Egyptian setting, Nile region, Cairo urban"
      elif topic_region == "levant":
          raw_prompt += ", Levantine setting, stone buildings, Mediterranean"
      elif topic_region == "maghreb":
          raw_prompt += ", North African setting, Moroccan/Tunisian architecture"
      
      # Add documentary style
      raw_prompt += ", photorealistic, documentary photography, cinematic lighting"
      
      # Add negative
      negative = ("text, writing, letters, watermark, cartoon, anime, "
                  "orientalist, stereotypical, fantasy, Aladdin-style")
      
      return raw_prompt, negative
  ```
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

#### 5.3 Voice Engine — Pre-Built Voice Library + Smart Selection 🎙️
- **Model:** Fish Speech / OpenAudio S1 (local)
- **VRAM:** ~4GB

##### 5.3.1 Voice Cloning from Real Recordings
- **المبدأ:** يوسف يوفّر تسجيلات صوتية حقيقية (أشخاص حقيقيين) → النظام يسوي AI voice clone → يستخدم الـ clone لإنتاج كل الفيديوهات
- **هذا أفضل بكثير من أصوات AI من الصفر — الصوت المستنسخ يحافظ على طبيعية الصوت البشري**

- **ما يحتاج يوسف يوفّره لكل صوت:**
  ```
  المطلوب: تسجيل صوتي نظيف WAV/MP3
  ├── المدة: 1-5 دقائق (كل ما أطول = clone أدق)
  │   ├── 30 ثانية = clone أساسي (مقبول)
  │   ├── 1-2 دقيقة = clone جيد (موصى به)
  │   └── 3-5 دقائق = clone ممتاز (أفضل نتيجة)
  ├── المحتوى: قراءة نص عربي فصيح بأسلوب طبيعي
  │   ├── يتضمن: جمل طويلة + قصيرة + أسئلة + تعجب
  │   └── يتضمن: نبرات مختلفة (هادئ + حماسي + درامي)
  ├── الجودة: بيئة هادئة، بدون صدى أو ضوضاء خلفية
  │   ├── مايكروفون: أي مايك USB مقبول (لا يحتاج استوديو)
  │   └── Format: WAV 44.1kHz 16-bit (أو MP3 320kbps)
  └── الملف يوضع في: config/voices/[voice_name].wav
  ```

- **أفضل نموذج Voice Cloning للعربية:**
  ```
  الترتيب حسب جودة العربية:
  
  🥇 1. Fish Speech 1.5 (محلي — مجاني)
     ├── أقوى نموذج مفتوح للعربية حالياً
     ├── يدعم zero-shot cloning (عينة واحدة تكفي)
     ├── VRAM: ~4GB
     ├── جودة العربية: 8.5/10
     └── يدعم emotion control (Feature 30)
  
  🥈 2. OpenAudio S1 (محلي — مجاني)
     ├── من Sesame/Fish Speech team
     ├── أحدث، جودة صوتية أعلى
     ├── VRAM: ~4GB
     ├── جودة العربية: 8/10 (أحدث بس أقل اختبار)
     └── يدعم multi-speaker
  
  🥉 3. XTTS v2 / Coqui TTS (محلي — مجاني)
     ├── مجرّب ومستقر
     ├── يدعم العربية رسمياً
     ├── VRAM: ~2GB
     ├── جودة العربية: 7.5/10
     └── أبطأ من Fish Speech
  
  ☁️ 4. ElevenLabs (API — مدفوع $22/شهر)
     ├── أفضل جودة cloning بالعالم
     ├── جودة العربية: 9/10
     ├── لكن: مو محلي + يكلف
     └── يستخدم كـ FALLBACK فقط
  ```

- **Clone Pipeline (مرة واحدة لكل صوت):**
  ```python
  def clone_voice(reference_wav: str, voice_id: str):
      """
      يستنسخ الصوت من التسجيل الحقيقي.
      يشتغل مرة واحدة — بعدها يستخدم الـ clone لكل الفيديوهات.
      """
      # 1. تنظيف الصوت (إزالة ضوضاء + تطبيع الصوت)
      cleaned = denoise_audio(reference_wav)       # using noisereduce library
      normalized = normalize_volume(cleaned)        # consistent volume
      
      # 2. استنساخ الصوت
      model = load_fish_speech()
      voice_embedding = model.create_speaker_embedding(normalized)
      
      # 3. اختبار الجودة — يولّد جملة اختبارية ويقيّمها
      test_text = "في عام ألفين وستة وعشرين، شهد العالم تحولات جذرية لم يتوقعها أحد."
      test_audio = model.synthesize(test_text, voice_embedding)
      
      quality_score = evaluate_arabic_pronunciation(test_audio)
      similarity_score = compare_voice_similarity(test_audio, normalized)
      
      if quality_score < 6 or similarity_score < 0.7:
          raise VoiceCloneError(f"Clone quality too low: {quality_score}/10, similarity: {similarity_score}")
      
      # 4. حفظ الـ embedding للاستخدام المستقبلي
      save_voice_profile(voice_id, voice_embedding, {
          "reference_file": reference_wav,
          "quality_score": quality_score,
          "similarity_score": similarity_score,
          "cloned_at": datetime.now(),
          "model": "fish_speech_1.5"
      })
      
      return voice_embedding
  ```

- **Voice Library (بعد الاستنساخ):**
  ```yaml
  voice_library:
    # ─── أصوات رجالية (مستنسخة من تسجيلات حقيقية) ───
    male_authoritative:
      id: "v_male_auth_01"
      name: "صوت المذيع الرسمي"
      source: "real_human_recording"              # تسجيل شخص حقيقي
      reference_file: "config/voices/male_authoritative_01.wav"  # الأصل
      clone_embedding: "config/voices/embeddings/v_male_auth_01.pt"  # الـ clone
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 120                 # دقيقتين تسجيل أصلي
      clone_quality_score: 8.9
      clone_similarity_score: 0.92
      characteristics:
        gender: "male"
        age_range: "35-50"
        tone: "authoritative, deep, calm"
        accent: "MSA (فصحى)"
        speed: "medium"
        emotion_range: "wide"
      best_for: ["documentary", "politics", "history"]
      
    male_energetic:
      id: "v_male_energy_01"
      name: "صوت الرياضة الحماسي"
      source: "real_human_recording"
      reference_file: "config/voices/male_energetic_01.wav"
      clone_embedding: "config/voices/embeddings/v_male_energy_01.pt"
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 90
      clone_quality_score: 8.5
      clone_similarity_score: 0.88
      characteristics:
        gender: "male"
        age_range: "25-35"
        tone: "energetic, fast, passionate"
        accent: "MSA with slight energy"
        speed: "fast"
        emotion_range: "medium"
      best_for: ["sports", "entertainment", "countdown"]
      
    male_mysterious:
      id: "v_male_mystery_01"
      name: "صوت الألغاز والتحقيقات"
      source: "real_human_recording"
      reference_file: "config/voices/male_mysterious_01.wav"
      clone_embedding: "config/voices/embeddings/v_male_mystery_01.pt"
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 60
      clone_quality_score: 8.3
      clone_similarity_score: 0.85
      characteristics:
        gender: "male"
        age_range: "30-45"
        tone: "mysterious, low, suspenseful"
        accent: "MSA"
        speed: "slow-medium"
        emotion_range: "wide"
      best_for: ["mysteries", "investigation", "conspiracy"]

    male_narrator:
      id: "v_male_narr_01"
      name: "صوت الراوي الكلاسيكي"
      source: "real_human_recording"
      reference_file: "config/voices/male_narrator_01.wav"
      clone_embedding: "config/voices/embeddings/v_male_narr_01.pt"
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 180
      clone_quality_score: 9.1
      clone_similarity_score: 0.93
      characteristics:
        gender: "male"
        age_range: "40-55"
        tone: "warm, storytelling, cinematic"
        accent: "MSA classical"
        speed: "medium-slow"
        emotion_range: "wide"
      best_for: ["storytelling", "history", "biography"]

    female_educational:
      id: "v_female_edu_01"
      name: "صوت العلوم والتعليم"
      source: "real_human_recording"
      reference_file: "config/voices/female_educational_01.wav"
      clone_embedding: "config/voices/embeddings/v_female_edu_01.pt"
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 90
      clone_quality_score: 8.6
      clone_similarity_score: 0.87
      characteristics:
        gender: "female"
        age_range: "28-40"
        tone: "clear, educational, engaging"
        accent: "MSA"
        speed: "medium"
        emotion_range: "medium"
      best_for: ["science", "technology", "explainer"]

    female_dramatic:
      id: "v_female_drama_01"
      name: "صوت الدراما والقصص"
      source: "real_human_recording"
      reference_file: "config/voices/female_dramatic_01.wav"
      clone_embedding: "config/voices/embeddings/v_female_drama_01.pt"
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 120
      clone_quality_score: 8.4
      clone_similarity_score: 0.86
      characteristics:
        gender: "female"
        age_range: "30-45"
        tone: "dramatic, emotional, cinematic"
        accent: "MSA"
        speed: "medium"
        emotion_range: "wide"
      best_for: ["human_interest", "social_issues", "storytelling"]

    young_male:
      id: "v_young_male_01"
      name: "صوت الشباب"
      source: "real_human_recording"
      reference_file: "config/voices/young_male_01.wav"
      clone_embedding: "config/voices/embeddings/v_young_male_01.pt"
      clone_model: "fish_speech_1.5"
      reference_duration_sec: 60
      clone_quality_score: 8.1
      clone_similarity_score: 0.84
      characteristics:
        gender: "male"
        age_range: "20-28"
        tone: "casual, modern, relatable"
        accent: "MSA with modern touch"
        speed: "medium-fast"
        emotion_range: "medium"
      best_for: ["entertainment", "technology", "culture"]
  ```

##### 5.3.2 Smart Voice Selection Agent
- **الـ agent يختار الصوت الأنسب لكل فيديو أوتوماتيك:**
  ```python
  def select_best_voice(job_data: dict) -> str:
      """
      Selects optimal voice from library based on content analysis.
      """
      topic = job_data['topic']
      channel = job_data['channel_id']
      narrative_style = job_data['narrative_style']
      emotional_arc = job_data['emotional_arc']
      
      # 1. Channel default (if configured)
      channel_voice = get_channel_default_voice(channel)
      
      # 2. Content-based matching
      scores = {}
      for voice_id, voice in voice_library.items():
          score = 0
          
          # Topic category match
          if job_data['category'] in voice['best_for']:
              score += 30
          
          # Narrative style match
          if narrative_style == "investigative" and voice['tone'] contains "mysterious":
              score += 20
          if narrative_style == "storytelling" and voice['tone'] contains "storytelling":
              score += 20
          if narrative_style == "explainer" and voice['tone'] contains "educational":
              score += 20
          
          # Emotion range needed
          arc_intensity = max(emotional_arc) - min(emotional_arc)
          if arc_intensity > 5 and voice['emotion_range'] == "wide":
              score += 15
          
          # Channel consistency bonus (same voice = branding)
          if voice_id == channel_voice:
              score += 25
          
          # Quality score
          score += voice['quality_score'] * 2
          
          # Anti-repetition: different voice than last 3 videos on channel
          if voice_id in get_recent_voices(channel, last_n=3):
              score -= 10  # Slight penalty, not blocking
          
          scores[voice_id] = score
      
      return max(scores, key=scores.get)
  ```

- **Channel-Voice Binding (اختياري):**
  ```yaml
  # في channels.yaml — كل قناة ممكن تقفل على صوت معين
  channels:
    documentary_ar:
      default_voice: "v_male_auth_01"      # دايماً نفس الصوت = براندينج
      allow_voice_switch: false             # لا يغيّر
      
    sports_ar:
      default_voice: "v_male_energy_01"
      allow_voice_switch: false
      
    science_ar:
      default_voice: null                   # يختار الأنسب كل مرة
      allow_voice_switch: true
      preferred_voices: ["v_female_edu_01", "v_male_narr_01"]
  ```

##### 5.3.3 Voice Quality Assurance
- **Per scene generation:**
  - Input: `narration_text` + selected voice reference + emotion tag (Feature 30)
  - Output: WAV audio clip
  - Auto-adjust speed to match target `duration_seconds`
- **Quality checks (automated):**
  ```
  Check 1: Arabic pronunciation — compare phonemes vs expected
  Check 2: Glitch detection — no clicks, pops, or artifacts
  Check 3: Emotion match — does the tone match the scene emotion tag?
  Check 4: Speed consistency — no sudden speedups/slowdowns
  Check 5: Volume consistency — no sudden loud/quiet sections
  
  Score < 6/10 → regenerate with same voice
  Score < 4/10 → try different voice from library
  3 failures → alert Yusif: "Voice quality issue on scene X"
  ```
- **Fallback chain:**
  ```
  Primary:   Fish Speech + selected library voice
  Fallback1: Fish Speech + different library voice
  Fallback2: OpenAudio S1 + selected library voice
  Fallback3: ElevenLabs API (paid, last resort)
  ```
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
  6. **Animated Arabic text overlays (post-production — NOT in AI images):**
     - All visible text rendered as **transparent animated video layers**, then composited
     - **NOT** FFmpeg drawtext (too limited for Arabic animations)
     - Method: PyCairo (proper Arabic shaping via HarfBuzz/Pango) → frame-by-frame PNGs → ProRes 4444 overlay → FFmpeg composite
     
     **AI Font Selection (Qwen 72B — during Phase 3):**
     - Reads script tone, topic, emotional arc → selects from 8 font categories:
       - Formal/News: IBM Plex Sans Arabic (clean, authoritative)
       - Dramatic: Aref Ruqaa (bold, high-contrast, shadows)
       - Historical: Amiri (classical, elegant, ornamental)
       - Modern/Tech: Readex Pro (geometric, minimal)
       - Islamic: Scheherazade New (traditional Naskh)
       - Military: Cairo Heavy (stark, impactful)
       - Editorial: Noto Sans Arabic (neutral, readable)
       - Storytelling: Tajawal (warm, rounded)
     - Each category has: primary font + accent font + weight range + style notes
     - Colors, background style (none/box/gradient/blur) also AI-selected
     
     **Animation Styles (per font category):**
     - Formal: slide-right entry (400ms) → clean, professional
     - Dramatic: blur-reveal (600ms) + glow pulse → cinematic tension
     - Historical: typewriter RTL (800ms) → elegant, deliberate
     - Modern: glitch-in (350ms) + subtle float → futuristic
     - Islamic: gentle fade-in (700ms) → respectful
     - Military: sharp slide-up (300ms) → decisive, commanding
     - Editorial: word-by-word (500ms) → emphasis on content
     - Storytelling: letter cascade (600ms) + float → playful
     
     **Special animations:**
     - Typewriter: Arabic-aware, reveals full ligature groups (لا as unit)
     - Word-by-word: syncs with Fish Speech word-level timestamps (karaoke-style)
     - Glitch: RGB channel shift + scanlines → digital feel
     
     **Content types:**
     - Title card at start
     - Section headers
     - Key facts/dates/statistics
     - Highlighted quotes
     - Subscribe reminder at end
  7. **Add intro/outro** templates (per channel branding)
  8. **Render final video:**
     - Resolution: 1920x1080 or 4K
     - Codec: H.264/H.265
     - Audio: AAC 320kbps
     - Format: MP4
- **Output:** Final video MP4 → goes to Phase 7

#### 5.7 Color Grading (CPU — after FLUX, before LTX)
- **Problem:** FLUX generates each image independently → inconsistent colors across scenes
- **Solution:** Unified cinematic color grade across all images
- **Method:**
  1. **LUT selection:** Same AI that picks fonts picks the matching LUT:
     - formal_news → documentary_neutral (clean, slightly desaturated)
     - dramatic → teal_orange (Hollywood look)
     - historical → sepia_warm (aged, warm feel)
     - modern_tech → cyberpunk (high saturation, neon)
     - islamic → warm_gold (golden, elegant tones)
     - military → cold_steel (blue-grey, harsh)
  2. **Apply LUT** to all scene images uniformly (OpenCV)
  3. **Reinhard normalize** to "hero image" (best-scored from Phase 6A) — reduces remaining color outliers
  4. Same LUT applied to **thumbnails** — brand consistency
- **One AI decision (Phase 3) drives:** font + animation + color grade + intro style = unified video identity

#### 5.8 Intelligent Transitions (AI-selected)
- **Problem:** All crossfades = monotonous, doesn't convey meaning
- **Solution:** Qwen 72B analyzes each scene pair → selects meaningful transition
- **Transition library:**
  | Transition | When to Use |
  |-----------|------------|
  | Cut (instant) | Same location, tension, continuous action |
  | Crossfade (0.5s) | Gentle topic change, related scenes |
  | Dissolve (1.0s) | Time passing, memory, dream-like |
  | Fade to black (1.5s) | Major time skip, chapter break |
  | Fade to white | Flashback, spiritual, revelation |
  | Slide/wipe | Geographic movement, timeline |
  | Zoom in | Narrowing focus, detail emphasis |
  | Glitch cut | Tech content, digital theme, conspiracy |
- **Fallback rules** if LLM fails: mood change → dissolve, tension → cut, time skip → fade black

#### 5.9 Music-Scene Sync (Dynamic Soundtrack)
- **Problem:** ONE MusicGen track for entire video = mood disconnect
- **Solution:** Group scenes into "mood zones" → generate one music track per zone
- **Process:**
  1. Phase 3 groups consecutive same-mood scenes into zones:
     - Scenes 1-3 (tense) → Zone A: "tense, 45s"
     - Scenes 4-6 (hopeful) → Zone B: "hopeful, 30s"
     - Scenes 7-9 (climax) → Zone C: "dramatic climax, 50s"
  2. MusicGen generates one track per zone with zone-specific prompt
  3. VideoComposer crossfades between zone tracks (2-3s overlap)
  4. Music ducking still applies during all narration
- **Mood compatibility groups** (can share track): {tense,dramatic}, {hopeful,inspiring}, {calm,reflective}

#### 5.10 Dynamic Intro/Outro
- **Problem:** Static template = every video looks the same in first 5 seconds
- **Solution:** Intro/outro style matches font_category:
  | Type | Intro Style | Duration |
  |------|------------|----------|
  | Formal/News | Logo + title slide + date, professional slide-in | 3-4s |
  | Dramatic | Dark reveal, smoke/particles, logo from darkness | 5-6s |
  | Historical | Parchment unfold, ink writing effect | 4-5s |
  | Modern/Tech | Digital grid/HUD, logo glitch-in | 3-4s |
  | Islamic | Geometric arabesque pattern → expands to title | 4-5s |
  | Military | Tactical map zoom → military stencil title | 3-4s |
- **Outro** (universal): Subscribe CTA + next video suggestion + channel logo (8-12s, YouTube end screen compatible)
- **Implementation:** PyCairo-generated (same as text animations) or pre-rendered template sequences

#### 5.11 Pacing & Scene Duration Optimization
- **Problem:** Uniform scene durations = boring; viewers feel monotony subconsciously
- **Solution:** Two systems working together:

**Pacing Analyzer (Phase 3):**
- Classifies scenes: hook (3-5s), setup (8-12s), explanation (12-20s), emotional peak (5-8s), conclusion (10-15s)
- Rhythm mapping: start medium → build longer → peak short/rapid → valley long → end medium
- Anti-monotony: no 3+ scenes at same duration, max 3:1 ratio between adjacent scenes

**Scene Duration Optimizer (after voice generation):**
- Adjusts based on actual narration audio length (we now know exact timing)
- Scene ≥ narration + 0.5s breathing room
- Text overlay scenes: add (word_count / 3)s reading time
- Data/statistics: +3s comprehension time
- After emotional peak: +1-2s "landing" time
- Visual showcase: can extend 2-3s beyond narration

#### 5.12 Audio QA (inline after each audio step)
- **Problem:** Images/video have 3-layer QA. Audio has NOTHING. Audio = 50% of quality.
- **Solution:** QA checks after each audio generation step:

**Voice QA:**
- **Deterministic:** silence gaps, clipping, SNR, duration match, RMS consistency
- **Whisper STT verification:** transcribe generated audio → compare vs script → Word Error Rate (WER > 15% = pronunciation problem)
- **Arabic-specific:** ع vs أ confusion, ح vs ه confusion, tashkeel pronunciation, name pronunciation
- **Prosody:** pitch contour (monotone detection), speaking rate variation, emotion match vs scene tag
- **Bonus:** extracts word-level timestamps for word-by-word text animation sync

**Music QA:**
- Duration, Content ID, clipping, silence, volume level (-18 to -24 LUFS for background)
- Mood analysis: librosa features (tempo, key, energy) vs scene mood tag
- Transition smoothness between mood zones

**Mix QA (after compose):**
- Voice intelligibility: Whisper on mixed audio, WER shouldn't increase >5% vs isolated
- Music ducking: -12dB to -18dB ratio during speech
- SFX timing: no overlap with key narration
- Overall loudness: -14 LUFS (YouTube target), true peak < -1 dBTP
- A/V sync drift check

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

#### GPU Logging System (`src/utils/gpu_logger.py`) 📋

**Every single GPU operation is logged. No exceptions.**

```python
import logging
import time
import torch
import json
from datetime import datetime
from pathlib import Path

class GPULogger:
    """
    Precision logging for every GPU model operation.
    In single-GPU environment, one unlogged VRAM leak = full pipeline crash.
    """
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # File logger — persistent, survives crashes
        self.file_logger = logging.getLogger(f"gpu.{job_id}")
        handler = logging.FileHandler(
            f"logs/gpu/{self.session_id}_{job_id}.log",
            encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S"
        ))
        self.file_logger.addHandler(handler)
        self.file_logger.setLevel(logging.DEBUG)
        
        # Structured event log — for dashboard + post-mortem analysis
        self.events_path = Path(f"logs/gpu/{self.session_id}_{job_id}_events.jsonl")
        
        # VRAM snapshots — continuous timeline
        self.snapshots_path = Path(f"logs/gpu/{self.session_id}_{job_id}_vram.csv")
        self._init_vram_csv()
    
    def _get_vram_state(self) -> dict:
        """Snapshot current VRAM state from nvidia-smi level."""
        free, total = torch.cuda.mem_get_info()
        allocated = torch.cuda.memory_allocated()
        reserved = torch.cuda.memory_reserved()
        return {
            "total_gb": round(total / 1e9, 2),
            "free_gb": round(free / 1e9, 2),
            "used_gb": round((total - free) / 1e9, 2),
            "allocated_gb": round(allocated / 1e9, 2),
            "reserved_gb": round(reserved / 1e9, 2),
            "fragmented_gb": round((reserved - allocated) / 1e9, 2),
            "usage_pct": round((1 - free / total) * 100, 1),
            "temp_c": self._get_gpu_temp()
        }
    
    def _get_gpu_temp(self) -> int:
        """GPU temperature — overheating = throttling = slower generation."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            return int(result.stdout.strip())
        except:
            return -1
    
    def _log_event(self, event_type: str, data: dict):
        """Append structured event to JSONL file."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "job_id": self.job_id,
            "event": event_type,
            "vram": self._get_vram_state(),
            **data
        }
        with open(self.events_path, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    
    # ─── Model Lifecycle Logging ───────────────────────────
    
    def log_model_load_start(self, model_name: str, model_type: str, expected_vram_gb: float):
        vram = self._get_vram_state()
        self.file_logger.info(
            f"🔄 LOAD START | model={model_name} | type={model_type} | "
            f"expected_vram={expected_vram_gb}GB | "
            f"available_vram={vram['free_gb']}GB | temp={vram['temp_c']}°C"
        )
        if vram['free_gb'] < expected_vram_gb:
            self.file_logger.critical(
                f"⛔ INSUFFICIENT VRAM! Need {expected_vram_gb}GB but only {vram['free_gb']}GB free!"
            )
        self._log_event("model_load_start", {
            "model": model_name, "type": model_type,
            "expected_vram_gb": expected_vram_gb
        })
        return time.time()
    
    def log_model_load_end(self, model_name: str, start_time: float, success: bool):
        elapsed = round(time.time() - start_time, 2)
        vram = self._get_vram_state()
        status = "✅ SUCCESS" if success else "❌ FAILED"
        self.file_logger.info(
            f"{status} LOAD | model={model_name} | "
            f"took={elapsed}s | vram_used={vram['used_gb']}GB ({vram['usage_pct']}%) | "
            f"temp={vram['temp_c']}°C"
        )
        self._log_event("model_load_end", {
            "model": model_name, "success": success,
            "elapsed_sec": elapsed
        })
    
    def log_model_unload_start(self, model_name: str):
        vram = self._get_vram_state()
        self.file_logger.info(
            f"🗑️ UNLOAD START | model={model_name} | "
            f"vram_before={vram['used_gb']}GB ({vram['usage_pct']}%)"
        )
        self._log_event("model_unload_start", {"model": model_name})
        return time.time()
    
    def log_model_unload_end(self, model_name: str, start_time: float):
        elapsed = round(time.time() - start_time, 2)
        vram = self._get_vram_state()
        
        # CRITICAL CHECK: Did VRAM actually free?
        if vram['usage_pct'] > 15:  # >15% still used after unload = LEAK
            self.file_logger.critical(
                f"🚨 VRAM LEAK DETECTED! After unloading {model_name}: "
                f"still {vram['used_gb']}GB used ({vram['usage_pct']}%)"
            )
            self._log_event("vram_leak_detected", {
                "model": model_name, "leaked_gb": vram['used_gb']
            })
        else:
            self.file_logger.info(
                f"✅ UNLOAD COMPLETE | model={model_name} | "
                f"took={elapsed}s | vram_after={vram['used_gb']}GB ({vram['usage_pct']}%)"
            )
        self._log_event("model_unload_end", {
            "model": model_name, "elapsed_sec": elapsed
        })
    
    # ─── Generation Task Logging ───────────────────────────
    
    def log_generation_start(self, model_name: str, task: str, batch_size: int):
        vram = self._get_vram_state()
        self.file_logger.info(
            f"⚡ GEN START | model={model_name} | task={task} | "
            f"batch={batch_size} | vram={vram['used_gb']}GB | temp={vram['temp_c']}°C"
        )
        self._log_event("generation_start", {
            "model": model_name, "task": task, "batch_size": batch_size
        })
        return time.time()
    
    def log_generation_progress(self, model_name: str, current: int, total: int):
        vram = self._get_vram_state()
        pct = round(current / total * 100, 1)
        self.file_logger.info(
            f"📊 PROGRESS | model={model_name} | {current}/{total} ({pct}%) | "
            f"vram={vram['used_gb']}GB ({vram['usage_pct']}%) | temp={vram['temp_c']}°C"
        )
        # Alert if VRAM creeping up during batch (memory leak within generation)
        if vram['usage_pct'] > 85:
            self.file_logger.warning(
                f"⚠️ VRAM HIGH during generation! {vram['usage_pct']}% — potential leak"
            )
        if vram['temp_c'] > 85:
            self.file_logger.warning(
                f"🌡️ GPU HOT! {vram['temp_c']}°C — may throttle"
            )
        self._log_event("generation_progress", {
            "model": model_name, "current": current, "total": total
        })
    
    def log_generation_end(self, model_name: str, task: str, start_time: float, 
                           success: bool, items_produced: int):
        elapsed = round(time.time() - start_time, 2)
        rate = round(items_produced / elapsed * 60, 1) if elapsed > 0 else 0
        vram = self._get_vram_state()
        status = "✅" if success else "❌"
        self.file_logger.info(
            f"{status} GEN END | model={model_name} | task={task} | "
            f"produced={items_produced} | took={elapsed}s | rate={rate}/min | "
            f"vram={vram['used_gb']}GB | temp={vram['temp_c']}°C"
        )
        self._log_event("generation_end", {
            "model": model_name, "task": task, "success": success,
            "items_produced": items_produced, "elapsed_sec": elapsed,
            "rate_per_min": rate
        })
    
    # ─── VRAM Emergency Logging ────────────────────────────
    
    def log_vram_flush(self, reason: str, before_gb: float, after_gb: float):
        self.file_logger.warning(
            f"🔧 VRAM FLUSH | reason={reason} | "
            f"before={before_gb}GB → after={after_gb}GB | "
            f"freed={round(before_gb - after_gb, 2)}GB"
        )
        self._log_event("vram_flush", {
            "reason": reason, "before_gb": before_gb, "after_gb": after_gb
        })
    
    def log_oom_event(self, model_name: str, task: str, vram_state: dict):
        self.file_logger.critical(
            f"💥 OOM EVENT | model={model_name} | task={task} | "
            f"vram={vram_state['used_gb']}GB/{vram_state['total_gb']}GB | "
            f"temp={vram_state['temp_c']}°C"
        )
        self._log_event("oom_event", {
            "model": model_name, "task": task
        })
    
    def log_gpu_reset(self, reason: str):
        self.file_logger.critical(
            f"🔴 GPU RESET | reason={reason} | nvidia-smi --gpu-reset executed"
        )
        self._log_event("gpu_reset", {"reason": reason})
    
    # ─── VRAM Continuous Snapshots ─────────────────────────
    
    def _init_vram_csv(self):
        with open(self.snapshots_path, "w") as f:
            f.write("timestamp,used_gb,free_gb,allocated_gb,reserved_gb,fragmented_gb,usage_pct,temp_c,active_model\n")
    
    def snapshot_vram(self, active_model: str = "none"):
        """Called every 5 seconds by VRAMMonitor — builds continuous timeline."""
        vram = self._get_vram_state()
        with open(self.snapshots_path, "a") as f:
            f.write(
                f"{datetime.now().isoformat()},"
                f"{vram['used_gb']},{vram['free_gb']},"
                f"{vram['allocated_gb']},{vram['reserved_gb']},"
                f"{vram['fragmented_gb']},{vram['usage_pct']},"
                f"{vram['temp_c']},{active_model}\n"
            )
```

#### Log Output Example (real production run)
```
14:00:01.234 | INFO    | 🔄 LOAD START | model=qwen2.5:72b | type=llm | expected_vram=16GB | available_vram=23.5GB | temp=42°C
14:00:46.891 | INFO    | ✅ SUCCESS LOAD | model=qwen2.5:72b | took=45.66s | vram_used=15.8GB (65.8%) | temp=48°C
14:00:47.001 | INFO    | ⚡ GEN START | model=qwen2.5:72b | task=script_writing | batch=1 | vram=15.8GB | temp=48°C
14:15:22.445 | INFO    | ✅ GEN END | model=qwen2.5:72b | task=script_writing | produced=1 | took=875.44s | rate=0.1/min | vram=15.9GB | temp=61°C
14:15:22.500 | INFO    | ⚡ GEN START | model=qwen2.5:72b | task=scene_splitting | batch=1 | vram=15.9GB | temp=61°C
14:17:55.100 | INFO    | ✅ GEN END | model=qwen2.5:72b | task=scene_splitting | produced=62 | took=152.6s | rate=24.4/min | vram=15.9GB | temp=63°C
14:17:55.200 | INFO    | 🗑️ UNLOAD START | model=qwen2.5:72b | vram_before=15.9GB (66.3%)
14:17:58.500 | INFO    | ✅ UNLOAD COMPLETE | model=qwen2.5:72b | took=3.3s | vram_after=0.4GB (1.7%)
14:17:58.600 | INFO    | 🔄 LOAD START | model=FLUX.1-dev | type=comfyui | expected_vram=12GB | available_vram=23.2GB | temp=52°C
14:18:13.200 | INFO    | ✅ SUCCESS LOAD | model=FLUX.1-dev | took=14.6s | vram_used=12.1GB (50.4%) | temp=54°C
14:18:13.300 | INFO    | ⚡ GEN START | model=FLUX.1-dev | task=scene_images | batch=62 | vram=12.1GB | temp=54°C
14:18:43.500 | INFO    | 📊 PROGRESS | model=FLUX.1-dev | 5/62 (8.1%) | vram=12.3GB (51.3%) | temp=67°C
14:19:13.700 | INFO    | 📊 PROGRESS | model=FLUX.1-dev | 10/62 (16.1%) | vram=12.3GB (51.3%) | temp=71°C
...
14:48:22.100 | INFO    | 📊 PROGRESS | model=FLUX.1-dev | 60/62 (96.8%) | vram=12.5GB (52.1%) | temp=76°C
14:48:44.300 | WARNING | ⚠️ VRAM HIGH during generation! 87.2% — potential leak
14:48:50.900 | INFO    | ✅ GEN END | model=FLUX.1-dev | task=scene_images | produced=62 | took=1837.6s | rate=2.0/min | vram=12.5GB | temp=77°C
```

#### Log Files Structure
```
logs/
├── gpu/
│   ├── 20260310_060000_job_042.log           # Human-readable full log
│   ├── 20260310_060000_job_042_events.jsonl   # Structured events (for dashboard)
│   ├── 20260310_060000_job_042_vram.csv       # VRAM timeline (for graphs)
│   ├── 20260310_093000_job_043.log
│   └── ...
├── pipeline/
│   ├── 20260310_job_042.log                   # Phase-level pipeline log
│   └── ...
└── alerts/
    ├── oom_events.jsonl                        # All OOM events (critical review)
    ├── vram_leaks.jsonl                        # All detected leaks
    └── gpu_resets.jsonl                        # All forced GPU resets
```

#### Dashboard Integration (Optional)
```python
# FastAPI endpoint: real-time GPU status
@app.get("/api/gpu/status")
def gpu_status():
    vram = gpu_logger._get_vram_state()
    return {
        "vram": vram,
        "active_model": gpu_manager.current_name,
        "current_task": pipeline.current_task,
        "uptime_hours": get_uptime(),
        "today_stats": {
            "models_loaded": count_events("model_load_end", today=True),
            "oom_events": count_events("oom_event", today=True),
            "vram_leaks": count_events("vram_leak_detected", today=True),
            "total_generation_time_min": sum_generation_time(today=True)
        }
    }

# Telegram alert: immediate notification for critical events
def on_critical_event(event):
    if event["event"] in ["oom_event", "vram_leak_detected", "gpu_reset"]:
        send_telegram(
            f"🚨 GPU ALERT\n"
            f"Event: {event['event']}\n"
            f"Model: {event.get('model', 'N/A')}\n"
            f"VRAM: {event['vram']['used_gb']}GB / {event['vram']['total_gb']}GB\n"
            f"Temp: {event['vram']['temp_c']}°C\n"
            f"Time: {event['timestamp']}"
        )
```

#### Post-Mortem Analysis Tools
```python
# بعد كل فيديو — تقرير أداء GPU
def generate_gpu_report(job_id: str) -> dict:
    events = load_events(job_id)
    vram_timeline = load_vram_csv(job_id)
    
    return {
        "job_id": job_id,
        "total_time_min": calculate_total_time(events),
        "model_swaps": count_events_type(events, "model_load_start"),
        "total_swap_time_sec": sum_swap_times(events),
        "peak_vram_gb": vram_timeline["used_gb"].max(),
        "peak_temp_c": vram_timeline["temp_c"].max(),
        "avg_temp_c": vram_timeline["temp_c"].mean(),
        "oom_events": count_events_type(events, "oom_event"),
        "vram_leaks": count_events_type(events, "vram_leak_detected"),
        "vram_flushes": count_events_type(events, "vram_flush"),
        "generation_breakdown": {
            model: {
                "time_sec": sum_gen_time(events, model),
                "items": sum_gen_items(events, model),
                "rate_per_min": calc_rate(events, model)
            }
            for model in get_unique_models(events)
        },
        "health_score": calculate_health_score(events)
        # 100 = perfect (no leaks, no OOM, no resets)
        # <80 = needs investigation
        # <50 = critical — pipeline unreliable
    }
```

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

---

## Central Database Schema (SQLite) 🗄️

**The backbone connecting all 40 features. Every agent reads/writes here.**

Database file: `data/factory.db`

### Core Tables

#### `jobs` — Master job tracking (1 row = 1 video)
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,                    -- "job_20260310_001"
    status TEXT NOT NULL DEFAULT 'pending', -- pending → research → seo → script → compliance → 
                                           -- images → visual_qa → video → voice → music → sfx →
                                           -- compose → final_qa → manual_review → publish → 
                                           -- published → tracking_24h → tracking_7d → tracking_30d
    channel_id TEXT NOT NULL,               -- "documentary_ar"
    topic TEXT,                             -- "انهيار فنزويلا"
    topic_source TEXT,                      -- "trend_scanner" | "calendar" | "manual" | "trending_hijack"
    priority TEXT DEFAULT 'normal',         -- "normal" | "fast_track" | "seasonal"
    narrative_style TEXT,                   -- "investigative" | "storytelling" | "explainer" | etc.
    selected_voice_id TEXT,                 -- "v_male_auth_01" — from voice library
    voice_selection_reason TEXT,            -- Why this voice was chosen
    topic_region TEXT,                      -- "iraq" | "gulf" | "egypt" | "levant" | "maghreb" | "global"
    target_length_min INTEGER,              -- Dynamic length (Feature 37)
    
    -- Phase completion timestamps
    phase1_completed_at TIMESTAMP,
    phase2_completed_at TIMESTAMP,
    phase3_completed_at TIMESTAMP,
    phase4_completed_at TIMESTAMP,
    phase5_completed_at TIMESTAMP,
    phase6_completed_at TIMESTAMP,
    phase7_completed_at TIMESTAMP,
    phase7_5_completed_at TIMESTAMP,        -- Manual review
    phase8_completed_at TIMESTAMP,
    phase9_last_analysis TIMESTAMP,         -- Performance intelligence
    
    -- Phase retry counts
    script_revisions INTEGER DEFAULT 0,     -- How many times script was revised (max 3)
    image_regenerations INTEGER DEFAULT 0,  -- How many images were regenerated
    video_retries INTEGER DEFAULT 0,
    
    -- Blocking / errors
    blocked_at TIMESTAMP,                   -- If any QA gate blocked
    blocked_reason TEXT,
    blocked_phase TEXT,                      -- "phase4" | "phase6" | "phase7"
    resolved_at TIMESTAMP,
    
    -- Manual review (Phase 7.5)
    manual_review_required BOOLEAN DEFAULT FALSE,
    manual_review_status TEXT,              -- "pending" | "approved" | "rejected" | "reprocess"
    manual_review_notes TEXT,
    manual_review_at TIMESTAMP,
    
    -- Final output
    youtube_video_id TEXT,
    youtube_url TEXT,
    published_at TIMESTAMP,
    scheduled_for TIMESTAMP,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_production_time_sec INTEGER,
    total_gpu_time_sec INTEGER
);

-- Index for quick status queries
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_channel ON jobs(channel_id);
CREATE INDEX idx_jobs_created ON jobs(created_at);
```

#### `research` — Phase 1 trend data
```sql
CREATE TABLE research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    topic TEXT NOT NULL,
    source TEXT,                    -- "youtube_trending" | "google_trends" | "news_rss" | "competitor"
    search_volume INTEGER,
    competition_score FLOAT,        -- 0-1 (lower = less competition)
    trend_velocity FLOAT,           -- Rising speed
    category TEXT,
    suggested_angle TEXT,
    rank_score FLOAT,               -- Combined ranking score
    raw_data JSON,                  -- Full API response
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `seo_data` — Phase 2 keyword & SEO analysis
```sql
CREATE TABLE seo_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    
    -- Keywords
    primary_keywords JSON,          -- ["فنزويلا", "انهيار اقتصادي", "نفط"]
    secondary_keywords JSON,
    long_tail_keywords JSON,
    
    -- Titles
    generated_titles JSON,          -- [{title, seo_score, keyword_density}]
    selected_title TEXT,
    selected_title_score FLOAT,
    
    -- Tags & Description
    tags JSON,                      -- 30 tags
    description_template TEXT,
    hashtags JSON,
    
    -- Competitor analysis
    top_competitors JSON,           -- [{channel, title, views, tags, description}]
    unique_angle TEXT,
    content_gap TEXT,
    
    -- Thumbnail keywords
    thumbnail_text_suggestions JSON, -- Suggested text for thumbnails
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `scripts` — Phase 3 scripts with revision history
```sql
CREATE TABLE scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    version INTEGER DEFAULT 1,      -- Revision number (1, 2, 3)
    status TEXT DEFAULT 'draft',    -- "draft" | "reviewing" | "approved" | "rejected"
    
    -- Script content
    full_text TEXT NOT NULL,         -- Complete Arabic script
    word_count INTEGER,
    estimated_duration_sec INTEGER,
    
    -- Structure
    hook_text TEXT,
    sections JSON,                  -- [{title, text, duration_sec}]
    conclusion_text TEXT,
    
    -- SEO integration
    keywords_included JSON,         -- Which SEO keywords appear in script
    keyword_density FLOAT,
    
    -- Emotional arc (Feature 29)
    emotional_arc JSON,             -- [{section, emotion, intensity_1_to_10}]
    
    -- Review results
    reviewer_notes TEXT,
    factual_accuracy_score FLOAT,
    engagement_score FLOAT,
    arabic_quality_score FLOAT,
    
    -- Research sources
    sources JSON,                   -- [{url, title, claims_supported}]
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_scripts_job ON scripts(job_id);
```

#### `scenes` — Scene-level data (the core unit connecting everything)
```sql
CREATE TABLE scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    scene_index INTEGER NOT NULL,   -- 0, 1, 2, ... (order)
    
    -- Script data
    narration_text TEXT NOT NULL,
    duration_sec FLOAT,
    
    -- Visual
    visual_prompt TEXT,
    visual_style TEXT,
    camera_movement TEXT,
    expected_elements JSON,         -- ["astronaut", "moon_surface"]
    
    -- Generated assets (file paths)
    image_path TEXT,                -- "output/images/job_042/scene_001.png"
    image_upscaled_path TEXT,       -- 4K version (Feature 33)
    video_clip_path TEXT,           -- "output/videos/job_042/scene_001.mp4"
    voice_path TEXT,                -- "output/audio/job_042/voice_001.wav"
    
    -- Generation metadata
    image_seed INTEGER,
    image_score FLOAT,              -- Visual QA score (1-10)
    image_regenerated BOOLEAN DEFAULT FALSE,
    video_method TEXT,              -- "ltx23" | "ken_burns" (fallback)
    voice_emotion TEXT,             -- "dramatic" | "calm" | etc. (Feature 30)
    voice_speed FLOAT DEFAULT 1.0,
    
    -- Audio
    music_mood TEXT,
    sfx_tags JSON,                  -- ["explosion", "crowd"]
    sfx_paths JSON,                 -- Generated SFX file paths
    
    -- Text overlay
    text_overlay JSON,              -- {text, style, position, animation}
    
    -- Presenter (Feature 32)
    presenter_mode TEXT,            -- "pip" | "fullscreen" | "none"
    presenter_path TEXT,            -- Generated presenter video path
    
    -- Timing (for final compose)
    start_time_sec FLOAT,          -- Position in final video
    end_time_sec FLOAT,
    transition_type TEXT,           -- "crossfade" | "cut" | "dissolve"
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_scenes_job ON scenes(job_id);
CREATE INDEX idx_scenes_order ON scenes(job_id, scene_index);
```

#### `compliance_checks` — Phase 4 + 7 QA results
```sql
CREATE TABLE compliance_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    phase TEXT NOT NULL,             -- "phase4_script" | "phase7_final"
    check_type TEXT NOT NULL,        -- "youtube_policy" | "copyright" | "fact_check" | "arabic_quality"
    
    status TEXT,                     -- "pass" | "warn" | "fail" | "block"
    score FLOAT,
    details TEXT,                    -- Explanation
    flagged_items JSON,             -- Specific issues found
    
    -- Fact checking specifics
    claims_checked INTEGER,
    claims_verified INTEGER,
    claims_unverified JSON,         -- [{claim, reason}]
    
    auto_fixed BOOLEAN DEFAULT FALSE,
    fix_description TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `qa_rubrics` — Full QA rubric storage for every asset check
```sql
CREATE TABLE qa_rubrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    scene_index INTEGER,                -- NULL for job-level checks (final video)
    asset_type TEXT NOT NULL,            -- 'image' | 'video' | 'thumbnail' | 'final_video'
    check_phase TEXT NOT NULL,           -- 'phase6a' | 'phase6b' | 'phase7' | 'phase8'
    attempt_number INTEGER DEFAULT 1,    -- Which attempt (1st, 2nd after regen...)
    
    -- Layer 1: Deterministic results
    deterministic_results JSON,          -- {text_detected, nsfw_score, blur_score, artifacts: [...]}
    deterministic_pass BOOLEAN,
    hard_fail_reason TEXT,               -- NULL if passed
    
    -- Layer 2: Vision rubric (per-axis scores)
    rubric_scores JSON,                  -- {axis_name: {score, reasoning, confidence}, ...}
    
    -- Layer 3: Combined verdict
    weighted_score REAL,                 -- Deterministic formula result
    final_verdict TEXT NOT NULL,          -- 'pass'|'regen_adjust'|'regen_new'|'fail'|'flag_human'
    flags JSON,                          -- ["low_confidence_composition", "near_threshold", ...]
    
    -- Metadata
    model_used TEXT,                     -- 'qwen2.5-vl:72b'
    inference_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_rubrics_job ON qa_rubrics(job_id);
CREATE INDEX idx_rubrics_verdict ON qa_rubrics(final_verdict);
```

**Why store everything?** Phase 9 uses rubric history to:
- Learn which FLUX prompts produce low-scoring images → improve prompt templates
- Track which axes are weak (e.g., always low on "composition") → adjust weights
- Measure regen rates → optimize pipeline speed
- Identify patterns: "political topics always need more retries" → adjust thresholds

---

#### `audio_tracks` — Music + SFX with Content ID protection
```sql
CREATE TABLE audio_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    track_type TEXT NOT NULL,        -- "intro_music" | "background" | "tension" | "outro" | "sfx"
    
    -- Generation
    prompt TEXT,
    file_path TEXT,
    duration_sec FLOAT,
    seed INTEGER,
    temperature FLOAT,
    
    -- Content ID protection (Feature 5.4.1)
    fingerprint BLOB,
    similarity_score FLOAT,          -- vs known songs database
    content_id_safe BOOLEAN,
    youtube_precheck_result TEXT,     -- "clean" | "claimed" | "not_checked"
    
    -- Post-processing
    pitch_shifted BOOLEAN DEFAULT FALSE,
    time_stretched BOOLEAN DEFAULT FALSE,
    reverb_added BOOLEAN DEFAULT FALSE,
    
    -- If regenerated
    regeneration_count INTEGER DEFAULT 0,
    regeneration_reason TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Publishing & Analytics Tables

#### `thumbnails` — Thumbnail generation + A/B testing
```sql
CREATE TABLE thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    variant TEXT,                     -- "A" | "B" | "C"
    file_path TEXT,
    
    -- Generation
    prompt TEXT,
    text_overlay TEXT,               -- Arabic text on thumbnail
    text_position TEXT,              -- "center_top" | "right_center"
    style TEXT,                      -- "bold_dramatic" | "minimal" | "colorful"
    
    -- Validation (Feature 17)
    readability_score FLOAT,         -- Vision LLM check at 320x180
    youtube_ui_overlap BOOLEAN,      -- Does text overlap with timestamp/duration?
    
    -- A/B test results (Feature 8.1)
    ab_test_id TEXT,                 -- YouTube Test & Compare ID
    impressions INTEGER,
    clicks INTEGER,
    ctr FLOAT,                       -- Click-through rate
    is_winner BOOLEAN,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `subtitles` — SRT files (Feature 8.2.5)
```sql
CREATE TABLE subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    language TEXT,                    -- "ar" | "en" | "tr" | etc.
    srt_path TEXT,
    word_count INTEGER,
    uploaded_to_youtube BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `youtube_analytics` — Performance tracking (Feature 8.4)
```sql
CREATE TABLE youtube_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    youtube_video_id TEXT,
    snapshot_period TEXT,             -- "24h" | "48h" | "7d" | "30d" | "90d"
    
    -- Core metrics
    views INTEGER,
    watch_time_hours FLOAT,
    avg_view_duration_sec INTEGER,
    avg_view_percentage FLOAT,       -- Retention %
    
    -- Engagement
    likes INTEGER,
    dislikes INTEGER,
    comments INTEGER,
    shares INTEGER,
    
    -- Discovery
    impressions INTEGER,
    ctr FLOAT,
    traffic_sources JSON,            -- {browse: 40%, search: 30%, suggested: 20%, external: 10%}
    
    -- Revenue
    estimated_revenue FLOAT,
    rpm FLOAT,                       -- Revenue per mille
    cpm FLOAT,                       -- Cost per mille
    
    -- Retention curve (Feature 12)
    retention_curve JSON,            -- [{time_sec, retention_pct}] — every 5 seconds
    drop_off_points JSON,            -- [{time_sec, drop_pct, scene_index}]
    
    -- Audience
    top_countries JSON,
    age_groups JSON,
    gender_split JSON,
    device_split JSON,
    
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analytics_job ON youtube_analytics(job_id);
CREATE INDEX idx_analytics_period ON youtube_analytics(snapshot_period);
```

#### `shorts` — YouTube Shorts tracking (Feature 9)
```sql
CREATE TABLE shorts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_job_id TEXT REFERENCES jobs(id),  -- Source long-form video
    youtube_video_id TEXT,
    
    -- Content
    source_scene_start INTEGER,      -- Which scene range was extracted
    source_scene_end INTEGER,
    title TEXT,
    tags JSON,
    file_path TEXT,
    duration_sec FLOAT,
    
    -- Performance
    views INTEGER,
    likes INTEGER,
    retention_pct FLOAT,
    
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Intelligence Tables

#### `competitor_channels` — Competitor monitoring (Feature 27)
```sql
CREATE TABLE competitor_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE,          -- YouTube channel ID
    channel_name TEXT,
    category TEXT,                   -- "documentary" | "politics" | etc.
    subscriber_count INTEGER,
    total_videos INTEGER,
    avg_views_per_video INTEGER,
    last_scanned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE competitor_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_channel_id TEXT REFERENCES competitor_channels(channel_id),
    youtube_video_id TEXT UNIQUE,
    title TEXT,
    topic TEXT,
    views INTEGER,
    published_at TIMESTAMP,
    tags JSON,
    description TEXT,
    view_velocity FLOAT,             -- Views per hour in first 24h
    is_viral BOOLEAN DEFAULT FALSE,  -- >500K views in 24h
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `content_calendar` — Planned content (Feature 11)
```sql
CREATE TABLE content_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT,
    planned_date DATE,
    topic TEXT,
    narrative_style TEXT,
    priority TEXT DEFAULT 'normal',
    source TEXT,                      -- "calendar_agent" | "manual" | "seasonal" | "trending"
    status TEXT DEFAULT 'planned',   -- "planned" | "approved" | "in_production" | "published" | "cancelled"
    job_id TEXT REFERENCES jobs(id), -- Linked once production starts
    approved_by TEXT,                -- "yusif" | "auto"
    approved_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_calendar_date ON content_calendar(planned_date);
```

#### `seasonal_events` — Pre-planned seasonal content (Feature 34)
```sql
CREATE TABLE seasonal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT,                  -- "رمضان"
    event_date DATE,                 -- Actual event date
    prep_start_date DATE,            -- When to start producing
    channel_id TEXT,
    topics JSON,                     -- Suggested topics for this event
    status TEXT DEFAULT 'upcoming',  -- "upcoming" | "producing" | "ready" | "published"
    job_ids JSON,                    -- Linked video jobs
    recurring BOOLEAN DEFAULT TRUE,  -- Repeats yearly?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `script_templates` — Evolved templates (Feature 24)
```sql
CREATE TABLE script_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,                       -- "high_retention_v3"
    narrative_style TEXT,
    channel_id TEXT,                 -- NULL = universal
    version INTEGER DEFAULT 1,
    
    -- Structure
    hook_type TEXT,                  -- "shocking_fact" | "rhetorical_question" | "mystery"
    hook_max_sec INTEGER,
    section_count INTEGER,
    section_avg_sec INTEGER,
    transition_style TEXT,
    conclusion_type TEXT,
    
    -- Performance basis
    based_on_jobs JSON,             -- Job IDs this template learned from
    avg_retention_pct FLOAT,
    avg_watch_time_sec INTEGER,
    sample_size INTEGER,            -- How many videos contributed
    
    -- Status
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retired_at TIMESTAMP            -- When replaced by better template
);
```

#### `anti_repetition` — Pattern tracking (Feature 18)
```sql
CREATE TABLE anti_repetition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    channel_id TEXT,
    
    -- Tracked patterns
    hook_style TEXT,                 -- "question" | "shocking_fact" | "mystery" | "narrative"
    title_structure TEXT,            -- "كيف...؟" | "لماذا...؟" | "الحقيقة وراء..."
    visual_palette TEXT,            -- "dark_cinematic" | "warm_golden" | "cool_blue"
    music_mood TEXT,
    narrative_style TEXT,
    
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_antirepeat_channel ON anti_repetition(channel_id, published_at);
```

#### `ab_tests` — A/B testing results (Feature 40)
```sql
CREATE TABLE ab_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_type TEXT,                  -- "hook_style" | "video_length" | "narration_speed" | "music_intensity"
    
    -- Variants
    variant_a_job_id TEXT REFERENCES jobs(id),
    variant_a_description TEXT,
    variant_b_job_id TEXT REFERENCES jobs(id),
    variant_b_description TEXT,
    
    -- Results (after 30 days)
    variant_a_retention FLOAT,
    variant_a_ctr FLOAT,
    variant_a_watch_time FLOAT,
    variant_a_revenue FLOAT,
    variant_b_retention FLOAT,
    variant_b_ctr FLOAT,
    variant_b_watch_time FLOAT,
    variant_b_revenue FLOAT,
    
    winner TEXT,                     -- "A" | "B" | "inconclusive"
    lesson_learned TEXT,             -- Fed to script_templates
    
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `audience_insights` — Audience intelligence (Feature 22)
```sql
CREATE TABLE audience_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT,
    snapshot_date DATE,
    
    -- Demographics
    top_countries JSON,
    age_distribution JSON,
    gender_split JSON,
    peak_watch_hours JSON,           -- [{hour, viewer_count}]
    device_split JSON,
    
    -- Comment mining
    topic_requests JSON,             -- ["سووا فيديو عن...", ...]
    sentiment_score FLOAT,           -- -1 to 1
    common_questions JSON,
    common_complaints JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `community_engagement` — Comment management (Feature 14)
```sql
CREATE TABLE community_engagement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    youtube_comment_id TEXT,
    
    action TEXT,                     -- "reply" | "heart" | "pin" | "hide" | "report"
    original_comment TEXT,
    reply_text TEXT,                 -- Our generated reply
    sentiment TEXT,                  -- "positive" | "negative" | "neutral" | "spam" | "request"
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `repurposed_content` — Multi-platform tracking (Feature 21)
```sql
CREATE TABLE repurposed_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    platform TEXT,                   -- "twitter" | "instagram" | "blog" | "podcast" | "telegram" | "pinterest"
    content_type TEXT,               -- "thread" | "reel" | "article" | "audio" | "post" | "pin"
    
    content TEXT,                    -- The actual content (or file path)
    file_path TEXT,
    platform_post_id TEXT,           -- ID on the platform after publishing
    platform_url TEXT,
    
    -- Performance
    views INTEGER,
    engagement INTEGER,              -- Likes + comments + shares
    
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `revenue` — Revenue tracking (Feature 25)
```sql
CREATE TABLE revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    channel_id TEXT,
    date DATE,
    
    -- AdSense
    adsense_revenue FLOAT,
    rpm FLOAT,
    cpm FLOAT,
    
    -- Sponsorship (Feature 20)
    sponsor_name TEXT,
    sponsor_revenue FLOAT,
    sponsor_segment_skip_rate FLOAT,
    
    -- Mid-roll (Feature 19)
    midroll_count INTEGER,
    midroll_revenue FLOAT,
    midroll_positions JSON,          -- [{time_sec, drop_off_pct}]
    
    -- Totals
    total_revenue FLOAT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_revenue_date ON revenue(date);
CREATE INDEX idx_revenue_channel ON revenue(channel_id);
```

#### `performance_rules` — Phase 9 auto-learned rules
```sql
CREATE TABLE performance_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT UNIQUE,              -- "intro_max_sec"
    rule_value TEXT,                    -- "20"
    rule_type TEXT,                     -- "script" | "visual" | "audio" | "publish" | "thumbnail"
    confidence FLOAT,                   -- 0-1 (based on sample size)
    sample_size INTEGER,                -- How many videos contributed
    reason TEXT,                        -- "Intros >20s lose 15% viewers"
    applies_to_channel TEXT,            -- NULL = all channels
    
    -- Source data
    discovery_date DATE,
    based_on_metric TEXT,               -- "retention" | "ctr" | "watch_time" | "revenue"
    metric_improvement_pct FLOAT,       -- "+15%"
    
    active BOOLEAN DEFAULT TRUE,
    superseded_by INTEGER REFERENCES performance_rules(id),  -- Newer rule replaced this
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `algorithm_signals` — YouTube algorithm tracking (Feature 39)
```sql
CREATE TABLE algorithm_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE,
    channel_id TEXT,
    
    -- Signals
    avg_impressions INTEGER,
    avg_ctr FLOAT,
    impression_change_pct FLOAT,     -- vs 7-day average
    traffic_source_shift JSON,       -- Changes in traffic distribution
    
    -- Cross-reference
    competitors_also_dropped BOOLEAN,
    detected_algorithm_change BOOLEAN,
    recommended_action TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Database Relationships Diagram
```
                    ┌──────────────┐
                    │    jobs      │ ← Master table (1 row = 1 video)
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────────────────────┐
          │                │                                │
    ┌─────▼──────┐  ┌──────▼───────┐              ┌────────▼────────┐
    │  research  │  │   seo_data   │              │    scripts      │
    │ (Phase 1)  │  │  (Phase 2)   │              │   (Phase 3)     │
    └────────────┘  └──────────────┘              └─────────────────┘
                                                          │
                    ┌──────────────┐              ┌───────▼─────────┐
                    │ compliance   │◄─────────────│     scenes      │
                    │  _checks     │              │  (Phase 3→5→6)  │
                    │ (Phase 4+7)  │              │ images, video,  │
                    └──────────────┘              │ voice, overlays │
                                                  └───────┬─────────┘
          ┌────────────────┼────────────────────────────────┤
          │                │                                │
    ┌─────▼──────┐  ┌──────▼───────┐              ┌────────▼────────┐
    │audio_tracks│  │  thumbnails  │              │    shorts       │
    │(Phase 5)   │  │ (Phase 8)   │              │  (Feature 9)    │
    │ +ContentID │  │  +A/B test   │              └─────────────────┘
    └────────────┘  └──────────────┘
                                                  ┌─────────────────┐
    ┌────────────┐  ┌──────────────┐              │  repurposed     │
    │ youtube    │  │  revenue     │              │  _content       │
    │ _analytics │  │ (Feature 25) │              │ (Feature 21)    │
    │(Feature 8) │  └──────────────┘              └─────────────────┘
    └────────────┘
                    ┌──────────────┐  ┌───────────────────┐
                    │ content      │  │ script_templates  │
                    │ _calendar    │  │ (Feature 24)      │
                    │(Feature 11)  │  └───────────────────┘
                    └──────────────┘
                                      ┌───────────────────┐
    ┌────────────┐  ┌──────────────┐  │ audience          │
    │ competitor │  │ algorithm    │  │ _insights         │
    │ _channels  │  │ _signals     │  │ (Feature 22)      │
    │ _videos    │  │(Feature 39)  │  └───────────────────┘
    └────────────┘  └──────────────┘
                                      ┌───────────────────┐
    ┌────────────┐  ┌──────────────┐  │ community         │
    │ ab_tests   │  │ anti         │  │ _engagement       │
    │(Feature 40)│  │ _repetition  │  │ (Feature 14)      │
    └────────────┘  │(Feature 18)  │  └───────────────────┘
                    └──────────────┘
```

### Database Access Pattern
```python
# src/utils/database.py

class FactoryDB:
    """Central database access for all agents."""
    
    def __init__(self, db_path="data/factory.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")    # Write-ahead logging (concurrent reads)
        self.conn.execute("PRAGMA foreign_keys=ON")      # Enforce relationships
        self.conn.execute("PRAGMA busy_timeout=5000")    # Wait 5s if locked
    
    # ─── Job Management ────────────────────
    def create_job(self, channel_id, topic, **kwargs) -> str: ...
    def update_job_status(self, job_id, status) -> None: ...
    def get_job(self, job_id) -> dict: ...
    def get_active_jobs(self) -> list: ...
    def get_blocked_jobs(self) -> list: ...
    
    # ─── Phase Data ────────────────────────
    def save_research(self, job_id, topics) -> None: ...
    def save_seo_data(self, job_id, keywords, titles, tags) -> None: ...
    def save_script(self, job_id, text, version) -> int: ...
    def save_scenes(self, job_id, scenes_list) -> None: ...
    def save_compliance_check(self, job_id, phase, results) -> None: ...
    
    # ─── Asset Tracking ────────────────────
    def update_scene_image(self, job_id, scene_index, path, score) -> None: ...
    def update_scene_video(self, job_id, scene_index, path, method) -> None: ...
    def update_scene_voice(self, job_id, scene_index, path) -> None: ...
    def save_audio_track(self, job_id, track_type, path, fingerprint) -> None: ...
    
    # ─── Analytics & Intelligence ──────────
    def save_analytics(self, job_id, period, metrics) -> None: ...
    def get_retention_curve(self, job_id) -> list: ...
    def get_revenue_by_channel(self, channel_id, days=30) -> dict: ...
    def get_best_performing_jobs(self, channel_id, limit=20) -> list: ...
    
    # ─── Anti-Repetition ───────────────────
    def log_content_pattern(self, job_id, patterns) -> None: ...
    def get_recent_patterns(self, channel_id, last_n=10) -> list: ...
    
    # ─── Cross-Agent Queries ───────────────
    def get_pipeline_status(self) -> dict:
        """Dashboard: status of all active jobs."""
        return {
            "active": self.get_active_jobs(),
            "blocked": self.get_blocked_jobs(),
            "today_published": self.get_published_today(),
            "queue_size": self.get_pending_count()
        }
```

### Checkpoint & Recovery
```python
# Every phase updates job status BEFORE starting work:
db.update_job_status(job_id, "images")  # Mark: now generating images

# If pipeline crashes and restarts:
def resume_pipeline(job_id):
    job = db.get_job(job_id)
    status = job['status']
    
    # Resume from last completed phase
    if status == "images":
        # Check which scenes already have images
        scenes = db.get_scenes(job_id)
        remaining = [s for s in scenes if not s['image_path']]
        # Generate only missing images
        generate_images(remaining)
    elif status == "video":
        # Check which scenes already have video clips
        remaining = [s for s in scenes if not s['video_clip_path']]
        generate_videos(remaining)
    # ... etc
```

### Database Maintenance
```python
# Periodic cleanup (cron job — weekly)
def cleanup_database():
    # Archive analytics older than 90 days to separate file
    db.execute("INSERT INTO archive.youtube_analytics SELECT * FROM youtube_analytics WHERE captured_at < date('now', '-90 days')")
    db.execute("DELETE FROM youtube_analytics WHERE captured_at < date('now', '-90 days')")
    
    # Vacuum to reclaim space
    db.execute("VACUUM")
    
    # Log database size
    size_mb = os.path.getsize("data/factory.db") / 1e6
    logger.info(f"Database size: {size_mb:.1f}MB")
```

---

## Phase 6: QA — Deep Visual Verification ✅ GATE (TWO STAGES)

> **Vision Model: Qwen2.5-VL 72B** — strongest open-source vision model.
> Runs locally via Ollama. Far more accurate than Llama Vision 11B.
> 
> **Phase 6 runs TWICE** — once for images, once for video clips.

### ⚠️ Design Principles

**1. Vision = Judge, NOT Source of Truth**
The Vision LLM scores and flags — it does NOT make final pass/fail decisions alone.
Vision LLMs can hallucinate confidence, miss subtle errors, or over-approve.
All decisions combine: **Vision rubric scores + deterministic checks + calculated thresholds.**

**2. Structured Rubric, NOT vague pass/fail**
Every image/video scored on specific axes (semantic match, composition, artifacts, style, emotion...)
with per-axis confidence levels. Low confidence on ANY axis = flag for human review.

**3. Vision CANNOT verify historical accuracy**
For documentary/political content, Vision can say "this looks like a documentary frame"
but CANNOT reliably verify correct uniforms, flags, military ranks, or era-appropriate details.
Historical accuracy is enforced **upstream**:
- Phase 3: `HistoricalContextValidator` embeds constraints in visual prompts
- Phase 5: Prompt engineering with era-specific negative prompts
- Phase 4: Sensitive topics → auto-route to manual review (Phase 7.5)

**4. Sequence checking = conservative**
Evaluating visual flow across scenes is genuinely hard. Approach: only flag **OBVIOUS** breaks
with high confidence. Use sliding windows (3 images at a time), not all-at-once.
Better to miss a subtle issue than give false confidence.

### Stage 6A: Image ↔ Script Verification (after FLUX, before LTX)

#### 6A.1 Two-Layer Image Verification

**Layer 1: Deterministic Checks (no LLM — hard rules):**
- OCR text detection (Tesseract/EasyOCR) → any text = AUTOMATIC FAIL
- NSFW classifier (NudeNet, local) → score > 0.5 = AUTOMATIC FAIL
- Blur detection (Laplacian variance) → below threshold = FAIL
- AI artifact detector (extra fingers/limbs, face distortion via dlib)
- Black/white/corrupt frame detection
- File integrity check

**Layer 2: Vision LLM Rubric (Qwen2.5-VL — 7 axes):**
- **A. Semantic Match** (1-10): Does image convey the MEANING of the narration?
- **B. Visual Element Presence**: Which expected elements are present/absent/uncertain?
- **C. Composition Quality** (1-10): Well-composed for documentary?
- **D. Style Fit** (1-10): Matches the target style (cinematic/editorial/archival)?
- **E. Artifact Severity** (1-10): Visible AI generation artifacts?
- **F. Cultural Appropriateness** (1-10): Appropriate for target region audience?
- **G. Emotional Tone Match** (1-10): Visual mood matches scene emotion?
- Each axis includes: score + one-line reasoning + confidence (high/medium/low)

**Layer 3: Combined Verdict (deterministic formula, NOT LLM opinion):**
- Weighted score = semantic(0.25) + elements(0.20) + composition(0.15) + style(0.10) + artifacts(0.15) + cultural(0.05) + emotion(0.10)
- Hard fails override: text detected, NSFW, corrupt, extra limbs, any axis confidence="low"
- Thresholds: ≥7.0 PASS, 4.0-6.9 regen with adjustment, <4.0 regen with new prompt

#### 6A.2 Style Consistency Check (Two-Layer)
- **Deterministic:** Color histogram comparison (OpenCV), brightness/contrast distribution, pairwise distance → outlier = >2 std deviations
- **Vision LLM:** All images sent to Qwen2.5-VL — note art style, color temperature, lighting per image, flag breaks
- **Combined:** Both layers agree = high confidence flag; deterministic only = medium; LLM only = note (don't fail)

#### 6A.3 Sequence Flow Check (Conservative)
- **Deterministic:** Scene-to-scene color shift magnitude, CLIP embeddings similarity, brightness flow
- **Vision LLM:** Sliding window of 3 consecutive images + narration — only flag OBVIOUS jarring transitions
- **⚠️ Conservative by design:** Only flag high-confidence breaks. Better to miss a subtle issue than give false confidence that "sequence is perfect"

#### 6A.4 Telegram Image Gallery 📱
- **Every image sent to Yusif** via Telegram album with:
  - Scene number, narration text, QA score, missing elements
- Summary message with inline buttons: `[Approve All] [Regenerate Failed] [View Details]`

#### 6A.5 Before/After Comparison (on regeneration)
- When an image is regenerated, send **BOTH versions** to Telegram:
  - Original image + score + issues list
  - Regenerated image + new score + improvements
  - Prompt changes highlighted (what was added/removed/modified)
  - Inline buttons: `[✅ Accept] [🔄 Try Again] [✏️ Edit Prompt]`
- Same treatment for video clips after regen
- Both versions stored in `qa_rubrics` (attempt_number tracks which try)

### Gate 6A
```
IF >90% images pass (score ≥ 7) → proceed to LTX video generation
IF 70-90% pass → regenerate failed ones (1 round), re-verify
IF <70% pass → BLOCK + alert Yusif
```

### Stage 6B: Video Clip ↔ Script Verification (after LTX, before voice)

#### 6B.1 Two-Layer Video Clip Verification

**Layer 1: Deterministic Video Checks (no LLM):**
- Frame-to-frame optical flow → detect frozen frames (zero flow) and sudden jumps
- Temporal consistency (SSIM between adjacent frames) → SSIM drop > 0.3 = glitch
- OCR on all keyframes → any text = AUTOMATIC FAIL
- Black/white/corrupt frame detection
- Duration check vs expected, FPS consistency

**Layer 2: Vision LLM Rubric (Qwen2.5-VL — 5 axes on keyframes):**
- **A. Motion Plausibility** (1-10): Do keyframes show believable motion?
- **B. Script Motion Match** (1-10): Does movement match the motion prompt?
- **C. Temporal Coherence** (1-10): Logical time progression? No teleporting objects?
- **D. AI Artifact Severity** (1-10): Morphing, warping, flickering, melting?
- **E. Source Image Fidelity** (1-10): Did LTX preserve or degrade the source image?
- Each axis: score + reasoning + confidence level

**Layer 3: Combined Verdict + Fallback Logic:**
- Weighted formula: motion(0.25) + script(0.25) + temporal(0.20) + artifacts(0.20) + fidelity(0.10)
- Hard fails: text detected, >30% frozen frames, >2 SSIM glitches
- **Fallback logic** (on FAIL):
  - artifacts bad BUT source good → "regen_video" (retry LTX, different motion)
  - source fidelity bad → "regen_image" (go back to FLUX)
  - motion keeps failing after 2 retries → "ken_burns" (LTX can't do this)

#### 6B.2 Telegram Video Gallery 📱
- **Every video clip sent to Yusif** via Telegram with:
  - Scene number, narration text, motion description, QA score
- Summary with inline buttons: `[Approve All] [View Flagged] [Reject & Regen]`

### Gate 6B
```
IF >85% clips pass → proceed to voice generation
IF 60-85% pass → regenerate failed (LTX retry or Ken Burns fallback), re-verify
IF <60% pass → BLOCK + alert Yusif
```

### Flow Summary
```
FLUX images → 6A (image QA) → LTX video → 6B (video QA) → Voice
                  ↑                              ↑
                  └─ regen loop                   └─ regen/fallback loop
```

---

## Phase 6C: Text Overlay QA ✅ GATE (NEW)

### Purpose
After FFmpeg composes the video with Arabic text overlays — verify overlays are readable, positioned correctly, and timed properly. This catches problems that ONLY exist after composition.

### Components

#### 6C.1 Two-Layer Overlay Verification

**Layer 1: Deterministic (hard rules):**
- **OCR verification:** Extract frame at each overlay timestamp → OCR (EasyOCR Arabic) → compare vs expected text → match < 80% = unreadable
- **Contrast ratio:** Text region vs background → WCAG AA minimum 4.5:1
- **Safe zone check:** Text not in top 5% (YouTube title bar) or bottom 10% (YouTube controls)
- **Timing sync:** Overlay appears/disappears within ±0.5s of narration → off by >1.0s = fail
- **Minimum display:** Each overlay visible for ≥ 2 seconds
- **RTL check:** Arabic text renders right-to-left correctly, no reversed characters

**Layer 2: Vision LLM (supplementary):**
- Qwen2.5-VL checks: readability, positioning, visual integration with documentary style, occlusion of key content
- 4 axes, each with score + reasoning + confidence

**Auto-fix on failure** (up to 2 retries):
- Low contrast → add semi-transparent dark box behind text
- Bad position → reposition to safe zone
- Timing off → adjust FFmpeg overlay timestamps
- Font too small → increase size
- RTL broken → switch to Noto Naskh Arabic font

### Gate Logic
```
IF all overlays pass (deterministic + vision) → proceed to Final QA
IF auto-fixable issues → re-compose with fixes → re-check (max 2 retries)
IF 2 retries failed → BLOCK + alert Yusif
```

---

## Phase 7: QA — Final Assembled Video Check ✅ GATE

### Purpose
After FFmpeg composes the **FULL** final video (all clips + voice + music + SFX + text overlays) — verify the assembled product is correct.

> **Vision Model: Qwen2.5-VL 72B** — same model as Phase 6, used here on the FINAL assembled video.

### Components

#### 7.1 Technical Quality Check (automated — CPU only)
- **Audio-Video Sync:**
  - Narration aligns with correct scenes
  - No audio drift over time
  - Music doesn't overpower narration (volume levels)
- **Duration Check:**
  - Total video length matches expected (8-12 min)
  - No scenes too short (<2s) or too long (>20s)
  - No black frames or frozen frames
- **Resolution & Bitrate:**
  - Minimum 1080p, bitrate adequate
  - Audio quality (no clipping, no silence gaps)
- **File Integrity:**
  - MP4 valid and playable, no corruption

#### 7.2 Content Coherence — Vision Check (Qwen2.5-VL 72B)
- **Extract 1 keyframe per scene** from the FINAL assembled video
- **Qwen2.5-VL analyzes** keyframes + narration transcript together:
  - Does each frame match its narration?
  - Are **Arabic text overlays** readable, correctly positioned, properly timed?
  - Is the intro/outro present and branded correctly?
  - Does it flow as a **complete** video (not disjointed clips)?
  - Any visual artifacts introduced during FFmpeg composition?
- Score: 1-10 content coherence

#### 7.3 Final Compliance Re-check (Qwen 72B text)
- YouTube policy sweep on full transcript + metadata
- Any accidental inappropriate content in assembled video?
- Content ID final check on mixed audio track

#### 7.4 Telegram Final Preview 📱
- **Full assembled video sent to Yusif** via Telegram
- Includes: QA scores, duration, topic, compliance status
- Inline buttons: `[✅ Publish] [🔄 Regenerate] [❌ Cancel]`

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
- **Text overlay:** PyCairo for Arabic text rendering (same engine as video overlays)
  - Uses **accent_font** from FontAnimationConfig (bolder than primary for thumbnails)
  - Same **accent_color** and **background_style** as video overlays
  - Same **color grade LUT** applied to thumbnail image
  - Result: viewer sees thumbnail → clicks → video has SAME visual identity = professional, branded
- **Selection:** Full 3-layer QA (same rigor as scene images):
  - **Layer 1 (Deterministic):** Resolution, file size, face detection, mobile readability simulation (downscale to 168x94 → OCR), color vibrancy, YouTube dead zone check (duration badge area), competitor similarity (CLIP embeddings)
  - **Layer 2 (Vision Rubric):** Click appeal, topic relevance, mobile readability, emotional impact, professionalism, differentiation (show competitor thumbnails alongside) — 6 axes, each with score + reasoning + confidence
  - **Layer 3 (Ranking):** Weighted formula ranks all 3 variants. All 3 < 6.0 → regenerate. Stored in `qa_rubrics` table (asset_type='thumbnail')
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

#### 8.2.5 Styled Subtitle Generator — Local AI Agent
- **Auto-generate .ass** (Advanced SubStation Alpha) instead of plain SRT
- **Font matching:** Same primary_font and colors from AI font selection (Phase 3)
  - Font, size (52px at 1080p), outline (2px black), shadow (1px)
  - Accent styling: key words/names in accent_color, quotes in italic, numbers bold
- Sync timestamps from voice audio timing (word-level from Fish Speech)
- Arabic subtitles (MSA) — clean, accurate, already written
- Optional: English translated subtitles (via local Qwen 2.5 72B translation)
- **All processing local** — no API calls needed
- Upload as closed captions to YouTube — **massive SEO boost** (YouTube Arabic auto-captions are poor)
- Fallback: if .ass upload fails → generate plain .srt
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

## Phase 7.5: Manual Review Gate (Optional) ✅👤 HUMAN GATE

### Purpose
**Optional human checkpoint before publishing.** Prevents weak videos from going live and damaging channel reputation.

### Configuration
```yaml
manual_review:
  enabled: true                    # Global toggle
  mode: "selective"                # "all" | "selective" | "off"
  
  # Selective mode rules:
  auto_publish_if:
    - all_qa_scores_above: 8       # Phase 4 + 6 + 7 all scored 8+
    - channel_has_published: 20    # Channel already has 20+ successful videos
    - topic_is_not: "politics"     # Non-sensitive topic
    
  require_review_if:
    - any_qa_score_below: 7        # Any QA gate scored below 7
    - topic_category: "politics"   # Sensitive topics always need review
    - first_video_on_channel: true # First 10 videos on any new channel
    - trending_hijack: true        # Fast-tracked content
    - new_narrative_style: true    # First time using a new style
```

### Review Flow
```
Phase 7 (Final QA) PASSES
         │
         ▼
   ┌─────────────┐
   │ Auto-publish │──── YES ───▶ Phase 8 (Publish)
   │  criteria    │
   │    met?      │
   └──────┬──────┘
          │ NO
          ▼
   ┌─────────────────────────────────────────────────┐
   │  📱 TELEGRAM REVIEW REQUEST                      │
   │                                                   │
   │  🎬 Video: "لغز انهيار فنزويلا"                  │
   │  📺 Channel: documentary_ar                       │
   │  ⏱️ Duration: 11:24                               │
   │  📊 QA Scores: Script 8.5 | Visual 7.2 | Final 8.0│
   │  ⚠️ Flag: Visual QA slightly low                  │
   │                                                   │
   │  📎 [Watch Preview]  — private YouTube link        │
   │  📄 [Read Script]    — full script text            │
   │  🖼️ [See Thumbnails] — 3 thumbnail options         │
   │                                                   │
   │  [✅ Approve & Publish]                            │
   │  [✏️ Approve with Notes] — "fix scene 23 image"    │
   │  [🔄 Reprocess] — re-run specific phase            │
   │  [❌ Reject] — cancel this video                   │
   └─────────────────────────────────────────────────┘
```

### Review Actions
| Action | Result |
|--------|--------|
| ✅ Approve | → Phase 8 publishes immediately |
| ✏️ Approve with Notes | → Agent fixes noted issues → re-QA → auto-publish |
| 🔄 Reprocess Phase X | → Re-runs specified phase (e.g., "regenerate scene 23 image") |
| ❌ Reject | → Job cancelled, reason logged, topic freed for retry |

### Review Timeout
```
IF no response in 12 hours:
  → Send reminder: "⏰ Video waiting for review since 12h"
IF no response in 24 hours:
  → Auto-action based on config:
    - "auto_publish" — publish anyway (for high-scoring videos)
    - "hold" — keep waiting (for sensitive content)
    - "cancel" — cancel the job
```

### Preview System
- **Private YouTube upload:** Video uploaded as `unlisted` for Yusif to watch
  - Also serves as Content ID pre-check (Feature 5.4.1 Layer 4)
  - If approved → change visibility to public/scheduled
  - If rejected → delete unlisted video
- **Script preview:** Full script text sent via Telegram (or link to file)
- **Thumbnail preview:** 3 options sent as images via Telegram

---

## Phase 9: Performance Intelligence 🔄📊

### Purpose
**The learning engine.** Analyzes every published video's performance and feeds insights back to improve ALL future videos. This is what separates a static factory from an evolving, self-improving system.

### Trigger
- Runs automatically after each video at: **24h, 48h, 7 days, 30 days, 90 days**
- Weekly summary report every Sunday
- Monthly deep analysis on 1st of each month

### Components

#### 9.0 Vision QA Rubric Calibration (NEW)
- **Trigger:** Every 20 published videos (enough statistical data)
- **Process:**
  1. Pull all `qa_rubrics` scores + `youtube_analytics` performance for published videos
  2. Calculate Pearson correlation: each rubric axis vs retention/CTR/watch time
  3. Axes with strong correlation to performance → increase weight
  4. Axes with no correlation → decrease weight (or remove)
  5. Analyze threshold: find optimal pass/fail cutoff via ROC curve
  6. Track regen efficiency: did regenerated assets actually improve final performance?
- **Output:** Updated weights + thresholds saved to `calibration_history` table + `settings.yaml`
- **Example discovery:** "composition quality correlates 0.7 with retention → increase weight from 0.15 to 0.22"
- **Safety:** New weights applied gradually. If calibrated weights produce worse results for 5 videos → revert to previous

#### 9.1 CTR Analyzer
- **Tracks:** Impressions → Clicks → CTR for every video
- **Analysis:**
  ```
  Per-video CTR breakdown:
  ├── Title effectiveness: which power words correlate with high CTR?
  ├── Thumbnail effectiveness: which styles/colors/compositions win?
  ├── Posting time effect: does 6PM get better CTR than 10AM?
  └── Topic category: which categories get highest CTR?
  
  Discovery:
  "عناوين تبدأ بـ 'لماذا' تحقق CTR أعلى بـ 23% من 'كيف'"
  "Thumbnails مع وجوه بشرية → CTR +18%"
  "النشر الخميس 6PM → CTR أعلى بـ 15% من الأحد"
  ```
- **Feeds back to:**
  - Phase 2 (Title Generator): prioritize high-CTR word patterns
  - Phase 8 (Thumbnail): generate styles that historically win
  - Phase 8 (Publisher): schedule at optimal times

#### 9.2 Watch Time Analyzer
- **Tracks:** Average view duration, total watch hours
- **Analysis:**
  ```
  Per-video watch time breakdown:
  ├── Avg view duration vs video length → "12-min videos watched avg 7.2 min (60%)"
  ├── Optimal length by category: "politics: 10 min, documentary: 14 min"
  ├── Correlation: narration speed ↔ watch time
  └── Correlation: music intensity ↔ watch time
  
  Discovery:
  "فيديوهات 12-14 دقيقة تحقق أعلى watch time إجمالي"
  "سرعة الصوت 0.95x تحقق +8% watch time مقابل 1.0x"
  ```
- **Feeds back to:**
  - Phase 3 (Script Writer): adjust target length per category
  - Feature 37 (Dynamic Length): data-driven length decisions
  - Feature 30 (Voice Emotion): optimal narration speed

#### 9.3 Audience Retention Analyzer (الأهم)
- **Tracks:** Second-by-second retention curve for every video
- **Analysis:**
  ```
  Retention curve analysis:
  ├── Drop-off points: WHERE do viewers leave?
  │   ├── Map drop-off timestamp → scene_index → scene content
  │   ├── "Viewers drop 12% at scene 15 (2:45) — long explanation, no visual change"
  │   └── "Viewers drop 8% at 5:30 — mid-roll ad placement too aggressive"
  │
  ├── Retention spikes: WHERE do viewers replay?
  │   ├── "Spike at 4:20 — dramatic reveal moment"
  │   └── "Spike at 0:05 — hook is so good people replay it"
  │
  ├── Hook effectiveness: % retained after 30 seconds
  │   ├── "Question hooks retain 82% at 30s"
  │   ├── "Shocking fact hooks retain 78% at 30s"
  │   └── "Narrative hooks retain 71% at 30s"
  │
  └── Section-level retention:
      ├── "Intro sections: avg 85% retention"
      ├── "Explanation sections: avg 62% retention (PROBLEM)"
      ├── "Reveal sections: avg 88% retention (BEST)"
      └── "Conclusion: avg 70% retention"
  ```
- **Auto-generated rules (stored in DB → fed to Script Writer):**
  ```python
  retention_rules = [
      {"rule": "intro_max_sec", "value": 20, "reason": "Intros >20s lose 15% viewers"},
      {"rule": "visual_change_max_sec", "value": 10, "reason": "No visual change >10s → drop-off"},
      {"rule": "question_every_min", "value": 2.5, "reason": "Rhetorical Q every 2.5 min retains +12%"},
      {"rule": "explanation_max_sec", "value": 45, "reason": "Explanations >45s lose viewers — break with visual"},
      {"rule": "midroll_not_before_sec", "value": 180, "reason": "Ads before 3:00 → 20% viewer loss"},
      {"rule": "midroll_after_cliffhanger", "value": True, "reason": "Ads after cliffhanger → only 5% loss"},
  ]
  ```
- **Feeds back to:**
  - Phase 3 (Script Writer): avoid patterns that cause drop-offs
  - Feature 29 (Emotional Arc): reinforce patterns that spike retention
  - Feature 19 (Ad Placement): optimize mid-roll positions
  - Feature 24 (Template Evolution): build templates from best-retaining scripts

#### 9.4 Revenue Intelligence
- **Tracks:** RPM, CPM, total revenue per video/channel/topic
- **Analysis:**
  ```
  Revenue patterns:
  ├── RPM by topic: "Technology $3.20 > Documentary $2.40 > Politics $1.80"
  ├── RPM by length: "12+ min = $2.80 RPM vs 8 min = $1.90 RPM (+47%)"
  ├── RPM by day: "Thursday-Saturday = highest RPM"
  ├── RPM by season: "Q4 (Oct-Dec) = 2x RPM vs Q1"
  └── Mid-roll revenue: "4 mid-rolls = optimal (3 = -20%, 5 = viewers leave)"
  ```
- **Feeds back to:**
  - Phase 1 (Topic Ranker): bonus score for high-RPM topics
  - Feature 37 (Dynamic Length): prefer lengths with higher RPM
  - Phase 8 (Publisher): schedule high-value videos for high-RPM days/seasons

#### 9.5 Cross-Video Learning
- **Pattern mining across ALL published videos:**
  ```
  After 50+ videos, agent discovers:
  
  "Videos with these traits perform in top 20%:"
  ├── Hook type: shocking_fact + rhetorical_question combo
  ├── Length: 11-13 minutes
  ├── Sections: 4 (not 3, not 5)
  ├── Narration speed: 0.95x
  ├── Music: dramatic in intro, calm in middle, epic at reveal
  ├── Visual: photorealistic style, dark palette
  ├── Posting: Thursday 5-7 PM
  └── Thumbnail: face + 3 Arabic words + red accent color
  
  "Videos with these traits perform in bottom 20%:"
  ├── Hook type: slow narrative start
  ├── Length: >16 minutes
  ├── Flat emotional arc (no peaks)
  ├── Narration speed: 1.1x+ (too fast)
  └── Thumbnail: no text, abstract image
  ```
- **Auto-updates:**
  - Script templates (Feature 24)
  - Anti-repetition rules (Feature 18)
  - Thumbnail generator prompts
  - Channel-specific guidelines

#### 9.6 Weekly & Monthly Reports
- **Weekly report (Telegram):**
  ```
  📊 Weekly Report — documentary_ar
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Videos published: 7
  Total views: 125,000
  Total watch hours: 4,200
  Revenue: $310
  Best performer: "لغز انهيار فنزويلا" (45K views, CTR 8.2%)
  Worst performer: "اقتصاد الأرجنتين" (8K views, CTR 3.1%)
  
  🔍 Insights:
  • CTR improved +12% this week (better thumbnails)
  • Avg retention dropped 3% — explanations too long in 3 videos
  • Thursday 6PM posts outperformed Sunday 10AM by 40%
  
  🎯 Recommendations:
  • Shorten explanation sections to <40 seconds
  • Keep posting at Thu/Fri 6PM
  • Topic "conspiracy/mystery" category trending — consider more
  ```
- **Monthly deep analysis:**
  - Full revenue breakdown
  - Audience growth analysis
  - Competitor comparison
  - Algorithm health check
  - Template evolution recommendations
  - Next month's optimal strategy

### Phase 9 Pipeline Integration
```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 9: FEEDBACK LOOP                       │
│                                                                 │
│  YouTube Analytics API (official) → pulls data every 24h        │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ CTR Analyzer │  │ Watch Time   │  │ Retention    │          │
│  │             │  │ Analyzer     │  │ Analyzer     │          │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                │                  │                   │
│         ▼                ▼                  ▼                   │
│  ┌─────────────────────────────────────────────────┐           │
│  │         Cross-Video Learning Engine              │           │
│  │  (analyzes patterns across ALL published videos) │           │
│  └──────────────────────┬──────────────────────────┘           │
│                         │                                       │
│         ┌───────────────┼───────────────────┐                  │
│         ▼               ▼                   ▼                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐            │
│  │ Phase 1    │  │ Phase 2    │  │ Phase 3      │            │
│  │ Topic      │  │ Title/SEO  │  │ Script       │            │
│  │ Selection  │  │ Patterns   │  │ Templates    │            │
│  │ (RPM bonus)│  │ (CTR data) │  │ (retention)  │            │
│  └────────────┘  └────────────┘  └──────────────┘            │
│         ┌───────────────┼───────────────────┐                  │
│         ▼               ▼                   ▼                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐            │
│  │ Phase 5    │  │ Phase 8    │  │ Feature 19   │            │
│  │ Visual     │  │ Thumbnails │  │ Ad Placement │            │
│  │ Style      │  │ + Schedule │  │ Optimization │            │
│  └────────────┘  └────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

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
| **Voice Cloning + TTS** | Fish Speech 1.5 (best Arabic), fallback: OpenAudio S1 / XTTS v2 / ElevenLabs API |
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
| Fish Speech 1.5 | ~2GB | Arabic voice cloning + TTS (best open-source Arabic clone quality) |
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
│   ├── voices/                 # Voice cloning library
│   │   ├── male_authoritative_01.wav    # تسجيل حقيقي — مذيع رسمي
│   │   ├── male_energetic_01.wav        # تسجيل حقيقي — حماسي
│   │   ├── male_mysterious_01.wav       # تسجيل حقيقي — غامض
│   │   ├── male_narrator_01.wav         # تسجيل حقيقي — راوي
│   │   ├── female_educational_01.wav    # تسجيل حقيقي — تعليمي
│   │   ├── female_dramatic_01.wav       # تسجيل حقيقي — درامي
│   │   ├── young_male_01.wav            # تسجيل حقيقي — شبابي
│   │   ├── embeddings/                  # AI voice clone embeddings
│   │   │   ├── v_male_auth_01.pt
│   │   │   ├── v_male_energy_01.pt
│   │   │   └── ...
│   │   └── voice_library.yaml           # Voice metadata + clone scores
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
│   │   ├── ab_testing.py       # A/B script testing framework
│   │   └── manual_review.py   # Human review gate (Telegram interactive)
│   ├── phase9_intelligence/
│   │   ├── ctr_analyzer.py     # CTR pattern analysis
│   │   ├── watchtime_analyzer.py # Watch time optimization
│   │   ├── retention_analyzer.py # Second-by-second retention analysis
│   │   ├── revenue_intel.py    # Revenue pattern discovery
│   │   ├── cross_video.py      # Cross-video pattern mining
│   │   └── reporter.py         # Weekly/monthly report generation
│   └── utils/
│       ├── gpu_logger.py       # Precision GPU logging (every load/unload/gen/OOM/leak)
│       ├── gpu_manager.py      # VRAM memory manager (load/unload/flush/monitor)
│       ├── content_id_guard.py # Audio fingerprint + Content ID protection
│       ├── gpu_scheduler.py    # GPU task queue (sequential, batched by model)
│       ├── database.py         # Central SQLite (FactoryDB — all 40 agents read/write)
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
├── logs/
│   ├── gpu/                    # Per-job GPU logs (.log + .jsonl + .csv)
│   ├── pipeline/               # Phase-level pipeline logs
│   └── alerts/                 # Critical events (OOM, leaks, resets)
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

09:55  ═══ PHASE 7.5: MANUAL REVIEW (if required) ═══
       Send preview to Yusif via Telegram
       [✅ Approve] [✏️ Fix] [🔄 Reprocess] [❌ Reject]
       Auto-publish if QA scores all 8+ and topic is non-sensitive

10:00  ═══ PHASE 8: PUBLISH ═══
       Generate 3 thumbnails → A/B test on YouTube
       Assemble SEO metadata (title + desc + tags)
       Upload SRT subtitles (Arabic + English)
       Upload to YouTube (scheduled for optimal time)
       Send confirmation to Yusif via Telegram
       "✅ [channel] — [title] — scheduled for 18:00"

18:00  Video goes live

       ═══ PHASE 9: PERFORMANCE INTELLIGENCE (continuous) ═══
+24h   Pull analytics: views, CTR, retention curve
+48h   Pull analytics: watch time, engagement
+7d    Deep analysis: retention drop-offs, revenue, audience
+30d   Full report: cross-video patterns, template updates
       Feed ALL data back → Phase 1 (topics), Phase 2 (SEO),
       Phase 3 (scripts), Phase 8 (thumbnails, schedule)
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
