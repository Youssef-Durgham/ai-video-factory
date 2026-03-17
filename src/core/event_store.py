"""
Persists all events to SQLite for audit trail, TRACING, and replay.

With 40 agents + EventBus, debugging is a nightmare without proper tracing.
Every event MUST carry trace context.

DEBUGGING WORKFLOW:
1. Job fails → get trace_id from job table
2. SELECT * FROM events WHERE trace_id = ? ORDER BY timestamp
3. See COMPLETE history: every phase, every check, every retry
4. parent_span_id shows call hierarchy
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional

from src.core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)


class EventStore:
    """
    Persistent event log with FULL tracing support.

    Subscribes to EventBus (subscribe_all) and persists every event
    to the 'events' table (already created by FactoryDB schema).

    Query methods enable:
    - Full job trace reconstruction
    - Hierarchical trace trees (parent→child spans)
    - Error/critical filtering
    - Slow operation detection (bottleneck finder)
    - Recent event browsing
    """

    def __init__(self, db, event_bus: Optional[EventBus] = None):
        """
        Args:
            db: FactoryDB instance (events table already exists in schema).
            event_bus: If provided, auto-subscribes to all events.
        """
        self.db = db
        if event_bus:
            event_bus.subscribe_all(self.store)
        logger.info("EventStore initialized")

    def store(self, event: Event):
        """Store event with full tracing context."""
        if not event.span_id:
            event.span_id = str(uuid.uuid4())[:8]
        if not event.trace_id:
            event.trace_id = str(uuid.uuid4())[:12]

        try:
            self.db.conn.execute("""
                INSERT INTO events (event_type, job_id, trace_id, span_id,
                    parent_span_id, source, severity, duration_ms, data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.type.value, event.job_id, event.trace_id, event.span_id,
                event.parent_span_id, event.source, event.severity,
                event.duration_ms, json.dumps(event.data),
                event.timestamp.isoformat()
            ))
            self.db.conn.commit()
        except Exception as e:
            logger.error(f"EventStore.store failed: {e}")

    def get_job_trace(self, job_id: str) -> list[dict]:
        """Get complete trace for a job — THE primary debugging tool."""
        rows = self.db.conn.execute(
            "SELECT * FROM events WHERE job_id = ? ORDER BY timestamp ASC",
            (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trace_tree(self, trace_id: str) -> list[dict]:
        """Build hierarchical trace tree from flat events."""
        events = self.db.conn.execute(
            "SELECT * FROM events WHERE trace_id = ? ORDER BY timestamp",
            (trace_id,)
        ).fetchall()

        by_span: dict[str, dict] = {}
        for e in events:
            by_span[e["span_id"]] = dict(e)

        roots = []
        for e in events:
            e_dict = by_span[e["span_id"]]
            parent = e["parent_span_id"]
            if parent and parent in by_span:
                by_span[parent].setdefault("children", []).append(e_dict)
            else:
                roots.append(e_dict)
        return roots

    def get_errors(self, job_id: str = None, hours: int = 24) -> list[dict]:
        """Get recent errors/criticals — for /health command."""
        query = """
            SELECT * FROM events
            WHERE severity IN ('error', 'critical')
            AND timestamp > datetime('now', ?)
        """
        params: list = [f"-{hours} hours"]
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY timestamp DESC LIMIT 50"
        return [dict(r) for r in self.db.conn.execute(query, params).fetchall()]

    def get_slow_operations(self, job_id: str, threshold_ms: int = 5000) -> list[dict]:
        """Find operations that took longer than threshold — bottleneck finder."""
        rows = self.db.conn.execute("""
            SELECT source, event_type, duration_ms, span_id, data
            FROM events
            WHERE job_id = ? AND duration_ms > ?
            ORDER BY duration_ms DESC
        """, (job_id, threshold_ms)).fetchall()
        return [dict(r) for r in rows]

    def get_recent(self, event_type: str = None, limit: int = 100) -> list[dict]:
        """Get recent events, optionally filtered by type."""
        query = "SELECT * FROM events"
        params: list = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.db.conn.execute(query, params).fetchall()]

    def get_event_count(self, job_id: str) -> dict:
        """Get event counts by type for a job — quick overview."""
        rows = self.db.conn.execute("""
            SELECT event_type, severity, COUNT(*) as count
            FROM events WHERE job_id = ?
            GROUP BY event_type, severity
            ORDER BY count DESC
        """, (job_id,)).fetchall()
        return [dict(r) for r in rows]

    def purge_old_events(self, days: int = 90):
        """Delete events older than N days to keep DB size manageable."""
        self.db.conn.execute(
            "DELETE FROM events WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",)
        )
        self.db.conn.commit()
        logger.info(f"Purged events older than {days} days")
