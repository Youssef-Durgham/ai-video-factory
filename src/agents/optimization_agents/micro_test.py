"""
Micro Test Agent — Hook testing before publish.
Tests different intros/hooks with a small audience before full publish.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from src.core.database import FactoryDB
from src.core import llm

logger = logging.getLogger(__name__)

TEST_DURATION_HOURS = 2
MIN_VIEWS_FOR_SIGNIFICANCE = 100
CTR_SIGNIFICANCE_DELTA = 0.02  # 2% CTR difference = significant


class MicroTest:
    """
    Runs A/B-style tests on video hooks/intros before full publish.
    Uploads as unlisted, shares with test audience, picks winner.
    """

    def __init__(self, db: FactoryDB, youtube_api=None, telegram_bot=None):
        self.db = db
        self.youtube = youtube_api
        self.telegram = telegram_bot

    def run(self, job_id: str, variants: list[dict]) -> dict:
        """
        Run a micro-test with multiple hook variants.

        Args:
            job_id: Job being tested.
            variants: List of {"variant_id": str, "title": str, "thumbnail_path": str}

        Returns: {"winner": variant_id, "results": [...]}
        """
        if len(variants) < 2:
            logger.info(f"Need at least 2 variants for micro-test, got {len(variants)}")
            return {"winner": variants[0]["variant_id"] if variants else None, "results": []}

        # Upload variants as unlisted
        test_ids = self._upload_variants(job_id, variants)
        if not test_ids:
            return {"winner": variants[0]["variant_id"], "results": []}

        # Wait for test period
        logger.info(f"Micro-test started for {job_id}: {len(test_ids)} variants, waiting {TEST_DURATION_HOURS}h")
        self._notify_test_start(job_id, variants)

        # Save test record
        self._save_test(job_id, test_ids, variants)

        return {
            "status": "running",
            "test_ids": test_ids,
            "check_after_hours": TEST_DURATION_HOURS,
        }

    def check_results(self, job_id: str) -> dict:
        """
        Check micro-test results after the test period.

        Returns: {"winner": variant_id, "results": [...]}
        """
        test = self._get_test(job_id)
        if not test:
            return {"status": "no_test"}

        test_ids = json.loads(test.get("test_video_ids", "[]"))
        variants = json.loads(test.get("variants", "[]"))

        results = []
        for i, test_vid_id in enumerate(test_ids):
            metrics = self._get_video_metrics(test_vid_id)
            variant_id = variants[i]["variant_id"] if i < len(variants) else f"v{i}"
            results.append({
                "variant_id": variant_id,
                "youtube_id": test_vid_id,
                "views": metrics.get("views", 0),
                "ctr": metrics.get("ctr", 0),
                "avg_watch_pct": metrics.get("avg_watch_pct", 0),
                "impressions": metrics.get("impressions", 0),
            })

        # Pick winner
        winner = self._pick_winner(results)

        # Clean up losers
        self._cleanup_losers(test_ids, winner, results)

        # Save results
        self._save_results(job_id, winner, results)

        logger.info(f"Micro-test results for {job_id}: winner={winner}")
        return {"winner": winner, "results": results}

    def generate_variants(self, job_id: str) -> list[dict]:
        """Generate hook/title variants for testing using LLM."""
        job = self._get_job(job_id)
        if not job:
            return []

        prompt = f"""Generate 3 different title + hook variations for this Arabic documentary video.

Topic: {job.get('topic', '')}
Original title: {job.get('title', job.get('topic', ''))}

Each variant should take a different angle:
1. Curiosity-driven (question or mystery)
2. Shock/fact-driven (surprising statistic or revelation)
3. Story-driven (personal/narrative hook)

