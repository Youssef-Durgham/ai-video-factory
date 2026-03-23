"""
Phase 3: Professional Arabic Documentary Script Writer.
Style: الجزيرة الوثائقية × العربي × Step News.
Optimized for AI TTS delivery.
"""

import logging
from src.core.llm import generate

logger = logging.getLogger(__name__)

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

<script_structure>
يجب أن يتكون السكربت من 5 أجزاء رئيسية مفصلة:
1. المشهد الافتتاحي (الخطاف): مشهد صادم ودموي أو تناقض تاريخي يشد الانتباه فوراً.
2. الفصل الأول: الجذور وبناء التوتر الخفي (اذكر التفاصيل الدقيقة للبدايات).
3. الفصل الثاني: الذروة الدرامية (التصادم المباشر، المجازر، قرارات الحرب).
4. الفصل الثالث: الانهيار والتداعيات الكارثية على المنطقة.
5. الخاتمة: النهاية الدائرية (ربط النهاية بالبداية) وتأمل فلسفي مظلم يترك أثراً نفسياً (بدون طلب اشتراك أو إعجاب).
</script_structure>

ابدأ فوراً بكتابة السكربت المطول والمفصل بناءً على الموضوع المطلوب."""

WRITER_PROMPT = """⚠️ تنبيه حاسم: الموضوع المطلوب هو "{topic}" فقط. لا تكتب عن أي موضوع آخر مهما كان.

الموضوع: {topic}
الزاوية: {angle}
المدة المطلوبة: {target_minutes} دقائق (حوالي {target_words} كلمة)

الحقائق والمعلومات المرجعية:
{research_text}

تذكير أخير: اكتب حصراً عن "{topic}". أي انحراف عن الموضوع سيؤدي لرفض السكربت فوراً.
اكتب السكربت الآن — خمسة مشاهد كاملة كما هو محدد في تعليماتك."""


class ScriptWriter:
    """Professional Arabic documentary script writer using Qwen 3.5-27B."""

    def __init__(self, config: dict):
        self.config = config

    def write_script(
        self,
        topic: str,
        research: dict,
        seo_data: dict,
        channel_config: dict,
        performance_rules: list[dict] = None,
    ) -> str:
        """Write a professional Arabic documentary script."""
        title = seo_data.get("selected_title", f"الحقيقة عن {topic}")
        channel_name = channel_config.get("name", "وثائقيات")

        target_min = channel_config.get("content", {}).get("target_length_min", [8, 12])
        if isinstance(target_min, list):
            target_minutes = (target_min[0] + target_min[1]) // 2
        else:
            target_minutes = target_min
        target_words = target_minutes * 130

        research_text = research.get("research_text", f"الموضوع: {topic}")
        if len(research_text) > 6000:
            research_text = research_text[:6000] + "\n\n[... المزيد من التفاصيل ...]"

        angle = research.get("angle", "تحليل شامل مع قصص استكشاف")

        prompt = WRITER_PROMPT.format(
            topic=topic,
            angle=angle,
            target_minutes=target_minutes,
            target_words=target_words,
            research_text=research_text,
        )

        result = generate(
            prompt=prompt,
            system=WRITER_SYSTEM,
            max_tokens=16384,
            temperature=0.6,
            think=False,  # Disable thinking — it eats 80%+ of output tokens
        )

        if not result:
            return ""

        # Validate topic relevance — Qwen sometimes hallucinates unrelated topics
        topic_keywords = [w for w in topic.split() if len(w) > 2]
        if topic_keywords and not any(kw in result for kw in topic_keywords):
            logger.warning(f"Script OFF-TOPIC! Retrying with reinforced prompt. Keywords missing: {topic_keywords}")
            result = generate(
                prompt=f"""⚠️⚠️⚠️ تنبيه: يجب أن تكتب حصراً عن "{topic}". الموضوع هو "{topic}" ولا شيء غيره.

{prompt}""",
                system=WRITER_SYSTEM,
                max_tokens=16384,
                temperature=0.4,
                think=False,
            )
            if not result:
                return ""

        script_text = self._extract_narration(result)
        word_count = len(script_text.split())

        if word_count < target_words * 0.6:
            logger.warning(f"Script too short ({word_count} words vs target {target_words})")
            result2 = generate(
                prompt=f"""⚠️ الموضوع: {topic}

السكربت السابق ({word_count} كلمة) أقصر من المطلوب {target_words} كلمة.
وسّع كل مشهد بتفاصيل إضافية وقصص أعمق عن "{topic}" حصراً.
أعد كتابة السكربت كاملاً بالطول المطلوب. لا تغيّر الموضوع.""",
                system=WRITER_SYSTEM,
                max_tokens=16384,
                temperature=0.6,
                think=False,
            )
            if result2 and len(result2.split()) > word_count:
                script_text = self._extract_narration(result2)

        return script_text

    def _extract_narration(self, raw_script: str) -> str:
        """Extract narration text from structured script (remove cues/headers/directions)."""
        lines = raw_script.strip().split("\n")
        narration_lines = []

        for line in lines:
            stripped = line.strip()
            # Skip empty lines
            if not stripped:
                continue
            # Skip direction cues in square brackets [المشهد: ...] [الصوت: ...]
            if stripped.startswith("[") and stripped.endswith("]"):
                continue
            # Skip inline cues like "- [المشهد: ...]"
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
            # Skip metadata lines (duration, topic type, etc.)
            if stripped.startswith("**المدة") or stripped.startswith("**الموضوع") or stripped.startswith("**نوع"):
                continue
            # Skip narration/speaker markers
            if stripped in ("🎙️ السرد:", "السرد:", "المذيع:", "المعلق:"):
                continue
            # Strip speaker prefixes if inline (e.g., "المعلق: في ذلك اليوم...")
            for prefix in ("المذيع:", "المعلق:", "السرد:", "🎙️ السرد:", "الراوي:"):
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):].strip()
                    break
            # Skip emoji-prefixed direction lines
            if stripped.startswith("📹") or stripped.startswith("🔊"):
                continue
            # Keep everything else as narration
            narration_lines.append(stripped)

        if narration_lines:
            text = "\n\n".join(narration_lines)
            return self._remove_youtube_cta(text)

        # Fallback: return raw script
        return self._remove_youtube_cta(raw_script)

    @staticmethod
    def _remove_youtube_cta(text: str) -> str:
        """Remove YouTube subscribe/like/bell CTA phrases that LLMs love to inject."""
        import re
        # Common YouTube CTA patterns in Arabic
        cta_patterns = [
            r'[فو]?لا\s*تنس[َى]\s*(الاشتراك|أن تشترك).*?(الجرس|القناة|إعجاب).*?[\.!؟\n]',
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
        # Clean up leftover whitespace
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text
