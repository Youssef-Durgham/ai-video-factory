"""
Voice Cloner — Multi-sample voice extraction from YouTube.

Pipeline: YouTube URL → yt-dlp → demucs vocal separation → Whisper transcription
→ Energy analysis → Extract multiple samples (calm, dramatic, questioning)
→ Voice profiles for Fish Speech.

KEY INSIGHT: Fish Speech copies the STYLE of the reference, not just the voice.
So we need references for different moods:
- Calm narration (main reference)
- Dramatic/emphasis (for intense scenes)
- Questioning tone (for rhetorical questions)
"""

import json
import logging
import re
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import sys

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def _find_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff: return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError: pass
    for p in [Path(r"C:\ffmpeg\bin\ffmpeg.exe"), Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe")]:
        if p.exists(): return str(p)
    return "ffmpeg"

def _find_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if ffprobe: return ffprobe
    ffmpeg = _find_ffmpeg()
    probe = Path(ffmpeg).parent / "ffprobe.exe"
    if probe.exists(): return str(probe)
    return "ffprobe"

FFMPEG = _find_ffmpeg()
FFPROBE = _find_ffprobe()
YTDLP = [sys.executable, "-m", "yt_dlp"]
DEMUCS = [sys.executable, "-m", "demucs"]

logger.info(f"Voice tools: ffmpeg={FFMPEG}, yt-dlp=python -m yt_dlp, demucs=python -m demucs")


@dataclass
class VoiceProfile:
    voice_id: str
    name: str
    reference_audio: str
    source_url: str
    created_at: str
    duration_sec: float


class VoiceCloner:
    VOICES_DIR = BASE_DIR / "config" / "voices"
    EMBEDDINGS_DIR = BASE_DIR / "config" / "voices" / "embeddings"
    TEMP_DIR = BASE_DIR / "config" / "voices" / "_temp"

    def __init__(self):
        self.VOICES_DIR.mkdir(parents=True, exist_ok=True)
        self.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    def clone_from_youtube(self, url: str, voice_id: str, name: str) -> VoiceProfile:
        """Full pipeline: YouTube URL → multi-sample voice profiles."""
        if self.TEMP_DIR.exists():
            shutil.rmtree(self.TEMP_DIR, ignore_errors=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Download audio
            logger.info(f"Downloading audio from {url}")
            self._download_audio(url)

            # 2. Convert to WAV
            source_wav = self._convert_to_wav()

            # 3. Separate vocals (demucs double-pass)
            vocals_path = self._separate_vocals(source_wav)

            # 4. Transcribe with Whisper (much better than YouTube subs)
            logger.info("Transcribing with Whisper...")
            segments = self._whisper_transcribe(vocals_path)

            # 5. Analyze energy to find different mood segments
            logger.info("Analyzing energy for mood segments...")
            mood_segments = self._find_mood_segments(vocals_path, segments)

            # 6. Extract main reference (longest calm segment, ~30-60s)
            main_ref = self._extract_main_reference(vocals_path, mood_segments, segments)

            # 7. Save voice profile
            final_audio = self.EMBEDDINGS_DIR / f"{voice_id}.wav"
            shutil.copy2(main_ref["path"], final_audio)

            # Save transcription
            lab_path = final_audio.with_suffix(".lab")
            lab_path.write_text(main_ref["text"], encoding="utf-8")
            logger.info(f"Main reference: {main_ref['duration']:.1f}s, mood={main_ref['mood']}")

            # 8. Save mood-specific references (if found)
            for mood, seg in mood_segments.items():
                if mood == "calm":
                    continue  # Already saved as main
                mood_audio = self.EMBEDDINGS_DIR / f"{voice_id}_{mood}.wav"
                shutil.copy2(seg["path"], mood_audio)
                mood_lab = mood_audio.with_suffix(".lab")
                mood_lab.write_text(seg["text"], encoding="utf-8")
                logger.info(f"Mood reference '{mood}': {seg['duration']:.1f}s")

            duration = self._get_duration(final_audio)
            profile = VoiceProfile(
                voice_id=voice_id,
                name=name,
                reference_audio=str(final_audio),
                source_url=url,
                created_at=datetime.utcnow().isoformat(),
                duration_sec=duration,
            )

            meta_path = self.VOICES_DIR / f"{voice_id}.json"
            meta = asdict(profile)
            # Store mood references in metadata
            meta["mood_references"] = {}
            for mood in mood_segments:
                mood_audio = self.EMBEDDINGS_DIR / f"{voice_id}_{mood}.wav"
                if mood_audio.exists():
                    meta["mood_references"][mood] = str(mood_audio)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            logger.info(f"Voice profile '{voice_id}' created: {duration:.1f}s, {len(mood_segments)} moods")
            return profile

        finally:
            shutil.rmtree(self.TEMP_DIR, ignore_errors=True)

    # ════════════════════════════════════════════════════════════
    # Step 1: Download
    # ════════════════════════════════════════════════════════════

    def _download_audio(self, url: str):
        subprocess.run(
            YTDLP + ["-x", "--audio-quality", "0",
                     "-o", str(self.TEMP_DIR / "source.%(ext)s"), url],
            capture_output=True, text=True, timeout=300, check=True,
        )

    def _convert_to_wav(self) -> Path:
        downloaded = None
        for ext in ["opus", "m4a", "webm", "mp3", "wav", "ogg"]:
            candidates = list(self.TEMP_DIR.glob(f"source*.{ext}"))
            if candidates:
                downloaded = candidates[0]
                break
        if not downloaded:
            audio_files = [f for f in self.TEMP_DIR.iterdir()
                          if f.suffix in ('.opus', '.m4a', '.webm', '.mp3', '.wav', '.ogg', '.aac')]
            if audio_files:
                downloaded = audio_files[0]
            else:
                raise RuntimeError("yt-dlp did not produce audio")

        source_wav = self.TEMP_DIR / "source.wav"
        subprocess.run(
            [FFMPEG, "-y", "-i", str(downloaded),
             "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
             str(source_wav)],
            capture_output=True, timeout=120, check=True,
        )
        return source_wav

    # ════════════════════════════════════════════════════════════
    # Step 2: Vocal separation
    # ════════════════════════════════════════════════════════════

    def _separate_vocals(self, source_wav: Path) -> Path:
        vocals_path = source_wav
        try:
            logger.info("Separating vocals with demucs...")
            result = subprocess.run(
                DEMUCS + ["-n", "htdemucs", "--two-stems", "vocals",
                         "--shifts", "3",
                         "-o", str(self.TEMP_DIR / "sep"), str(source_wav)],
                capture_output=True, text=True, timeout=900,
            )
            if result.returncode == 0:
                candidates = list((self.TEMP_DIR / "sep").rglob("vocals.wav"))
                if candidates:
                    vocals_path = candidates[0]
                    logger.info("Demucs vocal separation successful")

                    # Light cleanup
                    cleaned = self.TEMP_DIR / "vocals_clean.wav"
                    subprocess.run(
                        [FFMPEG, "-y", "-i", str(vocals_path),
                         "-af", "highpass=f=80,lowpass=f=12000,afftdn=nf=-20:nt=w,loudnorm=I=-16:TP=-1.5:LRA=11",
                         str(cleaned)],
                        capture_output=True, timeout=120,
                    )
                    if cleaned.exists():
                        vocals_path = cleaned
        except Exception as e:
            logger.warning(f"Demucs error: {e} — using raw audio")

        return vocals_path

    # ════════════════════════════════════════════════════════════
    # Step 3: Whisper transcription (replaces YouTube subs)
    # ════════════════════════════════════════════════════════════

    def _whisper_transcribe(self, audio_path: Path) -> list[dict]:
        """Transcribe with Whisper — returns timestamped segments."""
        try:
            import warnings
            warnings.filterwarnings("ignore")
            import os
            os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

            from faster_whisper import WhisperModel
            model = WhisperModel("small", device="cpu", compute_type="int8")

            segments_iter, info = model.transcribe(
                str(audio_path), language="ar", beam_size=3,
                word_timestamps=True,
            )

            segments = []
            for seg in segments_iter:
                segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "words": [{"word": w.word, "start": w.start, "end": w.end, "prob": w.probability}
                              for w in (seg.words or [])],
                })

            del model
            import gc
            gc.collect()

            logger.info(f"Whisper transcribed {len(segments)} segments")
            return segments

        except Exception as e:
            logger.warning(f"Whisper transcription failed: {e}")
            return []

    # ════════════════════════════════════════════════════════════
    # Step 4: Mood analysis (energy-based)
    # ════════════════════════════════════════════════════════════

    def _find_mood_segments(self, audio_path: Path, whisper_segments: list) -> dict:
        """
        Multi-signal mood analysis: pitch + speech rate + energy + text.
        
        For each Whisper segment, compute a mood score using 4 signals:
        - Pitch variation (F0 std): high variation = dramatic
        - Speech rate (words/sec): fast transitions = dramatic, slow = calm
        - Energy (RMS): loud = dramatic, quiet = calm  
        - Text cues: ؟ = question, ! = exclamation, dramatic words = dramatic
        """
        try:
            import numpy as np
            import librosa

            y, sr = librosa.load(str(audio_path), sr=22050)
            total_dur = len(y) / sr

            if not whisper_segments:
                return {}

            # ── Score each Whisper segment on 4 axes ──
            scored_segments = []

            for seg in whisper_segments:
                start_sample = int(seg["start"] * sr)
                end_sample = min(int(seg["end"] * sr), len(y))
                if end_sample - start_sample < sr * 0.5:
                    continue  # Too short

                chunk = y[start_sample:end_sample]
                duration = (end_sample - start_sample) / sr
                text = seg["text"].strip()
                words = text.split()
                if not words:
                    continue

                # 1. Pitch variation (F0 standard deviation)
                try:
                    f0, voiced, _ = librosa.pyin(
                        chunk, fmin=60, fmax=400, sr=sr,
                        frame_length=2048, hop_length=512,
                    )
                    f0_valid = f0[voiced] if voiced is not None else f0[~np.isnan(f0)]
                    pitch_std = float(np.std(f0_valid)) if len(f0_valid) > 5 else 0.0
                    pitch_mean = float(np.mean(f0_valid)) if len(f0_valid) > 5 else 150.0
                except Exception:
                    pitch_std = 0.0
                    pitch_mean = 150.0

                # 2. Speech rate (words per second)
                speech_rate = len(words) / max(duration, 0.1)

                # 3. Energy (RMS)
                rms = float(np.sqrt(np.mean(chunk ** 2)))

                # 4. Text cues
                has_question = text.endswith("؟") or "؟" in text
                has_exclaim = "!" in text
                dramatic_words = {"مذهل", "خطير", "غامض", "لا يصدق", "مستحيل",
                                  "صادم", "كارثة", "انفجار", "اختفاء", "رهيب",
                                  "تختفي", "تدمر", "تنهار", "مفاجئ", "لغز"}
                has_dramatic_text = any(w in text for w in dramatic_words)

                # ── Classify mood ──
                # Weights: pitch_variation(35%) + text(30%) + energy(20%) + speech_rate(15%)
                drama_score = 0.0

                # Pitch: high std = dramatic (documentary narrators vary pitch for drama)
                if pitch_std > 30:
                    drama_score += 0.35
                elif pitch_std > 15:
                    drama_score += 0.15

                # Text: strongest signal
                if has_dramatic_text or has_exclaim:
                    drama_score += 0.30
                elif has_question:
                    drama_score += 0.10  # Questions are separate mood

                # Energy: loud = dramatic
                # (normalized later against all segments)
                energy_raw = rms

                # Speech rate: very fast or very slow = dramatic
                # Normal documentary = ~2.5 words/sec
                rate_deviation = abs(speech_rate - 2.5)
                if rate_deviation > 1.5:
                    drama_score += 0.15
                elif rate_deviation > 0.8:
                    drama_score += 0.07

                scored_segments.append({
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": text,
                    "pitch_std": pitch_std,
                    "pitch_mean": pitch_mean,
                    "speech_rate": speech_rate,
                    "energy": energy_raw,
                    "drama_score": drama_score,
                    "is_question": has_question,
                })

            if not scored_segments:
                return {}

            # ── Normalize energy across all segments ──
            energies = [s["energy"] for s in scored_segments]
            avg_energy = np.mean(energies)
            std_energy = np.std(energies) if len(energies) > 1 else 0.1

            for seg in scored_segments:
                energy_z = (seg["energy"] - avg_energy) / max(std_energy, 0.01)
                if energy_z > 0.8:
                    seg["drama_score"] += 0.20
                elif energy_z > 0.3:
                    seg["drama_score"] += 0.10

                # Final classification
                if seg["is_question"]:
                    seg["mood"] = "question"
                elif seg["drama_score"] >= 0.45:
                    seg["mood"] = "dramatic"
                elif seg["drama_score"] <= 0.15:
                    seg["mood"] = "calm"
                else:
                    seg["mood"] = "neutral"

            # ── Find best contiguous windows per mood ──
            result = {}

            for target_mood in ["calm", "dramatic", "question"]:
                # Collect segments of this mood
                mood_segs = [s for s in scored_segments if s["mood"] == target_mood]
                if not mood_segs:
                    continue

                # Find best contiguous group (close in time)
                mood_segs.sort(key=lambda s: s["start"])
                best_group = self._find_best_contiguous_group(mood_segs, min_duration=8, max_duration=60)

                if not best_group:
                    # Use single best segment for questions
                    if target_mood == "question" and mood_segs:
                        best_group = [mood_segs[0]]
                    else:
                        continue

                # Extract audio
                group_start = max(0, best_group[0]["start"] - 1)
                group_end = min(total_dur, best_group[-1]["end"] + 1)
                group_dur = group_end - group_start

                seg_path = self.TEMP_DIR / f"mood_{target_mood}.wav"
                subprocess.run(
                    [FFMPEG, "-y", "-i", str(audio_path),
                     "-ss", str(group_start), "-t", str(group_dur),
                     "-ac", "1", "-ar", "44100",
                     "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                     str(seg_path)],
                    capture_output=True, timeout=60,
                )

                if seg_path.exists():
                    seg_text = " ".join(s["text"] for s in best_group)
                    result[target_mood] = {
                        "path": seg_path,
                        "duration": group_dur,
                        "text": seg_text,
                        "mood": target_mood,
                    }
                    logger.info(
                        f"Mood '{target_mood}': {group_dur:.1f}s, "
                        f"avg_pitch_std={np.mean([s['pitch_std'] for s in best_group]):.1f}, "
                        f"avg_drama={np.mean([s['drama_score'] for s in best_group]):.2f}"
                    )

            logger.info(f"Found mood segments: {list(result.keys())}")
            return result

        except Exception as e:
            logger.warning(f"Mood analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _find_best_contiguous_group(self, segments: list, min_duration: float = 8, max_duration: float = 60) -> list:
        """Find best group of nearby segments that together reach min_duration."""
        if not segments:
            return []

        best_group = []
        best_duration = 0

        for i in range(len(segments)):
            group = [segments[i]]
            group_dur = segments[i]["end"] - segments[i]["start"]

            for j in range(i + 1, len(segments)):
                gap = segments[j]["start"] - segments[j - 1]["end"]
                if gap > 5:  # More than 5s gap = not contiguous
                    break
                group.append(segments[j])
                group_dur = segments[j]["end"] - segments[i]["start"]
                if group_dur >= max_duration:
                    break

            if group_dur >= min_duration and group_dur > best_duration:
                best_group = group[:]
                best_duration = group_dur

        return best_group

    def _find_longest_run(self, arr: list, value: str, min_len: int = 5) -> tuple:
        """Find longest contiguous run of value in array."""
        best_start, best_len = -1, 0
        cur_start, cur_len = -1, 0

        for i, v in enumerate(arr):
            if v == value:
                if cur_start < 0:
                    cur_start = i
                cur_len += 1
            else:
                if cur_len > best_len and cur_len >= min_len:
                    best_start, best_len = cur_start, cur_len
                cur_start, cur_len = -1, 0

        if cur_len > best_len and cur_len >= min_len:
            best_start, best_len = cur_start, cur_len

        return best_start, best_len

    def _get_text_for_range(self, segments: list, start: float, end: float) -> str:
        """Get transcription text within a time range."""
        texts = []
        for seg in segments:
            if seg["end"] > start and seg["start"] < end:
                texts.append(seg["text"])
        return " ".join(texts)

    # ════════════════════════════════════════════════════════════
    # Step 5: Extract main reference
    # ════════════════════════════════════════════════════════════

    def _extract_main_reference(self, vocals_path: Path, mood_segments: dict, whisper_segments: list) -> dict:
        """Extract the best main reference (prefer calm, 30-60s)."""
        # Use calm segment if available and long enough
        if "calm" in mood_segments and mood_segments["calm"]["duration"] >= 20:
            return mood_segments["calm"]

        # Otherwise find best 60s window with most speech
        total_dur = self._get_duration(vocals_path)
        target = min(60, total_dur)

        best_start = 0
        best_speech = 0
        for start_sec in range(0, max(1, int(total_dur - target)), 2):
            speech = sum(
                min(seg["end"], start_sec + target) - max(seg["start"], start_sec)
                for seg in whisper_segments
                if seg["end"] > start_sec and seg["start"] < start_sec + target
            )
            if speech > best_speech:
                best_speech = speech
                best_start = start_sec

        ref_path = self.TEMP_DIR / "main_reference.wav"
        subprocess.run(
            [FFMPEG, "-y", "-i", str(vocals_path),
             "-ss", str(best_start), "-t", str(target),
             "-ac", "1", "-ar", "44100",
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             str(ref_path)],
            capture_output=True, timeout=60,
        )

        ref_text = self._get_text_for_range(whisper_segments, best_start, best_start + target)

        return {
            "path": ref_path,
            "duration": target,
            "text": ref_text,
            "mood": "calm",
        }

    # ════════════════════════════════════════════════════════════
    # Utility methods
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _get_duration(path: Path) -> float:
        try:
            r = subprocess.run(
                [FFPROBE, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                return round(float(r.stdout.strip()), 2)
        except Exception: pass
        try:
            r = subprocess.run(
                [FFMPEG, "-i", str(path), "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", r.stderr)
            if m:
                h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                return round(h * 3600 + mn * 60 + s + cs / 100, 2)
        except Exception: pass
        return 0.0

    def list_voices(self) -> list[VoiceProfile]:
        profiles = []
        for meta_file in self.VOICES_DIR.glob("*.json"):
            if meta_file.name == "default.json":
                continue
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                # Filter out non-VoiceProfile fields
                vp_fields = {f.name for f in VoiceProfile.__dataclass_fields__.values()}
                filtered = {k: v for k, v in data.items() if k in vp_fields}
                profiles.append(VoiceProfile(**filtered))
            except Exception as e:
                logger.warning(f"Failed to load voice profile {meta_file}: {e}")
        return profiles

    def get_voice(self, voice_id: str) -> Optional[VoiceProfile]:
        meta_path = self.VOICES_DIR / f"{voice_id}.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            vp_fields = {f.name for f in VoiceProfile.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in vp_fields}
            return VoiceProfile(**filtered)
        except Exception:
            return None

    def get_mood_reference(self, voice_id: str, mood: str) -> Optional[str]:
        """Get path to mood-specific reference audio."""
        meta_path = self.VOICES_DIR / f"{voice_id}.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            refs = data.get("mood_references", {})
            path = refs.get(mood)
            if path and Path(path).exists():
                return path
        except Exception:
            pass
        return None

    def delete_voice(self, voice_id: str) -> bool:
        meta_path = self.VOICES_DIR / f"{voice_id}.json"
        deleted = False
        # Delete all embeddings for this voice (main + mood variants)
        for f in self.EMBEDDINGS_DIR.glob(f"{voice_id}*"):
            f.unlink()
            deleted = True
        if meta_path.exists():
            meta_path.unlink()
            deleted = True
        # Clear default if it was this voice
        default_path = self.VOICES_DIR / "default.json"
        if default_path.exists():
            try:
                d = json.loads(default_path.read_text(encoding="utf-8"))
                if d.get("default_voice_id") == voice_id:
                    default_path.unlink()
            except Exception: pass
        return deleted

    def get_default_voice_id(self) -> Optional[str]:
        default_path = self.VOICES_DIR / "default.json"
        if default_path.exists():
            try:
                d = json.loads(default_path.read_text(encoding="utf-8"))
                return d.get("default_voice_id")
            except Exception: pass
        return None

    def set_default_voice(self, voice_id: str):
        default_path = self.VOICES_DIR / "default.json"
        default_path.write_text(
            json.dumps({"default_voice_id": voice_id}, ensure_ascii=False),
            encoding="utf-8",
        )