Return JSON array: [{{
    "variant_id": "v1",
    "title": "Arabic title",
    "hook_approach": "curiosity|shock|story",
    "hook_text": "First 2 sentences of script"
}}]"""

        try:
            variants = llm.generate_json(prompt, temperature=0.7)
            if isinstance(variants, dict):
                variants = variants.get("variants", [variants])
            return variants if isinstance(variants, list) else [variants]
        except Exception as e:
            logger.warning(f"Variant generation failed: {e}")
            return []

    def _pick_winner(self, results: list[dict]) -> Optional[str]:
        """Pick the winning variant based on metrics."""
        if not results:
            return None

        # Score: 60% CTR + 40% watch time
        for r in results:
            r["score"] = r.get("ctr", 0) * 0.6 + r.get("avg_watch_pct", 0) * 0.004

        best = max(results, key=lambda x: x.get("score", 0))
        return best.get("variant_id")

    def _upload_variants(self, job_id: str, variants: list[dict]) -> list[str]:
        """Upload variant videos as unlisted."""
        if not self.youtube:
            logger.info(f"[DRY RUN] Would upload {len(variants)} test variants")
            return [f"test_{v['variant_id']}" for v in variants]

        test_ids = []
        for v in variants:
            try:
                # Simplified — actual upload would use resumable upload
                response = self.youtube.videos().insert(
                    part="snippet,status",
                    body={
                        "snippet": {
                            "title": v.get("title", "Test"),
                            "description": "Micro-test — will be removed",
                            "defaultLanguage": "ar",
                        },
                        "status": {
                            "privacyStatus": "unlisted",
                            "selfDeclaredMadeForKids": False,
                        },
                    },
                ).execute()
                test_ids.append(response["id"])
            except Exception as e:
                logger.error(f"Failed to upload test variant: {e}")

        return test_ids

    def _get_video_metrics(self, video_id: str) -> dict:
        """Get metrics for a test video."""
        if not self.youtube:
            return {"views": 0, "ctr": 0, "avg_watch_pct": 0, "impressions": 0}

        try:
            stats = self.youtube.videos().list(
                part="statistics", id=video_id
            ).execute()
            if stats.get("items"):
                s = stats["items"][0]["statistics"]
                return {
                    "views": int(s.get("viewCount", 0)),
                    "impressions": 0,  # Requires Analytics API
                    "ctr": 0,
                    "avg_watch_pct": 0,
                }
        except Exception:
            pass
        return {"views": 0, "ctr": 0, "avg_watch_pct": 0, "impressions": 0}

    def _cleanup_losers(self, test_ids: list[str], winner_variant: str, results: list[dict]):
        """Delete losing test videos."""
        if not self.youtube:
            return
        winner_yt_id = None
        for r in results:
            if r.get("variant_id") == winner_variant:
                winner_yt_id = r.get("youtube_id")
                break

        for vid_id in test_ids:
            if vid_id != winner_yt_id:
                try:
                    self.youtube.videos().delete(id=vid_id).execute()
                    logger.info(f"Deleted test video {vid_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete test video: {e}")

    def _get_job(self, job_id: str) -> Optional[dict]:
        try:
            row = self.db.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _save_test(self, job_id: str, test_ids: list[str], variants: list[dict]):
        try:
            self.db.conn.execute("""
                INSERT INTO micro_tests (job_id, test_video_ids, variants, status, created_at)
                VALUES (?, ?, ?, 'running', ?)
            """, (job_id, json.dumps(test_ids), json.dumps(variants, ensure_ascii=False),
                  datetime.now().isoformat()))
            self.db.conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save micro-test: {e}")

    def _get_test(self, job_id: str) -> Optional[dict]:
        try:
            row = self.db.conn.execute(
                "SELECT * FROM micro_tests WHERE job_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _save_results(self, job_id: str, winner: str, results: list[dict]):
        try:
            self.db.conn.execute("""
                UPDATE micro_tests SET status = 'completed', winner = ?,
                       results = ?, completed_at = ?
                WHERE job_id = ?
            """, (winner, json.dumps(results), datetime.now().isoformat(), job_id))
            self.db.conn.commit()
        except Exception:
            pass

    def _notify_test_start(self, job_id: str, variants: list[dict]):
        if not self.telegram:
            return
        lines = [f"🧪 <b>Micro-test started</b> — {job_id}\n"]
        for v in variants:
            lines.append(f"  • {v.get('variant_id', '?')}: {v.get('title', '?')[:60]}")
        lines.append(f"\nResults in {TEST_DURATION_HOURS}h")
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self.telegram.send("\n".join(lines)))
        except Exception:
            pass
