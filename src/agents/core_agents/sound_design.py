"""
Sound Design Agent — Cinematic audio layering.
Manages ambient backgrounds, audio transitions, music ducking curves,
SFX timing relative to narration.
"""

import json
import logging
from typing import Optional

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

# Ambient background presets
AMBIENT_PRESETS = {
    "office": {"file": "office_hum.wav", "volume": 0.08},
    "city": {"file": "city_traffic.wav", "volume": 0.10},
    "nature": {"file": "forest_birds.wav", "volume": 0.12},
    "rain": {"file": "rain_gentle.wav", "volume": 0.10},
    "war_zone": {"file": "distant_artillery.wav", "volume": 0.08},
    "crowd": {"file": "crowd_murmur.wav", "volume": 0.10},
    "desert": {"file": "desert_wind.wav", "volume": 0.08},
    "ocean": {"file": "ocean_waves.wav", "volume": 0.10},
    "mosque": {"file": "mosque_ambient.wav", "volume": 0.06},
    "silence": {"file": None, "volume": 0.0},
}

# Music ducking configuration
DUCKING_DEFAULTS = {
    "voice_active": 0.15,       # Music volume when narration is playing
    "voice_pause": 0.35,        # Music volume during narration pauses
    "transition": 0.50,         # Music volume during scene transitions
    "intro": 0.80,              # Music volume during intro (no narration)
    "outro": 0.70,              # Music volume during outro
    "duck_attack_ms": 200,      # Fade-down speed
    "duck_release_ms": 500,     # Fade-up speed
}

# Audio transition types
AUDIO_TRANSITIONS = {
    "crossfade": {"duration_ms": 1000},
    "hard_cut": {"duration_ms": 0},
    "fade_out_in": {"fade_out_ms": 500, "silence_ms": 200, "fade_in_ms": 500},
    "swoosh": {"sfx": "swoosh.wav", "duration_ms": 600},
    "impact": {"sfx": "impact_boom.wav", "duration_ms": 400},
    "reverse_cymbal": {"sfx": "reverse_cymbal.wav", "duration_ms": 2000},
}


