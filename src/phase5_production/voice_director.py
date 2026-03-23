"""
VoiceDirector v4 — Broadcast-grade narration with biological breath,
cadence variation, de-essing, vocal fry, and compound word emphasis.

v4 fixes:
1. Biological breath logic — breath depth proportional to upcoming sentence length
2. Cadence variation — rising/sustained endings to maintain dramatic flow
3. De-essing — tame harsh sibilants (س ص ش) with surgical EQ
4. Vocal fry injection — subtle crackle at phrase endings for organic feel
5. Compound word emphasis — slow down long/important terms via text markers

Architecture:
  Text → preprocess (phonetics, compound emphasis) → classify → direct
       → generate TTS → post-process chain:
         coloring → micro-emotion → cadence → de-essing → vocal fry
         → breath adjustment → speed → volume → pauses → concat
"""

import re
import random
import logging
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from src.phase5_production.ffmpeg_path import FFMPEG


# ═══ Segment Types ═══

class SegmentType:
    WHISPER = "whisper"
    MYSTERY = "mystery"
    NARRATION = "narration"
    DRAMATIC = "dramatic"
    EXCITEMENT = "excitement"
    QUESTION = "question"
    REVELATION = "revelation"
    TRANSITION = "transition"
    CLIMAX = "climax"


@dataclass
class DirectedSegment:
    """A text segment with full prosody direction."""
    text: str
    original_text: str = ""        # Before preprocessing
    segment_type: str = SegmentType.NARRATION
    pause_before_ms: int = 0
    pause_after_ms: int = 300
    temperature: float = 0.7
    top_p: float = 0.7
    repetition_penalty: float = 1.2
    speed_factor: float = 1.0
    volume_db: float = 0.0
    intensity: float = 0.5
    cadence: str = "falling"       # falling | rising | sustained
    micro_emotion: str = "neutral" # neutral | tremolo | smile | grave
    breath_depth: str = "normal"   # none | shallow | normal | deep
    char_count: int = 0            # Original text length (for breath logic)


# ═══ Base Parameters per Segment Type ═══

SEGMENT_PARAMS = {
    SegmentType.WHISPER: {
        "pause_before_ms": 300,
        "pause_after_ms": 600,
        "temperature": 0.55,
        "top_p": 0.6,
        "repetition_penalty": 1.1,
        "speed_factor": 0.85,
        "volume_db": -4.0,
        "cadence": "sustained",     # Whisper doesn't drop — stays level
        "micro_emotion": "neutral",
    },
    SegmentType.MYSTERY: {
        "pause_before_ms": 400,
        "pause_after_ms": 700,
        "temperature": 0.7,
        "top_p": 0.7,
        "repetition_penalty": 1.1,
        "speed_factor": 0.88,
        "volume_db": -1.5,
        "cadence": "sustained",     # Mystery stays open — unresolved
        "micro_emotion": "grave",
    },
    SegmentType.NARRATION: {
        "pause_before_ms": 0,
        "pause_after_ms": 300,
        "temperature": 0.75,
        "top_p": 0.75,
        "repetition_penalty": 1.1,
        "speed_factor": 1.0,
        "volume_db": 0.0,
        "cadence": "falling",
        "micro_emotion": "neutral",
    },
    SegmentType.DRAMATIC: {
        "pause_before_ms": 500,
        "pause_after_ms": 800,
        "temperature": 0.85,
        "top_p": 0.85,
        "repetition_penalty": 1.05,
        "speed_factor": 0.90,
        "volume_db": 1.0,
        "cadence": "falling",
        "micro_emotion": "grave",
    },
    SegmentType.EXCITEMENT: {
        "pause_before_ms": 100,
        "pause_after_ms": 300,
        "temperature": 0.9,
        "top_p": 0.88,
        "repetition_penalty": 1.05,
        "speed_factor": 1.08,
        "volume_db": 1.5,
        "cadence": "rising",        # Excitement lifts at the end
        "micro_emotion": "smile",
    },
    SegmentType.QUESTION: {
        "pause_before_ms": 200,
        "pause_after_ms": 700,
        "temperature": 0.8,
        "top_p": 0.8,
        "repetition_penalty": 1.1,
        "speed_factor": 0.93,
        "volume_db": 0.0,
        "cadence": "rising",        # Questions rise naturally
        "micro_emotion": "neutral",
    },
    SegmentType.REVELATION: {
        "pause_before_ms": 600,
        "pause_after_ms": 1000,
        "temperature": 0.88,
        "top_p": 0.85,
        "repetition_penalty": 1.05,
        "speed_factor": 0.82,
        "volume_db": 2.0,
        "cadence": "rising",        # Revelation opens up — invites next thought
        "micro_emotion": "grave",
    },
    SegmentType.TRANSITION: {
        "pause_before_ms": 800,
        "pause_after_ms": 500,
        "temperature": 0.72,
        "top_p": 0.72,
        "repetition_penalty": 1.15,
        "speed_factor": 0.95,
        "volume_db": -0.5,
        "cadence": "rising",        # Transition opens to next section
        "micro_emotion": "neutral",
    },
    SegmentType.CLIMAX: {
        "pause_before_ms": 900,
        "pause_after_ms": 1500,
        "temperature": 0.95,
        "top_p": 0.92,
        "repetition_penalty": 1.0,
        "speed_factor": 0.75,
        "volume_db": 4.0,
        "cadence": "falling",       # Climax resolves — definitive ending
        "micro_emotion": "grave",
    },
}


