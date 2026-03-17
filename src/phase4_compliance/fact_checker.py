"""
Phase 4: Fact verification with sources.
Cross-references key claims with 2+ independent sources.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

FACT_CHECK_PROMPT = """أنت مدقق حقائق محترف.
تحقق من الادعاءات الواردة في السكربت التالي:

═══ السكربت ═══
{script_text}

═══ المصادر المتاحة للتحقق ═══
{sources_text}

═══ المطلوب ═══
1. حدد كل ادعاء واقعي في السكربت (تواريخ، أرقام، أسماء، أحداث)
2. تحقق من كل ادعاء مقابل المصادر
3. صنّف كل ادعاء:
   - verified: مؤكد بمصدرين على الأقل
   - partially_verified: مؤكد بمصدر واحد
   - unverified: لم يتم التحقق منه
   - disputed: متنازع عليه بين المصادر
   - false: خاطئ بوضوح

أجب بـ JSON:
{{
    "total_claims": 15,
    "verified": 10,
    "partially_verified": 3,
    "unverified": 1,
    "disputed": 1,
    "false": 0,
    "score": 8.5,
    "status": "pass|warn|block",
    "claims": [
        {{
            "claim": "الادعاء",
            "status": "verified|partially_verified|unverified|disputed|false",
            "confidence": 0.9,
            "sources": ["مصدر1", "مصدر2"],
            "correction": null,
            "suggestion": null
        }}
    ],
    "high_risk_claims": [
        {{
            "claim": "الادعاء الخطير",
            "risk": "يمكن أن يسبب إشكالية قانونية/سياسية",
            "recommendation": "أضف تحفظاً: 'وفقاً لبعض المصادر...'"
        }}
    ]
}}"""


class FactChecker:
    """Verify factual claims in the script against sources."""

    def __init__(self, config: dict):
        self.config = config

    def check(
        self,
        script_text: str,
        research_sources: list[dict] = None,
    ) -> dict:
        """
        Cross-reference script claims with research sources.
        Requires 2+ sources for key claims.
        """
        if research_sources is None:
            research_sources = []

        text = script_text[:6000] if len(script_text) > 6000 else script_text
        sources_text = self._format_sources(research_sources)

        try:
            result = generate_json(
                prompt=FACT_CHECK_PROMPT.format(
                    script_text=text,
                    sources_text=sources_text,
                ),
                temperature=0.2,
            )

            total = result.get("total_claims", 0)
            verified = result.get("verified", 0)
            false_claims = result.get("false", 0)
            score = float(result.get("score", 5))

            # Override status based on false claims
            if false_claims > 0:
                result["status"] = "block"
                score = min(score, 3.0)
            elif result.get("unverified", 0) > total * 0.3:
                result["status"] = "warn"
                score = min(score, 6.0)

            result["score"] = score

            logger.info(
                f"Fact check: {result.get('status', '?').upper()} "
                f"(verified: {verified}/{total}, false: {false_claims}, score: {score})"
            )
            return result

        except Exception as e:
            logger.error(f"Fact checking failed: {e}")
            return {
                "status": "warn",
                "score": 5.0,
                "total_claims": 0,
                "verified": 0,
                "false": 0,
                "claims": [],
                "error": str(e),
            }

    def _format_sources(self, sources: list[dict], max_chars: int = 4000) -> str:
        """Format sources for LLM context."""
        lines = []
        total = 0
        for s in sources:
            title = s.get("title", "")
            url = s.get("url", "")
            snippet = s.get("snippet", s.get("summary", ""))[:300]
            line = f"- {title}\n  {snippet}\n  {url}\n"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(lines) if lines else "لا توجد مصادر خارجية للتحقق — اعتمد على معرفتك."
