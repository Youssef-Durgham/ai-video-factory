"""
Job data model — represents a single video production job.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Job(BaseModel):
    id: str
    status: str = "pending"
    channel_id: str
    topic: str
    topic_source: str = "manual"
    topic_region: str = "global"
    priority: str = "normal"
    narrative_style: Optional[str] = None
    selected_voice_id: Optional[str] = None
    voice_selection_reason: Optional[str] = None
    target_length_min: Optional[int] = None
    script_revisions: int = 0
    image_regenerations: int = 0
    video_retries: int = 0
    blocked_at: Optional[datetime] = None
    blocked_reason: Optional[str] = None
    blocked_phase: Optional[str] = None
    manual_review_required: bool = False
    manual_review_status: Optional[str] = None
    manual_review_notes: Optional[str] = None
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    total_production_time_sec: Optional[int] = None
    total_gpu_time_sec: Optional[int] = None
