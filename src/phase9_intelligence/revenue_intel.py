"""
Phase 9 — Revenue Intelligence.
Analyzes RPM (Revenue Per Mille) patterns across topics, video lengths,
publish times, and audience demographics.
Optimizes future content for maximum revenue.
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
MIN_VIEWS_FOR_RPM = 500
PUBLISH_HOUR_BUCKETS = [
    (6, 12, "morning"),
    (12, 17, "afternoon"),
    (17, 21, "evening"),
    (21, 6, "night"),
]


@dataclass
class RPMByTopic:
    """RPM performance grouped by topic/category."""
    topic_category: str
    avg_rpm: float
    total_revenue: float
    video_count: int
    best_video_rpm: float
    best_video_job_id: str = ""
    confidence: float = 0.0


@dataclass
class RPMByLength:
    """RPM performance grouped by video length."""
    length_range: str
    avg_rpm: float
    total_revenue: float
    video_count: int
    avg_watch_hours: float = 0.0


@dataclass
class RPMByPublishTime:
    """RPM performance grouped by publish day/time."""
    time_slot: str
    avg_rpm: float
    video_count: int
    avg_views: float = 0.0
    best_day: str = ""


@dataclass
class RevenueReport:
    """Full revenue intelligence report."""
    channel_id: str
    analysis_date: datetime = field(default_factory=datetime.now)
    total_revenue: float = 0.0
    total_videos: int = 0
    overall_avg_rpm: float = 0.0
    rpm_by_topic: list[RPMByTopic] = field(default_factory=list)
    rpm_by_length: list[RPMByLength] = field(default_factory=list)
    rpm_by_publish_time: list[RPMByPublishTime] = field(default_factory=list)
    top_earners: list[dict] = field(default_factory=list)
    revenue_trend: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class RevenueIntel:
    """
    Revenue pattern analysis — identifies highest-RPM topics, optimal lengths,
    and best publish times for maximum ad revenue.
    """

    def __init__(self, db: FactoryDB, youtube_analytics: Resource):
        self.db = db
        self.yt_analytics = youtube_analytics

    # ─── Public API ───────────────────────────────────────────

    def analyze_channel(self, channel_id: str, days: int = 90) -> RevenueReport:
        """
        Full revenue analysis for a channel.
        Returns RevenueReport with RPM breakdowns and optimization recs.
        """
        report = RevenueReport(channel_id=channel_id)

        videos = self._get_videos_with_revenue(channel_id)
        valid = [v for v in videos if v.get("views", 0) >= MIN_VIEWS_FOR_RPM]

        if not valid:
            logger.warning(f"No videos with sufficient views for revenue analysis: {channel_id}")
            return report

        report.total_videos = len(valid)
        report.total_revenue = sum(v.get("estimated_revenue", 0) or 0 for v in valid)
        report.overall_avg_rpm = (
            sum(v.get("rpm", 0) or 0 for v in valid) / len(valid)
        )

        report.rpm_by_topic = self._analyze_by_topic(valid)
        report.rpm_by_length = self._analyze_by_length(valid)
        report.rpm_by_publish_time = self._analyze_by_publish_time(valid)
        report.top_earners = self._get_top_earners(valid, n=10)
        report.revenue_trend = self._calculate_trend(valid)
        report.recommendations = self._generate_recommendations(report)

        self._save_rules(channel_id, report)

        logger.info(
            f"Revenue analysis: channel={channel_id} | "
            f"total=${report.total_revenue:.2f} | avg_rpm=${report.overall_avg_rpm:.2f} | "
            f"videos={report.total_videos}"
        )
        return report

    def get_video_revenue(self, job_id: str, period: str = "30d") -> dict:
        """Single-video revenue snapshot at milestone."""
        job = self.db.get_job(job_id)
        if not job or not job.get("youtube_video_id"):
            return {}

        video_id = job["youtube_video_id"]
        return self._fetch_revenue_metrics(video_id, period)

    # ─── Data Fetching ────────────────────────────────────────

    def _get_videos_with_revenue(self, channel_id: str) -> list[dict]:
        """Get published videos with revenue data."""
        rows = self.db.conn.execute("""
            SELECT j.id, j.topic, j.topic_region, j.youtube_video_id,
                   j.target_length_min, j.published_at,
                   a.views, a.watch_time_hours, a.avg_view_duration_sec,
                   a.impressions, a.ctr, a.estimated_revenue, a.rpm
            FROM jobs j
            INNER JOIN youtube_analytics a ON j.id = a.job_id
            WHERE j.channel_id = ? AND j.status = 'published'
            AND a.id = (
                SELECT id FROM youtube_analytics
                WHERE job_id = j.id ORDER BY captured_at DESC LIMIT 1
            )
            ORDER BY a.estimated_revenue DESC
        """, (channel_id,)).fetchall()
        return [dict(r) for r in rows]

    def _fetch_revenue_metrics(self, video_id: str, period: str) -> dict:
        """Fetch revenue metrics from YouTube Analytics API."""
        days = {"24h": 1, "48h": 2, "7d": 7, "30d": 30, "90d": 90}.get(period, 30)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            response = self.yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedRevenue,estimatedAdRevenue,grossRevenue,cpm,playbackBasedCpm",
                filters=f"video=={video_id}",
                dimensions="video",
            ).execute()

            rows = response.get("rows", [])
            if not rows:
                return {}

            row = rows[0]
            views = int(row[1]) if len(row) > 1 else 0
            revenue = float(row[2]) if len(row) > 2 else 0
            return {
                "video_id": video_id,
                "views": views,
                "revenue": round(revenue, 2),
                "ad_revenue": round(float(row[3]), 2) if len(row) > 3 else 0,
                "gross_revenue": round(float(row[4]), 2) if len(row) > 4 else 0,
                "cpm": round(float(row[5]), 2) if len(row) > 5 else 0,
                "rpm": round((revenue / views * 1000), 2) if views > 0 else 0,
            }
        except Exception as e:
            logger.error(f"Revenue API error for {video_id}: {e}")
            return {}

    # ─── Analysis by Dimension ────────────────────────────────

    def _analyze_by_topic(self, videos: list[dict]) -> list[RPMByTopic]:
        """Group RPM analysis by topic category."""
        groups: dict[str, list[dict]] = {}
        for v in videos:
            cat = v.get("topic_region", "global")
            groups.setdefault(cat, []).append(v)

        results: list[RPMByTopic] = []
        for cat, vids in groups.items():
            rpms = [v.get("rpm", 0) or 0 for v in vids]
            revenues = [v.get("estimated_revenue", 0) or 0 for v in vids]
            best = max(vids, key=lambda x: x.get("rpm", 0) or 0)
            results.append(RPMByTopic(
                topic_category=cat,
                avg_rpm=round(sum(rpms) / len(rpms), 2),
                total_revenue=round(sum(revenues), 2),
                video_count=len(vids),
                best_video_rpm=round(best.get("rpm", 0) or 0, 2),
                best_video_job_id=best["id"],
                confidence=min(1.0, len(vids) / 10),
            ))

        results.sort(key=lambda r: r.avg_rpm, reverse=True)
        return results

    def _analyze_by_length(self, videos: list[dict]) -> list[RPMByLength]:
        """Group RPM analysis by video length."""
        from src.phase9_intelligence.watchtime_analyzer import LENGTH_BUCKETS_MIN

        results: list[RPMByLength] = []
        for min_m, max_m, label in LENGTH_BUCKETS_MIN:
            bucket_vids = [
                v for v in videos
                if self._estimate_length_min(v) >= min_m
                and self._estimate_length_min(v) < max_m
            ]
            if not bucket_vids:
                continue

            rpms = [v.get("rpm", 0) or 0 for v in bucket_vids]
            revenues = [v.get("estimated_revenue", 0) or 0 for v in bucket_vids]
            watch_hrs = [v.get("watch_time_hours", 0) or 0 for v in bucket_vids]

            results.append(RPMByLength(
                length_range=label,
                avg_rpm=round(sum(rpms) / len(rpms), 2),
                total_revenue=round(sum(revenues), 2),
                video_count=len(bucket_vids),
                avg_watch_hours=round(sum(watch_hrs) / len(watch_hrs), 1),
            ))

        results.sort(key=lambda r: r.avg_rpm, reverse=True)
        return results

    def _analyze_by_publish_time(self, videos: list[dict]) -> list[RPMByPublishTime]:
        """Group RPM by publish time slot."""
        slots: dict[str, list[dict]] = {}
        day_counts: dict[str, dict[str, int]] = {}

        for v in videos:
            pub = v.get("published_at")
            if not pub:
                continue
            if isinstance(pub, str):
                try:
                    pub = datetime.fromisoformat(pub)
                except ValueError:
                    continue

            hour = pub.hour
            slot_name = "night"
            for start_h, end_h, name in PUBLISH_HOUR_BUCKETS:
                if start_h <= end_h:
                    if start_h <= hour < end_h:
                        slot_name = name
                        break
                else:  # Wraps midnight
                    if hour >= start_h or hour < end_h:
                        slot_name = name
                        break

            slots.setdefault(slot_name, []).append(v)

            day_name = pub.strftime("%A")
            day_counts.setdefault(slot_name, {}).setdefault(day_name, 0)
            day_counts[slot_name][day_name] += 1

        results: list[RPMByPublishTime] = []
        for slot, vids in slots.items():
            rpms = [v.get("rpm", 0) or 0 for v in vids]
            views = [v.get("views", 0) for v in vids]
            best_day = max(
                day_counts.get(slot, {}).items(),
                key=lambda x: x[1],
                default=("N/A", 0),
            )[0]

            results.append(RPMByPublishTime(
                time_slot=slot,
                avg_rpm=round(sum(rpms) / len(rpms), 2),
                video_count=len(vids),
                avg_views=round(sum(views) / len(views), 0),
                best_day=best_day,
            ))

        results.sort(key=lambda r: r.avg_rpm, reverse=True)
        return results

    def _get_top_earners(self, videos: list[dict], n: int = 10) -> list[dict]:
        """Get top N revenue-generating videos."""
        sorted_vids = sorted(
            videos, key=lambda v: v.get("estimated_revenue", 0) or 0, reverse=True
        )
        return [
            {
                "job_id": v["id"],
                "topic": v.get("topic", ""),
                "revenue": round(v.get("estimated_revenue", 0) or 0, 2),
                "rpm": round(v.get("rpm", 0) or 0, 2),
                "views": v.get("views", 0),
            }
            for v in sorted_vids[:n]
        ]

    def _calculate_trend(self, videos: list[dict]) -> list[dict]:
        """Calculate monthly revenue trend."""
        monthly: dict[str, dict] = {}
        for v in videos:
            pub = v.get("published_at")
            if not pub:
                continue
            if isinstance(pub, str):
                try:
                    pub = datetime.fromisoformat(pub)
                except ValueError:
                    continue

            month_key = pub.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = {"revenue": 0.0, "videos": 0, "views": 0}
            monthly[month_key]["revenue"] += v.get("estimated_revenue", 0) or 0
            monthly[month_key]["videos"] += 1
            monthly[month_key]["views"] += v.get("views", 0)

        return [
            {"month": k, **vals}
            for k, vals in sorted(monthly.items())
        ]

    # ─── Recommendations ──────────────────────────────────────

    def _generate_recommendations(self, report: RevenueReport) -> list[str]:
        """Generate revenue optimization recommendations."""
        recs: list[str] = []

        if report.rpm_by_topic:
            best = report.rpm_by_topic[0]
            recs.append(
                f"💰 Highest RPM category: '{best.topic_category}' "
                f"(${best.avg_rpm}/1K views, {best.video_count} videos)"
            )

        if report.rpm_by_length:
            best_len = report.rpm_by_length[0]
            recs.append(
                f"📏 Best RPM by length: '{best_len.length_range}' "
                f"(${best_len.avg_rpm}/1K views)"
            )

        if report.rpm_by_publish_time:
            best_time = report.rpm_by_publish_time[0]
            recs.append(
                f"🕐 Best publish time for RPM: {best_time.time_slot} "
                f"(${best_time.avg_rpm}/1K, best day: {best_time.best_day})"
            )

        if report.revenue_trend and len(report.revenue_trend) >= 2:
            recent = report.revenue_trend[-1]["revenue"]
            prev = report.revenue_trend[-2]["revenue"]
            change = ((recent - prev) / prev * 100) if prev > 0 else 0
            direction = "📈" if change > 0 else "📉"
            recs.append(
                f"{direction} Revenue trend: {change:+.1f}% month-over-month "
                f"(${recent:.2f} vs ${prev:.2f})"
            )

        return recs

    # ─── Rules Persistence ────────────────────────────────────

    def _save_rules(self, channel_id: str, report: RevenueReport):
        """Save revenue insights as performance rules."""
        if report.rpm_by_topic:
            best = report.rpm_by_topic[0]
            if best.confidence >= 0.4:
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO performance_rules
                    (rule_name, rule_value, rule_type, confidence, sample_size,
                     reason, applies_to_channel, discovery_date, based_on_metric, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"best_rpm_topic_{channel_id}",
                    json.dumps({
                        "category": best.topic_category,
                        "avg_rpm": best.avg_rpm,
                    }),
                    "revenue",
                    best.confidence,
                    best.video_count,
                    f"Category '{best.topic_category}' has highest RPM (${best.avg_rpm})",
                    channel_id,
                    datetime.now().strftime("%Y-%m-%d"),
                    "rpm",
                    True,
                ))

        if report.rpm_by_publish_time:
            best_time = report.rpm_by_publish_time[0]
            self.db.conn.execute("""
                INSERT OR REPLACE INTO performance_rules
                (rule_name, rule_value, rule_type, confidence, sample_size,
                 reason, applies_to_channel, discovery_date, based_on_metric, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"best_publish_time_{channel_id}",
                json.dumps({
                    "time_slot": best_time.time_slot,
                    "best_day": best_time.best_day,
                    "avg_rpm": best_time.avg_rpm,
                }),
                "publish_time",
                min(1.0, best_time.video_count / 10),
                best_time.video_count,
                f"Best publish time: {best_time.time_slot} ({best_time.best_day})",
                channel_id,
                datetime.now().strftime("%Y-%m-%d"),
                "rpm",
                True,
            ))

        self.db.conn.commit()

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _estimate_length_min(video: dict) -> float:
        """Estimate video length in minutes."""
        if video.get("target_length_min"):
            return float(video["target_length_min"])
        avg_dur = video.get("avg_view_duration_sec", 0)
        avg_pct = video.get("avg_view_percentage", 50) or 50
        if avg_pct > 0:
            return (avg_dur / (avg_pct / 100)) / 60
        return 10.0
