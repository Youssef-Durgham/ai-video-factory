"""
Phase 4: MSA grammar + pronunciation check for TTS readability.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

ARABIC_QA_PROMPT = """أنت مدقق لغوي عربي متخصص بالنصوص المعدّة للإلقاء الصوتي (TTS).

راجع النص التالي:

{script_text}

═══ معايير المراجعة ═══
1. فصحى صحيحة: لا عامية، لا أخطاء نحوية أو صرفية
2. سهولة النطق: لا كلمات ملتبسة، لا تراكيب ثقيلة على اللسان
3. إيقاع القراءة: جمل متنوعة الطول، مناسبة للإلقاء
4. لا لبس في النطق:
   - كلمات لها أكثر من نطق (بدون تشكيل) → وضّحها
   - أسماء أعلام غير عربية → أضف نطقها
   - أرقام كبيرة → تأكد أنها مكتوبة بطريقة مناسبة للقراءة
5. تجنب:
   - جمل أطول من 25 كلمة
   - تكرار نفس الكلمة في جملتين متتاليتين
   - بداية 3 جمل متتالية بنفس الأداة
   - كلمات نادرة قد يخطئ TTS في نطقها

أجب بـ JSON:
{{
    "score": 8.5,
    "status": "pass|warn|block",
    "grammar_issues": [
        {{
            "location": "الفقرة/الجملة",
            "issue": "وصف المشكلة",
            "original": "النص الأصلي",
            "corrected": "النص المصحح",
            "severity": "critical|major|minor"
        }}
    ],
    "pronunciation_issues": [
        {{
            "word": "الكلمة",
            "issue": "لماذا قد يخطئ TTS بنطقها",
            "suggestion": "بديل أوضح أو تشكيل"
        }}
    ],
    "readability_issues": [
        {{
            "issue": "جملة طويلة جداً / تكرار / إيقاع رتيب",
            "location": "الموقع",
            "suggestion": "الحل"
        }}
    ],
    "dialect_detected": false,
    "dialect_examples": [],
    "overall_notes": "ملاحظات عامة"
}}"""


class ArabicQualityChecker:
    """MSA grammar + TTS pronunciation friendliness check."""

    def __init__(self, config: dict):
        self.config = config

    def check(self, script_text: str) -> dict:
        """
        Check Arabic language quality and TTS readability.
        """
        text = script_text[:6000] if len(script_text) > 6000 else script_text

        try:
            result = generate_json(
                prompt=ARABIC_QA_PROMPT.format(script_text=text),
                temperature=0.2,
            )

            score = float(result.get("score", 5))

            # Count issues by severity
            grammar = result.get("grammar_issues", [])
            critical_count = sum(1 for g in grammar if g.get("severity") == "critical")

            # Dialect detection is automatic block
            if result.get("dialect_detected", False):
                result["status"] = "block"
                score = min(score, 4.0)
                logger.warning("Dialect detected in script — blocking")
            elif critical_count > 3:
                result["status"] = "block"
                score = min(score, 5.0)
            elif critical_count > 0 or len(grammar) > 5:
                result["status"] = "warn"
            else:
                result["status"] = result.get("status", "pass")

            result["score"] = score

            logger.info(
                f"Arabic quality: {result['status'].upper()} "
                f"(score: {score}, grammar issues: {len(grammar)}, "
                f"pronunciation issues: {len(result.get('pronunciation_issues', []))})"
            )
            return result

        except Exception as e:
            logger.error(f"Arabic quality check failed: {e}")
            return {
                "score": 5.0,
                "status": "warn",
                "grammar_issues": [],
                "pronunciation_issues": [],
                "readability_issues": [],
                "error": str(e),
            }
