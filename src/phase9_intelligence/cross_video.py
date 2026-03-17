"""
Phase 9 — Cross-Video Pattern Mining.
Analyzes patterns across all published videos to discover what works.
Correlates production choices (visual style, voice, pacing, narrative)
with performance metrics (views, retention, CTR, revenue).
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

# ═══ Config ═══
MIN_SAMPLE_FOR_PATTERN = 5
CORRELATION_THRESHOLD = 0.3     # Minimum correlation to report


@dataclass
class ProductionPattern:
    """A discovered correlation between production choices and performance."""
    pattern_name: str
    dimension: str              # "visual_style" | "voice" | "narrative" | "pacing" | "music"
    value: str
    avg_performance: float      # Normalized 0-100
    metric_used: str            # "views" | "retention" | "ctr" | "rpm"
    sample_size: int
    confidence: float
    vs_baseline: float          # % above/below channel average
    examples: list[str] = field(default_factory=list)


@dataclass
class TopicCluster:
    """A cluster of related topics with performance data."""
    cluster_name: str
    topics: list[str] = field(default_factory=list)
    video_count: int = 0
    avg_views: float = 0.0
    avg_ctr: float = 0.0
    avg_retention: float = 0.0
    avg_rpm: float = 0.0
    trend: str = ""             # "growing" | "stable" | "declining"


@dataclass
class CrossVideoReport:
    """Full cross-video analysis report."""
    channel_id: str
    analysis_date: datetime = field(default_factory=datetime.now)
    total_videos: int = 0
    production_patterns: list[ProductionPattern] = field(default_factory=list)
    topic_clusters: list[TopicCluster] = field(default_factory=list)
    anti_patterns: list[ProductionPattern] = field(default_factory=list)
    style_evolution: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class CrossVideoAnalyzer:
    """
    Mines patterns across all published videos.
    Discovers what production choices correlate with better performance.
    """

    def __init__(self, db: FactoryDB):
        self.db = db

    # ─── Public API ───────────────────────────────────────────

    def analyze_channel(self, channel_id: str) -> CrossVideoReport:
        """
        Full cross-video pattern analysis for a channel.
        Returns patterns, clusters, and recommendations.
        """
        report = CrossVideoReport(channel_id=channel_id)

        videos = self._get_all_video_data(channel_id)
        if len(videos) < MIN_SAMPLE_FOR_PATTERN:
            logger.warning(
                f"Not enough videos for cross-video analysis: "
                f"{len(videos)}/{MIN_SAMPLE_FOR_PATTERN}"
            )
            return report

        report.total_videos = len(videos)

        # Analyze production dimensions
        report.production_patterns = self._analyze_production_patterns(videos)
        report.anti_patterns = [
            p for p in report.production_patterns if p.vs_baseline < -10
        ]
        report.production_patterns = [
            p for p in report.production_patterns if p.vs_baseline >= -10
        ]

        report.topic_clusters = self._analyze_topic_clusters(videos)
        report.style_evolution = self._track_style_evolution(videos)
        report.recommendations = self._generate_recommendations(report)

        # Save high-confidence patterns as rules
        self._save_rules(channel_id, report)

        logger.info(
            f"Cross-video analysis: channel={channel_id} | "
            f"videos={report.total_videos} | "
            f"patterns={len(report.production_patterns)} | "
            f"anti_patterns={len(report.anti_patterns)}"
        )
        return report

    # ─── Data Fetching ────────────────────────────────────────

    def _get_all_video_data(self, channel_id: str) -> list[dict]:
        """Get all published videos with scenes, analytics, and SEO data."""
        rows = self.db.conn.execute("""
            SELECT j.id, j.topic, j.topic_region, j.narrative_style,
                   j.selected_voice_id, j.published_at, j.target_length_min,
                   a.views, a.watch_time_hours, a.avg_view_duration_sec,
                   a.avg_view_percentage, a.impressions, a.ctr,
                   a.estimated_revenue, a.rpm
            FROM jobs j
            INNER JOIN youtube_analytics a ON j.id = a.job_id
            WHERE j.channel_id = ? AND j.status = 'published'
            AND a.id = (
                SELECT id FROM youtube_analytics
                WHERE job_id = j.id ORDER BY captured_at DESC LIMIT 1
            )
            ORDER BY j.published_at
        """, (channel_id,)).fetchall()

        videos = []
        for r in rows:
            v = dict(r)
            # Enrich with scene-level data
            scenes = self.db.get_scenes(v["id"])
            if scenes:
                v["visual_styles"] = list({s.get("visual_style", "") for s in scenes if s.get("visual_style")})
                v["music_moods"] = list({s.get("music_mood", "") for s in scenes if s.get("music_mood")})
                v["transitions"] = list({s.get("transition_type", "") for s in scenes if s.get("transition_type")})
                v["avg_scene_duration"] = sum(s.get("duration_sec", 10) for s in scenes) / len(scenes)
                v["scene_count"] = len(scenes)
            else:
                v["visual_styles"] = []
                v["music_moods"] = []
                v["transitions"] = []
                v["avg_scene_duration"] = 10
                v["scene_count"] = 0
            videos.append(v)

        return videos

    # ─── Pattern Analysis ─────────────────────────────────────

    def _analyze_production_patterns(self, videos: list[dict]) -> list[ProductionPattern]:
        """Analyze correlations between production choices and performance."""
        patterns: list[ProductionPattern] = []

        # Calculate baselines
        baselines = {
            "views": sum(v.get("views", 0) for v in videos) / len(videos),
            "ctr": sum(v.get("ctr", 0) for v in videos) / len(videos),
            "retention": sum(v.get("avg_view_percentage", 0) for v in videos) / len(videos),
            "rpm": sum(v.get("rpm", 0) or 0 for v in videos) / len(videos),
        }

        # Visual style patterns
        patterns.extend(self._analyze_dimension(
            videos, "visual_styles", "visual_style", baselines
        ))

        # Narrative style patterns
        patterns.extend(self._analyze_dimension_single(
            videos, "narrative_style", "narrative", baselines
        ))

        # Voice patterns
        patterns.extend(self._analyze_dimension_single(
            videos, "selected_voice_id", "voice", baselines
        ))

        # Music mood patterns
        patterns.extend(self._analyze_dimension(
            videos, "music_moods", "music", baselines
        ))

        # Pacing patterns (scene duration)
        patterns.extend(self._analyze_pacing(videos, baselines))

        # Sort by performance impact
        patterns.sort(key=lambda p: p.vs_baseline, reverse=True)
        return patterns

    def _analyze_dimension(
        self,
        videos: list[dict],
        list_key: str,
        dimension: str,
        baselines: dict,
    ) -> list[ProductionPattern]:
        """Analyze a multi-value dimension (e.g., visual_styles is a list)."""
        patterns: list[ProductionPattern] = []
        value_videos: dict[str, list[dict]] = {}

        for v in videos:
            for val in v.get(list_key, []):
                if val:
                    value_videos.setdefault(val, []).append(v)

        for val, vids in value_videos.items():
            if len(vids) < MIN_SAMPLE_FOR_PATTERN:
                continue

            for metric in ("views", "ctr", "retention", "rpm"):
                metric_key = {
                    "views": "views",
                    "ctr": "ctr",
                    "retention": "avg_view_percentage",
                    "rpm": "rpm",
                }[metric]

                avg_perf = sum(v.get(metric_key, 0) or 0 for v in vids) / len(vids)
                baseline = baselines[metric]
                if baseline == 0:
                    continue

                vs_baseline = ((avg_perf - baseline) / baseline) * 100

                if abs(vs_baseline) >= 10:  # Only report meaningful differences
                    patterns.append(ProductionPattern(
                        pattern_name=f"{dimension}_{val}_{metric}",
                        dimension=dimension,
                        value=val,
                        avg_performance=round(avg_perf, 2),
                        metric_used=metric,
                        sample_size=len(vids),
                        confidence=min(1.0, len(vids) / 15),
                        vs_baseline=round(vs_baseline, 1),
                        examples=[v["id"] for v in vids[:3]],
                    ))

        return patterns

    def _analyze_dimension_single(
        self,
        videos: list[dict],
        key: str,
        dimension: str,
        baselines: dict,
    ) -> list[ProductionPattern]:
        """Analyze a single-value dimension (e.g., narrative_style)."""
        patterns: list[ProductionPattern] = []
        groups: dict[str, list[dict]] = {}

        for v in videos:
            val = v.get(key)
            if val:
                groups.setdefault(val, []).append(v)

        for val, vids in groups.items():
            if len(vids) < MIN_SAMPLE_FOR_PATTERN:
                continue

            for metric in ("views", "ctr", "retention"):
                metric_key = {
                    "views": "views",
                    "ctr": "ctr",
                    "retention": "avg_view_percentage",
                }[metric]

                avg_perf = sum(v.get(metric_key, 0) or 0 for v in vids) / len(vids)
                baseline = baselines[metric]
                if baseline == 0:
                    continue

                vs_baseline = ((avg_perf - baseline) / baseline) * 100

                if abs(vs_baseline) >= 10:
                    patterns.append(ProductionPattern(
                        pattern_name=f"{dimension}_{val}_{metric}",
                        dimension=dimension,
                        value=val,
                        avg_performance=round(avg_perf, 2),
                        metric_used=metric,
                        sample_size=len(vids),
                        confidence=min(1.0, len(vids) / 15),
                        vs_baseline=round(vs_baseline, 1),
                        examples=[v["id"] for v in vids[:3]],
                    ))

        return patterns

    def _analyze_pacing(
        self, videos: list[dict], baselines: dict
    ) -> list[ProductionPattern]:
        """Analyze scene pacing (avg scene duration) correlation with performance."""
        patterns: list[ProductionPattern] = []

        # Bucket by pacing
        fast = [v for v in videos if v.get("avg_scene_duration", 10) < 8]
        medium = [v for v in videos if 8 <= v.get("avg_scene_duration", 10) <= 12]
        slow = [v for v in videos if v.get("avg_scene_duration", 10) > 12]

        for label, group in [("fast_pacing", fast), ("medium_pacing", medium), ("slow_pacing", slow)]:
            if len(group) < MIN_SAMPLE_FOR_PATTERN:
                continue

            avg_retention = (
                sum(v.get("avg_view_percentage", 0) for v in group) / len(group)
            )
            baseline = baselines["retention"]
            if baseline == 0:
                continue

            vs_baseline = ((avg_retention - baseline) / baseline) * 100
            if abs(vs_baseline) >= 5:
                patterns.append(ProductionPattern(
                    pattern_name=f"pacing_{label}_retention",
                    dimension="pacing",
                    value=label,
                    avg_performance=round(avg_retention, 1),
                    metric_used="retention",
                    sample_size=len(group),
                    confidence=min(1.0, len(group) / 10),
                    vs_baseline=round(vs_baseline, 1),
                ))

        return patterns

    # ─── Topic Clustering ─────────────────────────────────────

    def _analyze_topic_clusters(self, videos: list[dict]) -> list[TopicCluster]:
        """Group videos by topic region/category and analyze cluster performance."""
        clusters_map: dict[str, list[dict]] = {}

        for v in videos:
            cat = v.get("topic_region", "global")
            clusters_map.setdefault(cat, []).append(v)

        clusters: list[TopicCluster] = []
        for cat, vids in clusters_map.items():
            if len(vids) < 2:
                continue

            # Determine trend from chronological view counts
            sorted_vids = sorted(vids, key=lambda x: x.get("published_at") or "")
            if len(sorted_vids) >= 4:
                first_half = sorted_vids[:len(sorted_vids) // 2]
                second_half = sorted_vids[len(sorted_vids) // 2:]
                avg_first = sum(v.get("views", 0) for v in first_half) / len(first_half)
                avg_second = sum(v.get("views", 0) for v in second_half) / len(second_half)
                if avg_second > avg_first * 1.15:
                    trend = "growing"
                elif avg_second < avg_first * 0.85:
                    trend = "declining"
                else:
                    trend = "stable"
            else:
                trend = "insufficient_data"

            clusters.append(TopicCluster(
                cluster_name=cat,
                topics=[v.get("topic", "") for v in vids],
                video_count=len(vids),
                avg_views=round(sum(v.get("views", 0) for v in vids) / len(vids), 0),
                avg_ctr=round(sum(v.get("ctr", 0) for v in vids) / len(vids), 2),
                avg_retention=round(
                    sum(v.get("avg_view_percentage", 0) for v in vids) / len(vids), 1
                ),
                avg_rpm=round(sum(v.get("rpm", 0) or 0 for v in vids) / len(vids), 2),
                trend=trend,
            ))

        clusters.sort(key=lambda c: c.avg_views, reverse=True)
        return clusters

    # ─── Style Evolution ──────────────────────────────────────

    def _track_style_evolution(self, videos: list[dict]) -> list[dict]:
        """Track how production style has evolved over time."""
        if len(videos) < 6:
            return []

        # Split into thirds chronologically
        third = len(videos) // 3
        periods = [
            ("early", videos[:third]),
            ("middle", videos[third:2 * third]),
            ("recent", videos[2 * third:]),
        ]

        evolution = []
        for period_name, vids in periods:
            all_styles = []
            all_moods = []
            for v in vids:
                all_styles.extend(v.get("visual_styles", []))
                all_moods.extend(v.get("music_moods", []))

            evolution.append({
                "period": period_name,
                "video_count": len(vids),
                "top_visual_styles": [s for s, _ in Counter(all_styles).most_common(3)],
                "top_music_moods": [m for m, _ in Counter(all_moods).most_common(3)],
                "avg_scene_duration": round(
                    sum(v.get("avg_scene_duration", 10) for v in vids) / len(vids), 1
                ),
                "avg_views": round(sum(v.get("views", 0) for v in vids) / len(vids), 0),
                "avg_retention": round(
                    sum(v.get("avg_view_percentage", 0) for v in vids) / len(vids), 1
                ),
            })

        return evolution

    # ─── Recommendations ──────────────────────────────────────

    def _generate_recommendations(self, report: CrossVideoReport) -> list[str]:
        """Generate cross-video recommendations."""
        recs: list[str] = []

        # Top production patterns
        for p in report.production_patterns[:3]:
            emoji = "✅" if p.vs_baseline > 0 else "⚠️"
            recs.append(
                f"{emoji} {p.dimension}: '{p.value}' → "
                f"{p.vs_baseline:+.1f}% vs baseline {p.metric_used} "
                f"(n={p.sample_size})"
            )

        # Anti-patterns
        for p in report.anti_patterns[:2]:
            recs.append(
                f"🚫 Avoid {p.dimension}='{p.value}': "
                f"{p.vs_baseline:.1f}% below baseline {p.metric_used}"
            )

        # Growing topic clusters
        growing = [c for c in report.topic_clusters if c.trend == "growing"]
        if growing:
            recs.append(
                f"📈 Growing category: '{growing[0].cluster_name}' — "
                f"consider more content here"
            )

        declining = [c for c in report.topic_clusters if c.trend == "declining"]
        if declining:
            recs.append(
                f"📉 Declining category: '{declining[0].cluster_name}' — "
                f"consider pivoting or refreshing approach"
            )

        return recs

    # ─── Rules Persistence ────────────────────────────────────

    def _save_rules(self, channel_id: str, report: CrossVideoReport):
        """Save high-confidence patterns as performance rules."""
        for p in report.production_patterns:
            if p.confidence >= 0.5 and p.vs_baseline > 15:
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO performance_rules
                    (rule_name, rule_value, rule_type, confidence, sample_size,
                     reason, applies_to_channel, discovery_date, based_on_metric,
                     metric_improvement_pct, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"pattern_{p.pattern_name}",
                    json.dumps({
                        "dimension": p.dimension,
                        "value": p.value,
                        "avg_performance": p.avg_performance,
                    }),
                    "cross_video",
                    p.confidence,
                    p.sample_size,
                    f"{p.dimension}='{p.value}' yields {p.vs_baseline:+.1f}% {p.metric_used}",
                    channel_id,
                    datetime.now().strftime("%Y-%m-%d"),
                    p.metric_used,
                    p.vs_baseline,
                    True,
                ))
        self.db.conn.commit()
