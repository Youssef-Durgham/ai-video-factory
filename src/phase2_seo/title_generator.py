"""
Phase 2: LLM-powered Arabic title generation.
Generates and scores 10 titles using SEO data.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

TITLE_SYSTEM_PROMPT = """أنت خبير SEO متخصص في عناوين YouTube العربية.
تكتب عناوين تجذب النقرات وتحقق أعلى CTR مع الحفاظ على المصداقية.
لا تكتب عناوين مضللة — يجب أن يعكس العنوان محتوى الفيديو الفعلي."""

TITLE_PROMPT_TEMPLATE = """
اكتب 10 عناوين لفيديو YouTube عربي عن:

الموضوع: {topic}
الزاوية: {angle}
الكلمات المفتاحية الأساسية: {primary_keywords}
الكلمات المفتاحية الثانوية: {secondary_keywords}
أنماط العناوين الناجحة عند المنافسين: {title_patterns}

قواعد العناوين:
- أقل من 60 حرف (الأمثل 45-55)
- تحتوي على كلمة مفتاحية رئيسية واحدة على الأقل
- خطاف عاطفي (فضول، صدمة، سؤال)
- تُقرأ بشكل طبيعي بالعربية (RTL)
- لا تبدأ بـ "فيديو عن" أو ما شابه
- لا تستخدم علامات تعجب مبالغة (!!!!!)

أنماط مقترحة:
- سؤال: "لماذا...؟" "كيف...؟" "هل...؟"
- كشف: "الحقيقة التي..." "ما لا تعرفه عن..."
- قائمة: "أخطر 5..." "أغرب..."
- درامي: "انهيار..." "كارثة..." "القصة الكاملة لـ..."
- مباشر: "كل ما تحتاج معرفته عن..."

أجب بـ JSON:
{{
    "titles": [
        {{
            "title": "العنوان",
            "length": 45,
            "keywords_included": ["كلمة1", "كلمة2"],
            "hook_type": "question|revelation|list|dramatic|direct",
            "emotional_score": 8,
            "seo_score": 7,
            "overall_score": 7.5,
            "reasoning": "لماذا هذا العنوان جيد"
        }}
    ]
}}"""


class TitleGenerator:
    """Generate and score YouTube titles using LLM."""

    def __init__(self, config: dict):
        self.config = config

    def generate_titles(
        self,
        topic: str,
        keyword_report: dict,
        gap_analysis: dict,
    ) -> list[dict]:
        """
        Generate 10 titles using Qwen 3.5, scored by SEO + engagement.
        Returns sorted list (best first).
        """
        # Extract data for prompt
        top_keywords = keyword_report.get("top_results", {}).get("keywords", [])
        primary_kw = [k["keyword"] for k in top_keywords[:5]]
        secondary_kw = [k["keyword"] for k in top_keywords[5:15]]
        patterns = keyword_report.get("top_results", {}).get("title_patterns", [])

        angle = gap_analysis.get("recommended_angle", "تحليل شامل")

        prompt = TITLE_PROMPT_TEMPLATE.format(
            topic=topic,
            angle=angle,
            primary_keywords=", ".join(primary_kw) if primary_kw else topic,
            secondary_keywords=", ".join(secondary_kw) if secondary_kw else "N/A",
            title_patterns=str(patterns[:5]) if patterns else "لا توجد أنماط واضحة",
        )

        try:
            result = generate_json(
                prompt=prompt,
                system=TITLE_SYSTEM_PROMPT,
                temperature=0.7,
            )

            titles = result.get("titles", [])

            # Calculate final scores
            for t in titles:
                emotional = float(t.get("emotional_score", 5))
                seo = float(t.get("seo_score", 5))
                length = len(t.get("title", ""))

                # Length penalty
                length_score = 10 if 35 <= length <= 55 else (7 if length <= 60 else 4)

                # Keywords bonus
                kw_count = len(t.get("keywords_included", []))
                kw_score = min(10, kw_count * 3)

                t["overall_score"] = (
                    emotional * 0.30
                    + seo * 0.25
                    + length_score * 0.20
                    + kw_score * 0.15
                    + (10 if t.get("hook_type") in ("question", "revelation") else 7) * 0.10
                )

            # Sort by overall score
            titles.sort(key=lambda x: x.get("overall_score", 0), reverse=True)

            logger.info(
                f"Generated {len(titles)} titles. Best: '{titles[0]['title']}' "
                f"(score: {titles[0].get('overall_score', 0):.1f})"
                if titles else "No titles generated"
            )
            return titles

        except Exception as e:
            logger.error(f"Title generation failed: {e}")
            # Fallback titles
            return [
                {
                    "title": f"الحقيقة الكاملة عن {topic}",
                    "overall_score": 5.0,
                    "hook_type": "revelation",
                    "keywords_included": [topic],
                },
                {
                    "title": f"لماذا يتحدث الجميع عن {topic}؟",
                    "overall_score": 4.8,
                    "hook_type": "question",
                    "keywords_included": [topic],
                },
            ]
