"""
Phase 9 — CTR Analyzer.
Identifies which titles, thumbnails, and hook styles get highest CTR.
Pulls impressions/clicks from YouTube Analytics API and correlates
with metadata stored in FactoryDB.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from googleapiclient.discovery import Resource

from src.core.database import FactoryDB

logger = logging.getLogger(__name__)

# ═══ Thresholds ═══
MIN_IMPRESSIONS_FOR_ANALYSIS = 100
CTR_BUCKETS = {
    "excellent": 10.0,
    "good": 6.0,
    "average": 3.0,
    "poor": 0.0,
}


@dataclass
class TitlePattern:
    """A discovered pattern in high-CTR titles."""
    pattern_type: str          # "word" | "structure" | "length" | "emotion"
    pattern_value: str
    avg_ctr: float
    sample_size: int
    confidence: float          # 0.0–1.0
    examples: list[str] = field(default_factory=list)


@dataclass
class ThumbnailInsight:
    """Thumbnail style correlated with CTR performance."""
    style: str
    avg_ctr: float
    sample_size: int
    best_performer_job_id: Optional[str] = None
    notes: str = ""


@dataclass
class CTRReport:
    """Full CTR analysis report for a channel."""
    channel_id: str
    analysis_date: datetime = field(default_factory=datetime.now)
    overall_avg_ctr: float = 0.0
    total_videos_analyzed: int = 0
    title_patterns: list[TitlePattern] = field(default_factory=list)
    thumbnail_insights: list[ThumbnailInsight] = field(default_factory=list)
    top_performers: list[dict] = field(default_factory=list)
    bottom_performers: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class CTRAnalyzer:
    """
    Analyzes click-through rate patterns across published videos.
    Correlates title structure, thumbnail style, and hook type with CTR.
    """

    def __init__(self, db: FactoryDB, youtube_analytics: Resource):
        self.db = db
        self.yt_analytics = youtube_analytics

    # ─── Public API ───────────────────────────────────────────

    def analyze_channel(self, channel_id: str, days: int = 90) -> CTRReport:
        """
        Full CTR analysis for a channel over the given period.
        Returns CTRReport with patterns and recommendations.
        """
        report = CTRReport(channel_id=channel_id)

        # Fetch all published videos with analytics
        videos = self._get_published_videos(channel_id)
        if not videos:
            logger.warning(f"No published videos for channel {channel_id}")
            return report

        # Enrich with latest analytics data
        enriched = self._enrich_with_analytics(videos, days)
        valid = [v for v in enriched if v.get("impressions", 0) >= MIN_IMPRESSIONS_FOR_ANALYSIS]

        if not valid:
            logger.warning(f"No videos with enough impressions for channel {channel_id}")
            return report

        report.total_videos_analyzed = len(valid)
        report.overall_avg_ctr = sum(v["ctr"] for v in valid) / len(valid)

        # Analyze patterns
        report.title_patterns = self._analyze_title_patterns(valid)
        report.thumbnail_insights = self._analyze_thumbnail_styles(valid)
        report.top_performers = self._get_top_n(valid, n=5, ascending=False)
        report.bottom_performers = self._get_top_n(valid, n=5, ascending=True)
        report.recommendations = self._generate_recommendations(report)

        # Save discovered rules to DB
        self._save_rules(channel_id, report)

        logger.info(
            f"CTR analysis complete: channel={channel_id} | "
            f"videos={report.total_videos_analyzed} | avg_ctr={report.overall_avg_ctr:.2f}%"
        )
        return report

    def analyze_video(self, job_id: str, period: str = "7d") -> dict:
        """
        Single-video CTR analysis. Called at 24h, 48h, 7d, 30d milestones.
        Returns metrics dict and saves to youtube_analytics table.
        """
        job = self.db.get_job(job_id)
        if not job or not job.get("youtube_video_id"):
            logger.warning(f"Job {job_id} has no YouTube video ID")
            return {}

        video_id = job["youtube_video_id"]
        metrics = self._fetch_video_metrics(video_id, period)

        if metrics:
            self.db.save_analytics(job_id, period, metrics)
            logger.info(
                f"CTR snapshot: job={job_id} | period={period} | "
                f"impressions={metrics.get('impressions', 0)} | ctr={metrics.get('ctr', 0):.2f}%"
            )

        return metrics

    # ─── Data Fetching ────────────────────────────────────────

    def _get_published_videos(self, channel_id: str) -> list[dict]:
        """Get all published jobs for a channel with SEO data."""
        rows = self.db.conn.execute(
            "SELECT j.*, s.selected_title, s.generated_titles, s.primary_keywords "
            "FROM jobs j LEFT JOIN seo_data s ON j.id = s.job_id "
            "WHERE j.channel_id = ? AND j.status = 'published' "
            "AND j.youtube_video_id IS NOT NULL "
            "ORDER BY j.published_at DESC",
            (channel_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _enrich_with_analytics(self, videos: list[dict], days: int) -> list[dict]:
        """Enrich video list with latest analytics snapshot."""
        enriched = []
        for v in videos:
            # Get the most recent analytics snapshot
            row = self.db.conn.execute(
                "SELECT * FROM youtube_analytics WHERE job_id = ? "
                "ORDER BY captured_at DESC LIMIT 1",
                (v["id"],),
            ).fetchone()

            if row:
                analytics = dict(row)
                v["impressions"] = analytics.get("impressions", 0)
                v["ctr"] = analytics.get("ctr", 0.0)
                v["views"] = analytics.get("views", 0)
                v["avg_view_duration_sec"] = analytics.get("avg_view_duration_sec", 0)
                v["avg_view_percentage"] = analytics.get("avg_view_percentage", 0.0)
                enriched.append(v)
            else:
                # Try fetching from YouTube API directly
                metrics = self._fetch_video_metrics(v["youtube_video_id"], f"{days}d")
                if metrics and metrics.get("impressions", 0) > 0:
                    v.update(metrics)
                    self.db.save_analytics(v["id"], f"{days}d", metrics)
                    enriched.append(v)

        return enriched

    def _fetch_video_metrics(self, video_id: str, period: str = "7d") -> dict:
        """
        Fetch CTR metrics from YouTube Analytics API.
        Period format: '24h', '48h', '7d', '30d', '90d'
        """
        days = self._period_to_days(period)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            response = self.yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics=(
                    "views,estimatedMinutesWatched,averageViewDuration,"
                    "averageViewPercentage,likes,comments,shares,"
                    "annotationImpressions,annotationClickThroughRate,"
                    "cardImpressions,cardClickRate"
                ),
                filters=f"video=={video_id}",
                dimensions="video",
            ).execute()

            rows = response.get("rows", [])
            if not rows:
                return {}

            row = rows[0]
            # Column order matches metrics string
            return {
                "video_id": video_id,
                "views": int(row[1]) if len(row) > 1 else 0,
                "watch_hours": round(float(row[2]) / 60, 2) if len(row) > 2 else 0,
                "avg_duration": int(row[3]) if len(row) > 3 else 0,
                "avg_percentage": float(row[4]) if len(row) > 4 else 0,
                "likes": int(row[5]) if len(row) > 5 else 0,
                "comments": int(row[6]) if len(row) > 6 else 0,
                "shares": int(row[7]) if len(row) > 7 else 0,
                "impressions": int(row[8]) if len(row) > 8 else 0,
                "ctr": float(row[9]) if len(row) > 9 else 0,
            }

        except Exception as e:
            logger.error(f"YouTube Analytics API error for {video_id}: {e}")
            return {}

    # ─── Pattern Analysis ─────────────────────────────────────

    def _analyze_title_patterns(self, videos: list[dict]) -> list[TitlePattern]:
        """Find correlations between title structures and CTR."""
        patterns: list[TitlePattern] = []

        # Title length analysis
        length_buckets: dict[str, list[float]] = {
            "short (< 40)": [],
            "medium (40-60)": [],
            "long (> 60)": [],
        }
        for v in videos:
            title = v.get("selected_title") or v.get("topic", "")
            ctr = v.get("ctr", 0)
            tlen = len(title)
            if tlen < 40:
                length_buckets["short (< 40)"].append(ctr)
            elif tlen <= 60:
                length_buckets["medium (40-60)"].append(ctr)
            else:
                length_buckets["long (> 60)"].append(ctr)

        for bucket_name, ctrs in length_buckets.items():
            if len(ctrs) >= 3:
                patterns.append(TitlePattern(
                    pattern_type="length",
                    pattern_value=bucket_name,
                    avg_ctr=round(sum(ctrs) / len(ctrs), 2),
                    sample_size=len(ctrs),
                    confidence=min(1.0, len(ctrs) / 10),
                ))

        # Question mark / number presence
        for marker, label in [("?", "question"), ("!", "exclamation")]:
            with_marker = [v["ctr"] for v in videos
                          if marker in (v.get("selected_title") or "")]
            without_marker = [v["ctr"] for v in videos
                             if marker not in (v.get("selected_title") or "")]
            if len(with_marker) >= 3 and len(without_marker) >= 3:
                patterns.append(TitlePattern(
                    pattern_type="structure",
                    pattern_value=f"contains_{label}",
                    avg_ctr=round(sum(with_marker) / len(with_marker), 2),
                    sample_size=len(with_marker),
                    confidence=min(1.0, len(with_marker) / 10),
                ))

        # Number in title
        import re
        with_number = [v["ctr"] for v in videos
                      if re.search(r'\d+', v.get("selected_title") or "")]
        if len(with_number) >= 3:
            patterns.append(TitlePattern(
                pattern_type="structure",
                pattern_value="contains_number",
                avg_ctr=round(sum(with_number) / len(with_number), 2),
                sample_size=len(with_number),
                confidence=min(1.0, len(with_number) / 10),
            ))

        # Sort by avg_ctr descending
        patterns.sort(key=lambda p: p.avg_ctr, reverse=True)
        return patterns

    def _analyze_thumbnail_styles(self, videos: list[dict]) -> list[ThumbnailInsight]:
        """Correlate thumbnail styles with CTR performance."""
        insights: list[ThumbnailInsight] = []

        # Group by thumbnail style
        style_groups: dict[str, list[dict]] = {}
        for v in videos:
            thumb = self.db.conn.execute(
                "SELECT style FROM thumbnails WHERE job_id = ? AND is_winner = 1 LIMIT 1",
                (v["id"],),
            ).fetchone()
            style = dict(thumb).get("style", "unknown") if thumb else "unknown"
            style_groups.setdefault(style, []).append(v)

        for style, vids in style_groups.items():
            if len(vids) >= 2:
                avg_ctr = sum(v["ctr"] for v in vids) / len(vids)
                best = max(vids, key=lambda x: x.get("ctr", 0))
                insights.append(ThumbnailInsight(
                    style=style,
                    avg_ctr=round(avg_ctr, 2),
                    sample_size=len(vids),
                    best_performer_job_id=best["id"],
                ))

        insights.sort(key=lambda i: i.avg_ctr, reverse=True)
        return insights

    def _get_top_n(self, videos: list[dict], n: int = 5, ascending: bool = False) -> list[dict]:
        """Get top/bottom N videos by CTR."""
        sorted_vids = sorted(videos, key=lambda v: v.get("ctr", 0), reverse=not ascending)
        return [
            {
                "job_id": v["id"],
                "title": v.get("selected_title") or v.get("topic", ""),
                "ctr": v.get("ctr", 0),
                "impressions": v.get("impressions", 0),
                "views": v.get("views", 0),
            }
            for v in sorted_vids[:n]
        ]

    # ─── Recommendations ──────────────────────────────────────

    def _generate_recommendations(self, report: CTRReport) -> list[str]:
        """Generate actionable CTR recommendations."""
        recs: list[str] = []

        # Best title pattern
        if report.title_patterns:
            best = report.title_patterns[0]
            recs.append(
                f"Best title pattern: '{best.pattern_value}' "
                f"(avg CTR {best.avg_ctr}%, n={best.sample_size})"
            )

        # Best thumbnail style
        if report.thumbnail_insights:
            best_thumb = report.thumbnail_insights[0]
            recs.append(
                f"Best thumbnail style: '{best_thumb.style}' "
                f"(avg CTR {best_thumb.avg_ctr}%, n={best_thumb.sample_size})"
            )

        # Overall CTR health
        if report.overall_avg_ctr < 3.0:
            recs.append(
                "⚠️ Overall CTR is below 3% — consider A/B testing titles and thumbnails"
            )
        elif report.overall_avg_ctr > 8.0:
            recs.append(
                "✅ Excellent CTR (>8%) — current title/thumbnail strategy is working well"
            )

        return recs

    # ─── Rules Persistence ────────────────────────────────────

    def _save_rules(self, channel_id: str, report: CTRReport):
        """Save discovered CTR patterns as performance rules."""
        for pattern in report.title_patterns:
            if pattern.confidence >= 0.5 and pattern.sample_size >= 5:
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO performance_rules
                    (rule_name, rule_value, rule_type, confidence, sample_size,
                     reason, applies_to_channel, discovery_date, based_on_metric,
                     metric_improvement_pct, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"ctr_title_{pattern.pattern_type}_{pattern.pattern_value}",
                    json.dumps({"avg_ctr": pattern.avg_ctr, "type": pattern.pattern_type}),
                    "ctr_title",
                    pattern.confidence,
                    pattern.sample_size,
                    f"Title pattern '{pattern.pattern_value}' yields {pattern.avg_ctr}% CTR",
                    channel_id,
                    datetime.now().strftime("%Y-%m-%d"),
                    "ctr",
                    round(pattern.avg_ctr - report.overall_avg_ctr, 2),
                    True,
                ))
        self.db.conn.commit()

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _period_to_days(period: str) -> int:
        """Convert period string to days."""
        mapping = {"24h": 1, "48h": 2, "7d": 7, "30d": 30, "90d": 90}
        return mapping.get(period, 7)
