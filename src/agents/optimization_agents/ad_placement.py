"""
Ad Placement Agent — Smart mid-roll ad positions based on natural pauses in narration.
"""

import json
import logging
from typing import Optional

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

MIN_VIDEO_LENGTH_FOR_MIDROLLS_SEC = 480  # 8 minutes
MIN_INTERVAL_SEC = 120  # Minimum 2 min between ads
FIRST_AD_MIN_SEC = 180  # First ad no earlier than 3 min in
AVOID_END_SEC = 60  # No ads in last 60 seconds


class AdPlacementAgent:
    """
    Determines optimal mid-roll ad insertion points based on
    scene transitions, narration pauses, and retention data.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    def run(self, job_id: str, scenes: list[dict], total_duration_sec: float) -> list[dict]:
        """
        Calculate mid-roll ad positions.

        Returns: List of ad break positions with timestamps.
        """
        if total_duration_sec < MIN_VIDEO_LENGTH_FOR_MIDROLLS_SEC:
            logger.info(f"Video too short for mid-rolls: {total_duration_sec:.0f}s")
            return []

        # Find natural break points (scene transitions)
        breaks = self._find_natural_breaks(scenes)

        # Filter by timing constraints
        valid_breaks = self._filter_breaks(breaks, total_duration_sec)

        # Score breaks by suitability
        scored = self._score_breaks(valid_breaks, scenes)

        # Select optimal positions
        positions = self._select_positions(scored, total_duration_sec)

        logger.info(f"Ad placement for {job_id}: {len(positions)} mid-rolls in {total_duration_sec:.0f}s video")
        return positions

    def _find_natural_breaks(self, scenes: list[dict]) -> list[dict]:
        """Find natural pause points between scenes."""
        breaks = []
        cumulative_sec = 0.0

        for i, scene in enumerate(scenes):
            duration = scene.get("duration_seconds", 10)
            cumulative_sec += duration

            if i < len(scenes) - 1:
                next_scene = scenes[i + 1]
                # Score how "natural" this break point is
                mood_change = scene.get("music_mood") != next_scene.get("music_mood")
                transition = scene.get("transition_to_next", "crossfade")

                breaks.append({
                    "after_scene": i,
                    "timestamp_sec": round(cumulative_sec, 1),
                    "mood_change": mood_change,
                    "transition_type": transition,
                    "is_section_break": transition in ("fade_out_in", "hard_cut"),
                })

        return breaks

    def _filter_breaks(self, breaks: list[dict], total_duration: float) -> list[dict]:
        """Filter breaks by timing constraints."""
        return [
            b for b in breaks
            if FIRST_AD_MIN_SEC <= b["timestamp_sec"] <= total_duration - AVOID_END_SEC
        ]

    def _score_breaks(self, breaks: list[dict], scenes: list[dict]) -> list[dict]:
        """Score each break point by ad placement suitability."""
        for b in breaks:
            score = 50  # Base score
            if b.get("mood_change"):
                score += 20  # Mood changes are natural ad spots
            if b.get("is_section_break"):
                score += 30  # Section breaks are ideal
            if b.get("transition_type") == "fade_out_in":
                score += 15
            b["score"] = score

        return sorted(breaks, key=lambda x: x["score"], reverse=True)

    def _select_positions(self, scored_breaks: list[dict], total_duration: float) -> list[dict]:
        """Select final ad positions ensuring minimum intervals."""
        # Calculate target number of ads
        num_ads = max(1, int((total_duration - FIRST_AD_MIN_SEC) / (MIN_INTERVAL_SEC * 2)))
        num_ads = min(num_ads, 5)  # Cap at 5 mid-rolls

        selected = []
        for brk in scored_breaks:
            if len(selected) >= num_ads:
                break
            # Check minimum interval from existing selections
            too_close = any(
                abs(brk["timestamp_sec"] - s["timestamp_sec"]) < MIN_INTERVAL_SEC
                for s in selected
            )
            if not too_close:
                selected.append({
                    "timestamp_sec": brk["timestamp_sec"],
                    "after_scene": brk["after_scene"],
                    "score": brk["score"],
                    "reason": "mood_change" if brk.get("mood_change") else "section_break" if brk.get("is_section_break") else "natural_pause",
                })

        return sorted(selected, key=lambda x: x["timestamp_sec"])
