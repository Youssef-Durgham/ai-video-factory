"""
Phase 4: YouTube ToS compliance check.
Verifies script doesn't violate YouTube Community Guidelines.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

POLICY_CHECK_PROMPT = """أنت مدقق سياسات YouTube متخصص.
راجع السكربت التالي وتحقق من عدم انتهاكه لسياسات YouTube:

═══ السكربت ═══
{script_text}

═══ السياسات المطلوب التحقق منها ═══
1. خطاب الكراهية أو التمييز
2. تمجيد العنف أو وصف مشاهد عنيفة بشكل بياني
3. التحرش أو التنمر ضد أفراد محددين
4. أنشطة خطيرة أو ضارة
5. ادعاءات طبية/علمية مضللة
6. معلومات انتخابية مضللة
7. سلامة الأطفال
8. ممارسات خادعة أو spam
9. للمحتوى السياسي:
   - يجب تقديم حقائق لا دعاية
   - الادعاءات المثيرة للجدل يجب نسبها: "وفقاً لـ..."
   - لا دعوة للعنف
   - لا استهداف مجموعات محمية

أجب بـ JSON:
{{
    "status": "pass|warn|block",
    "score": 9.0,
    "checks": [
        {{
            "policy": "اسم السياسة",
            "status": "pass|warn|fail",
            "details": "التفاصيل",
            "location": "موقع المشكلة في السكربت (إن وجدت)"
        }}
    ],
    "overall_risk": "low|medium|high",
    "recommendations": ["توصية 1", "توصية 2"],
    "requires_disclosure": true,
    "sensitive_topics": ["politics", "religion"]
}}"""


class YouTubePolicyChecker:
    """Check script against YouTube Community Guidelines."""

    def __init__(self, config: dict):
        self.config = config

    def check(self, script_text: str) -> dict:
        """
        Run YouTube policy compliance check on script.
        Returns dict with status, score, and detailed checks.
        """
        # Trim for token limits
        text = script_text[:8000] if len(script_text) > 8000 else script_text

        try:
            result = generate_json(
                prompt=POLICY_CHECK_PROMPT.format(script_text=text),
                temperature=0.2,  # Very low — we want consistent evaluation
            )

            status = result.get("status", "pass")
            score = float(result.get("score", 5))

            # Check for automatic blocks
            checks = result.get("checks", [])
            has_fail = any(c.get("status") == "fail" for c in checks)
            if has_fail:
                status = "block"

            result["status"] = status
            result["score"] = score

            logger.info(
                f"YouTube policy check: {status.upper()} "
                f"(score: {score}, risk: {result.get('overall_risk', '?')})"
            )
            return result

        except Exception as e:
            logger.error(f"YouTube policy check failed: {e}")
            return {
                "status": "warn",
                "score": 5.0,
                "checks": [],
                "overall_risk": "unknown",
                "recommendations": ["فشل الفحص التلقائي — مراجعة يدوية مطلوبة"],
                "error": str(e),
            }
