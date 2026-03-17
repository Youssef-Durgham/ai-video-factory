"""
Content Calendar Agent — Weekly content planning with trend analysis,
gap detection, event awareness, and Telegram approval workflow.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)


class ContentCalendarAgent:
    """
    Generates a 7-day content plan per channel, sends to Telegram for approval,
    and queues approved topics for production.
    """

    def __init__(self, db: FactoryDB, telegram_bot=None):
        self.db = db
        self.telegram = telegram_bot

    def run(self, channel_id: str) -> list[dict]:
        """
        Generate a weekly content plan for a channel.
        Returns list of planned items (7 days).
        """
        # Gather inputs
        recent_topics = self._get_recent_topics(channel_id, days=30)
        upcoming_events = self._get_upcoming_events(channel_id)
        performance_rules = self.db.get_active_rules(channel_id)
        anti_rep_patterns = self.db.get_recent_patterns(channel_id, last_n=10)

        # Get channel config
        channel_config = self._get_channel_config(channel_id)

        # Generate plan via LLM
        plan = self._generate_plan(
            channel_id=channel_id,
            channel_config=channel_config,
            recent_topics=recent_topics,
            upcoming_events=upcoming_events,
            performance_rules=performance_rules,
            anti_rep_patterns=anti_rep_patterns,
        )

        # Save to DB
        self._save_plan(channel_id, plan)

        # Send to Telegram for approval
        if self.telegram:
            self._send_for_approval(channel_id, plan)

        return plan

    def approve_topic(self, calendar_id: int, approved_by: str = "yusif"):
        """Approve a planned topic — mark it ready for production."""
        self.db.conn.execute(
            "UPDATE content_calendar SET status = 'approved', approved_by = ?, approved_at = ? WHERE id = ?",
            (approved_by, datetime.now().isoformat(), calendar_id),
        )
        self.db.conn.commit()
        logger.info(f"Calendar item {calendar_id} approved by {approved_by}")

    def reject_topic(self, calendar_id: int):
        """Reject/cancel a planned topic."""
        self.db.conn.execute(
            "UPDATE content_calendar SET status = 'cancelled' WHERE id = ?",
            (calendar_id,),
        )
        self.db.conn.commit()

    def get_next_approved(self, channel_id: str) -> Optional[dict]:
        """Get next approved topic that hasn't been produced yet."""
        row = self.db.conn.execute(
            "SELECT * FROM content_calendar WHERE channel_id = ? AND status = 'approved' "
            "AND job_id IS NULL ORDER BY planned_date ASC LIMIT 1",
            (channel_id,),
        ).fetchone()
        return dict(row) if row else None

    def link_to_job(self, calendar_id: int, job_id: str):
        """Link a calendar entry to its production job."""
        self.db.conn.execute(
            "UPDATE content_calendar SET status = 'in_production', job_id = ? WHERE id = ?",
            (job_id, calendar_id),
        )
        self.db.conn.commit()

    # ─── Plan Generation ───────────────────────────────

    def _generate_plan(self, channel_id: str, channel_config: dict,
                       recent_topics: list, upcoming_events: list,
                       performance_rules: list, anti_rep_patterns: list) -> list[dict]:
        """Use LLM to generate a 7-day content plan."""

        recent_str = ", ".join(recent_topics[:15]) if recent_topics else "لا توجد مواضيع سابقة"
        events_str = json.dumps(upcoming_events, ensure_ascii=False) if upcoming_events else "لا توجد أحداث قادمة"
        rules_str = "\n".join(
            f"- {r.get('rule_name', '')}: {r.get('reason', '')}"
            for r in performance_rules[:10]
        ) if performance_rules else "لا توجد قواعد أداء بعد"

        # Extract blocked patterns
        from collections import Counter
        hook_counts = Counter(p.get("hook_style") for p in anti_rep_patterns if p.get("hook_style"))
        style_counts = Counter(p.get("narrative_style") for p in anti_rep_patterns if p.get("narrative_style"))

        topics_config = channel_config.get("topics", [])
        tone = channel_config.get("content", {}).get("tone", "educational, engaging")

        today = datetime.now()
        dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 8)]

        prompt = f"""You are a content strategist for an Arabic YouTube channel.

Channel: {channel_id}
Category topics: {', '.join(topics_config)}
Tone: {tone}
Recent topics (last 30 days): {recent_str}
Upcoming events: {events_str}
Performance rules: {rules_str}
Overused hooks: {dict(hook_counts.most_common(3))}
Overused styles: {dict(style_counts.most_common(3))}

Generate a 7-day content plan for dates: {', '.join(dates)}

For each day provide:
- date: the date
- topic: Arabic topic title (compelling, specific)
- narrative_style: one of [investigative, storytelling, explainer, countdown, debate]
- priority: normal or high
- reasoning: why this topic now (1 sentence)

Rules:
1. No topic should overlap with recent_topics
2. Vary narrative styles — don't repeat same style 2 days in a row
3. Include at least 1 event-tied topic if events exist
4. Mix between trending topics and evergreen content
5. Weekend topics can be lighter/more entertaining

Return a JSON array of 7 objects."""

        try:
            plan = llm.generate_json(prompt, temperature=0.7, max_tokens=4096)
            if isinstance(plan, dict) and "plan" in plan:
                plan = plan["plan"]
            if not isinstance(plan, list):
                plan = [plan]
            # Ensure 7 items
            while len(plan) < 7:
                plan.append({
                    "date": dates[len(plan)] if len(plan) < len(dates) else dates[-1],
                    "topic": "موضوع احتياطي",
                    "narrative_style": "explainer",
                    "priority": "normal",
                    "reasoning": "Filler topic",
                })
            return plan[:7]
        except Exception as e:
            logger.error(f"Plan generation failed: {e}")
            # Fallback: simple plan
            return [
                {
                    "date": dates[i],
                    "topic": f"موضوع مقترح #{i+1}",
                    "narrative_style": ["investigative", "storytelling", "explainer", "countdown", "debate", "storytelling", "investigative"][i],
                    "priority": "normal",
                    "reasoning": "Auto-generated fallback",
                }
                for i in range(7)
            ]

    # ─── DB Operations ─────────────────────────────────

    def _save_plan(self, channel_id: str, plan: list[dict]):
        """Save plan to content_calendar table."""
        for item in plan:
            self.db.conn.execute("""
                INSERT INTO content_calendar
                    (channel_id, planned_date, topic, narrative_style, priority, source, status, notes)
                VALUES (?, ?, ?, ?, ?, 'calendar_agent', 'planned', ?)
            """, (
                channel_id,
                item.get("date"),
                item.get("topic"),
                item.get("narrative_style"),
                item.get("priority", "normal"),
                item.get("reasoning", ""),
            ))
        self.db.conn.commit()
        logger.info(f"Saved {len(plan)} calendar items for {channel_id}")

    def _get_recent_topics(self, channel_id: str, days: int = 30) -> list[str]:
        """Get topics from recent published/planned videos."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = self.db.conn.execute(
            "SELECT topic FROM jobs WHERE channel_id = ? AND created_at > ? AND topic IS NOT NULL "
            "UNION SELECT topic FROM content_calendar WHERE channel_id = ? AND created_at > ?",
            (channel_id, cutoff, channel_id, cutoff),
        ).fetchall()
        return [r["topic"] for r in rows if r["topic"]]

    def _get_upcoming_events(self, channel_id: str) -> list[dict]:
        """Get seasonal events in the next 30 days."""
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        rows = self.db.conn.execute(
            "SELECT event_name, event_date, topics FROM seasonal_events "
            "WHERE event_date BETWEEN ? AND ? AND (channel_id IS NULL OR channel_id = ?)",
            (today, future, channel_id),
        ).fetchall()
        # seasonal_events table may not exist yet — handle gracefully
        if not rows:
            return []
        return [{"event": r["event_name"], "date": r["event_date"],
                 "topics": json.loads(r["topics"]) if r["topics"] else []} for r in rows]

    def _get_channel_config(self, channel_id: str) -> dict:
        """Load channel config. Fallback to defaults."""
        try:
            from src.core.config import get_channel_config
            return get_channel_config(channel_id)
        except Exception:
            return {"topics": [], "content": {"tone": "educational, engaging"}}

    # ─── Telegram Integration ──────────────────────────

    def _send_for_approval(self, channel_id: str, plan: list[dict]):
        """Send the weekly plan to Telegram with approval buttons."""
        lines = [f"📅 <b>خطة المحتوى الأسبوعية — {channel_id}</b>\n"]
        for i, item in enumerate(plan):
            emoji = "🔴" if item.get("priority") == "high" else "🟢"
            lines.append(
                f"{emoji} <b>{item.get('date', '?')}</b>\n"
                f"   📋 {item.get('topic', '?')}\n"
                f"   🎭 {item.get('narrative_style', '?')}\n"
                f"   💡 {item.get('reasoning', '')}\n"
            )

        text = "\n".join(lines)

        buttons = [
            [{"text": "✅ اعتماد الكل", "data": f"approve_calendar_all:{channel_id}"}],
            [{"text": "✏️ تعديل", "data": f"edit_calendar:{channel_id}"},
             {"text": "❌ رفض", "data": f"reject_calendar:{channel_id}"}],
        ]

        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                self.telegram.send(text, buttons=buttons)
            )
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")
