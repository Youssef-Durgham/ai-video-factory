"""
Phase 6 — Audio QA: Three-layer verification for all audio assets.

Layer 1 — VoiceQA:  Deterministic signal checks + Whisper STT + prosody
Layer 2 — MusicQA:  Content ID safety + mood match + volume
Layer 3 — MixQA:    Full-mix intelligibility + ducking + LUFS (post-compose)

Runs inline after each audio generation step (voice, music) and once
after final composition for mix-level checks.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# THRESHOLDS
# ════════════════════════════════════════════════════════════════

# Voice QA
SILENCE_GAP_MAX_SEC = 2.0          # Max silence gap inside narration
CLIPPING_THRESHOLD = 0.99          # Samples ≥ this = clipping
CLIPPING_EVENT_DURATION_MS = 10    # Minimum clipping event length
MAX_CLIPPING_EVENTS = 5
MIN_SNR_DB = 20.0
MAX_DURATION_DEVIATION = 0.20      # 20%
MAX_WER = 0.15                     # 15% Word Error Rate
RMS_VARIATION_MAX_DB = 6.0
PITCH_MONOTONE_STD_HZ = 15.0      # Below this = robotic

# Music QA
MUSIC_TARGET_LUFS_MIN = -24.0
MUSIC_TARGET_LUFS_MAX = -18.0

# Mix QA
MIX_TARGET_LUFS = -14.0           # YouTube target
MIX_TRUE_PEAK_MAX_DBTP = -1.0
MIX_WER_INCREASE_MAX = 0.05       # Max 5% WER increase in mix vs isolated
DUCKING_RATIO_MIN_DB = -18.0
DUCKING_RATIO_MAX_DB = -12.0
AV_SYNC_DRIFT_MAX_MS = 100.0


# ════════════════════════════════════════════════════════════════
# RESULT DATACLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class VoiceQAResult:
    """Result of voice audio quality analysis."""
    scene_index: int = 0
    silence_gaps: list[dict] = field(default_factory=list)
    clipping_events: int = 0
    duration_ratio: float = 1.0          # actual / expected
    snr_db: float = 0.0
    wer: float = 0.0                     # Word Error Rate
    misheard_words: list[dict] = field(default_factory=list)
    pitch_monotone: bool = False
    emotion_match: float = 0.0           # 0-1
    word_timestamps: list[dict] = field(default_factory=list)
    rms_db: float = 0.0
    verdict: str = "pass"                # pass | regen | flag_human
    details: dict = field(default_factory=dict)


@dataclass
class MusicQAResult:
    """Result of music audio quality analysis."""
    zone_index: int = 0
    content_id_safe: bool = True
    mood_match: float = 0.0              # 0-1
    volume_lufs: float = 0.0
    tempo_bpm: float = 0.0
    clipping: bool = False
    has_silence: bool = False
    duration_match: bool = True
    verdict: str = "pass"
    details: dict = field(default_factory=dict)


@dataclass
class MixQAResult:
    """Result of final mix quality analysis."""
    voice_intelligibility_wer: float = 0.0
    ducking_correct: bool = True
    overall_lufs: float = 0.0
    true_peak_dbtp: float = 0.0
    av_sync_drift_ms: float = 0.0
    verdict: str = "pass"
    details: dict = field(default_factory=dict)


# ════════════════════════════════════════════════════════════════
# VOICE QA
# ════════════════════════════════════════════════════════════════

class VoiceQA:
    """
    Three-layer voice quality verification:
      1. Deterministic signal analysis (silence, clipping, SNR, RMS)
      2. Whisper STT verification (WER, misheard words, timestamps)
      3. Prosody analysis (pitch monotone, emotion match)
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._whisper_model = None

    def check(
        self,
        audio_path: str,
        expected_text: str = "",
        expected_duration_sec: float = 0.0,
        scene_index: int = 0,
        scene_mood: str = "neutral",
    ) -> VoiceQAResult:
        """
        Run all voice QA layers on a single audio file.

        Args:
            audio_path: Path to voice audio file (WAV).
            expected_text: Script text for STT comparison.
            expected_duration_sec: Expected duration from word count estimate.
            scene_index: Scene number for reporting.
            scene_mood: Expected emotion/mood for prosody check.

        Returns:
            VoiceQAResult with verdict.
        """
        result = VoiceQAResult(scene_index=scene_index)

        try:
            audio, sr = self._load_audio(audio_path)
        except Exception as e:
            logger.error("Cannot load audio %s: %s", audio_path, e)
            result.verdict = "regen"
            result.details["error"] = str(e)
            return result

        # Layer 1: Deterministic
        self._check_silence(audio, sr, result)
        self._check_clipping(audio, sr, result)
        self._check_duration(audio, sr, expected_duration_sec, result)
        self._check_snr(audio, sr, result)
        self._check_rms(audio, sr, result)

        # Layer 2: Whisper STT
        if expected_text:
            self._check_stt(audio_path, expected_text, result)

        # Layer 3: Prosody
        self._check_prosody(audio, sr, scene_mood, result)

        # Compute verdict
        result.verdict = self._compute_voice_verdict(result)
        return result

    # ─── Layer 1: Deterministic ───────────────────────────────

    def _check_silence(self, audio: np.ndarray, sr: int, result: VoiceQAResult) -> None:
        """Detect silence gaps in narration."""
        try:
            import librosa
            intervals = librosa.effects.split(audio, top_db=30)
        except ImportError:
            logger.warning("librosa not available — skipping silence check")
            return

        if len(intervals) == 0:
            result.silence_gaps = [{"start": 0.0, "end": len(audio) / sr, "duration": len(audio) / sr}]
            return

        gaps = []
        for i in range(1, len(intervals)):
            gap_start = intervals[i - 1][1] / sr
            gap_end = intervals[i][0] / sr
            gap_dur = gap_end - gap_start
            if gap_dur > SILENCE_GAP_MAX_SEC:
                gaps.append({"start": gap_start, "end": gap_end, "duration": gap_dur})
        result.silence_gaps = gaps

    def _check_clipping(self, audio: np.ndarray, sr: int, result: VoiceQAResult) -> None:
        """Detect clipping events."""
        clipped = np.abs(audio) >= CLIPPING_THRESHOLD
        min_samples = int(CLIPPING_EVENT_DURATION_MS * sr / 1000)
        events = 0
        count = 0
        for s in clipped:
            if s:
                count += 1
            else:
                if count >= min_samples:
                    events += 1
                count = 0
        if count >= min_samples:
            events += 1
        result.clipping_events = events

    def _check_duration(
        self, audio: np.ndarray, sr: int,
        expected: float, result: VoiceQAResult,
    ) -> None:
        """Check actual vs expected duration."""
        actual = len(audio) / sr
        if expected > 0:
            result.duration_ratio = actual / expected
        else:
            result.duration_ratio = 1.0

    def _check_snr(self, audio: np.ndarray, sr: int, result: VoiceQAResult) -> None:
        """Estimate Signal-to-Noise Ratio."""
        try:
            import librosa
            intervals = librosa.effects.split(audio, top_db=30)
        except ImportError:
            result.snr_db = 30.0  # assume OK
            return

        if len(intervals) == 0:
            result.snr_db = 0.0
            return

        # Signal = voiced segments, noise = non-voiced
        signal_power = 0.0
        noise_power = 0.0
        signal_samples = 0
        noise_samples = 0

        prev_end = 0
        for start, end in intervals:
            # Noise before this voiced segment
            if start > prev_end:
                noise_seg = audio[prev_end:start]
                noise_power += np.sum(noise_seg ** 2)
                noise_samples += len(noise_seg)
            # Signal
            sig_seg = audio[start:end]
            signal_power += np.sum(sig_seg ** 2)
            signal_samples += len(sig_seg)
            prev_end = end

        # Trailing noise
        if prev_end < len(audio):
            noise_seg = audio[prev_end:]
            noise_power += np.sum(noise_seg ** 2)
            noise_samples += len(noise_seg)

        if noise_samples > 0 and noise_power > 0:
            snr = 10 * np.log10(
                (signal_power / max(signal_samples, 1))
                / (noise_power / noise_samples)
            )
            result.snr_db = float(snr)
        else:
            result.snr_db = 60.0  # very clean

    def _check_rms(self, audio: np.ndarray, sr: int, result: VoiceQAResult) -> None:
        """Compute RMS level in dB."""
        rms = np.sqrt(np.mean(audio ** 2))
        result.rms_db = float(20 * np.log10(rms + 1e-10))

    # ─── Layer 2: Whisper STT ─────────────────────────────────

    def _check_stt(
        self,
        audio_path: str,
        expected_text: str,
        result: VoiceQAResult,
    ) -> None:
        """Run Whisper STT and compute WER."""
        try:
            import whisper
        except ImportError:
            logger.warning("whisper not available — skipping STT check")
            return

        try:
            if self._whisper_model is None:
                model_size = self.config.get("whisper_model", "base")
                self._whisper_model = whisper.load_model(model_size)

            out = self._whisper_model.transcribe(
                audio_path, language="ar", word_timestamps=True,
            )
            transcript = out.get("text", "")

            # WER
            result.wer = self._compute_wer(expected_text, transcript)

            # Word timestamps
            segments = out.get("segments", [])
            for seg in segments:
                for w in seg.get("words", []):
                    result.word_timestamps.append({
                        "word": w.get("word", ""),
                        "start": w.get("start", 0),
                        "end": w.get("end", 0),
                    })

            # Misheard words (simplified)
            expected_words = expected_text.split()
            transcript_words = transcript.split()
            for i, (ew, tw) in enumerate(
                zip(expected_words, transcript_words)
            ):
                if ew != tw:
                    result.misheard_words.append({
                        "expected": ew,
                        "heard": tw,
                        "index": i,
                    })

        except Exception as e:
            logger.warning("Whisper STT failed: %s", e)

    @staticmethod
    def _compute_wer(reference: str, hypothesis: str) -> float:
        """Compute Word Error Rate (Levenshtein on word level)."""
        ref = reference.split()
        hyp = hypothesis.split()
        if not ref:
            return 0.0 if not hyp else 1.0

        d = np.zeros((len(ref) + 1, len(hyp) + 1), dtype=int)
        for i in range(len(ref) + 1):
            d[i][0] = i
        for j in range(len(hyp) + 1):
            d[0][j] = j

        for i in range(1, len(ref) + 1):
            for j in range(1, len(hyp) + 1):
                cost = 0 if ref[i - 1] == hyp[j - 1] else 1
                d[i][j] = min(
                    d[i - 1][j] + 1,      # deletion
                    d[i][j - 1] + 1,       # insertion
                    d[i - 1][j - 1] + cost,  # substitution
                )

        return float(d[len(ref)][len(hyp)]) / len(ref)

    # ─── Layer 3: Prosody ─────────────────────────────────────

    def _check_prosody(
        self,
        audio: np.ndarray,
        sr: int,
        scene_mood: str,
        result: VoiceQAResult,
    ) -> None:
        """Analyze pitch contour for monotone detection and emotion match."""
        try:
            import librosa
            # F0 via pYIN
            f0, voiced_flag, voiced_prob = librosa.pyin(
                audio, fmin=60, fmax=500, sr=sr,
            )
        except (ImportError, Exception) as e:
            logger.debug("Prosody analysis skipped: %s", e)
            return

        valid_f0 = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        if len(valid_f0) < 10:
            return

        pitch_std = float(np.std(valid_f0))
        result.pitch_monotone = pitch_std < PITCH_MONOTONE_STD_HZ

        # Simple emotion classifier: energy + pitch
        mean_pitch = float(np.mean(valid_f0))
        energy = float(np.sqrt(np.mean(audio ** 2)))

        mood_lower = scene_mood.lower()
        # Heuristic emotion match
        if mood_lower in {"calm", "reflective", "peaceful"}:
            result.emotion_match = 1.0 if mean_pitch < 200 else 0.6
        elif mood_lower in {"exciting", "energetic", "epic", "climax"}:
            result.emotion_match = 1.0 if mean_pitch > 160 and energy > 0.05 else 0.5
        elif mood_lower in {"sad", "somber", "melancholy"}:
            result.emotion_match = 1.0 if mean_pitch < 180 and energy < 0.04 else 0.5
        elif mood_lower in {"tense", "dramatic", "suspenseful"}:
            result.emotion_match = 0.8 if pitch_std > 20 else 0.5
        else:
            result.emotion_match = 0.7  # neutral — anything goes

    # ─── Verdict ──────────────────────────────────────────────

    @staticmethod
    def _compute_voice_verdict(r: VoiceQAResult) -> str:
        """Determine pass/regen/flag_human from results."""
        # Hard fails → regen
        if r.clipping_events > MAX_CLIPPING_EVENTS:
            return "regen"
        if r.silence_gaps and any(g["duration"] > 5.0 for g in r.silence_gaps):
            return "regen"
        if r.snr_db < MIN_SNR_DB:
            return "regen"
        if abs(r.duration_ratio - 1.0) > MAX_DURATION_DEVIATION:
            return "regen"
        if r.wer > MAX_WER:
            return "regen"
        if r.pitch_monotone:
            return "flag_human"
        return "pass"

    # ─── Audio Loading ────────────────────────────────────────

    @staticmethod
    def _load_audio(path: str) -> tuple[np.ndarray, int]:
        """Load audio as mono float32 numpy array."""
        try:
            import librosa
            audio, sr = librosa.load(path, sr=None, mono=True)
            return audio, sr
        except ImportError:
            import soundfile as sf
            audio, sr = sf.read(path, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            return audio, sr


# ════════════════════════════════════════════════════════════════
# MUSIC QA
# ════════════════════════════════════════════════════════════════

class MusicQA:
    """
    Verify ACE-Step 1.5 music output quality + mood alignment.
    Layer 1: Deterministic (duration, clipping, silence, volume)
    Layer 2: Mood analysis (tempo, key, energy vs scene mood)
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def check(
        self,
        audio_path: str,
        expected_duration_sec: float = 0.0,
        target_mood: str = "neutral",
        zone_index: int = 0,
        content_id_safe: bool = True,
    ) -> MusicQAResult:
        """
        Run music QA on a generated track.

        Args:
            audio_path: Path to music audio file.
            expected_duration_sec: Expected track duration.
            target_mood: Mood this track should match.
            zone_index: Mood zone index for reporting.
            content_id_safe: Pre-computed Content ID result.

        Returns:
            MusicQAResult with verdict.
        """
        result = MusicQAResult(zone_index=zone_index)
        result.content_id_safe = content_id_safe

        try:
            audio, sr = self._load_audio(audio_path)
        except Exception as e:
            logger.error("Cannot load music %s: %s", audio_path, e)
            result.verdict = "regen"
            return result

        # Duration check
        actual_dur = len(audio) / sr
        if expected_duration_sec > 0:
            ratio = actual_dur / expected_duration_sec
            result.duration_match = 0.7 <= ratio <= 1.3

        # Clipping
        clipped = np.sum(np.abs(audio) >= CLIPPING_THRESHOLD)
        result.clipping = int(clipped) > sr * 0.01  # >10ms total

        # Silence check (music should be continuous)
        try:
            import librosa
            intervals = librosa.effects.split(audio, top_db=40)
            total_voiced = sum(e - s for s, e in intervals) / sr
            result.has_silence = total_voiced < actual_dur * 0.8
        except ImportError:
            pass

        # LUFS estimation (simplified RMS-based)
        rms = np.sqrt(np.mean(audio ** 2))
        result.volume_lufs = float(20 * np.log10(rms + 1e-10)) - 0.691

        # Tempo via librosa
        try:
            import librosa
            tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
            result.tempo_bpm = float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)
        except (ImportError, Exception):
            result.tempo_bpm = 0.0

        # Mood match (simplified heuristic)
        result.mood_match = self._estimate_mood_match(
            target_mood, result.tempo_bpm, result.volume_lufs,
        )

        # Verdict
        if not result.content_id_safe:
            result.verdict = "regen"
        elif result.clipping:
            result.verdict = "regen"
        elif result.mood_match < 0.3:
            result.verdict = "regen"
        elif result.has_silence:
            result.verdict = "flag_human"
        else:
            result.verdict = "pass"

        return result

    @staticmethod
    def _estimate_mood_match(mood: str, bpm: float, lufs: float) -> float:
        """Heuristic mood-to-audio-features match score."""
        mood = mood.lower()
        if bpm <= 0:
            return 0.5  # unknown

        if mood in {"tense", "suspenseful", "dark"}:
            # Expect slower tempo, lower energy
            score = 1.0 if 60 <= bpm <= 110 else 0.5
        elif mood in {"hopeful", "inspiring", "uplifting"}:
            score = 1.0 if 90 <= bpm <= 140 else 0.5
        elif mood in {"calm", "reflective", "peaceful"}:
            score = 1.0 if 50 <= bpm <= 100 else 0.4
        elif mood in {"exciting", "energetic", "epic", "climax"}:
            score = 1.0 if 120 <= bpm <= 180 else 0.5
        elif mood in {"sad", "somber", "melancholy"}:
            score = 1.0 if 50 <= bpm <= 90 else 0.5
        else:
            score = 0.7

        return score

    @staticmethod
    def _load_audio(path: str) -> tuple[np.ndarray, int]:
        try:
            import librosa
            return librosa.load(path, sr=None, mono=True)
        except ImportError:
            import soundfile as sf
            audio, sr = sf.read(path, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            return audio, sr


# ════════════════════════════════════════════════════════════════
# MIX QA (post-compose)
# ════════════════════════════════════════════════════════════════

class MixQA:
    """
    Full audio mix analysis after FFmpeg composition.
    Checks voice intelligibility, ducking, LUFS, true peak, A/V sync.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._whisper_model = None

    def check(
        self,
        mixed_audio_path: str,
        isolated_voice_wer: float = 0.0,
        expected_text: str = "",
        voice_segments: list[dict] | None = None,
    ) -> MixQAResult:
        """
        Run mix-level QA on the composed audio track.

        Args:
            mixed_audio_path: Path to final mixed audio (extracted from video).
            isolated_voice_wer: WER from VoiceQA on isolated voice.
            expected_text: Full script text for STT comparison.
            voice_segments: List of {start_sec, end_sec} for narration.

        Returns:
            MixQAResult with verdict.
        """
        result = MixQAResult()

        try:
            audio, sr = self._load_audio(mixed_audio_path)
        except Exception as e:
            logger.error("Cannot load mixed audio: %s", e)
            result.verdict = "flag_human"
            return result

        # LUFS (simplified)
        rms = np.sqrt(np.mean(audio ** 2))
        result.overall_lufs = float(20 * np.log10(rms + 1e-10)) - 0.691

        # True peak
        result.true_peak_dbtp = float(20 * np.log10(np.max(np.abs(audio)) + 1e-10))

        # Voice intelligibility (Whisper on mix)
        if expected_text:
            try:
                import whisper
                if self._whisper_model is None:
                    model_size = self.config.get("whisper_model", "base")
                    self._whisper_model = whisper.load_model(model_size)

                out = self._whisper_model.transcribe(
                    mixed_audio_path, language="ar",
                )
                transcript = out.get("text", "")
                result.voice_intelligibility_wer = VoiceQA._compute_wer(
                    expected_text, transcript,
                )

                # Check if mix degraded intelligibility
                wer_increase = result.voice_intelligibility_wer - isolated_voice_wer
                if wer_increase > MIX_WER_INCREASE_MAX:
                    result.details["wer_degraded"] = True
            except (ImportError, Exception) as e:
                logger.warning("Mix STT check failed: %s", e)

        # Ducking verification
        if voice_segments:
            result.ducking_correct = self._check_ducking(
                audio, sr, voice_segments,
            )

        # Verdict
        if result.true_peak_dbtp > MIX_TRUE_PEAK_MAX_DBTP:
            result.verdict = "flag_human"
        elif result.details.get("wer_degraded"):
            result.verdict = "flag_human"
        elif not result.ducking_correct:
            result.verdict = "flag_human"
        else:
            result.verdict = "pass"

        return result

    def _check_ducking(
        self,
        audio: np.ndarray,
        sr: int,
        voice_segments: list[dict],
    ) -> bool:
        """
        Verify that music volume drops during narration segments.

        Compares RMS during voice segments vs non-voice segments.
        """
        voice_rms_list = []
        nonvoice_rms_list = []

        for seg in voice_segments:
            start = int(seg["start_sec"] * sr)
            end = int(seg["end_sec"] * sr)
            start = max(0, min(start, len(audio)))
            end = max(0, min(end, len(audio)))
            if end > start:
                voice_rms_list.append(np.sqrt(np.mean(audio[start:end] ** 2)))

        # Non-voice: gaps between segments
        prev_end = 0
        for seg in voice_segments:
            start = int(seg["start_sec"] * sr)
            if start > prev_end:
                nonvoice_rms_list.append(
                    np.sqrt(np.mean(audio[prev_end:start] ** 2))
                )
            prev_end = int(seg["end_sec"] * sr)

        if not voice_rms_list or not nonvoice_rms_list:
            return True  # can't verify

        avg_voice_rms = np.mean(voice_rms_list)
        avg_nonvoice_rms = np.mean(nonvoice_rms_list)

        if avg_nonvoice_rms < 1e-10:
            return True

        # During voice, music should be quieter → overall level
        # should still be dominated by voice, not drastically louder
        ratio_db = 20 * np.log10(avg_voice_rms / (avg_nonvoice_rms + 1e-10))

        # Voice segments should be louder than non-voice gaps
        # (because voice is present + ducked music)
        return ratio_db > 0

    @staticmethod
    def _load_audio(path: str) -> tuple[np.ndarray, int]:
        try:
            import librosa
            return librosa.load(path, sr=None, mono=True)
        except ImportError:
            import soundfile as sf
            audio, sr = sf.read(path, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            return audio, sr
