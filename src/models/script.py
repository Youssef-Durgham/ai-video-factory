"""
Script data model — versioned script with review history.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ScriptSection(BaseModel):
    title: str
    text: str
    duration_sec: float


class EmotionalArcPoint(BaseModel):
    section: str
    emotion: str
    intensity: float = Field(ge=1, le=10)


class Script(BaseModel):
    id: Optional[int] = None
    job_id: str
    version: int = 1
    status: str = "draft"
    full_text: str
    word_count: int = 0
    estimated_duration_sec: int = 0
    hook_text: Optional[str] = None
    sections: list[ScriptSection] = Field(default_factory=list)
    conclusion_text: Optional[str] = None
    keywords_included: list[str] = Field(default_factory=list)
    keyword_density: float = 0.0
    emotional_arc: list[EmotionalArcPoint] = Field(default_factory=list)
    reviewer_notes: Optional[str] = None
    factual_accuracy_score: Optional[float] = None
    engagement_score: Optional[float] = None
    arabic_quality_score: Optional[float] = None
    sources: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
