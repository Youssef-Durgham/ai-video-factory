"""
Phase 8 — Publish: YouTube upload pipeline.

Thumbnail generation + QA, subtitle generation + styling,
SEO assembly, YouTube upload, Shorts extraction, and A/B testing.
"""

from src.phase8_publish.thumbnail_gen import ThumbnailGenerator
from src.phase8_publish.thumbnail_validator import ThumbnailValidator
from src.phase8_publish.thumbnail_qa import ThumbnailQA
from src.phase8_publish.subtitle_gen import SubtitleGenerator
from src.phase8_publish.subtitle_styler import SubtitleStyler
from src.phase8_publish.seo_assembler import SEOAssembler
from src.phase8_publish.uploader import YouTubeUploader
from src.phase8_publish.shorts_gen import ShortsGenerator
from src.phase8_publish.ab_test import ABTestManager

__all__ = [
    "ThumbnailGenerator",
    "ThumbnailValidator",
    "ThumbnailQA",
    "SubtitleGenerator",
    "SubtitleStyler",
    "SEOAssembler",
    "YouTubeUploader",
    "ShortsGenerator",
    "ABTestManager",
]
