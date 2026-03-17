"""
Phase 9 — Intelligence Reporter.
Generates weekly and monthly Telegram reports with charts.
Aggregates insights from all analyzers into actionable summaries.
"""

import io
import json
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from googleapiclient.discovery import Resource

from src.core.database import FactoryDB
from src.core.telegram_bot import TelegramBot
from src.phase9_intelligence.ctr_analyzer import CTRAnalyzer, CTRReport
from src.phase9_intelligence.watchtime_analyzer import WatchtimeAnalyzer, WatchtimeReport
from src.phase9_intelligence.retention_analyzer import RetentionAnalyzer
from src.phase9_intelligence.revenue_intel import RevenueIntel, RevenueReport
from src.phase9_intelligence.cross_video import CrossVideoAnalyzer, CrossVideoReport

logger = logging.getLogger(__name__)

# ═══ Chart Config ═══
CHART_STYLE = "seaborn-v0_8-darkgrid"
CHART_DPI = 150
CHART_FIGSIZE = (10, 6)
CHART_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9C27B0"]


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    channel_id: str
    report_type: str = "weekly"     # "weekly" | "monthly" | "milestone"
    days: int = 7
    include_charts: bool = True
    include_recommendations: bool = True


@dataclass
class GeneratedChart:
    """A chart image ready for Telegram."""
    title: str
    file_path: str
    caption: str


