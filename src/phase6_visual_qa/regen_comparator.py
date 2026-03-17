"""
Phase 6 — Regeneration Comparator: Before/after asset comparison.

When an image or video is regenerated (attempt > 1), sends both versions
to Telegram with side-by-side scores, prompt changes, and inline buttons
for human review (Accept / Try Again / Edit Prompt).
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


@dataclass
class AssetVersion:
    """A single version of an asset (image or video)."""
    path: str = ""
    attempt: int = 1
    score: float = 0.0
    prompt: str = ""
    negative_prompt: str = ""
    issues: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    rubric_scores: dict = field(default_factory=dict)


@dataclass
class PromptDiff:
    """Differences between two prompts."""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    negative_added: list[str] = field(default_factory=list)
    negative_removed: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """Result of before/after comparison."""
    job_id: str = ""
    scene_index: int = 0
    asset_type: str = "image"       # image | video
    before: AssetVersion = field(default_factory=AssetVersion)
    after: AssetVersion = field(default_factory=AssetVersion)
    prompt_diff: PromptDiff = field(default_factory=PromptDiff)
    score_improvement: float = 0.0
    telegram_sent: bool = False


class RegenComparator:
    """
    Before/after comparison for regenerated assets.
    Builds comparison data and sends to Telegram with inline buttons.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.telegram_token = self.config.get("telegram_token", "")
        self.chat_id = self.config.get("telegram_chat_id", "")

    # ─── Public API ───────────────────────────────────────────

    def compare(
        self,
        job_id: str,
        scene_index: int,
        asset_type: str,
        before: AssetVersion,
        after: AssetVersion,
    ) -> ComparisonResult:
        """
        Build comparison between two asset versions.

        Args:
            job_id: Job identifier.
            scene_index: Scene number (0-based).
            asset_type: "image" or "video".
            before: Previous version data.
            after: New version data.

        Returns:
            ComparisonResult with diff and score data.
        """
        result = ComparisonResult(
            job_id=job_id,
            scene_index=scene_index,
            asset_type=asset_type,
            before=before,
            after=after,
        )

        result.prompt_diff = self._diff_prompts(before, after)
        result.score_improvement = after.score - before.score

        return result

    def compare_and_send(
        self,
        job_id: str,
        scene_index: int,
        asset_type: str,
        before: AssetVersion,
        after: AssetVersion,
    ) -> ComparisonResult:
        """Compare and send to Telegram in one call."""
        result = self.compare(job_id, scene_index, asset_type, before, after)
        self.send_comparison(result)
        return result

    def send_comparison(self, comparison: ComparisonResult) -> bool:
        """
        Send before/after comparison to Telegram.

        For images: sends both as a media group with captions.
        For videos: sends both clips sequentially with labels.
        Includes inline keyboard for Accept / Try Again / Edit Prompt.
        """
        if not self.telegram_token or not self.chat_id:
            logger.warning("Telegram not configured — skipping comparison send")
            return False

        try:
            caption = self._build_caption(comparison)

            if comparison.asset_type == "image":
                self._send_image_comparison(comparison, caption)
            else:
                self._send_video_comparison(comparison, caption)

            comparison.telegram_sent = True
            logger.info(
                "Sent regen comparison for job=%s scene=%d attempt=%d",
                comparison.job_id, comparison.scene_index,
                comparison.after.attempt,
            )
            return True

        except Exception as e:
            logger.error("Failed to send comparison to Telegram: %s", e)
            return False

    # ─── Caption Building ─────────────────────────────────────

    def _build_caption(self, c: ComparisonResult) -> str:
        """Build formatted Telegram caption for comparison."""
        emoji = "🖼" if c.asset_type == "image" else "🎬"
        lines = [
            f"🔄 Scene {c.scene_index + 1} — Regenerated (attempt {c.after.attempt})",
            "",
        ]

        # Scores
        score_emoji_before = "❌" if c.before.score < 7 else "⚠️"
        score_emoji_after = "✅" if c.after.score >= 7 else "⚠️"
        lines.append(
            f"{score_emoji_before} Before: {c.before.score:.1f}/10  →  "
            f"{score_emoji_after} After: {c.after.score:.1f}/10"
        )

        improvement = c.score_improvement
        if improvement > 0:
            lines.append(f"📈 Improvement: +{improvement:.1f}")
        elif improvement < 0:
            lines.append(f"📉 Regression: {improvement:.1f}")
        lines.append("")

        # Issues (before)
        if c.before.issues:
            lines.append("❌ Before issues:")
            for issue in c.before.issues[:5]:
                lines.append(f"  • {issue}")
            lines.append("")

        # Improvements (after)
        if c.after.improvements:
            lines.append("✅ After improvements:")
            for imp in c.after.improvements[:5]:
                lines.append(f"  • {imp}")
            lines.append("")

        # Prompt changes
        diff = c.prompt_diff
        if diff.added or diff.removed or diff.negative_added:
            lines.append("📝 Prompt changes:")
            for a in diff.added[:3]:
                lines.append(f'  + Added: "{a}"')
            for r in diff.removed[:3]:
                lines.append(f'  - Removed: "{r}"')
            for na in diff.negative_added[:3]:
                lines.append(f'  ⛔ Negative added: "{na}"')

        return "\n".join(lines)

    # ─── Telegram Sending ─────────────────────────────────────

    def _send_image_comparison(
        self, c: ComparisonResult, caption: str,
    ) -> None:
        """Send two images as a media group with comparison caption."""
        api = TELEGRAM_API.format(token=self.telegram_token)

        # Send media group (before + after)
        before_path = Path(c.before.path)
        after_path = Path(c.after.path)

        if before_path.exists() and after_path.exists():
            media = [
                {
                    "type": "photo",
                    "media": "attach://before",
                    "caption": f"❌ Before (attempt {c.before.attempt})",
                },
                {
                    "type": "photo",
                    "media": "attach://after",
                    "caption": f"✅ After (attempt {c.after.attempt})",
                },
            ]

            files = {
                "before": open(str(before_path), "rb"),
                "after": open(str(after_path), "rb"),
            }

            try:
                requests.post(
                    f"{api}/sendMediaGroup",
                    data={
                        "chat_id": self.chat_id,
                        "media": json.dumps(media),
                    },
                    files=files,
                    timeout=30,
                )
            finally:
                for f in files.values():
                    f.close()

        # Send caption + inline buttons as separate message
        callback_prefix = f"regen:{c.job_id}:{c.scene_index}:{c.after.attempt}"
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Accept", "callback_data": f"{callback_prefix}:accept"},
                    {"text": "🔄 Try Again", "callback_data": f"{callback_prefix}:retry"},
                    {"text": "✏️ Edit Prompt", "callback_data": f"{callback_prefix}:edit"},
                ]
            ]
        }

        requests.post(
            f"{api}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": caption,
                "reply_markup": keyboard,
            },
            timeout=15,
        )

    def _send_video_comparison(
        self, c: ComparisonResult, caption: str,
    ) -> None:
        """Send two video clips sequentially with comparison data."""
        api = TELEGRAM_API.format(token=self.telegram_token)

        for label, version in [("❌ BEFORE", c.before), ("✅ AFTER", c.after)]:
            vpath = Path(version.path)
            if vpath.exists():
                with open(str(vpath), "rb") as f:
                    requests.post(
                        f"{api}/sendVideo",
                        data={
                            "chat_id": self.chat_id,
                            "caption": f"{label} (attempt {version.attempt}) — Score: {version.score:.1f}/10",
                        },
                        files={"video": f},
                        timeout=60,
                    )

        # Caption + buttons
        callback_prefix = f"regen:{c.job_id}:{c.scene_index}:{c.after.attempt}"
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Accept", "callback_data": f"{callback_prefix}:accept"},
                    {"text": "🔄 Try Again", "callback_data": f"{callback_prefix}:retry"},
                    {"text": "✏️ Edit Prompt", "callback_data": f"{callback_prefix}:edit"},
                ]
            ]
        }

        requests.post(
            f"{api}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": caption,
                "reply_markup": keyboard,
            },
            timeout=15,
        )

    # ─── Prompt Diffing ──────────────────────────────────────

    @staticmethod
    def _diff_prompts(before: AssetVersion, after: AssetVersion) -> PromptDiff:
        """Compute differences between two prompt versions."""
        diff = PromptDiff()

        # Tokenize prompts by comma-separated phrases
        before_parts = {p.strip() for p in before.prompt.split(",") if p.strip()}
        after_parts = {p.strip() for p in after.prompt.split(",") if p.strip()}

        diff.added = sorted(after_parts - before_parts)
        diff.removed = sorted(before_parts - after_parts)

        # Negative prompts
        before_neg = {p.strip() for p in before.negative_prompt.split(",") if p.strip()}
        after_neg = {p.strip() for p in after.negative_prompt.split(",") if p.strip()}

        diff.negative_added = sorted(after_neg - before_neg)
        diff.negative_removed = sorted(before_neg - after_neg)

        return diff
