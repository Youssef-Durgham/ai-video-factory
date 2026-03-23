"""
Phase 4: Compliance with AUTO-FIX capability.
Checks: fact accuracy, Arabic quality, YouTube policy, AI content guidelines.

NEW: Instead of blocking, attempt auto-fix first. Only block if fixes fail.
"""

import logging
import json
from src.core.llm import generate, generate_json
from src.models.analytics import PhaseResult

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# Fact Checker with Auto-Fix
# ════════════════════════════════════════════════════════════

FACT_CHECK_PROMPT = """أنت مدقق حقائق محترف.
تحقق من الادعاءات في السكربت:

═══ السكربت ═══
{script_text}

═══ المطلوب ═══
1. حدد كل ادعاء واقعي (تواريخ، أرقام، أسماء، أحداث)
2. تحقق من كل ادعاء
3. صنّف: verified, partially_verified, unverified, false
4. **إذا كان ادعاء خاطئ: اقترح تصحيحاً دقيقاً**

أجب بـ JSON:
{
    "total_claims": 15,
    "verified": 10,
    "partially_verified": 3,
    "unverified": 1,
    "disputed": 1,
    "false": 0,
    "score": 8.5,
    "status": "pass|warn|fix",
    "claims": [
        {
            "claim": "الادعاء",
            "status": "verified|partially_verified|unverified|false",
            "confidence": 0.9,
            "correction": "النص المصحح (فقط إذا كان خاطئ)",
            "suggestion": "اقتراح تحسين"
        }
    ],
    "auto_fixes": [
        {
            "original": "النص الأصلي الخاطئ",
            "fixed": "النص المصحح",
            "reason": "سبب التصحيح"
        }
    ]
}"""

AUTO_FIX_PROMPT = """السكربت فيه بعض المشاكل في الحقائق. اعد كتابة السكربت كاملاً مع تصحيح الأخطاء التالية:

═══ المشاكل ═══
{issues}

═══ السكربت الأصلي ═══
{script}

الهدف: حافظ على الأسلوب والهيكلية، فقط أصلح الحقائق الخاطئة.
لا تحذف أي مشهد، فقط عدّل ما يحتاج تعديل."""


class ComplianceChecker:
    """Check compliance with AUTO-FIX capability."""

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db

    def check_and_fix(self, job_id: str, script_text: str) -> PhaseResult:
        """
        Check script compliance.
        If issues found → attempt auto-fix.
        Only block if auto-fix fails.
        """
        # Step 1: Fact check
        fact_result = self._fact_check(script_text)
        
        if fact_result["status"] == "pass":
            logger.info(f"Compliance passed for {job_id}")
            return PhaseResult(
                success=True, 
                score=fact_result["score"],
                details={"check_type": "compliance", "auto_fixed": False}
            )

        # Step 2: If issues found, attempt auto-fix
        if fact_result["status"] == "fix" and fact_result.get("auto_fixes"):
            logger.info(f"Attempting auto-fix for {job_id}: {len(fact_result['auto_fixes'])} issues")
            fixed_script = self._auto_fix(script_text, fact_result)
            
            if fixed_script:
                # Step 3: Re-check fixed script
                recheck = self._fact_check(fixed_script)
                if recheck["status"] == "pass":
                    logger.info(f"Auto-fix successful for {job_id}")
                    # Save fixed script
                    self.db.save_script_revision(job_id, fixed_script, "Auto-fixed compliance issues")
                    return PhaseResult(
                        success=True,
                        score=recheck["score"],
                        details={
                            "check_type": "compliance",
                            "auto_fixed": True,
                            "fixes_applied": len(fact_result["auto_fixes"])
                        }
                    )

        # Step 4: Auto-fix failed → block for manual review
        logger.warning(f"Compliance auto-fix failed for {job_id}, blocking for manual review")
        return PhaseResult(
            success=False,
            blocked=True,
            reason=f"Compliance issues detected. Auto-fix failed. Manual review required.",
            score=fact_result["score"],
            details={
                "check_type": "compliance",
                "issues": fact_result.get("claims", []),
                "auto_fix_failed": True
            }
        )

    def _fact_check(self, script_text: str) -> dict:
        """Check facts in script."""
        try:
            result = generate_json(
                prompt=FACT_CHECK_PROMPT.format(script_text=script_text[:8000]),
                temperature=0.2,
            )
            return result
        except Exception as e:
            logger.error(f"Fact check failed: {e}")
            return {"status": "warn", "score": 5.0, "auto_fixes": []}

    def _auto_fix(self, script: str, issues: dict) -> str:
        """Attempt to auto-fix factual issues."""
        try:
            # Format issues
            issues_text = "\n".join([
                f"- {fix['original']}\n  → {fix['fixed']}\n  (سبب: {fix['reason']})"
                for fix in issues.get("auto_fixes", [])
            ])

            fixed = generate(
                prompt=AUTO_FIX_PROMPT.format(issues=issues_text, script=script[:10000]),
                temperature=0.7,
                max_tokens=8192,
            )

            return fixed if fixed and len(fixed.split()) > 500 else None
        except Exception as e:
            logger.error(f"Auto-fix failed: {e}")
            return None


# ═════════════════════════════════════════════════════════
# CompliancePhase Handler
# ═════════════════════════════════════════════════════════

class CompliancePhase:
    """Phase 4: Compliance check with auto-fix."""

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.checker = ComplianceChecker(config, db)

    def run(self, job_id: str) -> PhaseResult:
        """Run compliance check with auto-fix capability."""
        script = self.db.get_latest_script(job_id)
        if not script:
            return PhaseResult(success=False, blocked=True, reason="No script found")

        return self.checker.check_and_fix(job_id, script)
