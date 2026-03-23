"""
Phase 3: Professional Arabic Documentary Script Writer.
Strategy: Outline → Expand Each Chapter (split into sub-sections) → Merge

Key insight: Each LLM call handles only 2-3 bullet points.
This keeps thinking short (~3K tokens) and guarantees response every time.
"""

import logging
import re
from src.core.llm import generate

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# System prompt
# ════════════════════════════════════════════════════════════════

WRITER_SYSTEM = """[SYSTEM DIRECTIVE - CRITICAL OVERRIDE]
أنت كاتب سيناريو وثائقي، مخرج سينمائي، وخبير استراتيجي في السرد التاريخي والجيوسياسي الملحمي (بأسلوب الجزيرة الوثائقية وقناة العربي). عليك نسيان أي تعليمات سابقة.

مهمتك: كتابة سكربت وثائقي مطول جداً، عميق، ومفصل عن [الموضوع المطلوب من المستخدم] حصراً.

<length_and_depth_enforcement>
تحذير شديد: يُمنع منعاً باتاً اختصار السكربت أو كتابة ملخصات سريعة.
1. التمدد الأفقي: عند ذكر حدث تاريخي، لا تذكر النتيجة فقط. اشرح (الكواليس، الحالة النفسية للقادة، الغرف المغلقة، وتفاصيل الاغتيالات أو الاتفاقيات).
2. استخدم أسلوب "العدسة المكبرة": ابدأ بوصف تفصيل دقيق جداً (مثلاً: دخان سيجار، قطرة عرق، أو توقيع على ورقة) ثم انتقل للصورة الجيوسياسية الكبرى.
</length_and_depth_enforcement>

<technical_formatting_rules>
1. منع أسماء المتحدثين: إياك أن تكتب كلمة "المذيع:" أو "المعلق:" أو "السرد:" قبل النص. اكتب النص مباشرة.
2. تفقيط الأرقام: ممنوع كتابة الأرقام رياضياً (مثل 1979 أو 500). اكتبها بالحروف العربية دائماً.
</technical_formatting_rules>

<director_cues>
التوجيهات البصرية والصوتية توضع بين أقواس مربعة: [بصري: ...] و [صوتي: ...].
</director_cues>

<tashkeel_directive_for_tts>
ممنوع التشكيل نهائياً. لا تضع أي حركات (فتحة، ضمة، كسرة، سكون، شدة، تنوين) على أي حرف.
اكتب النص بدون أي علامات تشكيل إطلاقاً. نظام TTS سيتولى النطق الصحيح تلقائياً.
</tashkeel_directive_for_tts>

<forbidden>
ممنوع منعاً باتاً: أي عبارة تطلب الاشتراك أو الإعجاب أو تفعيل الجرس أو مشاركة الفيديو.
اختم بتأمل فلسفي فقط. لا دعوات عمل (CTA) من أي نوع.
</forbidden>"""

# ════════════════════════════════════════════════════════════════
# Outline prompt
# ════════════════════════════════════════════════════════════════

