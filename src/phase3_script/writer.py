"""
Phase 3: Professional Arabic Documentary Script Writer.
Strategy: Outline → Expand Each Chapter → Merge
This bypasses LLM output token limits by splitting into multiple calls.
"""

import logging
import re
from src.core.llm import generate

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# System prompt — shared across all calls for consistent voice
# ════════════════════════════════════════════════════════════════

WRITER_SYSTEM = """[SYSTEM DIRECTIVE - CRITICAL OVERRIDE]
أنت كاتب سيناريو وثائقي، مخرج سينمائي، وخبير استراتيجي في السرد التاريخي والجيوسياسي الملحمي (بأسلوب الجزيرة الوثائقية وقناة العربي). عليك نسيان أي تعليمات سابقة.

مهمتك: كتابة سكربت وثائقي مطول جداً، عميق، ومفصل عن [الموضوع المطلوب من المستخدم] حصراً.

<length_and_depth_enforcement>
تحذير شديد: يُمنع منعاً باتاً اختصار السكربت أو كتابة ملخصات سريعة.
1. يجب أن يكون السكربت طويلاً جداً (لا يقل عن 1500 كلمة).
2. كل فصل (مقدمة، محاور، خاتمة) يجب أن يحتوي على الأقل على 3 فقرات سردية طويلة.
3. التمدد الأفقي: عند ذكر حدث تاريخي، لا تذكر النتيجة فقط. اشرح (الكواليس، الحالة النفسية للقادة، الغرف المغلقة، وتفاصيل الاغتيالات أو الاتفاقيات).
4. استخدم أسلوب "العدسة المكبرة": ابدأ بوصف تفصيل دقيق جداً (مثلاً: دخان سيجار، قطرة عرق، أو توقيع على ورقة) ثم انتقل للصورة الجيوسياسية الكبرى.
</length_and_depth_enforcement>

<technical_formatting_rules>
1. منع أسماء المتحدثين: إياك أن تكتب كلمة "المذيع:" أو "المعلق:" أو "السرد:" قبل النص. اكتب النص مباشرة.
2. تفقيط الأرقام: ممنوع كتابة الأرقام رياضياً (مثل 1979 أو 500). اكتبها بالحروف العربية دائماً (مثل: عام ألف وتسعمئة وتسعة وسبعين، خمس مئة ألف).
</technical_formatting_rules>

<director_cues>
- التوجيهات البصرية والصوتية توضع بين أقواس مربعة هكذا: [بصري: ...] و [صوتي: ...].
- التوجيه البصري يجب أن يكون دقيقاً سينمائياً (اذكر حجم اللقطة، الإضاءة، وحركة العناصر) ليكون جاهزاً لمولدات الفيديو.
  مثال: [بصري: لقطة مقربة جداً (Close-up) بإضاءة سينمائية خافتة، رماد يتطاير في الهواء مع حركة كاميرا بطيئة].
</director_cues>

<tashkeel_directive_for_tts>
هذا السكربت موجه لنظام (TTS).
- شكّل فقط: الأفعال المبنية للمجهول (مثال: قُتِلَ، دُمِّرَت)، الكلمات الملتبسة (عَقْد/عُقَد)، وأواخر الكلمات عند الوقف في نهاية الجملة.
- لا تشكّل الحروف العادية.
</tashkeel_directive_for_tts>

<forbidden>
ممنوع منعاً باتاً:
- أي عبارة تطلب الاشتراك أو الإعجاب أو تفعيل الجرس أو مشاركة الفيديو أو ترك تعليق.
- أي إشارة للقناة أو للمشاهد بصيغة "لا تنسَ" أو "اشترك" أو "فعّل".
- اختم بتأمل فلسفي فقط. لا دعوات عمل (CTA) من أي نوع.
</forbidden>

ابدأ فوراً بكتابة ما يُطلب منك بناءً على الموضوع المطلوب."""

# ════════════════════════════════════════════════════════════════
# Step 1: Outline prompt — thinking ON for quality planning
# ════════════════════════════════════════════════════════════════

