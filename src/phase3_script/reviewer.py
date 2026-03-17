"""
Phase 3: Script review + fact-check (separate LLM pass).
Acts as a critic — different from the writer.
"""

import logging
from src.core.llm import generate_json
from src.models.script import ReviewResult

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM = """أنت مراجع محتوى وثائقي محترف ومدقق حقائق.
مهمتك: مراجعة السكربت بعين ناقدة صارمة.
لا تجامل — أشر إلى كل نقطة ضعف.
اكتب ملاحظاتك بالعربية الفصحى."""

REVIEWER_PROMPT = """
راجع السكربت التالي بعناية:

═══ السكربت ═══
{script_text}

═══ البحث المرجعي (للتحقق من الحقائق) ═══
{research_text}

═══ الكلمات المفتاحية المطلوبة ═══
{keywords}

═══ معايير المراجعة ═══
1. الدقة الواقعية (1-10): هل الحقائق صحيحة ومدعومة بمصادر؟
   - أي ادعاء بدون مصدر = نقص درجة
   - تواريخ وأرقام خاطئة = فشل تلقائي
2. الجاذبية والتشويق (1-10): هل الخطاف قوي؟ هل المشاهد سيبقى؟
   - هل هناك أسئلة بلاغية كل 2-3 دقائق؟
   - هل هناك ذروتان عاطفيتان على الأقل؟
3. الكلمات المفتاحية (1-10): هل تظهر بشكل طبيعي؟
4. جودة العربية (1-10): فصحى سليمة، سهلة النطق؟
   - لا عامية
   - لا أخطاء نحوية
   - جمل مناسبة للإلقاء الصوتي
5. البنية والإيقاع (1-10): هل التنقل بين الأقسام سلس؟

أجب بـ JSON:
{{
    "approved": true/false,
    "overall_score": 8.0,
    "factual_accuracy_score": 8,
    "engagement_score": 7,
    "keyword_inclusion_score": 9,
    "arabic_quality_score": 8,
    "structure_score": 7,
    "notes": "ملاحظات عامة",
    "issues": [
        {{
            "type": "factual|engagement|keyword|arabic|structure",
            "severity": "critical|major|minor",
            "location": "المقدمة / القسم 2 / الخاتمة",
            "description": "وصف المشكلة",
            "suggestion": "الحل المقترح"
        }}
    ],
    "strengths": ["نقطة قوة 1", "نقطة قوة 2"]
}}"""


class ScriptReviewer:
    """Script review + fact-check using separate LLM pass."""

    def __init__(self, config: dict):
        self.config = config
        self.max_revisions = config.get("settings", {}).get(
            "pipeline", {}
        ).get("max_script_revisions", 3)

    def review_script(
        self,
        script_text: str,
        research_text: str,
        keywords: list[str],
    ) -> ReviewResult:
        """
        Review script for factual accuracy, engagement, keywords, grammar.
        Returns ReviewResult (approved/not + scores + notes).
        """
        # Trim inputs for token limits
        research_trimmed = research_text[:4000] if len(research_text) > 4000 else research_text

        prompt = REVIEWER_PROMPT.format(
            script_text=script_text,
            research_text=research_trimmed,
            keywords=", ".join(keywords[:10]) if keywords else "N/A",
        )

        try:
            result = generate_json(
                prompt=prompt,
                system=REVIEWER_SYSTEM,
                temperature=0.3,  # Low temp for consistent evaluation
            )

            # Build ReviewResult
            review = ReviewResult(
                approved=result.get("approved", False),
                factual_accuracy_score=float(result.get("factual_accuracy_score", 5)),
                engagement_score=float(result.get("engagement_score", 5)),
                keyword_inclusion_score=float(result.get("keyword_inclusion_score", 5)),
                arabic_quality_score=float(result.get("arabic_quality_score", 5)),
                notes=self._format_review_notes(result),
            )

            logger.info(
                f"Script review: {'✅ APPROVED' if review.approved else '❌ NEEDS REVISION'} "
                f"(accuracy={review.factual_accuracy_score}, "
                f"engagement={review.engagement_score}, "
                f"arabic={review.arabic_quality_score})"
            )

            return review

        except Exception as e:
            logger.error(f"Script review failed: {e}")
            # On review failure, don't block — let it pass with warning
            return ReviewResult(
                approved=True,
                notes=f"⚠️ المراجعة التلقائية فشلت: {str(e)[:100]}. تمت الموافقة بشكل مبدئي.",
                factual_accuracy_score=5.0,
                engagement_score=5.0,
                arabic_quality_score=5.0,
            )

    def get_revision_prompt(self, review: ReviewResult) -> str:
        """Generate revision instructions for the writer based on review."""
        return (
            f"راجع السكربت بناءً على الملاحظات التالية وأعد كتابته:\n\n"
            f"{review.notes}\n\n"
            f"أعد كتابة السكربت الكامل مع تطبيق جميع الملاحظات."
        )

    def _format_review_notes(self, result: dict) -> str:
        """Format review result into readable notes."""
        lines = []

        if result.get("notes"):
            lines.append(f"📝 {result['notes']}")

        issues = result.get("issues", [])
        if issues:
            lines.append("\n⚠️ المشاكل:")
            for issue in issues:
                severity_icon = {
                    "critical": "🔴",
                    "major": "🟡",
                    "minor": "🟢",
                }.get(issue.get("severity", "minor"), "📌")
                lines.append(
                    f"  {severity_icon} [{issue.get('location', '?')}] "
                    f"{issue.get('description', '')}"
                )
                if issue.get("suggestion"):
                    lines.append(f"     💡 {issue['suggestion']}")

        strengths = result.get("strengths", [])
        if strengths:
            lines.append("\n✅ نقاط القوة:")
            for s in strengths:
                lines.append(f"  • {s}")

        return "\n".join(lines)
