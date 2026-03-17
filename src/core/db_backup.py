"""
SQLite backup strategy.
DB corruption = EVERYTHING lost (jobs, scenes, rubrics, analytics, events, versions).

4-level backup:
1. WAL checkpoint (5 min) — prevents WAL growth
2. Hot backup (hourly) — sqlite3 backup API
3. Daily snapshot (2 AM) — VACUUM + compress + integrity check
4. Off-site (optional) — external drive / cloud

Recovery: auto-detect corruption on startup, restore from latest valid backup.
"""

import os
import glob
import shutil
import sqlite3
import subprocess
import platform
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseBackup:
    """
    Multi-level backup strategy for factory.db.

    Scheduled via FactoryScheduler:
    - wal_checkpoint: every 5 min
    - hot_backup: every 1 hour
    - daily_snapshot: daily at 2:00 AM
    """

    def __init__(self, db_path: str, backup_dir: str = "backups",
                 telegram=None):
        """
        Args:
            db_path: Path to the live database file.
            backup_dir: Root directory for backups.
            telegram: TelegramBot for alerts.
        """
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.telegram = telegram

        # Create backup directories
        os.makedirs(os.path.join(backup_dir, "hourly"), exist_ok=True)
        os.makedirs(os.path.join(backup_dir, "daily"), exist_ok=True)
        logger.info(f"DatabaseBackup initialized: {db_path} → {backup_dir}")

    def wal_checkpoint(self):
        """
        Level 1: WAL checkpoint (every 5 min via scheduler).
        Ensures WAL file doesn't grow unbounded.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            conn.close()
            logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.error(f"WAL checkpoint failed: {e}")

    def hot_backup(self):
        """
        Level 2: Hourly hot backup using sqlite3 backup API.
        Safe — no locking needed, works while DB is in use.
        Keeps last 48 hourly backups (2 days).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H")
        backup_path = os.path.join(
            self.backup_dir, "hourly", f"factory_{timestamp}.db"
        )

        try:
            src = sqlite3.connect(self.db_path)
            dst = sqlite3.connect(backup_path)
            src.backup(dst)
            dst.close()
            src.close()

            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            self._rotate_backups(
                os.path.join(self.backup_dir, "hourly"), keep=48
            )
            logger.info(f"Hourly backup: {backup_path} ({size_mb:.1f}MB)")

        except Exception as e:
            logger.error(f"Hot backup failed: {e}")
            if self.telegram:
                self._alert(f"⚠️ Hourly backup failed: {e}")

    def daily_snapshot(self):
        """
        Level 3: Daily snapshot with VACUUM + compress + integrity check.
        Keeps last 30 daily backups.
        """
        timestamp = datetime.now().strftime("%Y%m%d")
        snapshot_path = os.path.join(
            self.backup_dir, "daily", f"factory_{timestamp}.db"
        )

        try:
            # Backup using sqlite3 API
            src = sqlite3.connect(self.db_path)
            dst = sqlite3.connect(snapshot_path)
            src.backup(dst)

            # VACUUM the backup (not the live DB — avoids locking)
            dst.execute("VACUUM")

            # Integrity check
            result = dst.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                logger.error(f"Integrity check FAILED on daily backup: {result}")
                if self.telegram:
                    self._alert(
                        f"🚨 DB integrity check FAILED on daily backup: {result[0]}"
                    )
                dst.close()
                src.close()
                os.remove(snapshot_path)
                return

            dst.close()
            src.close()

            # Compress (try zstd, fall back to gzip)
            compressed_path = self._compress(snapshot_path)

            # Rotate
            self._rotate_backups(
                os.path.join(self.backup_dir, "daily"), keep=30
            )

            size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
            logger.info(f"Daily snapshot: {compressed_path} ({size_mb:.1f}MB)")

        except Exception as e:
            logger.error(f"Daily snapshot failed: {e}")
            if self.telegram:
                self._alert(f"🚨 Daily snapshot failed: {e}")

    def check_and_recover(self) -> bool:
        """
        Run on startup. Returns True if DB is healthy.
        If corrupt → auto-recover from latest backup.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()

            if result[0] == "ok":
                logger.info("Database integrity check passed")
                return True

            logger.error(f"DB CORRUPT: {result[0]}")
            if self.telegram:
                self._alert("🚨 DATABASE CORRUPTION DETECTED — auto-recovering...")

            return self._recover_from_backup()

        except Exception as e:
            logger.error(f"DB unreadable: {e}")
            if self.telegram:
                self._alert(f"🚨 Database unreadable: {e} — auto-recovering...")
            return self._recover_from_backup()

    def _recover_from_backup(self) -> bool:
        """Find latest valid backup and restore."""
        # Try hourly backups first (most recent)
        hourly_dir = os.path.join(self.backup_dir, "hourly")
        for backup in sorted(
            glob.glob(os.path.join(hourly_dir, "*.db")),
            key=os.path.getmtime, reverse=True
        ):
            if self._try_restore(backup):
                return True

        # Try daily snapshots (decompress first)
        daily_dir = os.path.join(self.backup_dir, "daily")

        # Try .db files first
        for backup in sorted(
            glob.glob(os.path.join(daily_dir, "*.db")),
            key=os.path.getmtime, reverse=True
        ):
            if self._try_restore(backup):
                return True

        # Try compressed files
        for ext in ("*.db.zst", "*.db.gz"):
            for backup in sorted(
                glob.glob(os.path.join(daily_dir, ext)),
                key=os.path.getmtime, reverse=True
            ):
                decompressed = self._decompress(backup)
                if decompressed and self._try_restore(decompressed):
                    # Clean up decompressed temp file
                    if decompressed != backup:
                        os.remove(decompressed)
                    return True
                if decompressed and decompressed != backup:
                    os.remove(decompressed)

        # No valid backup found
        logger.critical("No valid backup found. Database unrecoverable.")
        if self.telegram:
            self._alert(
                "🚨🚨 CRITICAL: No valid backup found. "
                "Database unrecoverable. Manual intervention required."
            )
        return False

    def _try_restore(self, backup_path: str) -> bool:
        """Try to restore from a specific backup. Returns True on success."""
        try:
            conn = sqlite3.connect(backup_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()

            if result[0] != "ok":
                return False

            # Valid backup — restore
            # Keep the corrupt DB for forensics
            corrupt_path = f"{self.db_path}.corrupt.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists(self.db_path):
                shutil.copy2(self.db_path, corrupt_path)

            shutil.copy2(backup_path, self.db_path)

            # Remove WAL/SHM files from corrupted state
            for ext in ("-wal", "-shm"):
                wal_path = self.db_path + ext
                if os.path.exists(wal_path):
                    os.remove(wal_path)

            logger.info(f"DB recovered from: {os.path.basename(backup_path)}")
            if self.telegram:
                self._alert(
                    f"✅ DB recovered from: {os.path.basename(backup_path)}\n"
                    f"Some recent data may be lost."
                )
            return True

        except Exception as e:
            logger.warning(f"Backup {backup_path} unusable: {e}")
            return False

    def _compress(self, file_path: str) -> str:
        """Compress a file with zstd (preferred) or gzip (fallback)."""
        # Try zstd
        try:
            compressed = f"{file_path}.zst"
            result = subprocess.run(
                ["zstd", "-19", "--rm", file_path, "-o", compressed],
                capture_output=True, timeout=300
            )
            if result.returncode == 0:
                return compressed
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback to Python gzip
        import gzip
        compressed = f"{file_path}.gz"
        with open(file_path, "rb") as f_in:
            with gzip.open(compressed, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(file_path)
        return compressed

    def _decompress(self, file_path: str) -> Optional[str]:
        """Decompress a .zst or .gz file. Returns path to decompressed file."""
        try:
            if file_path.endswith(".zst"):
                decompressed = file_path[:-4]  # Remove .zst
                try:
                    subprocess.run(
                        ["zstd", "-d", file_path, "-o", decompressed, "--keep"],
                        capture_output=True, check=True, timeout=120
                    )
                    return decompressed
                except (FileNotFoundError, subprocess.CalledProcessError):
                    # Try Python zstandard if available
                    try:
                        import zstandard
                        with open(file_path, "rb") as f_in:
                            dctx = zstandard.ZstdDecompressor()
                            with open(decompressed, "wb") as f_out:
                                dctx.copy_stream(f_in, f_out)
                        return decompressed
                    except ImportError:
                        return None

            elif file_path.endswith(".gz"):
                import gzip
                decompressed = file_path[:-3]  # Remove .gz
                with gzip.open(file_path, "rb") as f_in:
                    with open(decompressed, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                return decompressed

        except Exception as e:
            logger.error(f"Decompress failed for {file_path}: {e}")
        return None

    def _rotate_backups(self, directory: str, keep: int):
        """Delete oldest backups, keep last N."""
        all_files = sorted(
            glob.glob(os.path.join(directory, "*")),
            key=os.path.getmtime
        )
        while len(all_files) > keep:
            oldest = all_files.pop(0)
            try:
                os.remove(oldest)
                logger.debug(f"Rotated backup: {oldest}")
            except Exception as e:
                logger.warning(f"Failed to rotate {oldest}: {e}")

    def _alert(self, message: str):
        """Send alert via Telegram (fire-and-forget)."""
        if not self.telegram:
            return
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                self.telegram.alert(message)
            )
        except Exception:
            # Don't let alert failures break backup logic
            pass
