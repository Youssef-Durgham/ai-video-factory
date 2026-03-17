"""
Analytics data models — YouTube performance tracking + phase results.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class YouTubeMetrics(BaseModel):
    video_id: str
    snapshot_period: str
    views: int = 0
    watch_time_hours: float = 0.0
    avg_view_duration_sec: int = 0
    avg_view_percentage: float = 0.0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0
    ctr: float = 0.0
    estimated_revenue: float = 0.0
    rpm: float = 0.0
    retention_curve: list[dict] = Field(default_factory=list)
    top_countries: list[dict] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=datetime.now)


class PerformanceRule(BaseModel):
    rule_name: str
    rule_value: str
    rule_type: str
    confidence: float = 0.0
    sample_size: int = 0
    reason: str = ""
    applies_to_channel: Optional[str] = None
    active: bool = True


class GateResult(BaseModel):
    passed: bool
    action: str
    reason: str = ""
    retry_phase: Optional[str] = None
    failed_items: list = Field(default_factory=list)
    score: float = 0.0


class PhaseResult(BaseModel):
    success: bool
    blocked: bool = False
    reason: str = ""
    needs_regeneration: bool = False
    failed_scenes: list = Field(default_factory=list)
    score: float = 0.0
    is_gate: bool = False
    gate_data: dict = Field(default_factory=dict)
