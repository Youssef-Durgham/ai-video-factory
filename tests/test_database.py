"""Tests for FactoryDB — table creation, CRUD, WAL mode, foreign keys, concurrency."""

import sys
import os
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core.database import FactoryDB


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = FactoryDB(os.path.join(tmpdir, "test.db"))
        yield db
        db.close()


class TestTableCreation:
    def test_core_tables_exist(self, db):
        tables = {r[0] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for t in ("jobs", "scenes", "qa_rubrics", "events", "asset_versions"):
            assert t in tables, f"Missing table: {t}"

    def test_wal_mode(self, db):
        mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db):
        fk = db.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


class TestJobCRUD:
    def test_create_job(self, db):
        job_id = db.create_job("documentary_ar", "Test Topic")
        assert job_id.startswith("job_")
        job = db.get_job(job_id)
        assert job["status"] == "pending"
        assert job["channel_id"] == "documentary_ar"
        assert job["topic"] == "Test Topic"

    def test_update_status(self, db):
        job_id = db.create_job("ch1", "topic")
        db.update_job_status(job_id, "research")
        assert db.get_job(job_id)["status"] == "research"

    def test_block_job(self, db):
        job_id = db.create_job("ch1", "topic")
        db.update_job_status(job_id, "research")
        db.block_job(job_id, "research", "Test block reason")
        job = db.get_job(job_id)
        assert job["status"] == "blocked"
        assert job["blocked_reason"] == "Test block reason"
        assert job["blocked_phase"] == "research"

    def test_get_nonexistent_job(self, db):
        assert db.get_job("nonexistent_id") is None

    def test_get_active_jobs(self, db):
        id1 = db.create_job("ch1", "active topic")
        id2 = db.create_job("ch1", "another topic")
        db.update_job_status(id2, "research")
        active = db.get_active_jobs()
        active_ids = [j["id"] for j in active]
        assert id1 in active_ids
        assert id2 in active_ids

    def test_active_jobs_excludes_terminal(self, db):
        id1 = db.create_job("ch1", "topic")
        db.update_job_status(id1, "published")
        active = db.get_active_jobs()
        assert all(j["id"] != id1 for j in active)


class TestSceneCRUD:
    def test_save_and_get_scenes(self, db):
        job_id = db.create_job("ch1", "topic")
        scenes = [
            {"narration_text": "Scene one", "duration_seconds": 10,
             "visual_prompt": "A desert landscape"},
            {"narration_text": "Scene two", "duration_seconds": 8,
             "visual_prompt": "An ancient city"},
        ]
        db.save_scenes(job_id, scenes)
        result = db.get_scenes(job_id)
        assert len(result) == 2
        assert result[0]["narration_text"] == "Scene one"
        assert result[1]["scene_index"] == 1

    def test_update_scene_asset(self, db):
        job_id = db.create_job("ch1", "topic")
        db.save_scenes(job_id, [
            {"narration_text": "test", "duration_seconds": 5,
             "visual_prompt": "prompt"},
        ])
        db.update_scene_asset(job_id, 0, image_path="/path/to/image.png")
        scene = db.get_scenes(job_id)[0]
        assert scene["image_path"] == "/path/to/image.png"

    def test_scenes_ordered_by_index(self, db):
        job_id = db.create_job("ch1", "topic")
        scenes = [
            {"narration_text": f"Scene {i}", "duration_seconds": 5,
             "visual_prompt": f"prompt {i}"}
            for i in range(5)
        ]
        db.save_scenes(job_id, scenes)
        result = db.get_scenes(job_id)
        for i, s in enumerate(result):
            assert s["scene_index"] == i


class TestRubricStorage:
    def test_save_and_get_rubric(self, db):
        job_id = db.create_job("ch1", "topic")
        db.save_rubric(
            job_id=job_id, scene_index=0, asset_type="image",
            check_phase="phase6a", attempt=1,
            deterministic={"text_detected": False, "nsfw_score": 0.01},
            rubric_scores={"semantic_match": {"score": 8.5, "reasoning": "Good", "confidence": "high"}},
            weighted_score=8.5, verdict="pass", flags=[],
            model="qwen3.5:27b", inference_ms=1200
        )
        rubrics = db.get_rubrics(job_id)
        assert len(rubrics) == 1
        assert rubrics[0]["weighted_score"] == 8.5
        assert rubrics[0]["final_verdict"] == "pass"

    def test_rubric_filtering(self, db):
        job_id = db.create_job("ch1", "topic")
        for i in range(3):
            db.save_rubric(
                job_id=job_id, scene_index=i, asset_type="image",
                check_phase="phase6a", attempt=1,
                deterministic={}, rubric_scores={},
                weighted_score=7.0 + i, verdict="pass", flags=[]
            )
        db.save_rubric(
            job_id=job_id, scene_index=0, asset_type="video",
            check_phase="phase6b", attempt=1,
            deterministic={}, rubric_scores={},
            weighted_score=8.0, verdict="pass", flags=[]
        )
        image_rubrics = db.get_rubrics(job_id, asset_type="image")
        assert len(image_rubrics) == 3
        scene0 = db.get_rubrics(job_id, scene_index=0)
        assert len(scene0) == 2  # image + video

    def test_rubric_stats(self, db):
        job_id = db.create_job("ch1", "topic")
        for i in range(5):
            db.save_rubric(
                job_id=job_id, scene_index=i, asset_type="image",
                check_phase="phase6a", attempt=1,
                deterministic={}, rubric_scores={},
                weighted_score=7.0 + i * 0.5,
                verdict="pass" if i > 0 else "regen_adjust",
                flags=[]
            )
        stats = db.get_rubric_stats(job_id)
        assert len(stats) >= 1
        img_stat = [s for s in stats if s["asset_type"] == "image"][0]
        assert img_stat["total"] == 5
        assert img_stat["pass_count"] == 4


class TestAnalytics:
    def test_save_analytics(self, db):
        job_id = db.create_job("ch1", "topic")
        db.save_analytics(job_id, "24h", {
            "video_id": "abc123", "views": 1500,
            "watch_hours": 45.2, "avg_duration": 320,
            "avg_percentage": 55.0, "likes": 120, "comments": 30,
            "shares": 15, "impressions": 10000, "ctr": 5.2,
            "revenue": 12.50, "rpm": 8.33,
            "retention_curve": [100, 90, 80, 70],
            "countries": {"IQ": 40, "SA": 25, "EG": 15},
        })
        # Verify it was saved (no exception means success)


class TestConcurrentAccess:
    def test_concurrent_reads(self, db):
        job_id = db.create_job("ch1", "topic")
        errors = []

        def read_job():
            try:
                job = db.get_job(job_id)
                assert job is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_job) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_writes(self):
        """Test concurrent writes with separate connections (WAL mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db1 = FactoryDB(db_path)
            errors = []

            def create_jobs(prefix):
                try:
                    db_local = FactoryDB(db_path)
                    for i in range(5):
                        db_local.create_job("ch1", f"{prefix}_topic_{i}")
                    db_local.close()
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=create_jobs, args=(f"t{i}",))
                for i in range(3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert len(errors) == 0
            db1.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
