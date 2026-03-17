"""
Keeps all versions of regenerated assets.
Supports rollback — user can say "go back to version 1".

Naming: scene_{idx}_v{attempt}.{ext}
Final pointer: scene_{idx}_final.{ext} (symlink or copy on Windows)

DB table: asset_versions (already in FactoryDB schema).
"""

import os
import shutil
import logging
import platform
from pathlib import Path
from typing import Optional

from src.core.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


class AssetVersioner:
    """
    Every time an asset is generated or regenerated:
    1. Save with version suffix: scene_{idx}_v{attempt}.{ext}
    2. Update 'final' pointer to point to latest/best version
    3. Record version metadata in DB

    On Windows, symlinks require privileges, so we fall back to file copy
    for the 'final' pointer.
    """

    def __init__(self, db, event_bus: Optional[EventBus] = None):
        """
        Args:
            db: FactoryDB instance.
            event_bus: For emitting versioning events.
        """
        self.db = db
        self.event_bus = event_bus
        self._use_symlinks = self._check_symlink_support()
        logger.info(
            f"AssetVersioner initialized (symlinks={'yes' if self._use_symlinks else 'no, using copy'})"
        )

    def save_version(self, job_id: str, scene_index: int, asset_type: str,
                     file_path: str, qa_score: float = None,
                     reason: str = "initial", prompt: str = None) -> int:
        """
        Save new version of an asset. Returns version number.

        Deactivates previous versions, activates this one,
        and creates/updates the 'final' pointer.

        Args:
            job_id: Job ID.
            scene_index: Scene index (0-based).
            asset_type: 'image', 'video', 'voice', 'music', 'sfx'.
            file_path: Path to the generated file.
            qa_score: QA rubric score (if available).
            reason: Why this version was created.
            prompt: The prompt used to generate this version.

        Returns:
            The new version number.
        """
        # Get next version number
        row = self.db.conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM asset_versions "
            "WHERE job_id = ? AND scene_index = ? AND asset_type = ?",
            (job_id, scene_index, asset_type)
        ).fetchone()
        new_version = row[0] + 1

        # Build versioned path
        versioned_path = self._version_path(file_path, new_version)

        # Copy/move file to versioned path
        Path(versioned_path).parent.mkdir(parents=True, exist_ok=True)
        if os.path.abspath(file_path) != os.path.abspath(versioned_path):
            shutil.copy2(file_path, versioned_path)

        file_size = os.path.getsize(versioned_path)

        # Deactivate old versions
        self.db.conn.execute(
            "UPDATE asset_versions SET is_active = FALSE "
            "WHERE job_id = ? AND scene_index = ? AND asset_type = ?",
            (job_id, scene_index, asset_type)
        )

        # Insert new version
        self.db.conn.execute("""
            INSERT INTO asset_versions
                (job_id, scene_index, asset_type, version, file_path,
                 file_size_bytes, qa_score, is_active, creation_reason, prompt_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, ?, ?)
        """, (job_id, scene_index, asset_type, new_version,
              versioned_path, file_size, qa_score, reason, prompt))

        self.db.conn.commit()

        # Update 'final' pointer
        final_path = self._final_path(file_path)
        self._update_final_pointer(final_path, versioned_path)

        if self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.ASSET_VERSIONED,
                job_id=job_id,
                data={
                    "scene_index": scene_index,
                    "asset_type": asset_type,
                    "version": new_version,
                    "reason": reason,
                    "file_path": versioned_path,
                    "file_size": file_size,
                },
                source="asset_versioner",
            ))

        logger.info(
            f"Asset versioned: {job_id}/scene_{scene_index}/{asset_type} "
            f"v{new_version} ({reason})"
        )
        return new_version

    def rollback(self, job_id: str, scene_index: int, asset_type: str,
                 to_version: int) -> str:
        """
        Rollback to a previous version.
        Called when user says "use the first image".

        Returns: path to restored version.
        """
        # Verify target version exists
        row = self.db.conn.execute(
            "SELECT file_path FROM asset_versions "
            "WHERE job_id = ? AND scene_index = ? AND asset_type = ? AND version = ?",
            (job_id, scene_index, asset_type, to_version)
        ).fetchone()

        if not row:
            raise ValueError(
                f"Version {to_version} not found for "
                f"{job_id}/scene_{scene_index}/{asset_type}"
            )

        target_path = row["file_path"]
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Version file missing: {target_path}")

        # Deactivate all versions
        self.db.conn.execute(
            "UPDATE asset_versions SET is_active = FALSE "
            "WHERE job_id = ? AND scene_index = ? AND asset_type = ?",
            (job_id, scene_index, asset_type)
        )

        # Activate target version
        self.db.conn.execute(
            "UPDATE asset_versions SET is_active = TRUE "
            "WHERE job_id = ? AND scene_index = ? AND asset_type = ? AND version = ?",
            (job_id, scene_index, asset_type, to_version)
        )

        # Update final pointer
        final_path = self._final_path(target_path)
        self._update_final_pointer(final_path, target_path)

        self.db.conn.commit()

        if self.event_bus:
            self.event_bus.emit(Event(
                type=EventType.ASSET_ROLLED_BACK,
                job_id=job_id,
                data={
                    "scene_index": scene_index,
                    "asset_type": asset_type,
                    "rolled_back_to": to_version,
                },
                source="asset_versioner",
            ))

        logger.info(
            f"Asset rolled back: {job_id}/scene_{scene_index}/{asset_type} → v{to_version}"
        )
        return target_path

    def get_versions(self, job_id: str, scene_index: int,
                     asset_type: str) -> list[dict]:
        """Get all versions for an asset — for Telegram display."""
        rows = self.db.conn.execute("""
            SELECT * FROM asset_versions
            WHERE job_id = ? AND scene_index = ? AND asset_type = ?
            ORDER BY version ASC
        """, (job_id, scene_index, asset_type)).fetchall()
        return [dict(r) for r in rows]

    def get_active_version(self, job_id: str, scene_index: int,
                           asset_type: str) -> Optional[dict]:
        """Get the currently active version."""
        row = self.db.conn.execute("""
            SELECT * FROM asset_versions
            WHERE job_id = ? AND scene_index = ? AND asset_type = ?
            AND is_active = TRUE
        """, (job_id, scene_index, asset_type)).fetchone()
        return dict(row) if row else None

    def get_job_asset_summary(self, job_id: str) -> list[dict]:
        """Get summary of all asset versions for a job."""
        rows = self.db.conn.execute("""
            SELECT scene_index, asset_type,
                   COUNT(*) as total_versions,
                   MAX(version) as latest_version,
                   SUM(file_size_bytes) as total_size_bytes,
                   MAX(CASE WHEN is_active THEN version END) as active_version
            FROM asset_versions
            WHERE job_id = ?
            GROUP BY scene_index, asset_type
            ORDER BY scene_index, asset_type
        """, (job_id,)).fetchall()
        return [dict(r) for r in rows]

    # ─── Private Helpers ───────────────────────────────

    def _version_path(self, original_path: str, version: int) -> str:
        """Convert path to versioned: scene_001.png → scene_001_v1.png"""
        p = Path(original_path)
        stem = p.stem
        # Remove existing version suffix if present
        if "_v" in stem:
            stem = stem[:stem.rfind("_v")]
        # Remove "_final" suffix if present
        if stem.endswith("_final"):
            stem = stem[:-6]
        return str(p.parent / f"{stem}_v{version}{p.suffix}")

    def _final_path(self, original_path: str) -> str:
        """Convert path to final: scene_001_v2.png → scene_001_final.png"""
        p = Path(original_path)
        stem = p.stem
        if "_v" in stem:
            stem = stem[:stem.rfind("_v")]
        if stem.endswith("_final"):
            stem = stem[:-6]
        return str(p.parent / f"{stem}_final{p.suffix}")

    def _update_final_pointer(self, final_path: str, target_path: str):
        """Create/update the 'final' pointer (symlink or copy)."""
        try:
            if os.path.exists(final_path) or os.path.islink(final_path):
                os.remove(final_path)

            if self._use_symlinks:
                os.symlink(os.path.abspath(target_path), final_path)
            else:
                shutil.copy2(target_path, final_path)
        except Exception as e:
            logger.warning(f"Failed to update final pointer: {e}, using copy")
            if os.path.exists(final_path):
                os.remove(final_path)
            shutil.copy2(target_path, final_path)

    def _check_symlink_support(self) -> bool:
        """Check if the OS supports symlinks without special privileges."""
        if platform.system() != "Windows":
            return True
        # On Windows, try creating a test symlink
        try:
            import tempfile
            test_src = tempfile.mktemp()
            test_link = tempfile.mktemp()
            with open(test_src, "w") as f:
                f.write("test")
            os.symlink(test_src, test_link)
            os.remove(test_link)
            os.remove(test_src)
            return True
        except (OSError, NotImplementedError):
            return False