class SoundDesignAgent:
    """
    Designs the complete audio landscape for a video.
    Manages ambient layers, music ducking, SFX placement, and transitions.
    """

    def __init__(self, db: FactoryDB, ambient_dir: str = "data/ambient_library",
                 sfx_dir: str = "data/sfx_library"):
        self.db = db
        self.ambient_dir = ambient_dir
        self.sfx_dir = sfx_dir

    def run(self, job_id: str, scenes: list[dict]) -> dict:
        """
        Generate complete sound design plan for a video.

        Returns: {
            "ambient_layers": [...],
            "ducking_curves": [...],
            "sfx_timeline": [...],
            "audio_transitions": [...],
            "master_mix": {...},
        }
        """
        performance_rules = self._get_sound_rules()

        # Build ambient layer plan
        ambient = self._plan_ambient(scenes)

        # Build ducking curve
        ducking = self._plan_ducking(scenes)

        # Build SFX timeline
        sfx_timeline = self._plan_sfx(scenes)

        # Plan audio transitions between scenes
        transitions = self._plan_transitions(scenes)

        # Master mix settings
        master = self._master_mix_settings(performance_rules)

        plan = {
            "ambient_layers": ambient,
            "ducking_curves": ducking,
            "sfx_timeline": sfx_timeline,
            "audio_transitions": transitions,
            "master_mix": master,
        }

        # Save to DB
        self._save_plan(job_id, plan)

        logger.info(
            f"Sound design for {job_id}: {len(ambient)} ambient layers, "
            f"{len(sfx_timeline)} SFX cues, {len(transitions)} transitions"
        )
        return plan

    def _plan_ambient(self, scenes: list[dict]) -> list[dict]:
        """Select ambient backgrounds per scene based on content."""
        layers = []
        current_time_ms = 0

        for i, scene in enumerate(scenes):
            duration_ms = int(scene.get("duration_seconds", 10) * 1000)
            mood = scene.get("music_mood", "calm")

            # Select ambient based on scene content keywords
            narration = scene.get("narration_text", "").lower()
            ambient_key = self._match_ambient(narration, mood)
            preset = AMBIENT_PRESETS.get(ambient_key, AMBIENT_PRESETS["silence"])

            if preset["file"]:
                layers.append({
                    "scene_index": i,
                    "start_ms": current_time_ms,
                    "end_ms": current_time_ms + duration_ms,
                    "ambient_type": ambient_key,
                    "file": f"{self.ambient_dir}/{preset['file']}",
                    "volume": preset["volume"],
                    "fade_in_ms": 500 if i == 0 or (layers and layers[-1].get("ambient_type") != ambient_key) else 0,
                    "fade_out_ms": 500,
                })

            current_time_ms += duration_ms

        return layers

    def _plan_ducking(self, scenes: list[dict]) -> list[dict]:
        """Generate music volume ducking curves relative to narration."""
        curves = []
        current_time_ms = 0

        for i, scene in enumerate(scenes):
            duration_ms = int(scene.get("duration_seconds", 10) * 1000)
            narration_duration_ms = duration_ms - 500  # Assume narration fills most of scene

            # Narration active — duck music
            curves.append({
                "scene_index": i,
                "start_ms": current_time_ms,
                "end_ms": current_time_ms + narration_duration_ms,
                "music_volume": DUCKING_DEFAULTS["voice_active"],
                "attack_ms": DUCKING_DEFAULTS["duck_attack_ms"],
            })

            # Brief pause at end of scene — raise music slightly
            curves.append({
                "scene_index": i,
                "start_ms": current_time_ms + narration_duration_ms,
                "end_ms": current_time_ms + duration_ms,
                "music_volume": DUCKING_DEFAULTS["voice_pause"],
                "release_ms": DUCKING_DEFAULTS["duck_release_ms"],
            })

            current_time_ms += duration_ms

        return curves

    def _plan_sfx(self, scenes: list[dict]) -> list[dict]:
        """Place SFX at appropriate timestamps."""
        timeline = []
        current_time_ms = 0

        for i, scene in enumerate(scenes):
            duration_ms = int(scene.get("duration_seconds", 10) * 1000)
            sfx_list = scene.get("sfx", [])

            for j, sfx_desc in enumerate(sfx_list):
                # Distribute SFX evenly within the scene
                offset = int(duration_ms * (j + 1) / (len(sfx_list) + 1))
                timeline.append({
                    "scene_index": i,
                    "timestamp_ms": current_time_ms + offset,
                    "description": sfx_desc,
                    "volume": 0.5,
                    "duck_music": True,
                })

            current_time_ms += duration_ms

        return timeline

    def _plan_transitions(self, scenes: list[dict]) -> list[dict]:
        """Plan audio transitions between scenes."""
        transitions = []
        current_time_ms = 0

        for i, scene in enumerate(scenes):
            duration_ms = int(scene.get("duration_seconds", 10) * 1000)
            current_time_ms += duration_ms

            if i < len(scenes) - 1:
                next_scene = scenes[i + 1]
                curr_mood = scene.get("music_mood", "calm")
                next_mood = next_scene.get("music_mood", "calm")

                # Select transition type based on mood change
                if curr_mood == next_mood:
                    trans_type = "crossfade"
                elif next_mood in ("dramatic", "epic", "tense"):
                    trans_type = "impact"
                elif curr_mood in ("dramatic", "epic") and next_mood in ("calm", "reflective"):
                    trans_type = "fade_out_in"
                else:
                    trans_type = "crossfade"

                trans_config = AUDIO_TRANSITIONS.get(trans_type, AUDIO_TRANSITIONS["crossfade"])
                transitions.append({
                    "between_scenes": [i, i + 1],
                    "timestamp_ms": current_time_ms,
                    "type": trans_type,
                    **trans_config,
                })

        return transitions

    def _master_mix_settings(self, rules: list) -> dict:
        """Return master mix settings, adjusted by performance rules."""
        mix = {
            "voice_volume": 1.0,
            "music_volume": 0.25,
            "sfx_volume": 0.50,
            "ambient_volume": 0.10,
            "limiter_threshold_db": -1.0,
            "normalize": True,
            "sample_rate": 44100,
            "bit_depth": 24,
        }
        # Apply learned rules
        for rule in rules:
            if isinstance(rule, dict) and "mix_adjust" in rule:
                for k, v in rule["mix_adjust"].items():
                    if k in mix and isinstance(v, (int, float)):
                        mix[k] = v
        return mix

    def _match_ambient(self, narration: str, mood: str) -> str:
        """Match scene content to ambient preset."""
        keyword_map = {
            "حرب": "war_zone", "معركة": "war_zone", "قتال": "war_zone",
            "مدينة": "city", "شارع": "city", "عاصمة": "city",
            "طبيعة": "nature", "غابة": "nature", "جبل": "nature",
            "مطر": "rain", "عاصفة": "rain",
            "صحراء": "desert", "رمال": "desert",
            "بحر": "ocean", "محيط": "ocean",
            "مسجد": "mosque", "صلاة": "mosque",
            "جمهور": "crowd", "احتجاج": "crowd", "مظاهرة": "crowd",
        }
        for keyword, ambient in keyword_map.items():
            if keyword in narration:
                return ambient
        return "silence"

    def _get_sound_rules(self) -> list:
        """Fetch performance rules for sound design."""
        try:
            rows = self.db.conn.execute(
                "SELECT rule_text FROM performance_rules WHERE category = 'sound_design' AND active = 1"
            ).fetchall()
            rules = []
            for r in rows:
                try:
                    rules.append(json.loads(r["rule_text"]))
                except (json.JSONDecodeError, TypeError):
                    pass
            return rules
        except Exception:
            return []

    def _save_plan(self, job_id: str, plan: dict):
        """Save sound design plan to DB."""
        try:
            self.db.conn.execute(
                "UPDATE jobs SET sound_design = ? WHERE id = ?",
                (json.dumps(plan, ensure_ascii=False), job_id),
            )
            self.db.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save sound design plan: {e}")