# ═══ Arabic Keywords ═══

WHISPER_KEYWORDS = [
    "همس", "بهدوء", "بصمت", "سكون", "هادئ", "ناعم", "خافت",
    "رقيق", "بخفة", "لحظة صمت", "تأمل",
]
MYSTERY_KEYWORDS = [
    "غامض", "غموض", "سر", "أسرار", "خفي", "مختبئ", "لغز", "ألغاز",
    "مجهول", "خفايا", "ظل", "ظلام", "غريب", "عجيب", "لا أحد يعلم",
    "ما زال مجهولاً", "بقي مخفياً",
]
DRAMATIC_KEYWORDS = [
    "اختفت", "اختفى", "دمرت", "سقطت", "انهارت", "حرب", "كارثة",
    "مأساة", "صدمة", "فاجأ", "زلزال", "انفجار", "موت", "نهاية",
    "قُتل", "سقوط", "دمار", "خراب",
]
EXCITEMENT_KEYWORDS = [
    "اكتشف", "اكتشاف", "مذهل", "مدهش", "ثورة", "إنجاز", "عظيم",
    "رائع", "مفاجأة", "لا يصدق", "أول مرة", "تاريخي", "غيّر",
    "ضخم", "هائل", "استثنائي", "نجاح", "انتصار", "فوز",
]
REVELATION_KEYWORDS = [
    "الحقيقة", "السر الحقيقي", "ما لم يعرفه", "الصدمة",
    "المفاجأة الكبرى", "لكن", "إلا أن", "في الواقع",
    "الحقيقة المخفية", "ما لم يُقل",
]
CLIMAX_KEYWORDS = [
    "الإجابة", "الجواب النهائي", "الحقيقة الكاملة", "القرار",
    "اللحظة الحاسمة", "النتيجة", "في النهاية", "أخيراً",
]
TRAGEDY_KEYWORDS = [
    "مأساة", "ضحايا", "دماء", "حزن", "فقد", "رحيل", "وداع",
    "دموع", "ألم", "معاناة", "موت", "قتل", "مقتل", "استشهد",
]
TRIUMPH_KEYWORDS = [
    "نجاح", "انتصار", "فوز", "إنجاز", "تحقيق", "حلم", "أمل",
    "فخر", "عزة", "مجد", "بطولة", "ثورة", "تحرر", "حرية",
]
TRANSITION_PATTERNS = [
    r"^في هذا", r"^والآن", r"^لننتقل", r"^أما الآن",
    r"^في الجزء", r"^دعونا", r"^سنأخذكم", r"^لنكشف",
    r"^قبل أن", r"^لكن قبل",
]

# ═══ Arabized Technical Terms — Phonetic Corrections ═══
# Maps common arabized words to versions with diacritics/spacing
# that help Fish Speech pronounce them more naturally

PHONETIC_CORRECTIONS = {
    # Tech terms — add diacritics and micro-pauses for natural flow
    "خوارزميات": "خَوارِزمِيّات",
    "خوارزمية": "خَوارِزمِيّة",
    "ديجيتال": "ديجيتَال",
    "تكنولوجيا": "تِكنولوجيَا",
    "تكنولوجية": "تِكنولوجِيّة",
    "أيديولوجية": "أيديُولوجِيّة",
    "أيديولوجيا": "أيديُولوجيَا",
    "إلكتروني": "إلِكتروني",
    "إلكترونية": "إلِكترونِيّة",
    "ديمقراطية": "ديمُقراطِيّة",
    "بيروقراطية": "بيرُوقراطِيّة",
    "استراتيجية": "اِستِراتيجِيّة",
    "استراتيجي": "اِستِراتيجي",
    "بروتوكول": "بروتوكُول",
    "أوتوماتيكي": "أوتوماتيكي",
    "ميكانيكي": "ميكانيكي",
    "جيوسياسي": "جيُوسِياسي",
    "جيوسياسية": "جيُوسِياسِيّة",
    "إمبراطورية": "إمبَراطورِيّة",
    "إمبراطور": "إمبَراطور",
    "ميتافيزيقي": "ميتافيزيقي",
    "فلسفية": "فَلسَفِيّة",
    "أنثروبولوجيا": "أنثروبولوجيَا",
    "أركيولوجي": "أركيُولوجي",
    "جيولوجي": "جيُولوجي",
    "بيولوجي": "بيُولوجي",
    "هيدروجين": "هَيدروجين",
    "أكسجين": "أُكسِجين",
    "كاربون": "كاربُون",
    "بترول": "بِترول",
    "بتروكيماوي": "بِتروكيماوي",
    "ديناميكي": "ديناميكي",
    "سيناريو": "سيناريُو",
    "بروباغاندا": "بروباغَاندا",
    "بيانات": "بَيانات",
    "تلفزيون": "تِلِفِزيون",
    "راديو": "رَاديُو",
    "فيديو": "فيديُو",
    "كمبيوتر": "كَمبيوتَر",
    "إنترنت": "إنتَرنِت",
    "سوفتوير": "سوفتوِير",
    "هاردوير": "هاردوِير",
    "ساتلايت": "ساتَلايت",
    "بلوتوث": "بلوتوث",
}

# ═══ Hamza/Wasl Corrections ═══
# Common words where hamza gets dropped or wasl misread in fast speech

