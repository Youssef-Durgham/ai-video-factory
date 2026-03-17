"""
Phase 4: Plagiarism detection.
Checks script text for plagiarized content against source documents.
"""

import logging
import hashlib
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class CopyrightChecker:
    """Check script for plagiarized or copyrighted content."""

    def __init__(self, config: dict):
        self.config = config
        self.similarity_threshold = 0.7  # 70% similarity = plagiarism

    def check(
        self,
        script_text: str,
        research_sources: list[dict] = None,
    ) -> dict:
        """
        Check for plagiarism by comparing script against source texts.
        Also checks for common copyrighted patterns.
        """
        issues = []
        score = 10.0

        if research_sources is None:
            research_sources = []

        # Check 1: Compare script paragraphs against source snippets
        script_paragraphs = [
            p.strip() for p in script_text.split("\n") if len(p.strip()) > 50
        ]

        for para in script_paragraphs:
            for source in research_sources:
                snippet = source.get("snippet", "") or source.get("summary", "")
                if not snippet or len(snippet) < 30:
                    continue

                similarity = self._text_similarity(para, snippet)
                if similarity > self.similarity_threshold:
                    issues.append({
                        "type": "plagiarism",
                        "severity": "major" if similarity > 0.85 else "minor",
                        "similarity": round(similarity, 2),
                        "script_excerpt": para[:100],
                        "source": source.get("title", source.get("url", "unknown")),
                        "suggestion": "أعد صياغة هذه الفقرة بأسلوبك الخاص أو أضف نسبها لمصدرها",
                    })
                    score -= 2 if similarity > 0.85 else 1

        # Check 2: Common copyrighted content patterns
        copyright_patterns = [
            "جميع الحقوق محفوظة",
            "حقوق النشر",
            "©",
            "منقول من",
            "نسخة من",
        ]
        for pattern in copyright_patterns:
            if pattern in script_text:
                issues.append({
                    "type": "copyright_marker",
                    "severity": "minor",
                    "details": f"يحتوي على عبارة '{pattern}' — قد يشير لمحتوى منسوخ",
                })
                score -= 0.5

        # Check 3: Verify attributions exist
        attribution_markers = ["وفقاً لـ", "حسب", "كما ذكر", "بحسب", "أشار", "نقلت"]
        has_attributions = any(m in script_text for m in attribution_markers)
        if not has_attributions and len(script_paragraphs) > 10:
            issues.append({
                "type": "missing_attribution",
                "severity": "major",
                "details": "السكربت لا يحتوي على أي نسب للمصادر",
                "suggestion": "أضف نسب المعلومات: 'وفقاً لـ...'",
            })
            score -= 2

        # Determine status
        score = max(0, min(10, score))
        major_count = sum(1 for i in issues if i.get("severity") == "major")

        if major_count >= 2 or score < 4:
            status = "block"
        elif issues:
            status = "warn"
        else:
            status = "pass"

        result = {
            "status": status,
            "score": score,
            "issues": issues,
            "total_paragraphs_checked": len(script_paragraphs),
            "sources_compared": len(research_sources),
            "has_attributions": has_attributions,
        }

        logger.info(
            f"Copyright check: {status.upper()} "
            f"(score: {score}, issues: {len(issues)})"
        )
        return result

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        # Normalize
        t1 = text1.strip().lower()
        t2 = text2.strip().lower()
        return SequenceMatcher(None, t1, t2).ratio()