class IntelligenceReporter:
    """
    Generates comprehensive Telegram reports with charts.
    Aggregates all Phase 9 analyzer outputs into digestible summaries.
    """

    def __init__(
        self,
        db: FactoryDB,
        telegram: TelegramBot,
        youtube_analytics: Resource,
    ):
        self.db = db
        self.telegram = telegram
        self.yt_analytics = youtube_analytics

        # Initialize sub-analyzers
        self.ctr = CTRAnalyzer(db, youtube_analytics)
        self.watchtime = WatchtimeAnalyzer(db, youtube_analytics)
        self.retention = RetentionAnalyzer(db, youtube_analytics)
        self.revenue = RevenueIntel(db, youtube_analytics)
        self.cross_video = CrossVideoAnalyzer(db)

    # ─── Public API ───────────────────────────────────────────

    async def send_weekly_report(self, channel_id: str) -> None:
        """Generate and send weekly intelligence report via Telegram."""
        config = ReportConfig(channel_id=channel_id, report_type="weekly", days=7)
        await self._generate_and_send(config)

    async def send_monthly_report(self, channel_id: str) -> None:
        """Generate and send monthly intelligence report via Telegram."""
        config = ReportConfig(channel_id=channel_id, report_type="monthly", days=30)
        await self._generate_and_send(config)

    async def send_milestone_report(self, job_id: str, period: str) -> None:
        """
        Send a single-video milestone report (24h, 48h, 7d, 30d after publish).
        """
        job = self.db.get_job(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return

        # Collect milestone metrics
        ctr_metrics = self.ctr.analyze_video(job_id, period)
        watchtime_metrics = self.watchtime.analyze_video(job_id, period)
        retention_report = self.retention.analyze_video(job_id, period)
        revenue_metrics = self.revenue.get_video_revenue(job_id, period)

        # Format message
        title = job.get("topic", "Unknown")
        text = self._format_milestone_message(
            job_id, title, period,
            ctr_metrics, watchtime_metrics,
            retention_report, revenue_metrics,
        )

        await self.telegram.send(text)
        logger.info(f"Milestone report sent: job={job_id} period={period}")

    async def run_scheduled_analysis(self, channel_id: str) -> None:
        """
        Run all scheduled analyses — called by CRON.
        Checks which videos need milestone reports and sends them.
        """
        now = datetime.now()

        # Find videos needing milestone analysis
        milestones = [
            (timedelta(hours=24), "24h"),
            (timedelta(hours=48), "48h"),
            (timedelta(days=7), "7d"),
            (timedelta(days=30), "30d"),
        ]

        for delta, period in milestones:
            target_time = now - delta
            # Find videos published around this milestone (±2 hours window)
            window_start = (target_time - timedelta(hours=2)).isoformat()
            window_end = (target_time + timedelta(hours=2)).isoformat()

            rows = self.db.conn.execute("""
                SELECT id FROM jobs
                WHERE channel_id = ? AND status = 'published'
                AND published_at BETWEEN ? AND ?
                AND id NOT IN (
                    SELECT job_id FROM youtube_analytics
                    WHERE snapshot_period = ?
                )
            """, (channel_id, window_start, window_end, period)).fetchall()

            for row in rows:
                await self.send_milestone_report(row["id"], period)

        # Weekly report (every Monday)
        if now.weekday() == 0 and now.hour == 9:
            await self.send_weekly_report(channel_id)

        # Monthly report (1st of month)
        if now.day == 1 and now.hour == 10:
            await self.send_monthly_report(channel_id)

    # ─── Report Generation ────────────────────────────────────

    async def _generate_and_send(self, config: ReportConfig) -> None:
        """Generate full report and send via Telegram."""
        channel_id = config.channel_id
        days = config.days

        # Run all analyzers
        ctr_report = self.ctr.analyze_channel(channel_id, days)
        watchtime_report = self.watchtime.analyze_channel(channel_id, days)
        revenue_report = self.revenue.analyze_channel(channel_id, days)
        cross_report = self.cross_video.analyze_channel(channel_id)

        # Format header
        report_label = "📊 Weekly" if config.report_type == "weekly" else "📈 Monthly"
        header = (
            f"{report_label} Intelligence Report\n"
            f"Channel: {channel_id}\n"
            f"Period: Last {days} days\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"{'━' * 30}"
        )

        # Build sections
        sections = [
            header,
            self._format_overview(ctr_report, watchtime_report, revenue_report),
            self._format_ctr_section(ctr_report),
            self._format_watchtime_section(watchtime_report),
            self._format_revenue_section(revenue_report),
            self._format_patterns_section(cross_report),
            self._format_recommendations(
                ctr_report, watchtime_report, revenue_report, cross_report
            ),
        ]

        full_text = "\n\n".join(sections)

        # Send text report (split if >4096 chars for Telegram)
        for chunk in self._split_message(full_text, 4000):
            await self.telegram.send(chunk)

        # Generate and send charts
        if config.include_charts:
            charts = self._generate_charts(
                ctr_report, watchtime_report, revenue_report, cross_report
            )
            if charts:
                images = [{"path": c.file_path, "caption": c.caption} for c in charts]
                await self.telegram.send_image_album(images)

                # Cleanup temp files
                for c in charts:
                    try:
                        Path(c.file_path).unlink()
                    except OSError:
                        pass

        logger.info(f"{config.report_type.title()} report sent for {channel_id}")

    # ─── Message Formatting ───────────────────────────────────

    def _format_overview(
        self,
        ctr: CTRReport,
        watchtime: WatchtimeReport,
        revenue: RevenueReport,
    ) -> str:
        """Format overview section."""
        return (
            f"<b>📋 Overview</b>\n"
            f"Videos Analyzed: {ctr.total_videos_analyzed}\n"
            f"Avg CTR: {ctr.overall_avg_ctr:.2f}%\n"
            f"Avg Retention: {watchtime.overall_avg_view_pct:.1f}%\n"
            f"Total Revenue: ${revenue.total_revenue:.2f}\n"
            f"Avg RPM: ${revenue.overall_avg_rpm:.2f}"
        )

    def _format_ctr_section(self, report: CTRReport) -> str:
        """Format CTR analysis section."""
        lines = ["<b>🖱️ CTR Analysis</b>"]

        if report.top_performers:
            lines.append("\n<i>Top Performers:</i>")
            for v in report.top_performers[:3]:
                lines.append(
                    f"  • {v['title'][:40]}... → {v['ctr']:.2f}% CTR "
                    f"({v['impressions']:,} imp)"
                )

        if report.title_patterns:
            lines.append("\n<i>Title Patterns:</i>")
            for p in report.title_patterns[:3]:
                lines.append(
                    f"  • {p.pattern_value}: {p.avg_ctr:.2f}% avg CTR "
                    f"(n={p.sample_size})"
                )

        return "\n".join(lines)

    def _format_watchtime_section(self, report: WatchtimeReport) -> str:
        """Format watchtime analysis section."""
        lines = [
            "<b>⏱️ Watchtime</b>",
            f"Optimal Length: {report.optimal_length_minutes} min",
        ]

        if report.length_buckets:
            lines.append("\n<i>By Length:</i>")
            for b in report.length_buckets[:4]:
                lines.append(
                    f"  • {b.label}: {b.avg_view_percentage:.1f}% retention "
                    f"({b.video_count} videos)"
                )

        return "\n".join(lines)

    def _format_revenue_section(self, report: RevenueReport) -> str:
        """Format revenue section."""
        lines = [
            "<b>💰 Revenue</b>",
            f"Total: ${report.total_revenue:.2f}",
            f"Avg RPM: ${report.overall_avg_rpm:.2f}",
        ]

        if report.rpm_by_topic:
            lines.append("\n<i>RPM by Category:</i>")
            for t in report.rpm_by_topic[:3]:
                lines.append(
                    f"  • {t.topic_category}: ${t.avg_rpm:.2f}/1K "
                    f"(${t.total_revenue:.2f} total)"
                )

        if report.top_earners:
            lines.append("\n<i>Top Earners:</i>")
            for e in report.top_earners[:3]:
                lines.append(
                    f"  • {e['topic'][:35]}... → ${e['revenue']:.2f} "
                    f"({e['views']:,} views)"
                )

        return "\n".join(lines)

    def _format_patterns_section(self, report: CrossVideoReport) -> str:
        """Format cross-video patterns section."""
        lines = ["<b>🔍 Patterns</b>"]

        if report.production_patterns:
            lines.append("\n<i>What Works:</i>")
            for p in report.production_patterns[:3]:
                emoji = "✅" if p.vs_baseline > 0 else "⚠️"
                lines.append(
                    f"  {emoji} {p.dimension}='{p.value}': "
                    f"{p.vs_baseline:+.1f}% {p.metric_used}"
                )

        if report.anti_patterns:
            lines.append("\n<i>What to Avoid:</i>")
            for p in report.anti_patterns[:2]:
                lines.append(
                    f"  🚫 {p.dimension}='{p.value}': "
                    f"{p.vs_baseline:.1f}% {p.metric_used}"
                )

        return "\n".join(lines)

    def _format_recommendations(
        self,
        ctr: CTRReport,
        watchtime: WatchtimeReport,
        revenue: RevenueReport,
        cross: CrossVideoReport,
    ) -> str:
        """Format combined recommendations section."""
        lines = ["<b>💡 Recommendations</b>"]

        all_recs = (
            ctr.recommendations +
            watchtime.recommendations +
            revenue.recommendations +
            cross.recommendations
        )

        # Deduplicate and limit
        seen = set()
        for rec in all_recs[:8]:
            if rec not in seen:
                lines.append(f"  • {rec}")
                seen.add(rec)

        return "\n".join(lines)

    def _format_milestone_message(
        self,
        job_id: str,
        title: str,
        period: str,
        ctr: dict,
        watchtime: dict,
        retention,
        revenue: dict,
    ) -> str:
        """Format single-video milestone report."""
        period_labels = {
            "24h": "24 Hours",
            "48h": "48 Hours",
            "7d": "7 Days",
            "30d": "30 Days",
        }

        lines = [
            f"<b>🎬 Video Milestone: {period_labels.get(period, period)}</b>",
            f"Title: {title[:60]}",
            f"Job: {job_id}",
            f"{'━' * 25}",
        ]

        if ctr:
            lines.extend([
                f"\n<i>Performance:</i>",
                f"  Views: {ctr.get('views', 0):,}",
                f"  Impressions: {ctr.get('impressions', 0):,}",
                f"  CTR: {ctr.get('ctr', 0):.2f}%",
            ])

        if watchtime:
            lines.extend([
                f"  Avg View Duration: {watchtime.get('avg_duration', 0)}s",
                f"  Avg Retention: {watchtime.get('avg_percentage', 0):.1f}%",
            ])
            if watchtime.get("vs_channel_avg_pct") is not None:
                delta = watchtime["vs_channel_avg_pct"]
                emoji = "📈" if delta > 0 else "📉"
                lines.append(f"  {emoji} vs Channel Avg: {delta:+.1f}%")

        if revenue:
            lines.extend([
                f"\n<i>Revenue:</i>",
                f"  Estimated: ${revenue.get('revenue', 0):.2f}",
                f"  RPM: ${revenue.get('rpm', 0):.2f}",
            ])

        if hasattr(retention, "recommendations") and retention.recommendations:
            lines.append(f"\n<i>Retention Insights:</i>")
            for rec in retention.recommendations[:3]:
                lines.append(f"  • {rec}")

        return "\n".join(lines)

    # ─── Chart Generation ─────────────────────────────────────

    def _generate_charts(
        self,
        ctr: CTRReport,
        watchtime: WatchtimeReport,
        revenue: RevenueReport,
        cross: CrossVideoReport,
    ) -> list[GeneratedChart]:
        """Generate all report charts."""
        charts: list[GeneratedChart] = []

        try:
            plt.style.use(CHART_STYLE)
        except OSError:
            pass  # Fall back to default

        # CTR distribution chart
        if ctr.top_performers and ctr.bottom_performers:
            chart = self._chart_ctr_distribution(ctr)
            if chart:
                charts.append(chart)

        # Watchtime buckets chart
        if watchtime.length_buckets:
            chart = self._chart_watchtime_buckets(watchtime)
            if chart:
                charts.append(chart)

        # Revenue trend chart
        if revenue.revenue_trend and len(revenue.revenue_trend) >= 2:
            chart = self._chart_revenue_trend(revenue)
            if chart:
                charts.append(chart)

        # RPM by category chart
        if revenue.rpm_by_topic:
            chart = self._chart_rpm_by_topic(revenue)
            if chart:
                charts.append(chart)

        return charts

    def _chart_ctr_distribution(self, report: CTRReport) -> Optional[GeneratedChart]:
        """Generate CTR distribution bar chart."""
        try:
            all_videos = report.top_performers + report.bottom_performers
            titles = [v["title"][:25] + "…" for v in all_videos]
            ctrs = [v["ctr"] for v in all_videos]
            colors = [CHART_COLORS[0] if c >= report.overall_avg_ctr else CHART_COLORS[3] for c in ctrs]

            fig, ax = plt.subplots(figsize=CHART_FIGSIZE)
            bars = ax.barh(titles, ctrs, color=colors)
            ax.axvline(x=report.overall_avg_ctr, color="gray", linestyle="--", label=f"Avg: {report.overall_avg_ctr:.1f}%")
            ax.set_xlabel("CTR (%)")
            ax.set_title("CTR Distribution — Top & Bottom Performers")
            ax.legend()
            plt.tight_layout()

            path = self._save_chart(fig, "ctr_distribution")
            return GeneratedChart(
                title="CTR Distribution",
                file_path=path,
                caption="📊 CTR: Top & Bottom performers vs channel average",
            )
        except Exception as e:
            logger.error(f"Chart generation failed (CTR): {e}")
            return None

    def _chart_watchtime_buckets(self, report: WatchtimeReport) -> Optional[GeneratedChart]:
        """Generate watchtime by length bucket chart."""
        try:
            labels = [b.label for b in report.length_buckets]
            retentions = [b.avg_view_percentage for b in report.length_buckets]
            counts = [b.video_count for b in report.length_buckets]

            fig, ax1 = plt.subplots(figsize=CHART_FIGSIZE)
            x = range(len(labels))

            bars = ax1.bar(x, retentions, color=CHART_COLORS[1], alpha=0.7, label="Avg Retention %")
            ax1.set_ylabel("Retention (%)", color=CHART_COLORS[1])
            ax1.set_xlabel("Video Length")
            ax1.set_xticks(x)
            ax1.set_xticklabels(labels, rotation=30, ha="right")

            ax2 = ax1.twinx()
            ax2.plot(x, counts, color=CHART_COLORS[2], marker="o", linewidth=2, label="Video Count")
            ax2.set_ylabel("Video Count", color=CHART_COLORS[2])

            ax1.set_title("Retention by Video Length")
            fig.legend(loc="upper right", bbox_to_anchor=(0.95, 0.95))
            plt.tight_layout()

            path = self._save_chart(fig, "watchtime_buckets")
            return GeneratedChart(
                title="Watchtime by Length",
                file_path=path,
                caption="⏱️ Retention performance by video length bucket",
            )
        except Exception as e:
            logger.error(f"Chart generation failed (watchtime): {e}")
            return None

    def _chart_revenue_trend(self, report: RevenueReport) -> Optional[GeneratedChart]:
        """Generate monthly revenue trend chart."""
        try:
            months = [t["month"] for t in report.revenue_trend]
            revenues = [t["revenue"] for t in report.revenue_trend]
            video_counts = [t["videos"] for t in report.revenue_trend]

            fig, ax1 = plt.subplots(figsize=CHART_FIGSIZE)

            ax1.fill_between(range(len(months)), revenues, alpha=0.3, color=CHART_COLORS[0])
            ax1.plot(range(len(months)), revenues, color=CHART_COLORS[0], marker="o", linewidth=2, label="Revenue ($)")
            ax1.set_ylabel("Revenue ($)", color=CHART_COLORS[0])
            ax1.set_xlabel("Month")
            ax1.set_xticks(range(len(months)))
            ax1.set_xticklabels(months, rotation=45, ha="right")

            ax2 = ax1.twinx()
            ax2.bar(range(len(months)), video_counts, alpha=0.3, color=CHART_COLORS[1], label="Videos")
            ax2.set_ylabel("Videos Published", color=CHART_COLORS[1])

            ax1.set_title("Revenue Trend")
            fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.95))
            plt.tight_layout()

            path = self._save_chart(fig, "revenue_trend")
            return GeneratedChart(
                title="Revenue Trend",
                file_path=path,
                caption="💰 Monthly revenue trend with video count overlay",
            )
        except Exception as e:
            logger.error(f"Chart generation failed (revenue): {e}")
            return None

    def _chart_rpm_by_topic(self, report: RevenueReport) -> Optional[GeneratedChart]:
        """Generate RPM by topic category chart."""
        try:
            categories = [t.topic_category for t in report.rpm_by_topic]
            rpms = [t.avg_rpm for t in report.rpm_by_topic]
            counts = [t.video_count for t in report.rpm_by_topic]

            fig, ax = plt.subplots(figsize=CHART_FIGSIZE)
            bars = ax.bar(categories, rpms, color=CHART_COLORS[:len(categories)])

            # Add count labels on bars
            for bar, count in zip(bars, counts):
                ax.text(
                    bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                    f"n={count}", ha="center", va="bottom", fontsize=9,
                )

            ax.set_ylabel("Average RPM ($)")
            ax.set_title("RPM by Topic Category")
            ax.axhline(y=report.overall_avg_rpm, color="gray", linestyle="--",
                       label=f"Avg: ${report.overall_avg_rpm:.2f}")
            ax.legend()
            plt.tight_layout()

            path = self._save_chart(fig, "rpm_by_topic")
            return GeneratedChart(
                title="RPM by Topic",
                file_path=path,
                caption="💰 RPM comparison across topic categories",
            )
        except Exception as e:
            logger.error(f"Chart generation failed (RPM): {e}")
            return None

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _save_chart(fig: plt.Figure, name: str) -> str:
        """Save matplotlib figure to temp file and return path."""
        path = Path(tempfile.gettempdir()) / f"intel_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fig.savefig(str(path), dpi=CHART_DPI, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        """Split long message into Telegram-safe chunks."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_len:
                chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            chunks.append(current)
        return chunks
