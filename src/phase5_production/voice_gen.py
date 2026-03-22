"""
Phase 5 — Voice Generation via Fish Speech 1.5 + Edge TTS fallback.

Generates narration audio for each scene.
Primary: Fish Speech (local, high quality)
Fallback: Edge TTS (cloud, good quality)
"""

import asyncio
import logging
import os
import re as _re
import shutil
import subprocess
import sys
import time
import wave
import struct
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import requests


# ─── Resolve ffmpeg path (not always in PATH on Windows) ──────

def _find_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    for p in [Path(r"C:\ffmpeg\bin\ffmpeg.exe"), Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe")]:
        if p.exists():
            return str(p)
    return "ffmpeg"

FFMPEG = _find_ffmpeg()

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════

FISH_SPEECH_DIR = Path(r"C:\Users\3d\clawd\fish-speech")
FISH_SPEECH_URL = "http://127.0.0.1:8080"
FISH_SPEECH_TTS_URL = f"{FISH_SPEECH_URL}/v1/tts"

EDGE_TTS_VOICE = "ar-SA-HamedNeural"
EDGE_TTS_RATE = "-5%"


@dataclass
class VoiceGenConfig:
    """Configuration for voice generation."""
    fish_speech_dir: Path = FISH_SPEECH_DIR
    fish_speech_url: str = FISH_SPEECH_URL
    fish_speech_port: int = 8080
    max_retries: int = 5
    startup_timeout: int = 120
    edge_tts_voice: str = EDGE_TTS_VOICE
    edge_tts_rate: str = EDGE_TTS_RATE


@dataclass
class VoiceGenResult:
    """Result of a single voice generation."""
    success: bool
    audio_path: Optional[str] = None
    duration_sec: float = 0.0
    engine: str = ""  # "fish_speech" or "edge_tts"
    generation_time_sec: float = 0.0
    error: Optional[str] = None


class VoiceGenerator:
    """
    Generates voice narration via Fish Speech 1.5 (local) with Edge TTS fallback.

    Usage:
        gen = VoiceGenerator()
        gen.ensure_server()
        result = gen.generate(text="...", output_dir="output/job/voice", filename="scene_001")
    """

    def __init__(self, config: Optional[VoiceGenConfig] = None):
        self.config = config or VoiceGenConfig()
        self._session = requests.Session()
        self._fish_available = False

    # ─── Server Management ─────────────────────────────

    def check_server(self) -> bool:
        """Check if Fish Speech API server is running."""
        try:
            r = self._session.get(f"{self.config.fish_speech_url}/", timeout=5)
            return r.status_code in (200, 404, 405)  # Any response = server is up
        except Exception:
            # Server might be busy generating — check if process is alive
            try:
                import subprocess
                result = subprocess.run(
                    ["powershell", "-Command",
                     "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object -First 1"],
                    capture_output=True, text=True, timeout=5)
                if "8080" in result.stdout or result.returncode == 0:
                    logger.info("Fish Speech server busy but port 8080 is open — treating as available")
                    return True
            except Exception:
                pass
            return False

    def ensure_server(self, max_wait: Optional[int] = None) -> bool:
        """
        Ensure Fish Speech server is running. Auto-starts if needed.
        Returns True if server is available.
        """
        if self.check_server():
            logger.info("Fish Speech server already running")
            self._fish_available = True
            return True

        # Kill any zombie Fish Speech processes first
        try:
            import subprocess as _sp
            _sp.run(
                ["powershell", "-Command",
                 "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -match 'api_server.*checkpoint' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
            )
            logger.info("Killed zombie Fish Speech processes before starting fresh")
            import time as _time
            _time.sleep(2)
        except Exception:
            pass

        logger.info("Fish Speech not running — starting it...")
        max_wait = max_wait or self.config.startup_timeout

        try:
            cmd = [
                "python", "tools/api_server.py",
                "--llama-checkpoint-path", "checkpoints/s2-pro",
                "--decoder-checkpoint-path", "checkpoints/s2-pro/codec.pth",
                "--decoder-config-name", "modded_dac_vq",
                "--device", "cuda",
                "--half",
                "--listen", f"127.0.0.1:{self.config.fish_speech_port}",
            ]
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            subprocess.Popen(
                cmd,
                cwd=str(self.config.fish_speech_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=0x00000008,  # DETACHED_PROCESS on Windows
            )
            logger.info(f"Fish Speech process started, waiting up to {max_wait}s...")
        except Exception as e:
            logger.error(f"Failed to start Fish Speech: {e}")
            return False

        deadline = time.time() + max_wait
        while time.time() < deadline:
            if self.check_server():
                logger.info("Fish Speech server is ready!")
                self._fish_available = True
                return True
            time.sleep(3)

        logger.warning(f"Fish Speech did not start within {max_wait}s")
        return False

    # ─── Public API ────────────────────────────────────

    def generate(
        self,
        text: str,
        output_dir: str,
        filename: str = "voice",
        voice_id: Optional[str] = None,
    ) -> VoiceGenResult:
        """
        Generate voice audio for text. Tries Fish Speech first, then Edge TTS.

        Args:
            text: Narration text (Arabic).
            output_dir: Directory to save output MP3.
            filename: Output filename (without extension).
            voice_id: Optional voice profile ID for voice cloning.

        Returns:
            VoiceGenResult with path to generated audio.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        mp3_path = str(Path(output_dir) / f"{filename}.mp3")

        # Resolve voice profile
        voice_profile = None
        if voice_id:
            from src.phase5_production.voice_cloner import VoiceCloner
            cloner = VoiceCloner()
            voice_profile = cloner.get_voice(voice_id)
            if not voice_profile:
                logger.warning(f"Voice profile '{voice_id}' not found, using default")
        elif not voice_id:
            # Try default voice
            from src.phase5_production.voice_cloner import VoiceCloner
            cloner = VoiceCloner()
            default_id = cloner.get_default_voice_id()
            if default_id:
                voice_profile = cloner.get_voice(default_id)

        # Auto-detect Fish Speech if not checked yet
        if not self._fish_available:
            self._fish_available = self.check_server()
            if not self._fish_available:
                # Try to start it
                self.ensure_server()

        # Fish Speech ONLY — NO Edge TTS fallback
        # Edge TTS produces completely different voice = unusable
        if not self._fish_available:
            self._fish_available = self.check_server()
            if not self._fish_available:
                # Try starting server (reset the flag first)
                self._server_start_attempted = False
                self.ensure_server(max_wait=180)
        
        if not self._fish_available:
            return VoiceGenResult(
                success=False, error="Fish Speech server not available — cannot generate voice"
            )

        result = self._generate_fish_speech(text, output_dir, filename, mp3_path, voice_profile=voice_profile)
        return result

    def generate_directed(
        self,
        text: str,
        output_dir: str,
        filename: str = "voice",
        voice_id: Optional[str] = None,
    ) -> VoiceGenResult:
        """
        Generate voice with dramatic direction — varying pace, pauses, and emotion.
        
        Uses VoiceDirector to split text into emotional segments,
        generates each with tailored TTS parameters, applies post-processing
        (speed adjustment, silence gaps), then concatenates into final audio.
        
        This produces MUCH more dynamic output vs flat single-pass generation.
        """
        from src.phase5_production.voice_director import VoiceDirector, DirectedSegment

        director = VoiceDirector()
        segments = director.direct(text)

        if not segments:
            logger.warning("VoiceDirector returned no segments, falling back to flat generate")
            return self.generate(text, output_dir, filename, voice_id)

        if len(segments) == 1:
            # Single segment — just use directed params
            seg = segments[0]
            return self.generate(text, output_dir, filename, voice_id)

        logger.info(f"Directed generation: {len(segments)} segments")

        # Generate each segment separately
        seg_dir = str(Path(output_dir) / f"_segments_{filename}")
        Path(seg_dir).mkdir(parents=True, exist_ok=True)

        segment_paths = []
        for i, seg in enumerate(segments):
            seg_filename = f"seg_{i:03d}"
            seg_mp3 = str(Path(seg_dir) / f"{seg_filename}.mp3")
            seg_wav = str(Path(seg_dir) / f"{seg_filename}.wav")

            logger.info(
                f"  Segment {i+1}/{len(segments)}: [{seg.segment_type}] "
                f"temp={seg.temperature} speed={seg.speed_factor} "
                f"pause_after={seg.pause_after_ms}ms"
            )

            # Generate with segment-specific params
            result = self._generate_segment(
                text=seg.text,
                output_dir=seg_dir,
                filename=seg_filename,
                voice_id=voice_id,
                temperature=seg.temperature,
                top_p=seg.top_p,
                repetition_penalty=seg.repetition_penalty,
            )

            if not result.success:
                logger.warning(f"  Segment {i+1} failed: {result.error}, skipping")
                continue

            audio_path = result.audio_path

            # Post-process chain (8 steps, order matters):
            # breath → coloring → micro-emotion → cadence → de-essing
            # → vocal fry → speed → volume → pauses

            # 1. Breath adjustment (biological breath depth)
            if hasattr(seg, 'breath_depth'):
                audio_path = director.adjust_breath(audio_path, seg.breath_depth)

            # 2. Voice coloring (EQ, pitch shift, compression per segment type)
            audio_path = director.apply_coloring(audio_path, seg.segment_type)

            # 3. Micro-emotion (tremolo for tragedy, smile for triumph)
            if hasattr(seg, 'micro_emotion') and seg.micro_emotion != "neutral":
                audio_path = director.apply_micro_emotion(audio_path, seg.micro_emotion)

            # 4. Cadence modification (rising/sustained endings)
            if hasattr(seg, 'cadence') and seg.cadence != "falling":
                audio_path = director.apply_cadence(audio_path, seg.cadence)

            # 5. De-essing (tame harsh sibilants — س ص ش)
            audio_path = director.apply_deessing(audio_path)

            # 6. Vocal fry (subtle crackle at phrase endings)
            # Apply to dramatic/mystery/climax/revelation — not whisper or excitement
            if seg.segment_type in ("dramatic", "mystery", "climax", "revelation", "narration"):
                fry_intensity = seg.intensity * 0.4  # Scale with drama level
                audio_path = director.apply_vocal_fry(audio_path, intensity=fry_intensity)

            # 7. Speed adjustment
            if abs(seg.speed_factor - 1.0) > 0.02:
                audio_path = director.adjust_speed(audio_path, seg.speed_factor)

            # 8. Volume adjustment (whisper quieter, climax louder)
            if hasattr(seg, 'volume_db') and abs(seg.volume_db) > 0.3:
                audio_path = director.adjust_volume(audio_path, seg.volume_db)

            # 9. Add pauses (randomized for organic feel)
            if seg.pause_before_ms > 0 or seg.pause_after_ms > 0:
                audio_path = director.add_silence(
                    audio_path, before_ms=seg.pause_before_ms, after_ms=seg.pause_after_ms
                )

            segment_paths.append(audio_path)

        if not segment_paths:
            return VoiceGenResult(success=False, error="All segments failed")

        # Concatenate all segments
        final_mp3 = str(Path(output_dir) / f"{filename}.mp3")
        success = director.concat_segments(segment_paths, final_mp3)

        # Cleanup segment dir
        try:
            import shutil as _shutil
            _shutil.rmtree(seg_dir, ignore_errors=True)
        except Exception:
            pass

        if success:
            duration = self._get_audio_duration(final_mp3)
            return VoiceGenResult(
                success=True,
                audio_path=final_mp3,
                duration_sec=duration,
                engine="fish_speech_directed",
            )
        else:
            return VoiceGenResult(success=False, error="Failed to concat segments")

    def _generate_segment(
        self,
        text: str,
        output_dir: str,
        filename: str,
        voice_id: Optional[str] = None,
        **kwargs,
    ) -> VoiceGenResult:
        """Generate a single segment with custom TTS parameters."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        mp3_path = str(Path(output_dir) / f"{filename}.mp3")

        # Resolve voice profile
        voice_profile = None
        if voice_id:
            from src.phase5_production.voice_cloner import VoiceCloner
            cloner = VoiceCloner()
            voice_profile = cloner.get_voice(voice_id)
        if not voice_profile:
            from src.phase5_production.voice_cloner import VoiceCloner
            cloner = VoiceCloner()
            default_id = cloner.get_default_voice_id()
            if default_id:
                voice_profile = cloner.get_voice(default_id)

        if not self._fish_available:
            self._fish_available = self.check_server()

        if self._fish_available:
            return self._generate_fish_speech(
                text, output_dir, filename, mp3_path,
                voice_profile=voice_profile, **kwargs
            )

        return VoiceGenResult(success=False, error="Fish Speech not available")

    def generate_batch(
        self,
        scenes: list[dict],
        output_dir: str,
        voice_id: Optional[str] = None,
    ) -> list[VoiceGenResult]:
        """
        Generate voice for a list of scenes.

        Each scene dict needs:
            - scene_index: int
            - narration_text: str

        Returns list of VoiceGenResult in scene order.
        """
        results = []
        total = len(scenes)

        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            text = scene.get("narration_text", "")
            if not text or not text.strip():
                logger.warning(f"Scene {idx} has no narration text, skipping")
                results.append(VoiceGenResult(success=False, error="No narration text"))
                continue

            logger.info(f"Generating voice {i + 1}/{total} (scene {idx})")
            result = self.generate(
                text=text,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                voice_id=voice_id,
            )
            results.append(result)

        passed = sum(1 for r in results if r.success)
        logger.info(f"Voice batch complete: {passed}/{total} generated")
        return results

    # ─── Fish Speech Engine ────────────────────────────

    def _ensure_reference_uploaded(self, voice_profile) -> str:
        """Upload voice reference to Fish Speech server if not already there. Returns reference_id."""
        ref_id = voice_profile.voice_id
        
        # Check if already uploaded
        try:
            r = self._session.get(f"{self.config.fish_speech_url}/v1/references/list", timeout=10)
            if r.status_code == 200:
                import ormsgpack as _omp
                try:
                    data = _omp.unpackb(r.content)
                except Exception:
                    try:
                        data = r.json()
                    except Exception:
                        data = {}
                if ref_id in data.get("reference_ids", data.get(b"reference_ids", [])):
                    logger.info(f"Reference '{ref_id}' already on server")
                    return ref_id
        except Exception as e:
            logger.warning(f"Failed to check references: {e}")

        # Upload reference with transcription text
        ref_audio_path = voice_profile.reference_audio
        if not Path(ref_audio_path).exists():
            raise RuntimeError(f"Reference audio not found: {ref_audio_path}")

        # Read the reference text (stored alongside the audio as .lab file, or use a generic Arabic phrase)
        ref_text = ""
        lab_path = Path(ref_audio_path).with_suffix(".lab")
        if lab_path.exists():
            ref_text = lab_path.read_text(encoding="utf-8").strip()
        
        if not ref_text:
            # Try to get text from voice profile metadata
            meta_path = Path(ref_audio_path).parent.parent / f"{ref_id}.json"
            if meta_path.exists():
                import json
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                ref_text = meta.get("reference_text", "")

        if not ref_text:
            # Use a generic Arabic text as placeholder — better than empty
            ref_text = "هذا نموذج صوتي للتعرف على نبرة وطريقة النطق"
            logger.warning(f"No reference text for '{ref_id}', using placeholder")

        logger.info(f"Uploading reference '{ref_id}' to Fish Speech server (text: {ref_text[:50]}...)")

        with open(ref_audio_path, "rb") as f:
            audio_bytes = f.read()

        try:
            import ormsgpack
            # Use multipart form upload
            r = self._session.post(
                f"{self.config.fish_speech_url}/v1/references/add",
                files={"audio": (f"{ref_id}.wav", audio_bytes, "audio/wav")},
                data={"id": ref_id, "text": ref_text},
                timeout=30,
            )
            if r.status_code in (200, 201):
                logger.info(f"Reference '{ref_id}' uploaded successfully")
                return ref_id
            elif r.status_code == 409:
                logger.info(f"Reference '{ref_id}' already exists (409)")
                return ref_id
            else:
                logger.error(f"Failed to upload reference: {r.status_code} {r.text[:200]}")
        except Exception as e:
            logger.error(f"Failed to upload reference: {e}")

        return None

    def _generate_fish_speech(
        self, text: str, output_dir: str, filename: str, mp3_path: str,
        voice_profile=None, **kwargs,
    ) -> VoiceGenResult:
        """Generate voice using Fish Speech API with retries."""
        import ormsgpack

        wav_path = str(Path(output_dir) / f"{filename}.wav")
        start = time.time()

        # Use reference_id API for better voice cloning
        reference_id = None
        references = []
        if voice_profile and Path(voice_profile.reference_audio).exists():
            # Try to upload and use reference_id (best quality)
            reference_id = self._ensure_reference_uploaded(voice_profile)
            if not reference_id:
                # Fallback: inline reference with text
                logger.warning("reference_id upload failed, using inline reference")
                with open(voice_profile.reference_audio, "rb") as ref_f:
                    ref_audio_bytes = ref_f.read()
                # Try to get reference text
                lab_path = Path(voice_profile.reference_audio).with_suffix(".lab")
                ref_text = ""
                if lab_path.exists():
                    ref_text = lab_path.read_text(encoding="utf-8").strip()
                if not ref_text:
                    ref_text = "هذا نموذج صوتي للتعرف على نبرة وطريقة النطق"
                references = [{"audio": ref_audio_bytes, "text": ref_text}]
            logger.info(f"Using voice profile '{voice_profile.voice_id}' (ref_id={reference_id})")

        # ── Preprocess Arabic text for better pronunciation ──
        from src.phase5_production.arabic_text_processor import process_arabic_for_tts
        processed_text = process_arabic_for_tts(text)

        # TTS parameters tuned for documentary narration:
        # 0.75 temp = slight human-like variation (breathing/pitch micro-changes)
        #   0.7 was good, 0.75 adds ~5% instability = more human
        # 0.7 top_p = good variety without hallucination
        # 1.15 rep_penalty = natural flow (1.2 was slightly restrictive)
        temperature = kwargs.get("temperature", 0.75)
        top_p = kwargs.get("top_p", 0.7)
        repetition_penalty = kwargs.get("repetition_penalty", 1.15)

        request_data = {
            "text": processed_text,
            "references": references,
            "reference_id": reference_id,
            "format": "wav",
            "max_new_tokens": 4096,
            "chunk_length": 150,           # 150 = sweet spot (200 was too fast, 100 too fragmented)
            "top_p": top_p,
            "repetition_penalty": repetition_penalty,
            "temperature": temperature,
            "streaming": False,
            "use_memory_cache": "on" if reference_id else "off",
            "seed": None,
            "normalize": True,
        }

        body = ormsgpack.packb(request_data)

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                # Long texts need more time — Fish Speech generates at ~2-3 tok/s
                # 60s audio ≈ 120 tokens ≈ 60s generation, but with overhead allow 10min
                r = self._session.post(
                    FISH_SPEECH_TTS_URL,
                    data=body,
                    headers={"content-type": "application/msgpack"},
                    timeout=1200,
                )
                if r.status_code == 200:
                    with open(wav_path, "wb") as f:
                        f.write(r.content)

                    # Convert WAV to MP3
                    self._wav_to_mp3(wav_path, mp3_path)

                    duration = self._get_audio_duration(mp3_path)
                    elapsed = round(time.time() - start, 2)

                    # Clean up WAV
                    try:
                        Path(wav_path).unlink()
                    except Exception:
                        pass

                    return VoiceGenResult(
                        success=True,
                        audio_path=mp3_path,
                        duration_sec=duration,
                        engine="fish_speech",
                        generation_time_sec=elapsed,
                    )
                else:
                    last_error = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as e:
                last_error = str(e)

            if attempt < self.config.max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Fish Speech attempt {attempt + 1} failed: {last_error}, retrying in {wait}s...")
                time.sleep(wait)

        return VoiceGenResult(
            success=False,
            engine="fish_speech",
            generation_time_sec=round(time.time() - start, 2),
            error=last_error,
        )

    # ─── Edge TTS Engine ──────────────────────────────

    def _generate_edge_tts(self, text: str, mp3_path: str) -> VoiceGenResult:
        """Generate voice using Edge TTS with retries."""
        start = time.time()
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                import edge_tts

                communicate = edge_tts.Communicate(
                    text=text,
                    voice=self.config.edge_tts_voice,
                    rate=self.config.edge_tts_rate,
                )
                asyncio.get_event_loop().run_until_complete(
                    communicate.save(mp3_path)
                )

                duration = self._get_audio_duration(mp3_path)
                elapsed = round(time.time() - start, 2)

                return VoiceGenResult(
                    success=True,
                    audio_path=mp3_path,
                    duration_sec=duration,
                    engine="edge_tts",
                    generation_time_sec=elapsed,
                )
            except RuntimeError:
                # No event loop or loop is closed — create new one
                try:
                    import edge_tts
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    communicate = edge_tts.Communicate(
                        text=text,
                        voice=self.config.edge_tts_voice,
                        rate=self.config.edge_tts_rate,
                    )
                    loop.run_until_complete(communicate.save(mp3_path))

                    duration = self._get_audio_duration(mp3_path)
                    elapsed = round(time.time() - start, 2)

                    return VoiceGenResult(
                        success=True,
                        audio_path=mp3_path,
                        duration_sec=duration,
                        engine="edge_tts",
                        generation_time_sec=elapsed,
                    )
                except Exception as e:
                    last_error = str(e)
            except Exception as e:
                last_error = str(e)

            if attempt < self.config.max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Edge TTS attempt {attempt + 1} failed: {last_error}, retrying in {wait}s...")
                time.sleep(wait)

        return VoiceGenResult(
            success=False,
            engine="edge_tts",
            generation_time_sec=round(time.time() - start, 2),
            error=last_error,
        )

    # ─── Helpers ──────────────────────────────────────

    @staticmethod
    def _wav_to_mp3(wav_path: str, mp3_path: str):
        """Convert WAV to MP3 with subtle voice deepening for documentary authority.
        
        - Pitch shift: -0.5 semitone (barely noticeable, adds vocal weight)
        - Loudness normalization: -16 LUFS (broadcast standard)
        - No EQ/compression — keeps Fish Speech's natural quality
        """
        # Audio processing chain (order matters):
        # 1. asetrate: pitch down 0.5 semitone (deeper = documentary authority)
        # 2. aresample: restore sample rate after pitch shift
        # 3. highshelf: gentle de-ess (-3dB above 6kHz, tames س ص ش sibilance)
        # 4. loudnorm: broadcast standard -16 LUFS (consistent across clips)
        af_chain = (
            "asetrate=44100*0.9716,"
            "aresample=44100,"
            "equalizer=f=7000:t=h:w=3000:g=-3,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )
        subprocess.run(
            [
                FFMPEG, "-y", "-i", wav_path,
                "-af", af_chain,
                "-codec:a", "libmp3lame", "-qscale:a", "2",
                mp3_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if not Path(mp3_path).exists():
            raise RuntimeError(f"ffmpeg failed to create {mp3_path}")

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        """Get audio duration in seconds using ffmpeg -i (ffprobe may not exist)."""
        try:
            r = subprocess.run(
                [FFMPEG, "-i", audio_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", r.stderr)
            if m:
                h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                return round(h * 3600 + mn * 60 + s + cs / 100, 2)
        except Exception:
            pass
        return 0.0
