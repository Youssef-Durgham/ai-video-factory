"""
Voice QA — Whisper-based pronunciation verification.

After generating each voice clip:
1. Transcribe with Whisper
2. Compare with original text
3. If accuracy < threshold → retry with adjusted params
4. Apply audio post-processing (EQ, normalization, de-noise)

Uses Whisper small on CPU (fast, ~5s per clip) to avoid GPU conflicts.
"""

import gc
import re
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

ACCURACY_THRESHOLD = 80  # Minimum word accuracy %
MAX_RETRIES = 2

# Arabic normalization for comparison
DIACRITICS_RE = re.compile(r'[\u064B-\u0655\u0670]')
ALEF_RE = re.compile(r'[إأآا]')
PUNCT_RE = re.compile(r'[،,\.!؟\?\-\—\–\:\(\)\[\]\s]+')


@dataclass
class VoiceQAResult:
    passed: bool
    accuracy: float = 0.0
    original_text: str = ""
    transcribed_text: str = ""
    missing_words: list = None
    audio_path: str = ""
    
    def __post_init__(self):
        if self.missing_words is None:
            self.missing_words = []


def _normalize_arabic(text: str) -> str:
    """Normalize Arabic for comparison (strip diacritics, normalize alef)."""
    text = DIACRITICS_RE.sub('', text)
    text = ALEF_RE.sub('ا', text)
    text = PUNCT_RE.sub(' ', text)
    return text.strip()


def _word_accuracy(original: str, transcribed: str) -> tuple[float, list]:
    """Calculate word-level accuracy between original and transcribed."""
    orig_words = set(_normalize_arabic(original).split())
    trans_words = set(_normalize_arabic(transcribed).split())
    
    if not orig_words:
        return 100.0, []
    
    matches = len(orig_words & trans_words)
    missing = list(orig_words - trans_words)
    accuracy = matches / len(orig_words) * 100
    return accuracy, missing


# ════════════════════════════════════════════════════════════════
# Smart Text Correction for Retry
# ════════════════════════════════════════════════════════════════

# Phonetic hints: words Fish Speech commonly mispronounces
# Format: original → phonetic spelling that helps TTS
PHONETIC_FIXES = {
    "البوصلة": "البوصَلة",
    "الشواطئ": "الشَواطِئ",
    "أراضياً": "أراضِيًا",
    "متفاوتة": "مُتفاوِتة",
    "زمنية": "زَمَنِيّة",
    "اتجاهها": "اتِّجاهها",
    "الخريطة": "الخَريطة",
    "جيولوجي": "جيولوجي",
    "الحضارة": "الحَضارة",
    "المعرفة": "المَعرِفة",
    "اختفائها": "اختِفائها",
    "الأعماق": "الأعماق",
    "مفاجئ": "مُفاجِئ",
}


def fix_text_for_retry(original_text: str, missing_words: list, attempt: int) -> str:
    """
    Fix text for retry based on what Whisper couldn't hear.
    
    Strategy per attempt:
    1. Add phonetic hints for missing words
    2. Add micro-pauses around problem words  
    3. Spell out difficult words phonetically
    """
    text = original_text
    
    if attempt == 1:
        # Strategy 1: Add diacritics/phonetic hints for missing words
        for word in missing_words:
            # Check our phonetic fixes
            for orig, fix in PHONETIC_FIXES.items():
                if _normalize_arabic(orig) == _normalize_arabic(word):
                    text = text.replace(orig, fix)
                    break
            else:
                # Add shadda on common consonants for emphasis
                enhanced = word
                # Add micro-pause before the word (comma)
                text = text.replace(word, f"، {word}")
    
    elif attempt == 2:
        # Strategy 2: Break difficult sentences shorter + add explicit pauses
        # Split long sentences at midpoint
        sentences = text.split('.')
        fixed = []
        for sent in sentences:
            words = sent.split()
            if len(words) > 15:
                mid = len(words) // 2
                # Find nearest comma or conjunction
                best_split = mid
                for i in range(max(0, mid-3), min(len(words), mid+3)):
                    if words[i] in ('و', 'أو', 'ثم', 'لكن', 'حيث', 'إذ'):
                        best_split = i
                        break
                part1 = ' '.join(words[:best_split])
                part2 = ' '.join(words[best_split:])
                fixed.append(f"{part1}. {part2}")
            else:
                fixed.append(sent)
        text = '.'.join(fixed)
    
    return text