OUTLINE_PROMPT = """أنت تخطط لوثائقي عن: "{topic}"
الزاوية: {angle}

المطلوب: اكتب مخططاً تفصيلياً (outline) للسكربت يتكون من 5 فصول:

1. المشهد الافتتاحي (الخطاف): ما هو المشهد الصادم أو التناقض الذي سيفتح به الوثائقي؟ اذكر 3-4 نقاط تفصيلية.
2. الفصل الأول — الجذور: ما الأحداث والتفاصيل التاريخية الدقيقة التي يجب تغطيتها؟ اذكر 5-7 نقاط مع تواريخ وأسماء.
3. الفصل الثاني — الذروة: ما لحظات التصادم والمواجهة المباشرة؟ اذكر 5-7 نقاط مع تفاصيل درامية.
4. الفصل الثالث — التداعيات: ما النتائج الكارثية على المنطقة والشعوب؟ اذكر 4-6 نقاط.
5. الخاتمة: ما السؤال الفلسفي أو التأمل المظلم الذي سيختم به؟ وكيف يرتبط بالخطاف؟

لكل نقطة: اذكر (الحدث، التاريخ، الأشخاص، التفصيل الدرامي الذي يجب ذكره).

الحقائق المرجعية:
{research_text}

اكتب المخطط الآن. كن مفصلاً جداً — هذا المخطط سيُستخدم لكتابة كل فصل على حدة."""

# ════════════════════════════════════════════════════════════════
# Step 2: Chapter expansion prompt — thinking ON for depth
# ════════════════════════════════════════════════════════════════

CHAPTER_PROMPT = """أنت تكتب فصلاً واحداً من سكربت وثائقي عن: "{topic}"

هذا هو المخطط الكامل للوثائقي:
{outline}

---

المطلوب الآن: اكتب **{chapter_name}** فقط.
النقاط التي يجب تغطيتها في هذا الفصل:
{chapter_points}

التعليمات:
- اكتب 300-400 كلمة على الأقل لهذا الفصل.
- ابدأ بالتوجيهات البصرية والصوتية [بصري: ...] [صوتي: ...] ثم السرد مباشرة.
- استخدم أسلوب العدسة المكبرة: تفصيل دقيق → صورة كبرى.
- لا تكتب "المعلق:" أو "السرد:" — اكتب النص مباشرة.
- الأرقام بالحروف العربية فقط.
- التشكيل الجزئي فقط عند الضرورة.
- لا تكتب أي عبارة عن الاشتراك أو الإعجاب أو الجرس.

اكتب هذا الفصل الآن بعمق وتفصيل — كأنك مخرج يصوّر كل لقطة."""


