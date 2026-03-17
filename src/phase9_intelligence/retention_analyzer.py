"""
Phase 9 — Retention Analyzer.
Analyzes audience retention curves to find drop-off points,
correlates them with scene-level data (hook, transitions, pacing),
and produces scene-level insights for future script/edit optimization.
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
SIGNIFICANT_DROP_PCT = 5.0      # Drop > 5% between data points = significant
HOOK_WINDOW_SEC = 30            # First 30 seconds = hook zone
MIN_RETENTION_DATA_POINTS = 10


@dataclass
class DropOffPoint:
    """A significant audience drop-off in the retention curve."""
    timestamp_sec: int
    retention_before: float
    retention_after: float
    drop_magnitude: float       # Percentage points lost
    scene_index: Optional[int] = None
    scene_narration: str = ""
    probable_cause: str = ""    # "slow_pacing" | "topic_shift" | "weak_transition" etc.


@dataclass
class HookAnalysis:
    """Analysis of first 30 seconds retention."""
    hook_retention_pct: float   # Retention at 30s mark
    avg_channel_hook: float     # Channel average for comparison
    hook_quality: str           # "strong" | "average" | "weak"
    drop_in_first_10s: float
    recommendation: str = ""


@dataclass
class SceneRetention:
    """Retention performance mapped to a specific scene."""
    scene_index: int
    start_sec: float
    end_sec: float
    retention_start: float
    retention_end: float
    retention_delta: float      # Positive = gaining, negative = losing
    narration_preview: str = ""
    performance: str = ""       # "engaging" | "neutral" | "losing_audience"


@dataclass
class RetentionReport:
    """Full retention analysis for a video."""
    job_id: str
    youtube_video_id: str
    analysis_date: datetime = field(default_factory=datetime.now)
    retention_curve: list[dict] = field(default_factory=list)
    avg_retention: float = 0.0
    hook_analysis: Optional[HookAnalysis] = None
    drop_off_points: list[DropOffPoint] = field(default_factory=list)
    scene_retention: list[SceneRetention] = field(default_factory=list)
    best_scene_index: Optional[int] = None
    worst_scene_index: Optional[int] = None
    recommendations: list[str] = field(default_factory=list)


class RetentionAnalyzer:
    """
    Analyzes YouTube retention curves at scene-level granularity.
    Maps drop-off points to specific scenes and identifies patterns.
    """

    def __init__(self, db: FactoryDB, youtube_analytics: Resource):
        self.db = db
        self.yt_analytics = youtube_analytics

    # ─── Public API ───────────────────────────────────────────

    def analyze_video(self, job_id: str, period: str = "7d") -> RetentionReport:
        """
        Full retention analysis for a single video.
        Maps retention curve to scene structure.
        """
        job = self.db.get_job(job_id)
        if not job or not job.get("youtube_video_id"):
            logger.warning(f"Job {job_id} has no YouTube video ID")
            return RetentionReport(job_id=job_id, youtube_video_id="")

        video_id = job["youtube_video_id"]
        report = RetentionReport(job_id=job_id, youtube_video_id=video_id)

        # Fetch retention curve
        curve = self._fetch_retention_curve(video_id, period)
        if not curve or len(curve) < MIN_RETENTION_DATA_POINTS:
            logger.warning(f"Insufficient retention data for {video_id}")
            return report

        report.retention_curve = curve
        report.avg_retention = sum(p["retention"] for p in curve) / len(curve)

        # Hook analysis
        report.hook_analysis = self._analyze_hook(curve, job["channel_id"])

        # Find drop-off points
        scenes = self.db.get_scenes(job_id)
        report.drop_off_points = self._find_drop_offs(curve, scenes)

        # Map retention to scenes
        if scenes:
            report.scene_retention = self._map_to_scenes(curve, scenes)
            if report.scene_retention:
                best = max(report.scene_retention, key=lambda s: s.retention_delta)
                worst = min(report.scene_retention, key=lambda s: s.retention_delta)
                report.best_scene_index = best.scene_index
                report.worst_scene_index = worst.scene_index

        report.recommendations = self._generate_recommendations(report)

        # Save retention curve to analytics
        self._save_retention_data(job_id, period, report)

        logger.info(
            f"Retention analysis: job={job_id} | avg={report.avg_retention:.1f}% | "
            f"drops={len(report.drop_off_points)} | "
            f"best_scene={report.best_scene_index} | worst_scene={report.worst_scene_index}"
        )
        return report

    def analyze_channel_retention_patterns(self, channel_id: str) -> dict:
        """
        Cross-video retention pattern analysis.
        Finds common drop-off patterns across all channel videos.
        """
        videos = self.db.conn.execute(
            "SELECT job_id, retention_curve FROM youtube_analytics "
            "WHERE job_id IN (SELECT id FROM jobs WHERE channel_id = ? AND status = 'published') "
            "AND retention_curve IS NOT NULL "
            "ORDER BY captured_at DESC",
            (channel_id,),
        ).fetchall()

        if not videos:
            return {"patterns": [], "recommendations": []}

        # Aggregate drop-off analysis
        all_relative_drops: dict[str, list[float]] = {
            "0-10%": [], "10-25%": [], "25-50%": [], "50-75%": [], "75-100%": [],
        }

        for v in videos:
            curve = json.loads(v["retention_curve"]) if v["retention_curve"] else []
            if len(curve) < MIN_RETENTION_DATA_POINTS:
                continue

            for point in curve:
                pct = point.get("elapsed_pct", 0)
                ret = point.get("retention", 0)
                if pct <= 10:
                    all_relative_drops["0-10%"].append(ret)
                elif pct <= 25:
                    all_relative_drops["10-25%"].append(ret)
                elif pct <= 50:
                    all_relative_drops["25-50%"].append(ret)
                elif pct <= 75:
                    all_relative_drops["50-75%"].append(ret)
                else:
                    all_relative_drops["75-100%"].append(ret)

        patterns = {}
        for segment, retentions in all_relative_drops.items():
            if retentions:
                patterns[segment] = round(sum(retentions) / len(retentions), 1)

        recommendations = []
        if patterns.get("0-10%", 100) < 70:
            recommendations.append("Hooks are losing >30% in first 10% of video — strengthen openings")
        if patterns.get("50-75%", 100) < 30:
            recommendations.append("Heavy mid-video drop — consider stronger mid-roll hooks or pacing changes")

        return {"patterns": patterns, "recommendations": recommendations}

    # ─── Data Fetching ────────────────────────────────────────

    def _fetch_retention_curve(self, video_id: str, period: str) -> list[dict]:
        """
        Fetch audience retention curve from YouTube Analytics API.
        Returns list of {elapsed_pct, retention} data points.
        """
        days = {"24h": 1, "48h": 2, "7d": 7, "30d": 30, "90d": 90}.get(period, 7)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            response = self.yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="audienceWatchRatio",
                filters=f"video=={video_id}",
                dimensions="elapsedVideoTimeRatio",
            ).execute()

            rows = response.get("rows", [])
            return [
                {
                    "elapsed_pct": round(float(row[0]) * 100, 1),
                    "retention": round(float(row[1]) * 100, 1),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Retention curve fetch failed for {video_id}: {e}")
            return []

    # ─── Analysis ─────────────────────────────────────────────

    def _analyze_hook(self, curve: list[dict], channel_id: str) -> HookAnalysis:
        """Analyze first 30 seconds (hook zone) retention."""
        # Find retention at ~30s mark (varies by video length)
        # Approximate: first 5-10% of video
        hook_points = [p for p in curve if p["elapsed_pct"] <= 10]
        if not hook_points:
            hook_points = curve[:3]

        hook_retention = hook_points[-1]["retention"] if hook_points else 100.0
        first_drop = 100.0 - (hook_points[0]["retention"] if hook_points else 100.0)

        # Channel average hook
        avg_row = self.db.conn.execute("""
            SELECT AVG(CAST(
                json_extract(retention_curve, '$[2].retention') AS REAL
            )) as avg_hook
            FROM youtube_analytics
            WHERE job_id IN (
                SELECT id FROM jobs WHERE channel_id = ? AND status = 'published'
            ) AND retention_curve IS NOT NULL
        """, (channel_id,)).fetchone()
        channel_avg = float(avg_row["avg_hook"]) if avg_row and avg_row["avg_hook"] else 75.0

        quality = "strong" if hook_retention > 80 else "average" if hook_retention > 60 else "weak"

        return HookAnalysis(
            hook_retention_pct=round(hook_retention, 1),
            avg_channel_hook=round(channel_avg, 1),
            hook_quality=quality,
            drop_in_first_10s=round(first_drop, 1),
            recommendation=self._hook_recommendation(quality, hook_retention, channel_avg),
        )

    def _find_drop_offs(
        self, curve: list[dict], scenes: list[dict]
    ) -> list[DropOffPoint]:
        """Find significant drop-off points in retention curve."""
        drops: list[DropOffPoint] = []

        for i in range(1, len(curve)):
            prev = curve[i - 1]
            curr = curve[i]
            drop = prev["retention"] - curr["retention"]

            if drop >= SIGNIFICANT_DROP_PCT:
                # Map to scene
                scene_idx = None
                narration = ""
                cause = "unknown"

                if scenes:
                    # Estimate timestamp from percentage
                    total_dur = sum(s.get("duration_sec", 10) for s in scenes)
                    timestamp = (curr["elapsed_pct"] / 100) * total_dur
                    scene_idx, narration, cause = self._identify_scene_at_time(
                        scenes, timestamp
                    )

                drops.append(DropOffPoint(
                    timestamp_sec=int((curr["elapsed_pct"] / 100) * 600),  # Estimate
                    retention_before=prev["retention"],
                    retention_after=curr["retention"],
                    drop_magnitude=round(drop, 1),
                    scene_index=scene_idx,
                    scene_narration=narration[:100],
                    probable_cause=cause,
                ))

        drops.sort(key=lambda d: d.drop_magnitude, reverse=True)
        return drops

    def _map_to_scenes(
        self, curve: list[dict], scenes: list[dict]
    ) -> list[SceneRetention]:
        """Map retention curve data points to individual scenes."""
        if not scenes:
            return []

        total_duration = sum(s.get("duration_sec", 10) for s in scenes)
        scene_retentions: list[SceneRetention] = []
        cumulative_time = 0.0

        for scene in scenes:
            duration = scene.get("duration_sec", 10)
            start_pct = (cumulative_time / total_duration) * 100
            end_pct = ((cumulative_time + duration) / total_duration) * 100

            # Find retention at start and end of this scene
            ret_start = self._interpolate_retention(curve, start_pct)
            ret_end = self._interpolate_retention(curve, end_pct)

            delta = ret_end - ret_start
            performance = (
                "engaging" if delta > 1 else
                "neutral" if delta > -2 else
                "losing_audience"
            )

            scene_retentions.append(SceneRetention(
                scene_index=scene["scene_index"],
                start_sec=cumulative_time,
                end_sec=cumulative_time + duration,
                retention_start=round(ret_start, 1),
                retention_end=round(ret_end, 1),
                retention_delta=round(delta, 1),
                narration_preview=scene.get("narration_text", "")[:80],
                performance=performance,
            ))
            cumulative_time += duration

        return scene_retentions

    def _identify_scene_at_time(
        self, scenes: list[dict], timestamp: float
    ) -> tuple[Optional[int], str, str]:
        """Find which scene is playing at a given timestamp."""
        cumulative = 0.0
        for scene in scenes:
            duration = scene.get("duration_sec", 10)
            if cumulative <= timestamp < cumulative + duration:
                # Determine probable cause of drop
                cause = "content_shift"
                if scene.get("transition_type") in ("cut", "none"):
                    cause = "abrupt_transition"
                if scene.get("voice_emotion") != scenes[max(0, scene["scene_index"] - 1)].get("voice_emotion"):
                    cause = "tone_change"
                return (
                    scene["scene_index"],
                    scene.get("narration_text", ""),
                    cause,
                )
            cumulative += duration
        return None, "", "end_of_video"

    @staticmethod
    def _interpolate_retention(curve: list[dict], target_pct: float) -> float:
        """Linear interpolation of retention at a specific percentage."""
        if not curve:
            return 50.0

        for i in range(len(curve) - 1):
            if curve[i]["elapsed_pct"] <= target_pct <= curve[i + 1]["elapsed_pct"]:
                span = curve[i + 1]["elapsed_pct"] - curve[i]["elapsed_pct"]
                if span == 0:
                    return curve[i]["retention"]
                ratio = (target_pct - curve[i]["elapsed_pct"]) / span
                return curve[i]["retention"] + ratio * (
                    curve[i + 1]["retention"] - curve[i]["retention"]
                )

        # Outside range — return nearest
        if target_pct <= curve[0]["elapsed_pct"]:
            return curve[0]["retention"]
        return curve[-1]["retention"]

    # ─── Recommendations ──────────────────────────────────────

    @staticmethod
    def _hook_recommendation(quality: str, retention: float, channel_avg: float) -> str:
        if quality == "weak":
            return (
                f"Hook retention ({retention:.0f}%) is below channel average ({channel_avg:.0f}%). "
                "Consider starting with a stronger question, stat, or visual hook."
            )
        elif quality == "strong":
            return f"Strong hook ({retention:.0f}%) — above channel average ({channel_avg:.0f}%)."
        return f"Hook retention ({retention:.0f}%) is near channel average ({channel_avg:.0f}%)."

    def _generate_recommendations(self, report: RetentionReport) -> list[str]:
        """Generate actionable retention recommendations."""
        recs: list[str] = []

        if report.hook_analysis:
            recs.append(report.hook_analysis.recommendation)

        if report.drop_off_points:
            worst = report.drop_off_points[0]
            recs.append(
                f"Biggest drop: {worst.drop_magnitude:.1f}% at scene {worst.scene_index} "
                f"— cause: {worst.probable_cause}"
            )

        if report.worst_scene_index is not None:
            worst_scene = next(
                (s for s in report.scene_retention
                 if s.scene_index == report.worst_scene_index), None
            )
            if worst_scene:
                recs.append(
                    f"Weakest scene #{worst_scene.scene_index}: "
                    f"lost {abs(worst_scene.retention_delta):.1f}% retention "
                    f"({worst_scene.performance})"
                )

        if report.best_scene_index is not None:
            best_scene = next(
                (s for s in report.scene_retention
                 if s.scene_index == report.best_scene_index), None
            )
            if best_scene:
                recs.append(
                    f"Strongest scene #{best_scene.scene_index}: "
                    f"+{best_scene.retention_delta:.1f}% retention — "
                    f"study this scene's style"
                )

        return recs

    # ─── Persistence ──────────────────────────────────────────

    def _save_retention_data(self, job_id: str, period: str, report: RetentionReport):
        """Save retention curve data to analytics table."""
        self.db.conn.execute("""
            UPDATE youtube_analytics
            SET retention_curve = ?
            WHERE job_id = ? AND snapshot_period = ?
            AND id = (
                SELECT id FROM youtube_analytics
                WHERE job_id = ? AND snapshot_period = ?
                ORDER BY captured_at DESC LIMIT 1
            )
        """, (
            json.dumps(report.retention_curve),
            job_id, period, job_id, period,
        ))
        self.db.conn.commit()