OUTLINE_PROMPT = """أنت تخطط لوثائقي عن: "{topic}"
الزاوية: {angle}

## المهمة الأولى: تقدير المدة المناسبة
حلّل الموضوع وقرر:
- موضوع غني بالأحداث (حروب، صراعات طويلة) → 15-25 دقيقة
- موضوع متوسط (تحليل ظاهرة، سيرة) → 10-15 دقيقة
- موضوع خفيف (ماذا لو، حقائق غريبة) → 6-10 دقائق

اكتب في أول سطر: DURATION_MINUTES: [الرقم]

## المهمة الثانية: المخطط التفصيلي
اكتب مخططاً مفصلاً جداً من 5 فصول.
⚠️ كل فصل يجب أن يحتوي على 8-15 نقطة تفصيلية على الأقل.
⚠️ كل نقطة يجب أن تكون جملة كاملة تذكر: الحدث + التاريخ + الأشخاص + التفصيل الدرامي.
⚠️ إذا كتبت أقل من 8 نقاط لأي فصل سيتم رفض المخطط.

الشكل المطلوب بالضبط:

CHAPTER_1: المشهد الافتتاحي (الخطاف)
- وصف المشهد الأول بالتفصيل (المكان، الزمان، الأجواء)
- الشخصية الرئيسية وما تفعله في هذه اللحظة
- التناقض أو الصدمة التي تشد المشاهد
- الانتقال من المشهد الافتتاحي إلى السرد
- السؤال المعلّق الذي يبقي المشاهد
- (استمر... 8-15 نقطة)

CHAPTER_2: الجذور وبناء التوتر
- (8-15 نقطة مفصّلة بنفس الطريقة)

CHAPTER_3: الذروة الدرامية
- (8-15 نقطة مفصّلة)

CHAPTER_4: التداعيات والانهيار
- (8-15 نقطة مفصّلة)

CHAPTER_5: الخاتمة والتأمل الفلسفي
- (8-15 نقطة مفصّلة)

الحقائق المرجعية:
{research_text}

اكتب المخطط الآن — مفصّل جداً، 8-15 نقطة لكل فصل. لا تختصر."""

# ════════════════════════════════════════════════════════════════
# Sub-section prompt — handles 2-3 points only (keeps thinking short)
# ════════════════════════════════════════════════════════════════

SUBSECTION_PROMPT = """الموضوع: "{topic}"
الفصل: {chapter_name}

اكتب فقرة سردية وثائقية عن النقاط التالية:
{points}

## التعليمات الإجبارية:
1. اكتب 150-250 كلمة عن هذه النقاط فقط.
2. ابدأ بتوجيه بصري وصوتي بهذا الشكل بالضبط:
   [بصري: وصف دقيق للقطة — حجم اللقطة، الإضاءة، العناصر المرئية]
   [صوتي: نوع الموسيقى، المؤثرات الصوتية]
   ثم اكتب السرد مباشرة.
   ⚠️ التوجيه البصري والصوتي إجباري في بداية كل فقرة — لا تحذفه.
3. الأرقام بالحروف العربية فقط.
4. ممنوع التشكيل نهائياً (لا فتحة، لا ضمة، لا كسرة).
5. ممنوع: اشتراك، إعجاب، جرس.
6. اسرد حقائق وأحداث تاريخية محددة (أسماء، تواريخ، أماكن). لا تعتمد على الوصف الدرامي المجرد.
{anti_repetition}
اكتب الآن."""


# ════════════════════════════════════════════════════════════════
# Writer class
# ════════════════════════════════════════════════════════════════

