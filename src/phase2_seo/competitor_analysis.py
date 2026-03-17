"""
Phase 2: Competitor analysis — find content gaps.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

GAP_ANALYSIS_PROMPT = """أنت محلل محتوى YouTube متخصص بالمحتوى العربي.

الموضوع المطلوب: {topic}

فيديوهات المنافسين الموجودة على هذا الموضوع:
{competitor_videos}

حلّل المحتوى الموجود واكتشف الفجوات:
1. ما الزوايا التي لم يتناولها أحد؟
2. ما الأسئلة التي لم تُجَب؟
3. ما نقاط الضعف في الفيديوهات الموجودة؟
4. ما الزاوية الفريدة التي يمكننا تقديمها؟

أجب بـ JSON:
{{
    "unique_angles": ["زاوية فريدة 1", "زاوية فريدة 2"],
    "unanswered_questions": ["سؤال لم يُجَب 1", "سؤال 2"],
    "competitor_weaknesses": ["نقطة ضعف 1", "نقطة ضعف 2"],
    "recommended_angle": "الزاوية الموصى بها لفيديونا",
    "recommended_hook": "الخطاف الافتتاحي المقترح",
    "differentiation_score": 8.5
}}"""


class CompetitorAnalysis:
    """Analyze top videos on a topic to find content gaps."""

    def __init__(self, config: dict):
        self.config = config

    def find_content_gap(
        self,
        topic: str,
        competitor_data: dict,
    ) -> dict:
        """
        Analyze competitor titles/descriptions and find unique angles.
        Uses Qwen 3.5 for analysis.
        """
        # Format competitor videos for LLM
        videos_text = self._format_competitor_data(competitor_data)

        prompt = GAP_ANALYSIS_PROMPT.format(
            topic=topic,
            competitor_videos=videos_text,
        )

        try:
            result = generate_json(prompt=prompt, temperature=0.5)

            logger.info(
                f"Gap analysis for '{topic}': "
                f"{len(result.get('unique_angles', []))} unique angles found"
            )
            return result

        except Exception as e:
            logger.error(f"Competitor analysis failed: {e}")
            return {
                "unique_angles": ["تحليل شامل ومعمّق"],
                "unanswered_questions": [],
                "competitor_weaknesses": [],
                "recommended_angle": "تناول شامل مع تحليل عميق",
                "recommended_hook": f"ما لا تعرفه عن {topic}",
                "differentiation_score": 5.0,
            }

    def _format_competitor_data(self, data: dict) -> str:
        """Format competitor data for LLM context."""
        lines = []
        titles = data.get("top_titles", [])
        descriptions = data.get("descriptions", [])

        for i, title in enumerate(titles[:15]):
            desc = descriptions[i] if i < len(descriptions) else ""
            lines.append(f"{i+1}. العنوان: {title}")
            if desc:
                lines.append(f"   الوصف: {desc[:200]}")

        avg_views = data.get("avg_views", 0)
        if avg_views:
            lines.append(f"\nمتوسط المشاهدات: {avg_views:,}")

        return "\n".join(lines) if lines else "لا توجد فيديوهات منافسة واضحة"
