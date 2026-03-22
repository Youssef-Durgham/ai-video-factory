"""
Arabic Text Processor for TTS — improves pacing, pauses, and emphasis.

Fish Speech S2-Pro doesn't support SSML, but responds to:
- Ellipsis (...) → creates natural pauses/breathing
- Period (.) → sentence boundary pause
- Comma (،) → clause pause
- Question mark (؟) → rising intonation
- Exclamation (!) → emphasis

This module preprocesses Arabic text to maximize natural delivery.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# Number to Arabic words
# ════════════════════════════════════════════════════════════════

ONES = {
    0: "", 1: "واحد", 2: "اثنان", 3: "ثلاثة", 4: "أربعة", 5: "خمسة",
    6: "ستة", 7: "سبعة", 8: "ثمانية", 9: "تسعة", 10: "عشرة",
    11: "أحد عشر", 12: "اثنا عشر", 13: "ثلاثة عشر", 14: "أربعة عشر",
    15: "خمسة عشر", 16: "ستة عشر", 17: "سبعة عشر", 18: "ثمانية عشر",
    19: "تسعة عشر",
}
TENS = {
    2: "عشرون", 3: "ثلاثون", 4: "أربعون", 5: "خمسون",
    6: "ستون", 7: "سبعون", 8: "ثمانون", 9: "تسعون",
}
HUNDREDS = {
    1: "مئة", 2: "مئتان", 3: "ثلاثمئة", 4: "أربعمئة", 5: "خمسمئة",
    6: "ستمئة", 7: "سبعمئة", 8: "ثمانمئة", 9: "تسعمئة",
}


def _number_to_arabic(n: int) -> str:
    """Convert integer to Arabic words (0-999999)."""
    if n == 0:
        return "صفر"
    if n < 0:
        return "سالب " + _number_to_arabic(-n)

    parts = []

    if n >= 1000:
        thousands = n // 1000
        n %= 1000
        if thousands == 1:
            parts.append("ألف")
        elif thousands == 2:
            parts.append("ألفان")
        elif 3 <= thousands <= 10:
            parts.append(ONES.get(thousands, str(thousands)) + " آلاف")
        else:
            parts.append(_number_to_arabic(thousands) + " ألف")

    if n >= 100:
        h = n // 100
        n %= 100
        parts.append(HUNDREDS.get(h, ""))

    if n >= 20:
        t = n // 10
        o = n % 10
        if o > 0:
            parts.append(ONES[o] + " و" + TENS[t])
        else:
            parts.append(TENS[t])
    elif n > 0:
        parts.append(ONES[n])

    return " و".join(p for p in parts if p)


# ════════════════════════════════════════════════════════════════
# Abbreviations
# ════════════════════════════════════════════════════════════════

ABBREVIATIONS = {
    "km": "كيلومتر", "km²": "كيلومتر مربع", "m": "متر",
    "cm": "سنتيمتر", "mm": "مليمتر", "kg": "كيلوغرام",
    "°C": "درجة مئوية", "°F": "درجة فهرنهايت",
    "%": "بالمئة", "$": "دولار", "€": "يورو",
    "AD": "ميلادي", "BC": "قبل الميلاد",
    "AI": "الذكاء الاصطناعي", "DNA": "الحمض النووي",
    "USA": "الولايات المتحدة", "UK": "المملكة المتحدة",
    "UN": "الأمم المتحدة", "NASA": "ناسا",
}

# ════════════════════════════════════════════════════════════════
# Emphasis words (documentary style)
# ════════════════════════════════════════════════════════════════

# Words that should have emphasis — add ellipsis before for dramatic pause
EMPHASIS_WORDS = {
    "تختفي", "مفاجئ", "لغز", "غامض", "غريب", "اكتشاف", "خطير",
    "مذهل", "لا يصدق", "مستحيل", "سر", "غموض", "حقيقة",
    "صادم", "مرعب", "عجيب", "نادر", "فريد", "تاريخي",
    "كارثة", "انفجار", "اختفاء", "ظهور", "تحول",
}


# ════════════════════════════════════════════════════════════════
# Main processor
# ════════════════════════════════════════════════════════════════

def process_arabic_for_tts(text: str) -> str:
    """
    Preprocess Arabic text for natural documentary narration.
    
    NO diacritics injection — Fish Speech handles context better without.
    Focus on: numbers, abbreviations, pacing, pauses, emphasis.
    """
    if not text or not text.strip():
        return text

    original = text

    # 1. Expand abbreviations
    for abbr, expansion in ABBREVIATIONS.items():
        text = re.sub(rf'\b{re.escape(abbr)}\b', expansion, text)

    # 2. Convert numbers to words + add pacing pauses around data
    def _replace_number(m):
        try:
            n = int(m.group(0))
            arabic_num = _number_to_arabic(n)
            # Add comma before number for slight pause (prevents speed-up on data)
            return f"، {arabic_num}،"
        except ValueError:
            return m.group(0)

    text = re.sub(r'\b\d+\b', _replace_number, text)
    # Clean double commas from number insertion
    text = re.sub(r'،\s*،', '،', text)

    # 3. Percentage
    text = re.sub(r'(\d+)\s*%', lambda m: _number_to_arabic(int(m.group(1))) + " بالمئة", text)

    # 4. Normalize punctuation
    text = text.replace('—', '...')  # Em-dash → dramatic pause
    text = text.replace('–', '،')    # En-dash → comma pause

    # 5. Add dramatic pauses before emphasis words (documentary style)
    for word in EMPHASIS_WORDS:
        # Add ellipsis before emphasis word for dramatic pause
        # Only if not already preceded by punctuation
        text = re.sub(
            rf'([^\.\!\؟،\s])\s+({re.escape(word)})',
            rf'\1... \2',
            text
        )

    # 6. Extend sentence pauses for documentary pacing
    # Single period → period + space (Fish Speech reads this as longer pause)
    # Add ellipsis between sentences for breathing room
    text = re.sub(r'\.\s+', '... ', text)
    
    # 7. Break very long sentences (>20 words) with breathing pause
    sentences = text.split('...')
    processed = []
    for sent in sentences:
        words = sent.split()
        if len(words) > 20:
            mid = len(words) // 2
            # Find nearest natural break (conjunction)
            best = mid
            for i in range(max(0, mid-4), min(len(words), mid+4)):
                if words[i] in ('و', 'أو', 'ثم', 'لكن', 'حيث', 'إذ', 'بينما', 'حتى'):
                    best = i
                    break
            part1 = ' '.join(words[:best])
            part2 = ' '.join(words[best:])
            processed.append(f"{part1}... {part2}")
        else:
            processed.append(sent)
    text = '...'.join(processed)

    # 8. Clean up
    text = re.sub(r'\.{4,}', '...', text)  # Max 3 dots
    text = re.sub(r'\s+', ' ', text).strip()

    if text != original:
        logger.debug(f"Arabic TTS preprocessing: {len(original)} → {len(text)} chars")

    return text
