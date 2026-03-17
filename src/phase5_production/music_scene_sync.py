"""
Phase 5 — Music-Scene Sync: Dynamic per-mood-zone music generation.

Groups consecutive scenes by mood compatibility, generates one ACE-Step 1.5
track per mood zone, and manages crossfades at zone boundaries.

Pipeline:
  1. Script phase → MoodZone detection (group scenes by mood)
  2. Music phase  → Generate one track per zone via ACE-Step 1.5
  3. Compose phase → Crossfade between zone tracks
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# MOOD COMPATIBILITY GROUPS
# ════════════════════════════════════════════════════════════════

# Moods within the same group can share a single music track
MOOD_GROUPS: dict[str, set[str]] = {
    "tense":      {"tense", "dramatic", "suspenseful", "dark"},
    "hopeful":    {"hopeful", "inspiring", "triumphant", "uplifting"},
    "calm":       {"calm", "reflective", "peaceful", "meditative"},
    "sad":        {"sad", "somber", "melancholy", "mourning"},
    "exciting":   {"exciting", "energetic", "climactic", "epic", "climax"},
}

# Reverse map: mood → group key
_MOOD_TO_GROUP: dict[str, str] = {}
for _gk, _moods in MOOD_GROUPS.items():
    for _m in _moods:
        _MOOD_TO_GROUP[_m] = _gk


def _mood_group(mood: str) -> str:
    """Return the compatibility group key for a mood string."""
    return _MOOD_TO_GROUP.get(mood.lower().strip(), mood.lower().strip())


# ════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ════════════════════════════════════════════════════════════════


@dataclass
class MoodZone:
    """A contiguous zone of compatible moods across scenes."""
    zone_index: int
    mood_group: str
    dominant_mood: str
    start_scene: int          # scene index (0-based)
    end_scene: int            # inclusive
    duration_sec: float = 0.0
    music_prompt: str = ""
    music_path: str = ""
    crossfade_in_sec: float = 0.0
    crossfade_out_sec: float = 2.0


@dataclass
class MusicSyncPlan:
    """Full music sync plan for a video."""
    zones: list[MoodZone] = field(default_factory=list)
    total_duration_sec: float = 0.0
    zone_count: int = 0


# ════════════════════════════════════════════════════════════════
# MUSIC PROMPT TEMPLATES
# ════════════════════════════════════════════════════════════════

ZONE_PROMPT_TEMPLATES: dict[str, str] = {
    "tense": (
        "tense suspenseful documentary background music, dark ambient, "
        "minor key, sparse arrangement, {dur} seconds, original composition"
    ),
    "hopeful": (
        "hopeful uplifting background music, major key, gentle strings, "
        "warm piano, optimistic, inspiring, {dur} seconds, original composition"
    ),
    "calm": (
        "calm ambient background music, middle eastern oud, gentle, "
        "peaceful, reflective, {dur} seconds, original composition"
    ),
    "sad": (
        "sad melancholy background music, minor key, solo piano, "
        "somber strings, emotional, {dur} seconds, original composition"
    ),
    "exciting": (
        "exciting energetic cinematic music, powerful drums, brass, "
        "triumphant, dynamic, {dur} seconds, original composition"
    ),
}

DEFAULT_PROMPT_TEMPLATE = (
    "{mood} documentary background music, cinematic, atmospheric, "
    "{dur} seconds, original composition"
)


class MusicSceneSync:
    """
    Dynamic music generation synced to scene mood zones.

    Usage:
        sync = MusicSceneSync()
        plan = sync.detect_mood_zones(scenes)
        # Then pass plan.zones to MusicGen for per-zone generation
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.default_crossfade = self.config.get("zone_crossfade_sec", 2.0)

    # ─── Public API ───────────────────────────────────────────

    def detect_mood_zones(self, scenes: list[dict]) -> MusicSyncPlan:
        """
        Group consecutive scenes into mood-compatible zones.

        Args:
            scenes: Ordered scene dicts, each with:
                - index (int)
                - mood (str)
                - duration_sec (float)

        Returns:
            MusicSyncPlan with detected zones and generated prompts.
        """
        if not scenes:
            return MusicSyncPlan()

        zones: list[MoodZone] = []
        current_group = _mood_group(scenes[0].get("mood", "neutral"))
        zone_start = 0
        zone_duration = scenes[0].get("duration_sec", 10.0)
        moods_in_zone: list[str] = [scenes[0].get("mood", "neutral")]

        for i in range(1, len(scenes)):
            scene_mood = scenes[i].get("mood", "neutral")
            group = _mood_group(scene_mood)

            if group == current_group:
                # Same zone — extend
                zone_duration += scenes[i].get("duration_sec", 10.0)
                moods_in_zone.append(scene_mood)
            else:
                # New zone — finalize current
                zones.append(self._build_zone(
                    zone_index=len(zones),
                    mood_group=current_group,
                    moods=moods_in_zone,
                    start_scene=zone_start,
                    end_scene=i - 1,
                    duration_sec=zone_duration,
                ))

                # Start new zone
                current_group = group
                zone_start = i
                zone_duration = scenes[i].get("duration_sec", 10.0)
                moods_in_zone = [scene_mood]

        # Finalize last zone
        zones.append(self._build_zone(
            zone_index=len(zones),
            mood_group=current_group,
            moods=moods_in_zone,
            start_scene=zone_start,
            end_scene=len(scenes) - 1,
            duration_sec=zone_duration,
        ))

        # Set crossfade timings
        self._set_crossfades(zones)

        total = sum(z.duration_sec for z in zones)
        return MusicSyncPlan(
            zones=zones,
            total_duration_sec=total,
            zone_count=len(zones),
        )

    def get_music_prompts(self, plan: MusicSyncPlan) -> list[dict]:
        """
        Return a list of dicts ready for MusicGen, one per zone.

        Returns:
            List of {zone_index, prompt, duration_sec, mood_group}.
        """
        return [
            {
                "zone_index": z.zone_index,
                "prompt": z.music_prompt,
                "duration_sec": z.duration_sec,
                "mood_group": z.mood_group,
            }
            for z in plan.zones
        ]

    def get_crossfade_points(self, plan: MusicSyncPlan) -> list[dict]:
        """
        Return crossfade timing for FFmpeg audio mixing.

        Returns:
            List of {time_sec, crossfade_duration, from_zone, to_zone}.
        """
        points: list[dict] = []
        elapsed = 0.0
        for i, zone in enumerate(plan.zones):
            if i > 0:
                points.append({
                    "time_sec": elapsed,
                    "crossfade_duration": zone.crossfade_in_sec,
                    "from_zone": i - 1,
                    "to_zone": i,
                })
            elapsed += zone.duration_sec
        return points

    # ─── Internal ─────────────────────────────────────────────

    def _build_zone(
        self,
        zone_index: int,
        mood_group: str,
        moods: list[str],
        start_scene: int,
        end_scene: int,
        duration_sec: float,
    ) -> MoodZone:
        """Build a MoodZone with generated music prompt."""
        # Pick dominant mood (most frequent)
        from collections import Counter
        dominant = Counter(moods).most_common(1)[0][0]

        # Generate prompt
        template = ZONE_PROMPT_TEMPLATES.get(
            mood_group,
            DEFAULT_PROMPT_TEMPLATE,
        )
        prompt = template.format(
            dur=int(duration_sec),
            mood=dominant,
        )

        return MoodZone(
            zone_index=zone_index,
            mood_group=mood_group,
            dominant_mood=dominant,
            start_scene=start_scene,
            end_scene=end_scene,
            duration_sec=duration_sec,
            music_prompt=prompt,
        )

    def _set_crossfades(self, zones: list[MoodZone]) -> None:
        """Set crossfade durations between adjacent zones."""
        for i, zone in enumerate(zones):
            if i == 0:
                zone.crossfade_in_sec = 0.0
            else:
                zone.crossfade_in_sec = self.default_crossfade

            if i == len(zones) - 1:
                zone.crossfade_out_sec = 0.0
            else:
                zone.crossfade_out_sec = self.default_crossfade
