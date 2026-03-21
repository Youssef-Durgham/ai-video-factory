"""
FactoryDB — Central SQLite database for all agents and phases.
WAL mode for concurrent reads. Foreign keys enforced.
All 9 phases + agents read/write through this class.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import resolve_path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# FULL SCHEMA — All tables from ARCHITECTURE.md + BLUEPRINT.md
# ═══════════════════════════════════════════════════════════════

SCHEMA_SQL = """
-- ─── Core Tables ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    channel_id TEXT NOT NULL,
    topic TEXT,
    topic_source TEXT DEFAULT 'manual',
    priority TEXT DEFAULT 'normal',
    narrative_style TEXT,
    selected_voice_id TEXT,
    voice_selection_reason TEXT,
    topic_region TEXT DEFAULT 'global',
    target_length_min INTEGER,
    font_animation_config JSON,
    color_grade_config JSON,

    -- Phase completion timestamps
    phase1_completed_at TIMESTAMP,
    phase2_completed_at TIMESTAMP,
    phase3_completed_at TIMESTAMP,
    phase4_completed_at TIMESTAMP,
    phase5_completed_at TIMESTAMP,
    phase6_completed_at TIMESTAMP,
    phase7_completed_at TIMESTAMP,
    phase7_5_completed_at TIMESTAMP,
    phase8_completed_at TIMESTAMP,
    phase9_last_analysis TIMESTAMP,

    -- Phase retry counts
    script_revisions INTEGER DEFAULT 0,
    image_regenerations INTEGER DEFAULT 0,
    video_retries INTEGER DEFAULT 0,

    -- Blocking / errors
    blocked_at TIMESTAMP,
    blocked_reason TEXT,
    blocked_phase TEXT,
    resolved_at TIMESTAMP,

    -- Manual review
    manual_review_required BOOLEAN DEFAULT FALSE,
    manual_review_status TEXT,
    manual_review_notes TEXT,
    manual_review_at TIMESTAMP,

    -- Final output
    youtube_video_id TEXT,
    youtube_url TEXT,
    published_at TIMESTAMP,
    scheduled_for TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_production_time_sec INTEGER,
    total_gpu_time_sec INTEGER
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_channel ON jobs(channel_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

-- ─── Research ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    topic TEXT NOT NULL,
    source TEXT,
    search_volume INTEGER,
    competition_score REAL,
    trend_velocity REAL,
    category TEXT,
    suggested_angle TEXT,
    rank_score REAL,
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── SEO Data ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS seo_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    primary_keywords JSON,
    secondary_keywords JSON,
    long_tail_keywords JSON,
    generated_titles JSON,
    selected_title TEXT,
    selected_title_score REAL,
    tags JSON,
    description_template TEXT,
    hashtags JSON,
    top_competitors JSON,
    unique_angle TEXT,
    content_gap TEXT,
    thumbnail_text_suggestions JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Scripts ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'draft',
    full_text TEXT NOT NULL,
    word_count INTEGER,
    estimated_duration_sec INTEGER,
    hook_text TEXT,
    sections JSON,
    conclusion_text TEXT,
    keywords_included JSON,
    keyword_density REAL,
    emotional_arc JSON,
    reviewer_notes TEXT,
    factual_accuracy_score REAL,
    engagement_score REAL,
    arabic_quality_score REAL,
    sources JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scripts_job ON scripts(job_id);

-- ─── Scenes ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    scene_index INTEGER NOT NULL,
    narration_text TEXT NOT NULL,
    duration_sec REAL,
    visual_prompt TEXT,
    visual_style TEXT,
    camera_movement TEXT,
    expected_elements JSON,
    image_path TEXT,
    image_upscaled_path TEXT,
    video_clip_path TEXT,
    voice_path TEXT,
    image_seed INTEGER,
    image_score REAL,
    image_regenerated BOOLEAN DEFAULT FALSE,
    video_method TEXT,
    voice_emotion TEXT,
    voice_speed REAL DEFAULT 1.0,
    music_mood TEXT,
    sfx_tags JSON,
    sfx_paths JSON,
    text_overlay JSON,
    presenter_mode TEXT DEFAULT 'none',
    presenter_path TEXT,
    start_time_sec REAL,
    end_time_sec REAL,
    transition_type TEXT DEFAULT 'crossfade',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scenes_job ON scenes(job_id);
CREATE INDEX IF NOT EXISTS idx_scenes_order ON scenes(job_id, scene_index);

-- ─── Compliance Checks ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS compliance_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    phase TEXT NOT NULL,
    check_type TEXT NOT NULL,
    status TEXT,
    score REAL,
    details TEXT,
    flagged_items JSON,
    claims_checked INTEGER,
    claims_verified INTEGER,
    claims_unverified JSON,
    auto_fixed BOOLEAN DEFAULT FALSE,
    fix_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── QA Rubrics ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS qa_rubrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    scene_index INTEGER,
    asset_type TEXT NOT NULL,
    check_phase TEXT NOT NULL,
    attempt_number INTEGER DEFAULT 1,
    deterministic_results JSON,
    deterministic_pass BOOLEAN,
    hard_fail_reason TEXT,
    rubric_scores JSON,
    weighted_score REAL,
    final_verdict TEXT NOT NULL,
    flags JSON,
    model_used TEXT,
    inference_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_rubrics_job ON qa_rubrics(job_id);
CREATE INDEX IF NOT EXISTS idx_rubrics_scene ON qa_rubrics(job_id, scene_index);
CREATE INDEX IF NOT EXISTS idx_rubrics_verdict ON qa_rubrics(final_verdict);
CREATE INDEX IF NOT EXISTS idx_rubrics_phase ON qa_rubrics(check_phase);

-- ─── Audio Tracks ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audio_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    track_type TEXT NOT NULL,
    prompt TEXT,
    file_path TEXT,
    duration_sec REAL,
    seed INTEGER,
    temperature REAL,
    fingerprint BLOB,
    similarity_score REAL,
    content_id_safe BOOLEAN,
    youtube_precheck_result TEXT,
    pitch_shifted BOOLEAN DEFAULT FALSE,
    time_stretched BOOLEAN DEFAULT FALSE,
    reverb_added BOOLEAN DEFAULT FALSE,
    regeneration_count INTEGER DEFAULT 0,
    regeneration_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Mood Zones ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mood_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    zone_index INTEGER NOT NULL,
    mood TEXT NOT NULL,
    start_scene INTEGER NOT NULL,
    end_scene INTEGER NOT NULL,
    duration_sec REAL,
    music_prompt TEXT,
    music_path TEXT,
    crossfade_in_sec REAL DEFAULT 2.0,
    crossfade_out_sec REAL DEFAULT 2.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Thumbnails ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    variant TEXT,
    file_path TEXT,
    prompt TEXT,
    text_overlay TEXT,
    text_position TEXT,
    style TEXT,
    readability_score REAL,
    youtube_ui_overlap BOOLEAN,
    ab_test_id TEXT,
    impressions INTEGER,
    clicks INTEGER,
    ctr REAL,
    is_winner BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Subtitles ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    language TEXT,
    srt_path TEXT,
    word_count INTEGER,
    uploaded_to_youtube BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── YouTube Analytics ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS youtube_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    youtube_video_id TEXT,
    snapshot_period TEXT,
    views INTEGER,
    watch_time_hours REAL,
    avg_view_duration_sec INTEGER,
    avg_view_percentage REAL,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    impressions INTEGER,
    ctr REAL,
    estimated_revenue REAL,
    rpm REAL,
    retention_curve JSON,
    top_countries JSON,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analytics_job ON youtube_analytics(job_id);
CREATE INDEX IF NOT EXISTS idx_analytics_period ON youtube_analytics(snapshot_period);

-- ─── Shorts ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS shorts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_job_id TEXT REFERENCES jobs(id),
    youtube_video_id TEXT,
    source_scene_start INTEGER,
    source_scene_end INTEGER,
    title TEXT,
    tags JSON,
    file_path TEXT,
    duration_sec REAL,
    views INTEGER,
    likes INTEGER,
    retention_pct REAL,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Performance Rules ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS performance_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT UNIQUE,
    rule_value TEXT,
    rule_type TEXT,
    confidence REAL,
    sample_size INTEGER,
    reason TEXT,
    applies_to_channel TEXT,
    discovery_date DATE,
    based_on_metric TEXT,
    metric_improvement_pct REAL,
    active BOOLEAN DEFAULT TRUE,
    superseded_by INTEGER REFERENCES performance_rules(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Anti-Repetition ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anti_repetition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    channel_id TEXT,
    hook_style TEXT,
    title_structure TEXT,
    visual_palette TEXT,
    music_mood TEXT,
    narrative_style TEXT,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_antirepeat_channel ON anti_repetition(channel_id, published_at);

-- ─── Content Calendar ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS content_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT,
    planned_date DATE,
    topic TEXT,
    narrative_style TEXT,
    priority TEXT DEFAULT 'normal',
    source TEXT,
    status TEXT DEFAULT 'planned',
    job_id TEXT REFERENCES jobs(id),
    approved_by TEXT,
    approved_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_calendar_date ON content_calendar(planned_date);

-- ─── Asset Versions ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS asset_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    scene_index INTEGER,
    asset_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    qa_score REAL,
    is_active BOOLEAN DEFAULT TRUE,
    creation_reason TEXT,
    prompt_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    UNIQUE(job_id, scene_index, asset_type, version)
);

CREATE INDEX IF NOT EXISTS idx_versions_job ON asset_versions(job_id, scene_index);
CREATE INDEX IF NOT EXISTS idx_versions_active ON asset_versions(is_active);

-- ─── Events (Event Store) ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    job_id TEXT,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    source TEXT,
    severity TEXT DEFAULT 'info',
    duration_ms INTEGER DEFAULT 0,
    data JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
CREATE INDEX IF NOT EXISTS idx_events_parent ON events(parent_span_id);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);