HAMZA_CORRECTIONS = {
    # Ensure hamzat al-qat' is explicit
    "اكتشف": "اِكتَشَف",
    "اكتشاف": "اِكتِشاف",
    "اختفى": "اِختَفى",
    "اختفت": "اِختَفَت",
    "انهار": "اِنهار",
    "انهارت": "اِنهارَت",
    "استمر": "اِستَمَرّ",
    "استمرت": "اِستَمَرَّت",
    "استطاع": "اِستَطاع",
    "انتشر": "اِنتَشَر",
    "انتشرت": "اِنتَشَرَت",
    "ابتكر": "اِبتَكَر",
    "ابتكار": "اِبتِكار",
    "اعتقد": "اِعتَقَد",
    "اعتقاد": "اِعتِقاد",
    "افترض": "اِفتَرَض",
    "استخدم": "اِستَخدَم",
    "استخدام": "اِستِخدام",
    # Common words with hamzat wasl that need proper articulation
    "الإنسان": "الإنسان",
    "الأرض": "الأَرض",
    "الأمر": "الأَمر",
}


# ═══ Compound/Long Words — Insert Micro-Pauses for Emphasis (fix #5) ═══
# These words are "chewed" slowly by professional narrators
# We insert a zero-width comma (،) to hint Fish Speech to slow down

COMPOUND_EMPHASIS_WORDS = [
    "الذكاء الاصطناعي",
    "الخوارزميات",
    "خوارزميات",
    "تكنولوجيا",
    "إمبراطورية",
    "ميتافيزيقي",
    "أنثروبولوجيا",
    "جيوسياسية",
    "جيوسياسي",
    "بيروقراطية",
    "أيديولوجية",
    "استراتيجية",
    "إلكترونية",
    "بتروكيماوي",
    "ديمقراطية",
    "الاستعمار",
    "الحضارات",
    "الميثولوجيا",
    "الفلسفية",
    "الأركيولوجية",
    "البيولوجية",
    "الجيولوجية",
    "الأنثروبولوجيا",
    "التكنولوجية",
    "الإمبراطورية",
    "الاستراتيجية",
    "الديمقراطية",
    "البيروقراطية",
    "الميكانيكية",
    "الكهرومغناطيسية",
    "الثيرموديناميكية",
]