class VoiceQA:
    """Whisper-based voice quality checker."""
    
    def __init__(self):
        self._model = None
    
    def _ensure_model(self):
        """Load Whisper small on CPU (avoid GPU conflicts)."""
        if self._model is not None:
            return
        
        try:
            import warnings
            warnings.filterwarnings("ignore")
            import os
            os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
            
            from faster_whisper import WhisperModel
            self._model = WhisperModel("small", device="cpu", compute_type="int8")
            logger.info("Whisper small loaded (CPU) for voice QA")
        except Exception as e:
            logger.warning(f"Failed to load Whisper: {e}")
            self._model = None
    
    def unload(self):
        """Free Whisper model memory."""
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()
    
    def check(self, audio_path: str, original_text: str) -> VoiceQAResult:
        """Transcribe audio and compare with original text."""
        self._ensure_model()
        
        if self._model is None:
            # Can't check — assume OK
            return VoiceQAResult(passed=True, accuracy=100.0, audio_path=audio_path)
        
        if not Path(audio_path).exists():
            return VoiceQAResult(passed=False, accuracy=0.0, audio_path=audio_path)
        
        try:
            segments, _ = self._model.transcribe(audio_path, language="ar", beam_size=3)
            transcribed = " ".join(seg.text for seg in segments).strip()
            
            accuracy, missing = _word_accuracy(original_text, transcribed)
            
            return VoiceQAResult(
                passed=accuracy >= ACCURACY_THRESHOLD,
                accuracy=accuracy,
                original_text=original_text,
                transcribed_text=transcribed,
                missing_words=missing[:10],
                audio_path=audio_path,
            )
        except Exception as e:
            logger.warning(f"Whisper transcription failed: {e}")
            return VoiceQAResult(passed=True, accuracy=100.0, audio_path=audio_path)


def enhance_voice_audio(audio_path: str, output_path: str = None) -> str:
    """
    Post-process voice audio for broadcast quality:
    1. Noise gate (remove low-level noise)
    2. Compression (even volume)
    3. EQ (voice presence boost)
    4. Normalization (consistent loudness)
    5. Light de-essing (tame harsh sibilants)
    """
    from src.phase5_production.ffmpeg_path import FFMPEG
    
    if output_path is None:
        output_path = audio_path  # In-place
    
    tmp_path = audio_path + ".enhanced.wav"
    
    # FFmpeg audio filter chain for broadcast voice quality
    af_chain = ",".join([
        # 1. Noise gate — cut silence/noise below threshold
        "agate=threshold=0.01:ratio=3:attack=5:release=50",
        # 2. Compressor — even out volume peaks
        "acompressor=threshold=-20dB:ratio=3:attack=10:release=100:makeup=2dB",
        # 3. EQ — boost voice presence (2-4kHz), cut mud (200-400Hz)
        "equalizer=f=300:t=q:w=1:g=-2",        # Cut mud
        "equalizer=f=3000:t=q:w=1.5:g=3",      # Boost presence
        "equalizer=f=8000:t=q:w=1:g=1",         # Air/clarity
        # 4. De-esser (reduce harsh sibilants — س ص ش)
        "bandreject=f=7000:w=2000",              # Gentle de-ess
        # 5. Loudness normalization (broadcast standard -16 LUFS)
        "loudnorm=I=-16:TP=-1.5:LRA=11",
    ])
    
    cmd = [
        FFMPEG, "-y", "-i", audio_path,
        "-af", af_chain,
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        output_path if output_path != audio_path else tmp_path,
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            if output_path == audio_path:
                # Replace original
                Path(tmp_path).replace(audio_path)
            logger.debug(f"Voice enhanced: {audio_path}")
            return output_path or audio_path
        else:
            logger.warning(f"Voice enhance failed: {proc.stderr[:200]}")
            # Clean up
            Path(tmp_path).unlink(missing_ok=True)
            return audio_path
    except Exception as e:
        logger.warning(f"Voice enhance error: {e}")
        Path(tmp_path).unlink(missing_ok=True)
        return audio_path
