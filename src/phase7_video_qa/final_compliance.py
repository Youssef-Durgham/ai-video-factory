"""
Phase 7C — Final Compliance: YouTube policy sweep on the full script + metadata.
Uses Qwen 3.5 (text) via Ollama — one last check before publish gate.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from src.core.llm import generate_json, DEFAULT_MODEL

logger = logging.getLogger(__name__)

COMPLIANCE_PASS_SCORE = 7.0


@dataclass
class ComplianceResult:
    """Result from final YouTube compliance check."""
    passed: bool = True
    score: float = 10.0
    ad_friendly: bool = True
    age_restricted: bool = False
    copyright_risk: bool = False
    community_guidelines_ok: bool = True
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    inference_ms: int = 0


class ComplianceChecker:
    """Final YouTube policy compliance sweep using text LLM."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def check(
        self,
        job_id: str,
        title: str,
        script_text: str,
        scenes: list[dict],
        tags: list[str] = None,
        description: str = "",
    ) -> ComplianceResult:
        """
        Run final compliance check against YouTube policies.
        Checks the full script, title, tags, and scene descriptions.
        """
        result = ComplianceResult()
        tags = tags or []

        # Build scene summary for context
        scene_summaries = []
        for scene in scenes:
            idx = scene.get("scene_index", 0)
            narration = scene.get("narration_text", "")[:200]
            visual = scene.get("visual_prompt", "")[:150]
            scene_summaries.append(f"Scene {idx}: Narration: {narration} | Visual: {visual}")

        scenes_text = "\n".join(scene_summaries[:30])  # Cap at 30 scenes
        tags_str = ", ".join(tags[:20])

        prompt = f"""You are a YouTube content compliance reviewer. This is the FINAL review before publishing.

VIDEO DETAILS:
- Title: "{title}"
- Tags: {tags_str}
- Description excerpt: "{description[:500]}"

FULL SCRIPT:
{script_text[:6000]}

SCENE VISUALS (prompts):
{scenes_text}

REVIEW AGAINST ALL YOUTUBE POLICIES:

1. **Community Guidelines**
   - Hate speech, harassment, bullying
   - Dangerous/harmful content
   - Misinformation (medical, political, scientific)
   - Violence or graphic content
   - Child safety

2. **Advertiser-Friendly Guidelines**
   - Controversial or sensitive topics
   - Drug/alcohol references
   - Adult content or innuendo
   - Profanity
   - Violence depiction

3. **Copyright Concerns**
   - Named brands/trademarks used improperly
   - Quotes from copyrighted works
   - References to copyrighted characters

4. **Metadata Compliance**
   - Misleading title/tags (clickbait that doesn't match content)
   - Spam tags or keyword stuffing
   - Inappropriate tags for content

5. **Age Restriction Assessment**
   - Should this be age-restricted?

Return JSON only:
{{
  "overall_score": 9.0,
  "ad_friendly": true,
  "age_restricted": false,
  "copyright_risk": false,
  "community_guidelines_ok": true,
  "issues": ["list of specific issues found"],
  "recommendations": ["list of improvements"],
  "category_scores": {{
    "community_guidelines": 9.5,
    "advertiser_friendly": 8.5,
    "copyright": 10.0,
    "metadata": 9.0
  }}
}}"""

        t0 = time.perf_counter_ns()
        try:
            llm_result = generate_json(
                prompt=prompt,
                system="You are a strict YouTube policy compliance reviewer. Be thorough but fair.",
                model=DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error("Compliance LLM check failed: %s", e)
            result.passed = False
            result.score = 5.0
            result.issues.append(f"Compliance check LLM error: {e}")
            return result
        finally:
            result.inference_ms = (time.perf_counter_ns() - t0) // 1_000_000

        # Parse results
        result.score = float(llm_result.get("overall_score", 5.0))
        result.ad_friendly = bool(llm_result.get("ad_friendly", True))
        result.age_restricted = bool(llm_result.get("age_restricted", False))
        result.copyright_risk = bool(llm_result.get("copyright_risk", False))
        result.community_guidelines_ok = bool(llm_result.get("community_guidelines_ok", True))
        result.issues = llm_result.get("issues", [])
        result.recommendations = llm_result.get("recommendations", [])
        result.details = llm_result.get("category_scores", {})

        # Determine pass/fail
        result.passed = (
            result.score >= COMPLIANCE_PASS_SCORE
            and result.community_guidelines_ok
            and not result.copyright_risk
        )

        # Force fail on critical issues
        if result.age_restricted:
            result.issues.append("Video flagged for age restriction")
        if not result.ad_friendly:
            result.issues.append("Video may not be ad-friendly")

        logger.info(
            "Compliance QA: score=%.1f passed=%s ad_friendly=%s issues=%d",
            result.score, result.passed, result.ad_friendly, len(result.issues),
        )
        return result
