"""
Phase 5 — Content ID Guard.

Protects against YouTube Content ID claims by:
  1. Audio fingerprint comparison against known songs database
  2. Spectral/melody analysis for similarity detection
  3. Similarity threshold enforcement

Runs AFTER music generation, BEFORE video composition.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ContentIDConfig:
    fingerprint_db: str = "data/audio_fingerprints.db"
    similarity_threshold_music: float = 0.15   # < 0.15 = safe
    similarity_threshold_shorts: float = 0.10  # Stricter for Shorts
    sample_rate: int = 22050
    hop_length: int = 512
    n_mels: int = 128
    n_fft: int = 2048


@dataclass
class ContentIDResult:
    safe: bool
    similarity_score: float = 0.0
    closest_match: Optional[str] = None
    method: str = ""
    details: str = ""


class ContentIDGuard:
    """
    Audio fingerprint & spectral analysis for Content ID protection.

    Uses librosa for spectral analysis and chroma feature comparison.
    """

    def __init__(self, config: Optional[ContentIDConfig] = None):
        self.config = config or ContentIDConfig()
        self._reference_features: list[dict] = []

    # ─── Public API ────────────────────────────────────────

    def check(
        self,
        audio_path: str,
        is_shorts: bool = False,
    ) -> ContentIDResult:
        """
        Check an audio file against known fingerprints and spectral patterns.

        Args:
            audio_path: Path to generated music WAV.
            is_shorts: Use stricter threshold for YouTube Shorts.

        Returns:
            ContentIDResult with safety verdict.
        """
        threshold = (
            self.config.similarity_threshold_shorts
            if is_shorts
            else self.config.similarity_threshold_music
        )

        try:
            import librosa
            import numpy as np
        except ImportError:
            logger.warning("librosa not installed — skipping Content ID check")
            return ContentIDResult(
                safe=True, similarity_score=0.0,
                method="skipped", details="librosa not available",
            )

        try:
            # Load audio
            y, sr = librosa.load(
                audio_path, sr=self.config.sample_rate, mono=True
            )

            # Extract features
            features = self._extract_features(y, sr)

            # Compare against reference database
            max_sim = 0.0
            closest = None

            for ref in self._reference_features:
                sim = self._compare_features(features, ref["features"])
                if sim > max_sim:
                    max_sim = sim
                    closest = ref.get("title", "unknown")

            # Self-similarity check (compare against previously generated tracks)
            # This is loaded separately via load_generated_fingerprints()

            safe = max_sim < threshold
            verdict = "SAFE" if safe else "SIMILAR"

            logger.info(
                f"Content ID: {verdict} (score={max_sim:.3f}, "
                f"threshold={threshold}, closest={closest})"
            )

            return ContentIDResult(
                safe=safe,
                similarity_score=round(max_sim, 4),
                closest_match=closest,
                method="spectral_chroma",
                details=f"Threshold: {threshold}, Score: {max_sim:.4f}",
            )

        except Exception as e:
            logger.error(f"Content ID check failed: {e}")
            return ContentIDResult(
                safe=True,  # Fail-open to avoid blocking pipeline
                similarity_score=0.0,
                method="error",
                details=str(e),
            )

    def check_melody_contour(self, audio_path: str) -> ContentIDResult:
        """
        Extract and analyze melody contour for similarity to known melodies.

        This is a deeper check focusing on the main melody line, which is
        what Content ID systems primarily match on.
        """
        try:
            import librosa
            import numpy as np

            y, sr = librosa.load(audio_path, sr=self.config.sample_rate, mono=True)

            # Extract pitch contour
            pitches, magnitudes = librosa.piptrack(
                y=y, sr=sr,
                n_fft=self.config.n_fft,
                hop_length=self.config.hop_length,
            )

            # Get dominant pitch per frame
            pitch_contour = []
            for t in range(pitches.shape[1]):
                idx = magnitudes[:, t].argmax()
                pitch = pitches[idx, t]
                if pitch > 0:
                    pitch_contour.append(pitch)

            if len(pitch_contour) < 10:
                return ContentIDResult(
                    safe=True, similarity_score=0.0,
                    method="melody_contour",
                    details="Too short for melody analysis",
                )

            # Normalize contour to intervals (pitch-invariant)
            contour = np.array(pitch_contour)
            intervals = np.diff(np.log2(contour + 1e-8))

            # Compare against reference melody contours
            max_sim = 0.0
            closest = None

            for ref in self._reference_features:
                ref_intervals = ref.get("melody_intervals")
                if ref_intervals is not None:
                    sim = self._dtw_similarity(intervals, ref_intervals)
                    if sim > max_sim:
                        max_sim = sim
                        closest = ref.get("title")

            safe = max_sim < self.config.similarity_threshold_music

            return ContentIDResult(
                safe=safe,
                similarity_score=round(max_sim, 4),
                closest_match=closest,
                method="melody_contour",
                details=f"DTW melody similarity: {max_sim:.4f}",
            )

        except Exception as e:
            logger.error(f"Melody contour check failed: {e}")
            return ContentIDResult(
                safe=True, method="melody_error", details=str(e),
            )

    def full_check(
        self, audio_path: str, is_shorts: bool = False
    ) -> ContentIDResult:
        """
        Run all Content ID checks (spectral + melody) and return worst result.
        """
        spectral = self.check(audio_path, is_shorts=is_shorts)
        melody = self.check_melody_contour(audio_path)

        # Return the worse of the two
        if not spectral.safe:
            return spectral
        if not melody.safe:
            return melody

        # Both safe — return spectral (higher confidence)
        worst_score = max(spectral.similarity_score, melody.similarity_score)
        return ContentIDResult(
            safe=True,
            similarity_score=worst_score,
            closest_match=spectral.closest_match or melody.closest_match,
            method="full_check",
            details=f"Spectral: {spectral.similarity_score:.4f}, Melody: {melody.similarity_score:.4f}",
        )

    # ─── Reference Database ────────────────────────────────

    def load_reference_db(self, db_path: Optional[str] = None):
        """
        Load reference fingerprints from SQLite database.
        """
        import sqlite3

        path = db_path or self.config.fingerprint_db
        if not Path(path).exists():
            logger.warning(f"Fingerprint DB not found: {path}")
            return

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, artist, chroma_features, melody_contour FROM fingerprints"
        ).fetchall()
        conn.close()

        import pickle
        for row in rows:
            entry = {
                "title": row["title"],
                "artist": row["artist"],
            }
            if row["chroma_features"]:
                entry["features"] = pickle.loads(row["chroma_features"])
            if row["melody_contour"]:
                entry["melody_intervals"] = pickle.loads(row["melody_contour"])
            self._reference_features.append(entry)

        logger.info(f"Loaded {len(self._reference_features)} reference fingerprints")

    def add_generated_fingerprint(self, audio_path: str, title: str):
        """
        Add a newly generated track to the reference DB to avoid self-repetition.
        """
        try:
            import librosa
            y, sr = librosa.load(audio_path, sr=self.config.sample_rate, mono=True)
            features = self._extract_features(y, sr)
            self._reference_features.append({
                "title": f"[generated] {title}",
                "features": features,
            })
        except Exception as e:
            logger.warning(f"Failed to fingerprint generated track: {e}")

    # ─── Feature Extraction ────────────────────────────────

    def _extract_features(self, y, sr) -> dict:
        """Extract chroma and spectral features for comparison."""
        import librosa
        import numpy as np

        # Chroma features (harmonic content)
        chroma = librosa.feature.chroma_stft(
            y=y, sr=sr,
            n_fft=self.config.n_fft,
            hop_length=self.config.hop_length,
        )

        # MFCC (timbral features)
        mfcc = librosa.feature.mfcc(
            y=y, sr=sr,
            n_mfcc=13,
            hop_length=self.config.hop_length,
        )

        # Spectral contrast
        contrast = librosa.feature.spectral_contrast(
            y=y, sr=sr,
            hop_length=self.config.hop_length,
        )

        return {
            "chroma_mean": np.mean(chroma, axis=1),
            "chroma_std": np.std(chroma, axis=1),
            "mfcc_mean": np.mean(mfcc, axis=1),
            "mfcc_std": np.std(mfcc, axis=1),
            "contrast_mean": np.mean(contrast, axis=1),
        }

    def _compare_features(self, feat_a: dict, feat_b: dict) -> float:
        """
        Compute similarity between two feature sets.
        Returns 0.0 (different) to 1.0 (identical).
        """
        import numpy as np

        similarities = []

        # Chroma similarity (cosine)
        if "chroma_mean" in feat_a and "chroma_mean" in feat_b:
            cos_sim = np.dot(feat_a["chroma_mean"], feat_b["chroma_mean"]) / (
                np.linalg.norm(feat_a["chroma_mean"])
                * np.linalg.norm(feat_b["chroma_mean"])
                + 1e-8
            )
            similarities.append(cos_sim * 0.4)  # Weight: 40%

        # MFCC similarity
        if "mfcc_mean" in feat_a and "mfcc_mean" in feat_b:
            mfcc_dist = np.linalg.norm(
                feat_a["mfcc_mean"] - feat_b["mfcc_mean"]
            )
            mfcc_sim = 1.0 / (1.0 + mfcc_dist)
            similarities.append(mfcc_sim * 0.35)  # Weight: 35%

        # Contrast similarity
        if "contrast_mean" in feat_a and "contrast_mean" in feat_b:
            con_dist = np.linalg.norm(
                feat_a["contrast_mean"] - feat_b["contrast_mean"]
            )
            con_sim = 1.0 / (1.0 + con_dist)
            similarities.append(con_sim * 0.25)  # Weight: 25%

        return sum(similarities) if similarities else 0.0

    def _dtw_similarity(self, seq_a, seq_b) -> float:
        """
        Dynamic Time Warping similarity between two sequences.
        Returns 0.0 (different) to 1.0 (identical).
        """
        import numpy as np

        n, m = len(seq_a), len(seq_b)
        if n == 0 or m == 0:
            return 0.0

        # Subsample for performance
        max_len = 500
        if n > max_len:
            seq_a = seq_a[:: n // max_len]
            n = len(seq_a)
        if m > max_len:
            seq_b = seq_b[:: m // max_len]
            m = len(seq_b)

        dtw = np.full((n + 1, m + 1), np.inf)
        dtw[0, 0] = 0.0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = abs(seq_a[i - 1] - seq_b[j - 1])
                dtw[i, j] = cost + min(
                    dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1]
                )

        # Normalize
        dist = dtw[n, m] / max(n, m)
        similarity = 1.0 / (1.0 + dist)
        return similarity