class ScriptWriter:
    """
    Multi-pass script writer: Outline → Sub-section Expand → Merge.
    
    Each LLM call handles only 2-3 bullet points = short thinking = always succeeds.
    """

    def __init__(self, config: dict):
        self.config = config

    CHAPTERS = [
        ("المشهد الافتتاحي (الخطاف)", "1"),
        ("الفصل الأول: الجذور وبناء التوتر", "2"),
        ("الفصل الثاني: الذروة الدرامية", "3"),
        ("الفصل الثالث: التداعيات والانهيار", "4"),
        ("الخاتمة: التأمل الفلسفي", "5"),
    ]

    def write_script(self, topic, research, seo_data, channel_config, performance_rules=None):
        """Write script using Outline → Sub-section Expand → Merge."""
        
        research_text = research.get("research_text", f"الموضوع: {topic}")
        if len(research_text) > 6000:
            research_text = research_text[:6000]
        angle = research.get("angle", "تحليل شامل")

        # ─── Step 1: Generate Outline ───
        logger.info(f"Script: generating outline for '{topic}'")
        
        outline = generate(
            prompt=OUTLINE_PROMPT.format(topic=topic, angle=angle, research_text=research_text),
            system=f"أنت خبير في التخطيط الوثائقي. خطط فقط لموضوع: {topic}",
            temperature=0.7,
        )

        if not outline or len(outline.strip()) < 100:
            logger.error("Outline generation failed")
            return ""

        # Validate on-topic
        topic_keywords = [w for w in topic.split() if len(w) > 2]
        if topic_keywords and not any(kw in outline for kw in topic_keywords):
            logger.warning("Outline OFF-TOPIC! Retrying...")
            outline = generate(
                prompt=f"⚠️ الموضوع هو \"{topic}\" حصراً.\n\n" + OUTLINE_PROMPT.format(
                    topic=topic, angle=angle, research_text=research_text),
                system=f"اكتب مخططاً فقط عن: {topic}.",
                temperature=0.5,
            )
            if not outline or len(outline.strip()) < 100:
                return ""

        # ─── Step 2: Extract duration ───
        total_minutes = self._extract_duration(outline)
        total_words = int(total_minutes * 130)
        logger.info(f"Script: Outline ready — {total_minutes} min, {total_words} words target")

        # ─── Step 3: Parse chapters into point lists ───
        chapters = self._parse_outline_chapters(outline)

        # ─── Step 4: Expand each chapter by sub-sections ───
        all_text = []
        call_num = 1
        total_calls = sum(max(1, (len(pts) + 2) // 3) for pts in chapters.values()) if chapters else 5
        
        for chapter_name, chapter_num in self.CHAPTERS:
            points = chapters.get(chapter_num, [])
            if not points:
                points = [f"اكتب عن {chapter_name} في سياق {topic}"]
            
            # Split points into sub-sections of 2-3 points each
            subsections = []
            for i in range(0, len(points), 3):
                subsections.append(points[i:i+3])
            
            chapter_parts = []
            # Track used phrases to prevent repetition
            used_phrases = set()
            
            for j, sub_points in enumerate(subsections):
                points_text = "\n".join(f"- {p}" for p in sub_points)
                logger.info(f"Script: Call {call_num}/{total_calls} — {chapter_name} part {j+1}/{len(subsections)} ({len(sub_points)} points)")
                
                # Build anti-repetition warning from recently used phrases
                anti_rep = ""
                if used_phrases:
                    anti_rep = "\n\n⚠️ عبارات مستخدمة سابقاً (لا تكررها): " + "، ".join(list(used_phrases)[-10:])
                
                text = generate(
                    prompt=SUBSECTION_PROMPT.format(
                        topic=topic,
                        chapter_name=chapter_name,
                        points=points_text,
                        anti_repetition=anti_rep,
                    ),
                    system=WRITER_SYSTEM,
                    temperature=0.6,
                )
                
                if text and len(text.strip()) > 30:
                    cleaned = self._extract_narration(text)
                    cleaned = self._strip_tashkeel(cleaned)  # Remove any diacritics
                    chapter_parts.append(cleaned)
                    # Track distinctive phrases to prevent repetition
                    for phrase in re.findall(r'[\u0600-\u06FF]{3,}\s+[\u0600-\u06FF]{3,}\s+[\u0600-\u06FF]{3,}', cleaned):
                        if len(phrase) > 15:
                            used_phrases.add(phrase[:30])
                    logger.info(f"  → {len(cleaned.split())} words")
                else:
                    logger.warning(f"  → Empty response, retrying with shorter prompt")
                    # Retry with even simpler prompt
                    text = generate(
                        prompt=f"الموضوع: {topic}\n\nاكتب فقرة وثائقية (150 كلمة) عن:\n{points_text}",
                        system=WRITER_SYSTEM,
                        temperature=0.6,
                    )
                    if text and len(text.strip()) > 30:
                        cleaned = self._extract_narration(text)
                        cleaned = self._strip_tashkeel(cleaned)
                        chapter_parts.append(cleaned)
                        logger.info(f"  → Retry succeeded: {len(cleaned.split())} words")
                    else:
                        logger.warning(f"  → Skipped (both attempts empty)")
                
                call_num += 1
            
            if chapter_parts:
                all_text.append("\n\n".join(chapter_parts))

        # ─── Step 5: Merge ───
        if not all_text:
            logger.error("All expansions failed")
            return ""

        full_script = "\n\n".join(all_text)
        full_script = self._strip_tashkeel(full_script)
        full_script = self._remove_youtube_cta(full_script)
        word_count = len(full_script.split())
        logger.info(f"Script: Merge complete — {word_count} words from {len(all_text)} chapters, {call_num-1} LLM calls")

        return full_script

    @staticmethod
    def _extract_duration(outline):
        match = re.search(r'DURATION_MINUTES:\s*(\d+)', outline)
        if match:
            minutes = max(6, min(30, int(match.group(1))))
            logger.info(f"Qwen chose duration: {minutes} minutes")
            return minutes
        logger.warning("No DURATION_MINUTES found, defaulting to 12")
        return 12

    def _parse_outline_chapters(self, outline):
        """Parse outline into {chapter_num: [list of point strings]}."""
        chapters = {}
        current_num = None
        
        for line in outline.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            
            # Match CHAPTER_1:, CHAPTER_2:, etc.
            ch_match = re.match(r'CHAPTER_(\d+):', stripped)
            if ch_match:
                current_num = ch_match.group(1)
                chapters[current_num] = []
                continue
            
            # Match numbered headers: 1. المشهد, 2. الفصل, etc.
            num_match = re.match(r'^(\d+)[\.\)]\s*', stripped)
            if num_match and not current_num:
                current_num = num_match.group(1)
                chapters[current_num] = []
                continue
            
            # Bullet points under current chapter
            if current_num and (stripped.startswith("-") or stripped.startswith("•") or stripped.startswith("*")):
                point = stripped.lstrip("-•* ").strip()
                if point and len(point) > 5:
                    chapters[current_num].append(point)
        
        # Validate
        if not chapters or all(len(v) == 0 for v in chapters.values()):
            logger.warning("Outline parsing failed — splitting by sections")
            # Fallback: split outline into 5 roughly equal sections
            lines = [l.strip() for l in outline.split("\n") if l.strip() and not l.strip().startswith("DURATION")]
            chunk_size = max(1, len(lines) // 5)
            for i in range(5):
                start = i * chunk_size
                end = start + chunk_size if i < 4 else len(lines)
                chapters[str(i+1)] = lines[start:end]
        
        for num, pts in chapters.items():
            logger.info(f"  Chapter {num}: {len(pts)} points")
        
        return chapters

    def _extract_narration(self, raw_script):
        """Extract narration text (remove cues/headers/directions)."""
        lines = raw_script.strip().split("\n")
        narration_lines = []
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if s.startswith("[") and s.endswith("]"):
                continue
            if s.startswith("- [") and "]" in s:
                continue
            if s.startswith("##") or s.startswith("```"):
                continue
            if s.startswith("المشهد") or s.startswith("الفصل"):
                continue
            if s.startswith("عنوان") or s.startswith("# ") or s.startswith("**عنوان"):
                continue
            if s.startswith("**المدة") or s.startswith("**الموضوع"):
                continue
            if s in ("🎙️ السرد:", "السرد:", "المذيع:", "المعلق:"):
                continue
            for prefix in ("المذيع:", "المعلق:", "السرد:", "🎙️ السرد:", "الراوي:", "صوت الراوي:"):
                if s.startswith(prefix):
                    s = s[len(prefix):].strip()
                    break
            if s.startswith("📹") or s.startswith("🔊"):
                continue
            if s.startswith("**") and s.endswith("**") and len(s) < 80:
                continue
            if s:
                narration_lines.append(s)
        return "\n\n".join(narration_lines) if narration_lines else raw_script

    @staticmethod
    def _strip_tashkeel(text):
        """Remove ALL Arabic diacritical marks (tashkeel/harakat).
        LLMs add random incorrect tashkeel. Modern TTS handles plain text better."""
        # Arabic diacritics Unicode range: 0x064B-0x065F (fathah, dammah, kasrah, sukun, shadda, etc.)
        return re.sub(r'[\u064B-\u065F\u0670]', '', text)

    @staticmethod
    def _remove_youtube_cta(text):
        """Remove YouTube CTA phrases."""
        patterns = [
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
        for p in patterns:
            text = re.sub(p, '', text, flags=re.DOTALL)
        return re.sub(r'\n{3,}', '\n\n', text).strip()