-- ─── Job Queue ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
    priority INTEGER DEFAULT 1,
    position INTEGER,
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    estimated_duration_min INTEGER,
    scheduled_start TIMESTAMP,
    channel_id TEXT,
    CONSTRAINT valid_priority CHECK(priority IN (0, 1, 2))
);

CREATE INDEX IF NOT EXISTS idx_queue_priority ON job_queue(priority, position);

-- ─── API Quota Log ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS api_quota_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    operation TEXT NOT NULL,
    units_used INTEGER NOT NULL,
    job_id TEXT,
    response_status INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quota_date ON api_quota_log(date);

-- ─── Calibration History ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS calibration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_type TEXT,
    videos_analyzed INTEGER,
    old_weights JSON,
    new_weights JSON,
    old_threshold REAL,
    new_threshold REAL,
    correlations JSON,
    confidence REAL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── Competitor Channels ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS competitor_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE,
    channel_name TEXT,
    category TEXT,
    subscriber_count INTEGER,
    total_videos INTEGER,
    avg_views_per_video INTEGER,
    last_scanned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS competitor_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_channel_id TEXT REFERENCES competitor_channels(channel_id),
    youtube_video_id TEXT UNIQUE,
    title TEXT,
    topic TEXT,
    views INTEGER,
    published_at TIMESTAMP,
    tags JSON,
    description TEXT,
    view_velocity REAL,
    is_viral BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class FactoryDB:
    """
    Central database for all agents. SQLite with WAL mode for concurrent reads.
    """

    def __init__(self, db_path: str = "data/factory.db"):
        resolved = resolve_path(db_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(resolved)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")

        self._create_tables()
        logger.info(f"FactoryDB initialized: {self.db_path}")

    def _create_tables(self):
        """Create all tables if they don't exist."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    # ─── Job Management ────────────────────────────────

    def create_job(self, channel_id: str, topic: str, **kwargs) -> str:
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cols = ["id", "channel_id", "topic"]
        vals = [job_id, channel_id, topic]
        for k, v in kwargs.items():
            cols.append(k)
            vals.append(v)
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO jobs ({col_names}) VALUES ({placeholders})", vals
        )
        self.conn.commit()
        logger.info(f"Job created: {job_id} | channel={channel_id} | topic={topic}")
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_job_status(self, job_id: str, status: str):
        self.conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), job_id),
        )
        self.conn.commit()

    def block_job(self, job_id: str, phase: str, reason: str):
        self.conn.execute(
            "UPDATE jobs SET status = 'blocked', blocked_at = ?, "
            "blocked_phase = ?, blocked_reason = ? WHERE id = ?",
            (datetime.now().isoformat(), phase, reason, job_id),
        )
        self.conn.commit()

    def get_active_jobs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status NOT IN "
            "('published', 'blocked', 'cancelled', 'complete') "
            "ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_blocked_jobs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'blocked' ORDER BY blocked_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Scene Management ──────────────────────────────

    def save_scenes(self, job_id: str, scenes: list[dict]):
        # Delete existing scenes first to prevent duplicates
        # (compliance auto-fix and script revisions call this again)
        self.conn.execute("DELETE FROM scenes WHERE job_id = ?", (job_id,))

        for i, scene in enumerate(scenes):
            self.conn.execute("""
                INSERT INTO scenes (job_id, scene_index, narration_text, duration_sec,
                    visual_prompt, visual_style, camera_movement, expected_elements,
                    music_mood, sfx_tags, text_overlay, presenter_mode, transition_type,
                    voice_emotion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, i,
                scene.get("narration_text", ""),
                scene.get("duration_seconds", 10),
                scene.get("visual_prompt", ""),
                scene.get("visual_style"),
                scene.get("camera_movement"),
                json.dumps(scene.get("expected_visual_elements", [])),
                scene.get("music_mood"),
                json.dumps(scene.get("sfx", [])),
                json.dumps(scene.get("text_overlay")),
                scene.get("presenter_mode", "none"),
                scene.get("transition_to_next", "crossfade"),
                scene.get("voice_emotion", "calm"),
            ))
        self.conn.commit()

    def get_scenes(self, job_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scenes WHERE job_id = ? ORDER BY scene_index",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_scene_asset(self, job_id: str, scene_index: int, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id, scene_index]
        self.conn.execute(
            f"UPDATE scenes SET {sets}, updated_at = CURRENT_TIMESTAMP "
            f"WHERE job_id = ? AND scene_index = ?",
            vals,
        )
        self.conn.commit()

    # ─── Script Management ─────────────────────────────

    def save_script(self, job_id: str, full_text: str, version: int = 1, **kwargs) -> int:
        cols = ["job_id", "full_text", "version"]
        vals = [job_id, full_text, version]
        for k, v in kwargs.items():
            cols.append(k)
            vals.append(json.dumps(v) if isinstance(v, (list, dict)) else v)
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        cursor = self.conn.execute(
            f"INSERT INTO scripts ({col_names}) VALUES ({placeholders})", vals
        )
        self.conn.commit()
        return cursor.lastrowid

    # ─── QA Rubric Storage ─────────────────────────────

    def save_rubric(self, job_id: str, scene_index: Optional[int], asset_type: str,
                    check_phase: str, attempt: int, deterministic: dict,
                    rubric_scores: dict, weighted_score: float, verdict: str,
                    flags: list, hard_fail: str = None, model: str = None,
                    inference_ms: int = 0):
        self.conn.execute("""
            INSERT INTO qa_rubrics (job_id, scene_index, asset_type, check_phase,
                attempt_number, deterministic_results, deterministic_pass, hard_fail_reason,
                rubric_scores, weighted_score, final_verdict, flags, model_used, inference_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, scene_index, asset_type, check_phase, attempt,
            json.dumps(deterministic), hard_fail is None, hard_fail,
            json.dumps(rubric_scores), weighted_score, verdict,
            json.dumps(flags), model, inference_ms,
        ))
        self.conn.commit()

    def get_rubrics(self, job_id: str, scene_index: int = None,
                    asset_type: str = None) -> list[dict]:
        query = "SELECT * FROM qa_rubrics WHERE job_id = ?"
        params: list = [job_id]
        if scene_index is not None:
            query += " AND scene_index = ?"
            params.append(scene_index)
        if asset_type:
            query += " AND asset_type = ?"
            params.append(asset_type)
        query += " ORDER BY scene_index, attempt_number"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_rubric_stats(self, job_id: str) -> list[dict]:
        rows = self.conn.execute("""
            SELECT asset_type, check_phase,
                   COUNT(*) as total,
                   AVG(weighted_score) as avg_score,
                   SUM(CASE WHEN final_verdict = 'pass' THEN 1 ELSE 0 END) as pass_count,
                   SUM(CASE WHEN hard_fail_reason IS NOT NULL THEN 1 ELSE 0 END) as hard_fails,
                   SUM(CASE WHEN final_verdict = 'flag_human' THEN 1 ELSE 0 END) as human_flags,
                   AVG(attempt_number) as avg_attempts
            FROM qa_rubrics WHERE job_id = ?
            GROUP BY asset_type, check_phase
        """, (job_id,)).fetchall()
        return [dict(r) for r in rows]

    # ─── Analytics ─────────────────────────────────────

    def save_analytics(self, job_id: str, period: str, metrics: dict):
        self.conn.execute("""
            INSERT INTO youtube_analytics (job_id, youtube_video_id, snapshot_period,
                views, watch_time_hours, avg_view_duration_sec, avg_view_percentage,
                likes, comments, shares, impressions, ctr,
                estimated_revenue, rpm, retention_curve, top_countries, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, metrics.get("video_id"), period,
            metrics.get("views", 0), metrics.get("watch_hours", 0),
            metrics.get("avg_duration", 0), metrics.get("avg_percentage", 0),
            metrics.get("likes", 0), metrics.get("comments", 0),
            metrics.get("shares", 0), metrics.get("impressions", 0),
            metrics.get("ctr", 0), metrics.get("revenue", 0),
            metrics.get("rpm", 0),
            json.dumps(metrics.get("retention_curve", [])),
            json.dumps(metrics.get("countries", [])),
            datetime.now().isoformat(),
        ))
        self.conn.commit()

    # ─── Performance Rules ─────────────────────────────

    def get_active_rules(self, channel_id: str = None) -> list[dict]:
        query = "SELECT * FROM performance_rules WHERE active = 1"
        params: list = []
        if channel_id:
            query += " AND (applies_to_channel IS NULL OR applies_to_channel = ?)"
            params.append(channel_id)
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    # ─── Anti-Repetition ──────────────────────────────

    def get_recent_patterns(self, channel_id: str, last_n: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM anti_repetition WHERE channel_id = ? "
            "ORDER BY published_at DESC LIMIT ?",
            (channel_id, last_n),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Job Flags (for manual review decision) ───────

    def get_job_flags(self, job_id: str) -> list[dict]:
        """Get all QA flags for a job across all rubrics."""
        rows = self.conn.execute(
            "SELECT flags, final_verdict FROM qa_rubrics WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        all_flags = []
        for r in rows:
            flags = json.loads(r["flags"]) if r["flags"] else []
            for f in flags:
                severity = "warn"
                if r["final_verdict"] in ("fail", "flag_human"):
                    severity = "error"
                all_flags.append({"flag": f, "severity": severity})
        return all_flags

    def count_published_videos(self, channel_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE channel_id = ? AND status = 'published'",
            (channel_id,),
        ).fetchone()
        return row[0] if row else 0

    def count_videos_in_category(self, channel_id: str, category: str) -> int:
        # Simplified — in practice, topic_source or a category column
        row = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE channel_id = ? AND topic_region = ? AND status = 'published'",
            (channel_id, category),
        ).fetchone()
        return row[0] if row else 0

    def get_recent_strikes(self, channel_id: str, days: int = 90) -> list:
        # Placeholder — would need a strikes table in real implementation
        return []

    # ─── Cleanup ───────────────────────────────────────

    def close(self):
        self.conn.close()
