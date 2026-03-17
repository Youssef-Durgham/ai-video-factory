"""
Phase 3: Full Arabic MSA script writing with Qwen 3.5-27B via Ollama.
"""

import logging
from src.core.llm import generate

logger = logging.getLogger(__name__)

WRITER_SYSTEM = """أنت كاتب سكربتات وثائقية عربية محترف.
تكتب بالعربية الفصحى المعاصرة (MSA).
أسلوبك: درامي، مشوّق، تعليمي، يحترم ذكاء المشاهد.
كل جملة مكتوبة لتُقرأ بصوت عالٍ — سهلة النطق، واضحة الإيقاع.
المرجع: أسلوب قنوات مثل "الفاتورة المرعبة" و"DW وثائقية"."""

WRITER_PROMPT = """
اكتب سكربت فيديو وثائقي كامل.

═══ معلومات الفيديو ═══
الموضوع: {topic}
الزاوية: {angle}
العنوان: {title}
القناة: {channel_name}
النبرة: {channel_tone}
الأسلوب السردي: {narrative_style}
المدة المستهدفة: {target_minutes} دقائق ({target_words} كلمة تقريباً)

═══ الكلمات المفتاحية (يجب تضمينها بشكل طبيعي) ═══
{keywords}

═══ قواعد من أداء الفيديوهات السابقة ═══
{performance_rules}

═══ البحث المرجعي ═══
{research_text}

═══ هيكل السكربت المطلوب ═══
1. الخطاف (0:00-0:15): جملة افتتاحية صادمة أو سؤال مثير — تطابق وعد العنوان
2. المقدمة (0:15-0:45): سياق سريع — لماذا هذا الموضوع مهم الآن؟
3. المحتوى الرئيسي (0:45-{main_end}): 3-5 أقسام، كل قسم يحتوي:
   - نقطة رئيسية مدعومة بحقائق
   - قصة أو مثال ملموس
   - سؤال بلاغي أو لحظة تشويق
4. الذروة ({climax_start}): كشف أو تحول درامي
5. الخاتمة ({conclusion_start}-{end}): تأمل + منظور مستقبلي
6. CTA ({end}): دعوة للاشتراك طبيعية وغير مزعجة

═══ قواعد الكتابة ═══
- عربية فصحى معاصرة — لا عامية إطلاقاً
- كل ادعاء مهم يُنسب: "وفقاً لـ..." "تشير الأرقام إلى..."
- أسئلة بلاغية كل 2-3 دقائق: "لكن هل تساءلتم...؟"
- تنويع الإيقاع: جمل قصيرة حادة ← شرح مفصّل ← جملة قصيرة مفاجئة
- لا تكرر نفس البنية في قسمين متتاليين
- اكتب للأذن لا للعين: تجنب التراكيب المعقدة والجمل الطويلة جداً
- حد أدنى ذروتين عاطفيتين في السكربت

اكتب السكربت كاملاً الآن. كل فقرة تمثل مشهداً (5-15 ثانية عند القراءة).
افصل بين المشاهد بسطر فارغ.
"""


class ScriptWriter:
    """Full Arabic MSA script writer using Qwen 3.5-27B."""

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
        """
        Write a complete Arabic documentary script.
        Returns the full script text.
        """
        # Extract SEO data
        title = seo_data.get("selected_title", f"الحقيقة عن {topic}")
        keywords = seo_data.get("primary_keywords", [topic])
        if isinstance(keywords, list) and keywords and isinstance(keywords[0], dict):
            keywords = [k.get("keyword", "") for k in keywords]

        # Channel config
        channel_name = channel_config.get("name", "وثائقيات")
        channel_tone = channel_config.get("content", {}).get("tone", "educational, engaging")
        narrative_style = channel_config.get("narrative_style", "storytelling")

        # Target length
        target_min = channel_config.get("content", {}).get("target_length_min", [8, 12])
        if isinstance(target_min, list):
            target_minutes = (target_min[0] + target_min[1]) // 2
        else:
            target_minutes = target_min
        target_words = target_minutes * 130  # ~130 WPM Arabic

        # Time markers
        main_end = f"{target_minutes - 2}:00"
        climax_start = f"{target_minutes - 2}:00"
        conclusion_start = f"{target_minutes - 1}:00"
        end = f"{target_minutes}:00"

        # Performance rules
        rules_text = "لا توجد قواعد مسبقة (أول فيديو)"
        if performance_rules:
            rules_text = "\n".join(
                f"- {r.get('rule_name', '')}: {r.get('rule_value', '')} ({r.get('reason', '')})"
                for r in performance_rules[:10]
            )

        # Research text
        research_text = research.get("research_text", f"الموضوع: {topic}")
        # Trim research to avoid token limit
        if len(research_text) > 6000:
            research_text = research_text[:6000] + "\n\n[... تم اختصار البحث ...]"

        prompt = WRITER_PROMPT.format(
            topic=topic,
            angle=research.get("angle", "تحليل شامل"),
            title=title,
            channel_name=channel_name,
            channel_tone=channel_tone,
            narrative_style=narrative_style,
            target_minutes=target_minutes,
            target_words=target_words,
            keywords=", ".join(keywords[:10]),
            performance_rules=rules_text,
            research_text=research_text,
            main_end=main_end,
            climax_start=climax_start,
            conclusion_start=conclusion_start,
            end=end,
        )

        try:
            script = generate(
                prompt=prompt,
                system=WRITER_SYSTEM,
                temperature=0.7,
                max_tokens=8192,
            )

            word_count = len(script.split())
            logger.info(f"Script written: {word_count} words (~{word_count // 130} min)")

            return script

        except Exception as e:
            logger.error(f"Script writing failed: {e}")
            raise
