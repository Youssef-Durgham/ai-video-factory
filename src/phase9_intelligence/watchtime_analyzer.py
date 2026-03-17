"""
Phase 9 — Watchtime Analyzer.
Determines optimal video length per category/topic by analyzing
average view duration, average view percentage, and total watch time.
Feeds recommendations back to Phase 2 (script length) and Phase 7 (assembly).
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from googleapiclient.discovery import Resource

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

# ═══ Config ═══
MIN_VIDEOS_FOR_INSIGHT = 5
LENGTH_BUCKETS_MIN = [
    (0, 5, "short (0-5 min)"),
    (5, 10, "medium (5-10 min)"),
    (10, 15, "long (10-15 min)"),
    (15, 25, "extended (15-25 min)"),
    (25, 60, "deep_dive (25+ min)"),
]


@dataclass
class LengthBucket:
    """Performance metrics for a video length range."""
    label: str
    min_minutes: int
    max_minutes: int
    video_count: int = 0
    avg_view_percentage: float = 0.0
    avg_view_duration_sec: int = 0
    total_watch_hours: float = 0.0
    avg_views: float = 0.0
    avg_rpm: float = 0.0
    score: float = 0.0  # Composite optimization score


@dataclass
class CategoryInsight:
    """Optimal length insight for a topic category."""
    category: str
    optimal_length_min: int
    optimal_range: str
    confidence: float
    sample_size: int
    avg_retention_at_optimal: float
    recommendation: str


@dataclass
class WatchtimeReport:
    """Full watchtime analysis report."""
    channel_id: str
    analysis_date: datetime = field(default_factory=datetime.now)
    total_videos_analyzed: int = 0
    overall_avg_view_pct: float = 0.0
    overall_avg_duration_sec: int = 0
    length_buckets: list[LengthBucket] = field(default_factory=list)
    category_insights: list[CategoryInsight] = field(default_factory=list)
    optimal_length_minutes: int = 10
    recommendations: list[str] = field(default_factory=list)


class WatchtimeAnalyzer:
    """
    Analyzes watch time patterns to determine optimal video length.
    Considers average view percentage, total watch time, and RPM.
    """

    def __init__(self, db: FactoryDB, youtube_analytics: Resource):
        self.db = db
        self.yt_analytics = youtube_analytics

    # ─── Public API ───────────────────────────────────────────

    def analyze_channel(self, channel_id: str, days: int = 90) -> WatchtimeReport:
        """
        Full watchtime analysis for a channel.
        Returns WatchtimeReport with optimal length recommendations.
        """
        report = WatchtimeReport(channel_id=channel_id)

        videos = self._get_videos_with_analytics(channel_id)
        if not videos:
            logger.warning(f"No videos with analytics for channel {channel_id}")
            return report

        report.total_videos_analyzed = len(videos)
        report.overall_avg_view_pct = (
            sum(v["avg_view_percentage"] for v in videos) / len(videos)
        )
        report.overall_avg_duration_sec = int(
            sum(v["avg_view_duration_sec"] for v in videos) / len(videos)
        )

        # Bucket analysis
        report.length_buckets = self._analyze_length_buckets(videos)
        report.category_insights = self._analyze_by_category(videos)
        report.optimal_length_minutes = self._find_optimal_length(report.length_buckets)
        report.recommendations = self._generate_recommendations(report)

        # Save rules
        self._save_rules(channel_id, report)

        logger.info(
            f"Watchtime analysis: channel={channel_id} | "
            f"optimal_length={report.optimal_length_minutes}min | "
            f"avg_retention={report.overall_avg_view_pct:.1f}%"
        )
        return report

    def analyze_video(self, job_id: str, period: str = "7d") -> dict:
        """
        Single-video watchtime analysis at milestone.
        Returns watchtime metrics and comparison to channel average.
        """
        job = self.db.get_job(job_id)
        if not job or not job.get("youtube_video_id"):
            return {}

        video_id = job["youtube_video_id"]
        metrics = self._fetch_watchtime_metrics(video_id, period)

        if not metrics:
            return {}

        # Compare to channel average
        channel_avg = self._get_channel_average(job["channel_id"])
        metrics["vs_channel_avg_pct"] = round(
            metrics.get("avg_percentage", 0) - channel_avg.get("avg_view_percentage", 0), 1
        )
        metrics["vs_channel_avg_duration"] = (
            metrics.get("avg_duration", 0) - channel_avg.get("avg_view_duration_sec", 0)
        )

        return metrics

    # ─── Data Fetching ────────────────────────────────────────

    def _get_videos_with_analytics(self, channel_id: str) -> list[dict]:
        """Get published videos joined with their latest analytics."""
        rows = self.db.conn.execute("""
            SELECT j.id, j.topic, j.topic_region, j.youtube_video_id,
                   j.target_length_min, j.published_at,
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
            ORDER BY j.published_at DESC
        """, (channel_id,)).fetchall()
        return [dict(r) for r in rows]

    def _fetch_watchtime_metrics(self, video_id: str, period: str) -> dict:
        """Fetch watchtime metrics from YouTube Analytics API."""
        days = {"24h": 1, "48h": 2, "7d": 7, "30d": 30, "90d": 90}.get(period, 7)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            response = self.yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
                filters=f"video=={video_id}",
                dimensions="video",
            ).execute()

            rows = response.get("rows", [])
            if not rows:
                return {}

            row = rows[0]
            return {
                "video_id": video_id,
                "views": int(row[1]) if len(row) > 1 else 0,
                "watch_hours": round(float(row[2]) / 60, 2) if len(row) > 2 else 0,
                "avg_duration": int(row[3]) if len(row) > 3 else 0,
                "avg_percentage": float(row[4]) if len(row) > 4 else 0,
            }
        except Exception as e:
            logger.error(f"YouTube Analytics API error for {video_id}: {e}")
            return {}

    def _get_channel_average(self, channel_id: str) -> dict:
        """Get channel-wide average watchtime metrics."""
        row = self.db.conn.execute("""
            SELECT AVG(a.avg_view_duration_sec) as avg_view_duration_sec,
                   AVG(a.avg_view_percentage) as avg_view_percentage,
                   AVG(a.watch_time_hours) as avg_watch_hours
            FROM youtube_analytics a
            INNER JOIN jobs j ON a.job_id = j.id
            WHERE j.channel_id = ? AND j.status = 'published'
        """, (channel_id,)).fetchone()
        return dict(row) if row else {}

    # ─── Bucket Analysis ──────────────────────────────────────

    def _analyze_length_buckets(self, videos: list[dict]) -> list[LengthBucket]:
        """Group videos by length and analyze performance per bucket."""
        buckets: list[LengthBucket] = []

        for min_m, max_m, label in LENGTH_BUCKETS_MIN:
            bucket_vids = [
                v for v in videos
                if self._video_length_minutes(v) >= min_m
                and self._video_length_minutes(v) < max_m
            ]
            if not bucket_vids:
                continue

            bucket = LengthBucket(
                label=label,
                min_minutes=min_m,
                max_minutes=max_m,
                video_count=len(bucket_vids),
                avg_view_percentage=round(
                    sum(v["avg_view_percentage"] for v in bucket_vids) / len(bucket_vids), 1
                ),
                avg_view_duration_sec=int(
                    sum(v["avg_view_duration_sec"] for v in bucket_vids) / len(bucket_vids)
                ),
                total_watch_hours=round(
                    sum(v["watch_time_hours"] for v in bucket_vids), 1
                ),
                avg_views=round(
                    sum(v["views"] for v in bucket_vids) / len(bucket_vids), 0
                ),
                avg_rpm=round(
                    sum(v.get("rpm", 0) or 0 for v in bucket_vids) / len(bucket_vids), 2
                ),
            )

            # Composite score: retention × watch_hours × views (normalized)
            bucket.score = round(
                bucket.avg_view_percentage * bucket.total_watch_hours * bucket.avg_views / 10000,
                2,
            )
            buckets.append(bucket)

        buckets.sort(key=lambda b: b.score, reverse=True)
        return buckets

    def _analyze_by_category(self, videos: list[dict]) -> list[CategoryInsight]:
        """Find optimal video length per topic category."""
        insights: list[CategoryInsight] = []

        # Group by topic_region as proxy for category
        categories: dict[str, list[dict]] = {}
        for v in videos:
            cat = v.get("topic_region", "global")
            categories.setdefault(cat, []).append(v)

        for cat, vids in categories.items():
            if len(vids) < MIN_VIDEOS_FOR_INSIGHT:
                continue

            # Find length with highest retention
            best_vid = max(vids, key=lambda x: x.get("avg_view_percentage", 0))
            avg_len = sum(self._video_length_minutes(v) for v in vids) / len(vids)

            insights.append(CategoryInsight(
                category=cat,
                optimal_length_min=int(self._video_length_minutes(best_vid)),
                optimal_range=f"{int(avg_len - 2)}-{int(avg_len + 2)} min",
                confidence=min(1.0, len(vids) / 15),
                sample_size=len(vids),
                avg_retention_at_optimal=round(best_vid.get("avg_view_percentage", 0), 1),
                recommendation=(
                    f"For '{cat}' topics, aim for ~{int(avg_len)} min "
                    f"(retention: {best_vid.get('avg_view_percentage', 0):.1f}%)"
                ),
            ))

        return insights

    def _find_optimal_length(self, buckets: list[LengthBucket]) -> int:
        """Determine overall optimal video length from bucket analysis."""
        if not buckets:
            return 10  # Default

        # Best bucket by composite score
        best = buckets[0]
        return (best.min_minutes + best.max_minutes) // 2

    # ─── Recommendations ──────────────────────────────────────

    def _generate_recommendations(self, report: WatchtimeReport) -> list[str]:
        """Generate actionable watchtime recommendations."""
        recs: list[str] = []

        if report.length_buckets:
            best = report.length_buckets[0]
            recs.append(
                f"Optimal video length: {best.label} "
                f"(retention {best.avg_view_percentage}%, {best.video_count} videos)"
            )

        if report.overall_avg_view_pct < 40:
            recs.append(
                "⚠️ Average retention below 40% — consider shorter videos "
                "or stronger hooks in first 30 seconds"
            )
        elif report.overall_avg_view_pct > 60:
            recs.append(
                "✅ Strong retention (>60%) — audience is engaged, "
                "consider slightly longer content"
            )

        for insight in report.category_insights:
            recs.append(insight.recommendation)

        return recs

    # ─── Rules Persistence ────────────────────────────────────

    def _save_rules(self, channel_id: str, report: WatchtimeReport):
        """Save optimal length rules to performance_rules table."""
        if report.length_buckets:
            best = report.length_buckets[0]
            self.db.conn.execute("""
                INSERT OR REPLACE INTO performance_rules
                (rule_name, rule_value, rule_type, confidence, sample_size,
                 reason, applies_to_channel, discovery_date, based_on_metric, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"optimal_length_{channel_id}",
                json.dumps({
                    "optimal_minutes": report.optimal_length_minutes,
                    "best_bucket": best.label,
                    "avg_retention": best.avg_view_percentage,
                }),
                "watchtime",
                min(1.0, report.total_videos_analyzed / 20),
                report.total_videos_analyzed,
                f"Optimal length: {report.optimal_length_minutes} min "
                f"(retention {best.avg_view_percentage}%)",
                channel_id,
                datetime.now().strftime("%Y-%m-%d"),
                "avg_view_percentage",
                True,
            ))
            self.db.conn.commit()

        for insight in report.category_insights:
            if insight.confidence >= 0.5:
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO performance_rules
                    (rule_name, rule_value, rule_type, confidence, sample_size,
                     reason, applies_to_channel, discovery_date, based_on_metric, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"optimal_length_{channel_id}_{insight.category}",
                    json.dumps({
                        "category": insight.category,
                        "optimal_minutes": insight.optimal_length_min,
                        "range": insight.optimal_range,
                    }),
                    "watchtime_category",
                    insight.confidence,
                    insight.sample_size,
                    insight.recommendation,
                    channel_id,
                    datetime.now().strftime("%Y-%m-%d"),
                    "avg_view_percentage",
                    True,
                ))
        self.db.conn.commit()

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _video_length_minutes(video: dict) -> float:
        """Estimate video length in minutes from target or actual duration."""
        if video.get("target_length_min"):
            return float(video["target_length_min"])
        # Estimate from avg_view_duration and avg_view_percentage
        avg_dur = video.get("avg_view_duration_sec", 0)
        avg_pct = video.get("avg_view_percentage", 50)
        if avg_pct > 0:
            total_sec = avg_dur / (avg_pct / 100)
            return total_sec / 60
        return 10.0  # Default