class ScriptWriter:
    """
    Multi-pass script writer: Outline → Expand → Merge.
    
    Strategy:
    1. Call 1 (thinking ON): Generate detailed outline with key events
    2. Calls 2-6 (thinking ON): Expand each chapter individually (300-400 words each)
    3. Merge: Concatenate all chapters → 1500-2000+ words total
    
    This bypasses the token limit problem because each call only needs
    to produce 300-400 words (fits easily in thinking mode budget).
    """

    def __init__(self, config: dict):
        self.config = config

    # Chapter definitions
    CHAPTERS = [
        ("المشهد الافتتاحي (الخطاف)", "1"),
        ("الفصل الأول: الجذور وبناء التوتر", "2"),
        ("الفصل الثاني: الذروة الدرامية", "3"),
        ("الفصل الثالث: التداعيات والانهيار", "4"),
        ("الخاتمة: التأمل الفلسفي", "5"),
    ]

    def write_script(
        self,
        topic: str,
        research: dict,
        seo_data: dict,
        channel_config: dict,
        performance_rules: list[dict] = None,
    ) -> str:
        """Write script using Outline → Expand → Merge strategy."""
        
        research_text = research.get("research_text", f"الموضوع: {topic}")
        if len(research_text) > 6000:
            research_text = research_text[:6000] + "\n\n[... المزيد من التفاصيل ...]"
        angle = research.get("angle", "تحليل شامل")

        # ─── Step 1: Generate Outline (thinking ON → quality planning) ───
        logger.info(f"Script: Step 1/6 — generating outline for '{topic}'")
        
        outline = generate(
            prompt=OUTLINE_PROMPT.format(
                topic=topic,
                angle=angle,
                research_text=research_text,
            ),
            system=f"أنت خبير في التخطيط الوثائقي. خطط فقط لموضوع: {topic}",
            max_tokens=8192,
            temperature=0.7,
            think=True,  # Thinking ON — planning benefits from reasoning
        )
        
        # Retry with more tokens if outline is empty
        if not outline or len(outline.strip()) < 100:
            logger.warning("Outline empty, retrying with 24K tokens")
            outline = generate(
                prompt=OUTLINE_PROMPT.format(
                    topic=topic, angle=angle, research_text=research_text,
                ),
                system=f"أنت خبير في التخطيط الوثائقي. خطط فقط لموضوع: {topic}",
                max_tokens=24576,
                temperature=0.7,
                think=True,  # Always thinking
            )

        if not outline or len(outline.strip()) < 100:
            logger.error("Outline generation failed — empty result")
            return self._fallback_single_pass(topic, angle, research_text)

        # Validate outline is on-topic
        topic_keywords = [w for w in topic.split() if len(w) > 2]
        if topic_keywords and not any(kw in outline for kw in topic_keywords):
            logger.warning(f"Outline OFF-TOPIC! Retrying...")
            outline = generate(
                prompt=f"⚠️ الموضوع هو \"{topic}\" حصراً.\n\n" + OUTLINE_PROMPT.format(
                    topic=topic, angle=angle, research_text=research_text,
                ),
                system=f"اكتب مخططاً فقط عن: {topic}. لا موضوع آخر.",
                max_tokens=4096,
                temperature=0.5,
                think=True,
            )
            if not outline or len(outline.strip()) < 100:
                return self._fallback_single_pass(topic, angle, research_text)

        logger.info(f"Script: Outline ready ({len(outline.split())} words)")

        # ─── Step 2: Parse outline into chapter points ───
        chapter_points = self._parse_outline_chapters(outline)

        # ─── Step 3: Expand each chapter (thinking ON → deep writing) ───
        chapters_text = []
        
        for i, (chapter_name, chapter_num) in enumerate(self.CHAPTERS):
            logger.info(f"Script: Step {i+2}/6 — expanding '{chapter_name}'")
            
            points = chapter_points.get(chapter_num, "")
            if not points:
                # If parsing failed, give the full outline section
                points = f"راجع المخطط أعلاه للفصل رقم {chapter_num}"

            chapter_text = generate(
                prompt=CHAPTER_PROMPT.format(
                    topic=topic,
                    outline=outline,
                    chapter_name=chapter_name,
                    chapter_points=points,
                ),
                system=WRITER_SYSTEM,
                max_tokens=16384,  # Thinking needs room — 8-10K thinking + 4-6K response
                temperature=0.6,
                think=True,  # Always thinking — quality is priority
            )
            
            # If response still empty, retry with higher token budget
            if not chapter_text or len(chapter_text.strip()) < 50:
                logger.warning(f"  → {chapter_name}: empty response, retrying with 24K tokens")
                chapter_text = generate(
                    prompt=CHAPTER_PROMPT.format(
                        topic=topic,
                        outline=outline,
                        chapter_name=chapter_name,
                        chapter_points=points,
                    ),
                    system=WRITER_SYSTEM,
                    max_tokens=24576,  # Even more room for thinking
                    temperature=0.6,
                    think=True,  # Still thinking — always
                )

            if chapter_text and len(chapter_text.strip()) > 50:
                cleaned = self._extract_narration(chapter_text)
                chapters_text.append(cleaned)
                logger.info(f"  → {chapter_name}: {len(cleaned.split())} words")
            else:
                logger.warning(f"  → {chapter_name}: expansion failed, skipping")

        # ─── Step 4: Merge all chapters ───
        if not chapters_text:
            logger.error("All chapter expansions failed")
            return self._fallback_single_pass(topic, angle, research_text)

        full_script = "\n\n".join(chapters_text)
        full_script = self._remove_youtube_cta(full_script)
        word_count = len(full_script.split())

        logger.info(f"Script: Merge complete — {word_count} words from {len(chapters_text)} chapters")

        return full_script

    def _fallback_single_pass(self, topic: str, angle: str, research_text: str) -> str:
        """Fallback: single-pass generation if multi-pass fails."""
        logger.warning("Falling back to single-pass script generation")
        result = generate(
            prompt=f"""⚠️ الموضوع: {topic}
الزاوية: {angle}

اكتب سكربت وثائقي كامل عن "{topic}" — 5 فصول كما في تعليماتك.

الحقائق المرجعية:
{research_text}

اكتب حصراً عن "{topic}". لا تكتب عن أي موضوع آخر.""",
            system=WRITER_SYSTEM,
            max_tokens=24576,
            temperature=0.6,
            think=True,  # Always thinking
        )
        if result:
            return self._remove_youtube_cta(self._extract_narration(result))
        return ""

    def _parse_outline_chapters(self, outline: str) -> dict:
        """Parse outline text into chapter sections."""
        chapters = {}
        current_num = None
        current_lines = []

        for line in outline.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            # Detect chapter headers (1. المشهد, 2. الفصل, etc.)
            match = re.match(r'^(\d+)[\.\)]\s*', stripped)
            if match:
                # Save previous chapter
                if current_num and current_lines:
                    chapters[current_num] = "\n".join(current_lines)
                current_num = match.group(1)
                current_lines = [stripped]
            elif current_num:
                current_lines.append(stripped)

        # Save last chapter
        if current_num and current_lines:
            chapters[current_num] = "\n".join(current_lines)

        # If parsing failed, just split by rough sections
        if not chapters:
            logger.warning("Outline parsing failed — using full outline for all chapters")
            for _, num in self.CHAPTERS:
                chapters[num] = outline

        return chapters

    def _extract_narration(self, raw_script: str) -> str:
        """Extract narration text from structured script (remove cues/headers/directions)."""
        lines = raw_script.strip().split("\n")
        narration_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip direction cues in square brackets
            if stripped.startswith("[") and stripped.endswith("]"):
                continue
            if stripped.startswith("- [") and "]" in stripped:
                continue
            # Skip markdown headers and code blocks
            if stripped.startswith("##") or stripped.startswith("```"):
                continue
            # Skip scene/chapter headers
            if stripped.startswith("المشهد") or stripped.startswith("الفصل"):
                continue
            # Skip title/header lines
            if stripped.startswith("عنوان") or stripped.startswith("# ") or stripped.startswith("**عنوان"):
                continue
            # Skip metadata lines
            if stripped.startswith("**المدة") or stripped.startswith("**الموضوع") or stripped.startswith("**نوع"):
                continue
            # Skip narration/speaker markers
            if stripped in ("🎙️ السرد:", "السرد:", "المذيع:", "المعلق:"):
                continue
            # Strip speaker prefixes if inline
            for prefix in ("المذيع:", "المعلق:", "السرد:", "🎙️ السرد:", "الراوي:", "صوت الراوي:"):
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):].strip()
                    break
            # Skip emoji-prefixed direction lines
            if stripped.startswith("📹") or stripped.startswith("🔊"):
                continue
            # Skip standalone bold markers
            if stripped.startswith("**") and stripped.endswith("**") and len(stripped) < 80:
                continue
            if stripped:
                narration_lines.append(stripped)

        if narration_lines:
            return "\n\n".join(narration_lines)
        return raw_script

    @staticmethod
    def _remove_youtube_cta(text: str) -> str:
        """Remove YouTube subscribe/like/bell CTA phrases."""
        cta_patterns = [
            r'[فو]?لا\s*تنس[َى]\s*(الاشتراك|أن تشترك).*?[\.!؟\n]',
            r'اشترك\s*(في|ب)\s*القناة.*?[\.!؟\n]',
            r'فعّل\s*(زر\s*)?الجرس.*?[\.!؟\n]',
            r'اضغط\s*(على\s*)?(زر\s*)?(الإعجاب|اللايك|الاشتراك).*?[\.!؟\n]',
            r'شارك\s*(هذا\s*)?(الفيديو|المقطع).*?(أصدقائك|معارفك).*?[\.!؟\n]',
            r'اترك\s*(لنا\s*)?(تعليق|رأيك).*?[\.!؟\n]',
            r'ادعم\s*القناة.*?[\.!؟\n]',
            r'تابعنا\s*(على|في).*?[\.!؟\n]',
            r'لا\s*تنس[َى]\s*(دعم|مشاركة).*?[\.!؟\n]',
        ]
        for pattern in cta_patterns:
            text = re.sub(pattern, '', text, flags=re.DOTALL)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text