class VoiceDirector:
    """
    v4: Broadcast-grade narration with biological breath, de-essing,
    vocal fry, compound word emphasis, and organic cadence.
    """

    def __init__(self, seed: int = None):
        """
        Args:
            seed: Random seed for reproducible pacing variation.
                  None = truly random (different each run = more organic).
        """
        self._rng = random.Random(seed)

    def direct(self, text: str) -> list[DirectedSegment]:
        """Split text into directed segments with full prosody control."""
        # Phase 1: Preprocess Arabic text
        text = self._preprocess_arabic(text)

        sentences = self._split_sentences(text)

        segments = []
        total = len([s for s in sentences if s.strip()])

        seg_index = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            original = sentence
            seg_type = self._classify_sentence(sentence, seg_index, total)

            # Detect micro-emotion from content
            micro_emotion = self._detect_micro_emotion(sentence, seg_type)

            params = dict(SEGMENT_PARAMS.get(seg_type, SEGMENT_PARAMS[SegmentType.NARRATION]))
            params["micro_emotion"] = micro_emotion

            # Calculate intensity
            intensity = self._calc_intensity(seg_index, total)
            params["intensity"] = intensity

            # Scale by intensity
            params = self._scale_by_intensity(params, intensity, seg_type)

            # Randomize pacing (fix #1: anti-monotony)
            params = self._randomize_pacing(params, seg_type)

            # Add prosody markers
            directed_text = self._add_prosody_markers(sentence, seg_type, intensity)

            # Fix #1: Biological breath depth based on sentence length
            char_count = len(original)
            breath_depth = self._calc_breath_depth(char_count, seg_type)
            params["breath_depth"] = breath_depth
            params["char_count"] = char_count

            segment = DirectedSegment(
                text=directed_text,
                original_text=original,
                segment_type=seg_type,
                **params,
            )
            segments.append(segment)
            seg_index += 1

        segments = self._apply_arc(segments)

        logger.info(
            f"Directed {len(segments)} segments: "
            + " → ".join(
                f"{s.segment_type}({s.intensity:.0%},{s.cadence[0]},{s.micro_emotion[0]})"
                for s in segments
            )
        )

        return segments

    # ═══ Phase 1: Arabic Text Preprocessing (fixes #3 and #5) ═══

    def _preprocess_arabic(self, text: str) -> str:
        """
        Fix Arabic pronunciation issues before TTS:
        1. Add diacritics to arabized technical terms
        2. Fix hamza/wasl articulation
        3. Add micro-spacing between words that tend to merge
        """
        # Apply phonetic corrections for technical terms
        for term, corrected in PHONETIC_CORRECTIONS.items():
            if term in text:
                text = text.replace(term, corrected)

        # Apply hamza corrections
        for term, corrected in HAMZA_CORRECTIONS.items():
            # Only replace standalone words (not parts of other words)
            text = re.sub(rf'\b{re.escape(term)}\b', corrected, text)

        # Fix common wasl issues: "و الـ" should flow as "وَالـ"
        text = re.sub(r'و\s+ال', 'وَال', text)

        # Add zero-width joiner between words that tend to merge incorrectly
        text = re.sub(r'(\S)(ال[أإاآ])', r'\1 \2', text)

        # Fix #5: Compound word emphasis — add ellipsis BEFORE long terms
        # This creates a micro-pause that makes the narrator "approach" the word
        # deliberately, like a professional narrator emphasizing key terminology
        for compound in COMPOUND_EMPHASIS_WORDS:
            if compound in text:
                # Add "..." before the word for deliberate pacing
                text = text.replace(compound, f"... {compound}", 1)

        return text

    # ═══ Fix #1: Pacing Randomization ═══

    def _randomize_pacing(self, params: dict, seg_type: str) -> dict:
        """
        Add organic variation to pause durations and speed.
        
        Humans don't pause for exactly 300ms every time.
        Real speech has ±20-40% variation in pause length,
        and ±3-5% variation in speaking speed.
        
        This breaks the "too perfect" robotic feel.
        """
        # Pause variation: ±30% (more variation at longer pauses)
        pause_after = params["pause_after_ms"]
        if pause_after > 0:
            jitter = self._rng.uniform(-0.30, 0.30)
            params["pause_after_ms"] = max(50, int(pause_after * (1 + jitter)))

        pause_before = params["pause_before_ms"]
        if pause_before > 0:
            jitter = self._rng.uniform(-0.25, 0.25)
            params["pause_before_ms"] = max(50, int(pause_before * (1 + jitter)))

        # Speed variation: ±4% (subtle but breaks monotony)
        speed = params["speed_factor"]
        speed_jitter = self._rng.uniform(-0.04, 0.04)
        params["speed_factor"] = round(speed + speed_jitter, 3)

        # Occasionally add an unexpected extra pause (human "thinking" moment)
        # ~15% chance for non-whisper, non-climax segments
        if seg_type in (SegmentType.NARRATION, SegmentType.DRAMATIC):
            if self._rng.random() < 0.15:
                params["pause_before_ms"] += self._rng.randint(200, 500)

        return params

    # ═══ Fix #2: Sentence Cadence ═══

    def _get_cadence(self, seg_type: str) -> str:
        """Get cadence type and apply it."""
        return SEGMENT_PARAMS.get(seg_type, {}).get("cadence", "falling")

    # ═══ Fix #4: Micro-Emotion Detection ═══

    def _detect_micro_emotion(self, sentence: str, seg_type: str) -> str:
        """
        Detect subtle emotional coloring for the sentence.
        
        - tremolo: voice quiver for tragedy/loss (subtle vibrato)
        - smile: warmth/brightness for triumph/success
        - grave: deep seriousness for dramatic moments
        - neutral: clean delivery
        """
        # Check for tragedy content
        if any(kw in sentence for kw in TRAGEDY_KEYWORDS):
            return "tremolo"

        # Check for triumph/success content
        if any(kw in sentence for kw in TRIUMPH_KEYWORDS):
            return "smile"

        # Default from segment type
        base = SEGMENT_PARAMS.get(seg_type, {}).get("micro_emotion", "neutral")
        return base

    # ═══ Fix #1: Biological Breath Logic ═══

    def _calc_breath_depth(self, char_count: int, seg_type: str) -> str:
        """
        Calculate breath depth based on upcoming sentence length.
        
        Humans subconsciously inhale proportional to what they're about to say:
        - Short phrase (< 30 chars): no visible breath or tiny catch
        - Medium (30-80 chars): normal breath
        - Long (80-150 chars): deep breath
        - Very long (> 150 chars): very deep, audible breath
        
        Whisper segments: always shallow (soft intake)
        Climax: always deep (dramatic inhale before the big moment)
        """
        if seg_type == SegmentType.WHISPER:
            return "shallow"
        if seg_type == SegmentType.CLIMAX:
            return "deep"

        if char_count < 30:
            return "none"
        elif char_count < 80:
            return "shallow"
        elif char_count < 150:
            return "normal"
        else:
            return "deep"

    # ═══ Core Logic ═══

    def _calc_intensity(self, index: int, total: int) -> float:
        if total <= 1:
            return 0.7
        progress = index / (total - 1)
        intensity = 0.3 + 0.7 * (progress ** 1.4)
        return round(min(1.0, intensity), 2)

    def _scale_by_intensity(self, params: dict, intensity: float, seg_type: str) -> dict:
        params["temperature"] = min(0.95, params["temperature"] + intensity * 0.1)
        params["top_p"] = min(0.93, params["top_p"] + intensity * 0.08)
        params["repetition_penalty"] = max(1.0, params["repetition_penalty"] - intensity * 0.1)
        params["volume_db"] = params.get("volume_db", 0) + intensity * 2.0
        if seg_type not in (SegmentType.EXCITEMENT, SegmentType.WHISPER):
            params["speed_factor"] = params["speed_factor"] - intensity * 0.05
        params["pause_after_ms"] = int(params["pause_after_ms"] + intensity * 200)
        return params

    def _split_sentences(self, text: str) -> list[str]:
        sentences = re.split(r'(?<=[.؟!。])\s*', text)
        result = []
        for s in sentences:
            parts = s.split('\n')
            result.extend(p.strip() for p in parts if p.strip())
        return result

    def _classify_sentence(self, sentence: str, index: int, total: int) -> str:
        if index == total - 1 and total > 2:
            return SegmentType.CLIMAX
        if index == 0:
            return SegmentType.DRAMATIC
        if '؟' in sentence or sentence.endswith('?'):
            return SegmentType.QUESTION
        for pattern in TRANSITION_PATTERNS:
            if re.match(pattern, sentence):
                return SegmentType.TRANSITION

        if any(kw in sentence for kw in CLIMAX_KEYWORDS):
            return SegmentType.CLIMAX
        if any(kw in sentence for kw in WHISPER_KEYWORDS):
            return SegmentType.WHISPER
        if any(kw in sentence for kw in REVELATION_KEYWORDS):
            return SegmentType.REVELATION
        if any(kw in sentence for kw in MYSTERY_KEYWORDS):
            return SegmentType.MYSTERY
        if any(kw in sentence for kw in DRAMATIC_KEYWORDS):
            return SegmentType.DRAMATIC
        if any(kw in sentence for kw in EXCITEMENT_KEYWORDS):
            return SegmentType.EXCITEMENT

        if index == total - 2 and total > 3:
            return SegmentType.REVELATION

        return SegmentType.NARRATION

    def _add_prosody_markers(self, text: str, seg_type: str, intensity: float) -> str:
        if seg_type == SegmentType.WHISPER:
            text = text.replace("،", "،...")
            return text
        if seg_type == SegmentType.MYSTERY:
            for kw in MYSTERY_KEYWORDS:
                if kw in text:
                    text = text.replace(kw, f"... {kw}", 1)
                    break
            return text
        if seg_type == SegmentType.DRAMATIC:
            if intensity > 0.5:
                text = f"... {text}"
            return text
        if seg_type == SegmentType.REVELATION:
            for trigger in ["لكن", "إلا أن", "في الواقع", "الحقيقة"]:
                if trigger in text:
                    text = text.replace(trigger, f"{trigger}...", 1)
                    break
            return text
        if seg_type == SegmentType.QUESTION:
            text = f"... {text}"
            return text
        if seg_type == SegmentType.CLIMAX:
            text = f"... {text}"
            if not text.endswith('!') and not text.endswith('؟'):
                text = text.rstrip('.') + '!'
            return text
        if seg_type == SegmentType.EXCITEMENT:
            if not text.endswith('!'):
                text = text.rstrip('.') + '!'
            return text
        return text

    def _apply_arc(self, segments: list[DirectedSegment]) -> list[DirectedSegment]:
        if len(segments) <= 2:
            return segments

        # Break narration monotony
        narration_streak = 0
        for i, seg in enumerate(segments):
            if seg.segment_type == SegmentType.NARRATION:
                narration_streak += 1
                if narration_streak >= 3:
                    seg.temperature = min(0.9, seg.temperature + 0.08)
                    seg.speed_factor -= 0.05
                    seg.pause_after_ms += 200
                    seg.volume_db += 1.0
                    narration_streak = 0
            else:
                narration_streak = 0

        # Whisper contrast
        for i, seg in enumerate(segments):
            if seg.segment_type == SegmentType.WHISPER:
                if i > 0 and segments[i-1].volume_db < 1.0:
                    segments[i-1].volume_db += 1.5
                if i < len(segments) - 1 and segments[i+1].volume_db < 1.0:
                    segments[i+1].volume_db += 1.5

        # Ensure climax is loudest
        if segments:
            last = segments[-1]
            max_vol = max(s.volume_db for s in segments[:-1]) if len(segments) > 1 else 0
            if last.volume_db <= max_vol:
                last.volume_db = max_vol + 2.0
            last.temperature = max(last.temperature, 0.92)
            last.speed_factor = min(last.speed_factor, 0.82)

        # Alternate cadence to avoid monotony (fix #2)
        # Don't have 3+ falling cadences in a row
        falling_streak = 0
        for seg in segments:
            if seg.cadence == "falling":
                falling_streak += 1
                if falling_streak >= 3:
                    seg.cadence = "sustained"  # Break the pattern
                    falling_streak = 0
            else:
                falling_streak = 0

        return segments

    # ═══ Audio Coloring Chains ═══

    COLORING_CHAINS = {
        SegmentType.WHISPER: {
            "filters": [
                "asetrate=44100*1.02,aresample=44100",
                "equalizer=f=200:t=h:w=200:g=-3",
                "equalizer=f=3000:t=h:w=1000:g=2",
                "compand=attacks=0.1:decays=0.3:points=-80/-80|-30/-30|-20/-15|0/-10:gain=2",
            ],
        },
        SegmentType.MYSTERY: {
            "filters": [
                "asetrate=44100*0.97,aresample=44100",
                "equalizer=f=150:t=h:w=100:g=3",
                "equalizer=f=800:t=h:w=400:g=-1",
                "equalizer=f=4000:t=h:w=2000:g=-2",
            ],
        },
        SegmentType.DRAMATIC: {
            "filters": [
                "equalizer=f=120:t=h:w=80:g=2",
                "equalizer=f=2500:t=h:w=1000:g=2",
                "compand=attacks=0.05:decays=0.2:points=-80/-80|-20/-15|0/-5:gain=3",
            ],
        },
        SegmentType.CLIMAX: {
            "filters": [
                "asetrate=44100*0.96,aresample=44100",
                "equalizer=f=100:t=h:w=80:g=4",
                "equalizer=f=250:t=h:w=100:g=2",
                "equalizer=f=2800:t=h:w=800:g=3",
                "equalizer=f=6000:t=h:w=2000:g=1",
                "compand=attacks=0.03:decays=0.15:points=-80/-80|-20/-12|0/-3:gain=4",
            ],
        },
        SegmentType.EXCITEMENT: {
            "filters": [
                "asetrate=44100*1.01,aresample=44100",
                "equalizer=f=3000:t=h:w=1500:g=3",
                "equalizer=f=5000:t=h:w=2000:g=1",
                "compand=attacks=0.05:decays=0.2:points=-80/-80|-20/-12|0/-5:gain=3",
            ],
        },
        SegmentType.REVELATION: {
            "filters": [
                "asetrate=44100*0.98,aresample=44100",
                "equalizer=f=150:t=h:w=100:g=3",
                "equalizer=f=2500:t=h:w=1000:g=3",
                "compand=attacks=0.04:decays=0.2:points=-80/-80|-20/-12|0/-4:gain=3",
            ],
        },
        SegmentType.QUESTION: {
            "filters": [
                "equalizer=f=2000:t=h:w=1000:g=1.5",
                "equalizer=f=4000:t=h:w=1500:g=1",
            ],
        },
    }

    # ═══ Micro-Emotion Filters (fix #4) ═══

    MICRO_EMOTION_FILTERS = {
        "tremolo": {
            # Subtle voice quiver — like holding back tears
            # vibrato at 5Hz, very subtle depth
            "filters": ["vibrato=f=5:d=0.15"],
        },
        "smile": {
            # "Smiling" voice — slight brightness, gentle compression
            # Brightens formants without changing pitch
            "filters": [
                "equalizer=f=2500:t=h:w=800:g=1.5",
                "equalizer=f=4500:t=h:w=1000:g=1",
            ],
        },
        "grave": {
            # Deep seriousness — subtle bass reinforcement
            "filters": [
                "equalizer=f=130:t=h:w=80:g=1.5",
                "equalizer=f=300:t=h:w=100:g=0.5",
            ],
        },
        # "neutral": no filters
    }

    # ═══ Cadence Filters (fix #2) ═══

    CADENCE_FILTERS = {
        "rising": {
            # Last 15% of audio: slight pitch up to keep listener hooked
            # Uses asetrate trick on a split+concat, but simpler:
            # We boost high-end slightly at the tail
            "tail_filters": [
                "equalizer=f=3500:t=h:w=1500:g=2",
                "equalizer=f=5000:t=h:w=2000:g=1.5",
            ],
            "tail_pct": 0.15,
        },
        "sustained": {
            # Level ending — no drop. Mild compression at tail
            "tail_filters": [
                "compand=attacks=0.1:decays=0.5:points=-80/-80|-20/-18|0/-8:gain=2",
            ],
            "tail_pct": 0.20,
        },
        # "falling": natural TTS behavior — no modification needed
    }

    def apply_coloring(self, audio_path: str, seg_type: str, output_path: str = None) -> str:
        """Apply voice coloring filter chain."""
        chain = self.COLORING_CHAINS.get(seg_type)
        if not chain or not chain.get("filters"):
            return audio_path

        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.color.wav'))
        filter_str = ",".join(chain["filters"])

        try:
            result = subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-af", filter_str, temp_path],
                capture_output=True, timeout=30,
            )
            if Path(temp_path).exists() and Path(temp_path).stat().st_size > 0:
                Path(temp_path).replace(output_path)
                return output_path
        except Exception as e:
            logger.warning(f"Coloring failed [{seg_type}]: {e}")

        return audio_path

    def apply_micro_emotion(self, audio_path: str, emotion: str, output_path: str = None) -> str:
        """Apply micro-emotion audio effect."""
        if emotion == "neutral" or emotion not in self.MICRO_EMOTION_FILTERS:
            return audio_path

        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.emo.wav'))
        filters = self.MICRO_EMOTION_FILTERS[emotion]["filters"]
        filter_str = ",".join(filters)

        try:
            result = subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-af", filter_str, temp_path],
                capture_output=True, timeout=30,
            )
            if Path(temp_path).exists() and Path(temp_path).stat().st_size > 0:
                Path(temp_path).replace(output_path)
                return output_path
        except Exception as e:
            logger.warning(f"Micro-emotion failed [{emotion}]: {e}")

        return audio_path

    def apply_cadence(self, audio_path: str, cadence: str, output_path: str = None) -> str:
        """
        Apply cadence modification to sentence ending.
        
        For 'rising': boost high frequencies in the last 15% of audio
        For 'sustained': compress the tail to prevent natural drop-off
        For 'falling': do nothing (natural TTS behavior)
        """
        if cadence == "falling" or cadence not in self.CADENCE_FILTERS:
            return audio_path

        cad = self.CADENCE_FILTERS[cadence]
        tail_filters = cad.get("tail_filters", [])
        tail_pct = cad.get("tail_pct", 0.15)

        if not tail_filters:
            return audio_path

        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.cad.wav'))

        # Get audio duration
        duration = self._get_duration(audio_path)
        if duration <= 0:
            return audio_path

        tail_start = duration * (1 - tail_pct)
        filter_str = ",".join(tail_filters)

        # Strategy: split audio into head + tail, process tail, concat
        head_path = str(Path(audio_path).with_suffix('.head.wav'))
        tail_path = str(Path(audio_path).with_suffix('.tail.wav'))
        tail_proc_path = str(Path(audio_path).with_suffix('.tailp.wav'))

        try:
            # Extract head (unmodified)
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-t", str(tail_start), head_path],
                capture_output=True, timeout=15,
            )
            # Extract tail
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-ss", str(tail_start), tail_path],
                capture_output=True, timeout=15,
            )
            # Process tail
            subprocess.run(
                [FFMPEG, "-y", "-i", tail_path, "-af", filter_str, tail_proc_path],
                capture_output=True, timeout=15,
            )

            # Concat
            list_file = str(Path(audio_path).with_suffix('.cadlist.txt'))
            with open(list_file, 'w') as f:
                f.write(f"file '{Path(head_path).resolve()}'\n")
                f.write(f"file '{Path(tail_proc_path).resolve()}'\n")

            subprocess.run(
                [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", temp_path],
                capture_output=True, timeout=15,
            )

            # Cleanup
            for p in [head_path, tail_path, tail_proc_path, list_file]:
                Path(p).unlink(missing_ok=True)

            if Path(temp_path).exists() and Path(temp_path).stat().st_size > 0:
                Path(temp_path).replace(output_path)
                return output_path

        except Exception as e:
            logger.warning(f"Cadence modification failed [{cadence}]: {e}")
            for p in [head_path, tail_path, tail_proc_path, temp_path]:
                Path(p).unlink(missing_ok=True)

        return audio_path

    @staticmethod
    def _get_duration(audio_path: str) -> float:
        """Get audio duration in seconds."""
        try:
            r = subprocess.run(
                [FFMPEG, "-i", audio_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=10,
            )
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", r.stderr)
            if m:
                h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                return h * 3600 + mn * 60 + s + cs / 100
        except Exception:
            pass
        return 0.0

    # ═══ Fix #3: De-Essing (Sibilance Control) ═══

    @staticmethod
    def apply_deessing(audio_path: str, output_path: str = None) -> str:
        """
        Tame harsh sibilants (س ص ش = S, Ṣ, Sh sounds).
        
        Uses a surgical high-shelf EQ cut in the 5-9kHz range where
        sibilance lives, plus a narrow notch at the worst frequency.
        This is what broadcast engineers call a "de-esser".
        
        Applied to ALL segments as a mastering step.
        """
        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.deess.wav'))

        # Broadcast-grade Arabic de-esser chain:
        # Arabic سين/صاد sibilance peaks at 5.5-7.5kHz (wider than English)
        # 1. Wide cut across the full sibilance band (5.5-7.5kHz)
        # 2. Narrow notch at the sharpest peak (6.5kHz)
        # 3. Gentle shelf above 8kHz to soften digital harshness
        # 4. Warmth compensation at 3.5-4kHz (keep vocal presence)
        filters = [
            "equalizer=f=5500:t=q:w=1.5:g=-3",    # Lower sibilance band (سياسة)
            "equalizer=f=6500:t=q:w=2:g=-5",       # Peak sibilance notch (سيحكم)
            "equalizer=f=7500:t=q:w=1.5:g=-3",    # Upper sibilance band
            "equalizer=f=9000:t=h:w=3000:g=-2",   # High shelf — digital harshness
            "equalizer=f=3800:t=h:w=800:g=1.5",   # Warmth compensation
        ]

        try:
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-af", ",".join(filters), temp_path],
                capture_output=True, timeout=30,
            )
            if Path(temp_path).exists() and Path(temp_path).stat().st_size > 0:
                Path(temp_path).replace(output_path)
                return output_path
        except Exception as e:
            logger.warning(f"De-essing failed: {e}")

        return audio_path

    # ═══ Fix #4: Vocal Fry Injection ═══

    @staticmethod
    def apply_vocal_fry(audio_path: str, intensity: float = 0.5, output_path: str = None) -> str:
        """
        Add subtle vocal fry (creaky voice) at the tail of the audio.
        
        Vocal fry = low-frequency irregular vibration that appears at the end
        of breath when vocal cords relax. It's the "crackle" that makes a
        voice sound human and lived-in, not lab-clean.
        
        Implementation: 
        - Extract last 8-12% of audio
        - Apply subtle distortion (aflimiter with soft clip)
        - Add very low frequency rumble (20-60Hz)
        - Blend back at reduced volume
        
        Higher intensity = more noticeable fry (0.0-1.0)
        """
        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.fry.wav'))

        # Get duration
        duration = VoiceDirector._get_duration(audio_path)
        if duration < 1.0:
            return audio_path

        # Vocal fry region: last 10% of audio
        fry_pct = 0.10
        fry_start = duration * (1 - fry_pct)

        # Scale effect by intensity
        distortion_gain = 1 + intensity * 3    # 1-4
        rumble_vol = -20 + intensity * 8       # -20 to -12 dB
        blend_vol = -6 + intensity * 3         # -6 to -3 dB

        head_path = str(Path(audio_path).with_suffix('.fryh.wav'))
        tail_path = str(Path(audio_path).with_suffix('.fryt.wav'))
        tail_proc = str(Path(audio_path).with_suffix('.frytp.wav'))

        try:
            # Split
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-t", str(fry_start), head_path],
                capture_output=True, timeout=15,
            )
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-ss", str(fry_start), tail_path],
                capture_output=True, timeout=15,
            )

            # Process tail: soft clip + low rumble + slight pitch irregularity
            fry_filters = [
                f"volume={distortion_gain}",
                "alimiter=limit=0.8:attack=1:release=10",  # Soft clip = crackle
                f"equalizer=f=40:t=h:w=30:g={rumble_vol + 30}",  # Sub rumble
                "equalizer=f=80:t=h:w=40:g=2",              # Low growl
                "equalizer=f=5000:t=h:w=3000:g=-3",          # Tame highs
                f"volume={blend_vol}dB",                     # Pull back to blend level
            ]

            subprocess.run(
                [FFMPEG, "-y", "-i", tail_path, "-af", ",".join(fry_filters), tail_proc],
                capture_output=True, timeout=15,
            )

            # Concat head + processed tail
            list_file = str(Path(audio_path).with_suffix('.frylist.txt'))
            with open(list_file, 'w') as f:
                f.write(f"file '{Path(head_path).resolve()}'\n")
                f.write(f"file '{Path(tail_proc).resolve()}'\n")

            subprocess.run(
                [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                 "-c", "copy", temp_path],
                capture_output=True, timeout=15,
            )

            # Cleanup
            for p in [head_path, tail_path, tail_proc, list_file]:
                Path(p).unlink(missing_ok=True)

            if Path(temp_path).exists() and Path(temp_path).stat().st_size > 0:
                Path(temp_path).replace(output_path)
                return output_path

        except Exception as e:
            logger.warning(f"Vocal fry failed: {e}")
            for p in [head_path, tail_path, tail_proc, temp_path]:
                Path(p).unlink(missing_ok=True)

        return audio_path

    # ═══ Fix #1: Breath Adjustment ═══

    @staticmethod
    def adjust_breath(audio_path: str, breath_depth: str, output_path: str = None) -> str:
        """
        Adjust the breath sound at the start of audio to match biological expectation.
        
        Strategy:
        - "none": Trim any initial silence/breath (first 100ms)
        - "shallow": Keep breath short, reduce its volume
        - "normal": No change (trust TTS default)
        - "deep": Extend initial breath region, boost low frequencies in it
        
        This breaks the "breathe every X seconds" pattern by making each
        breath proportional to the sentence it precedes.
        """
        if breath_depth == "normal":
            return audio_path

        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.breath.wav'))

        try:
            if breath_depth == "none":
                # Trim first 80ms (removes unnecessary micro-breath)
                subprocess.run(
                    [FFMPEG, "-y", "-ss", "0.08", "-i", audio_path, temp_path],
                    capture_output=True, timeout=15,
                )
            elif breath_depth == "shallow":
                # Reduce volume of first 150ms by 6dB
                subprocess.run(
                    [FFMPEG, "-y", "-i", audio_path, "-af",
                     "volume=enable='lt(t,0.15)':volume=-6dB",
                     temp_path],
                    capture_output=True, timeout=15,
                )
            elif breath_depth == "deep":
                # Boost bass in first 200ms + extend by 50ms silence before
                subprocess.run(
                    [FFMPEG, "-y", "-i", audio_path, "-af",
                     "adelay=50|50,"
                     "equalizer=f=100:t=h:w=80:g=3:enable='lt(t,0.25)'",
                     temp_path],
                    capture_output=True, timeout=15,
                )

            if Path(temp_path).exists() and Path(temp_path).stat().st_size > 0:
                Path(temp_path).replace(output_path)
                return output_path

        except Exception as e:
            logger.warning(f"Breath adjustment failed [{breath_depth}]: {e}")

        return audio_path

    # ═══ Standard Post-Processing ═══

    @staticmethod
    def adjust_volume(audio_path: str, volume_db: float, output_path: str = None) -> str:
        if abs(volume_db) < 0.3:
            return audio_path
        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.tmp.wav'))
        try:
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-af", f"volume={volume_db}dB", temp_path],
                capture_output=True, timeout=30,
            )
            if Path(temp_path).exists():
                Path(temp_path).replace(output_path)
                return output_path
        except Exception as e:
            logger.warning(f"Volume adjustment failed: {e}")
        return audio_path

    @staticmethod
    def add_silence(audio_path: str, before_ms: int = 0, after_ms: int = 0, output_path: str = None) -> str:
        if before_ms == 0 and after_ms == 0:
            return audio_path
        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.tmp.wav'))
        filters = []
        if before_ms > 0:
            filters.append(f"adelay={before_ms}|{before_ms}")
        if after_ms > 0:
            filters.append(f"apad=pad_dur={after_ms}ms")
        try:
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-af", ",".join(filters), temp_path],
                capture_output=True, timeout=30,
            )
            if Path(temp_path).exists():
                Path(temp_path).replace(output_path)
                return output_path
        except Exception as e:
            logger.warning(f"Silence failed: {e}")
        return audio_path

    @staticmethod
    def adjust_speed(audio_path: str, speed_factor: float, output_path: str = None) -> str:
        if abs(speed_factor - 1.0) < 0.02:
            return audio_path
        output_path = output_path or audio_path
        temp_path = str(Path(audio_path).with_suffix('.tmp.wav'))
        speed = max(0.5, min(2.0, speed_factor))
        try:
            subprocess.run(
                [FFMPEG, "-y", "-i", audio_path, "-af", f"atempo={speed}", temp_path],
                capture_output=True, timeout=30,
            )
            if Path(temp_path).exists():
                Path(temp_path).replace(output_path)
                return output_path
        except Exception as e:
            logger.warning(f"Speed adjustment failed: {e}")
        return audio_path

    @staticmethod
    def concat_segments(segment_paths: list[str], output_path: str) -> bool:
        if not segment_paths:
            return False
        list_path = str(Path(output_path).with_suffix('.txt'))
        with open(list_path, 'w', encoding='utf-8') as f:
            for p in segment_paths:
                f.write(f"file '{Path(p).resolve()}'\n")
        try:
            subprocess.run(
                [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                 "-codec:a", "libmp3lame", "-qscale:a", "2", output_path],
                capture_output=True, timeout=120,
            )
            Path(list_path).unlink(missing_ok=True)
            return Path(output_path).exists()
        except Exception as e:
            logger.error(f"Concat failed: {e}")
            Path(list_path).unlink(missing_ok=True)
            return False
