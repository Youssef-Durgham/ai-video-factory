"""
Phase 4: Anti-low-effort AI content scoring.
Ensures content won't be flagged by YouTube as low-effort AI.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

AI_QUALITY_PROMPT = """أنت مقيّم جودة محتوى YouTube متخصص بكشف المحتوى منخفض الجهد.

YouTube يصنف المحتوى التالي كـ "محتوى AI منخفض الجهد" ويعاقب عليه:
❌ صور AI بدون تعليق صوتي (عرض شرائح)
❌ تعليق صوتي AI عام بدون شخصية أو رأي
❌ لا تحليل أصلي أو وجهة نظر شخصية
❌ أنماط بصرية متكررة (نفس الأسلوب في كل إطار)
❌ لا بنية سردية (مجرد سرد حقائق)

قيّم السكربت التالي:

{script_text}

معلومات المشاهد:
- عدد المشاهد: {scene_count}
- أنماط بصرية مختلفة: {unique_styles}
- مشاهد بنص overlay: {overlay_count}

أجب بـ JSON:
{{
    "score": 8,
    "status": "pass|warn|block",
    "checks": {{
        "original_analysis": {{
            "score": 8,
            "found": true,
            "examples": ["مثال على تحليل أصلي في السكربت"]
        }},
        "rhetorical_questions": {{
            "score": 7,
            "count": 5,
            "adequate": true
        }},
        "personal_perspective": {{
            "score": 8,
            "found": true,
            "examples": ["مثال على رأي أو منظور شخصي"]
        }},
        "emotional_arc": {{
            "score": 7,
            "has_arc": true,
            "peaks_count": 2
        }},
        "narrative_structure": {{
            "score": 8,
            "has_story": true,
            "structure_type": "investigative|storytelling|explainer"
        }},
        "visual_variety": {{
            "score": 7,
            "unique_styles": 3,
            "adequate": true
        }},
        "production_value": {{
            "score": 8,
            "has_overlays": true,
            "has_structure": true
        }}
    }},
    "recommendations": ["توصية لرفع الجودة"],
    "youtube_ai_label_required": true
}}"""


class AIContentChecker:
    """Score content to ensure it's not flagged as low-effort AI."""

    def __init__(self, config: dict):
        self.config = config

    def check(
        self,
        script_text: str,
        scenes: list[dict] = None,
    ) -> dict:
        """
        Evaluate whether this content would be considered high-effort.
        Score >= 7: PASS — high-effort content
        Score 4-6: WARN — add more original analysis
        Score < 4: BLOCK — too generic, YouTube may flag
        """
        if scenes is None:
            scenes = []

        # Count scene variety
        unique_styles = len(set(s.get("visual_style", "") for s in scenes))
        overlay_count = sum(1 for s in scenes if s.get("text_overlay"))

        text = script_text[:6000] if len(script_text) > 6000 else script_text

        try:
            result = generate_json(
                prompt=AI_QUALITY_PROMPT.format(
                    script_text=text,
                    scene_count=len(scenes),
                    unique_styles=unique_styles,
                    overlay_count=overlay_count,
                ),
                temperature=0.2,
            )

            score = float(result.get("score", 5))

            # Determine status
            if score >= 7:
                status = "pass"
            elif score >= 4:
                status = "warn"
            else:
                status = "block"

            result["status"] = status
            result["score"] = score

            logger.info(f"AI content check: {status.upper()} (score: {score}/10)")
            return result

        except Exception as e:
            logger.error(f"AI content check failed: {e}")
            return {
                "score": 5.0,
                "status": "warn",
                "checks": {},
                "recommendations": ["فشل الفحص — مراجعة يدوية"],
                "error": str(e),
            }
