"""
Scene data model — the fundamental unit connecting script to production.
"""

from pydantic import BaseModel, Field
from typing import Optional


class TextOverlay(BaseModel):
    text: str
    style: str = "fact"
    position: str = "bottom_center"
    animation: str = "fade_slide"


class Scene(BaseModel):
    scene_index: int
    narration_text: str
    duration_seconds: float = Field(ge=3, le=30)
    visual_prompt: str
    visual_style: str = "photorealistic_cinematic"
    camera_movement: str = "slow_zoom_in"
    music_mood: str = "dramatic"
    sfx: list[str] = Field(default_factory=list)
    text_overlay: Optional[TextOverlay] = None
    expected_visual_elements: list[str] = Field(default_factory=list)
    transition_to_next: str = "crossfade"
    presenter_mode: str = "none"
    voice_emotion: str = "calm"
    image_path: Optional[str] = None
    image_upscaled_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    voice_path: Optional[str] = None
    image_score: Optional[float] = None
    video_method: Optional[str] = None
