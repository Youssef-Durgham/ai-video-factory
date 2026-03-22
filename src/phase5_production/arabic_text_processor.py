"""
Arabic Text Processor for TTS — MINIMAL approach.

Lesson learned: Fish Speech S2-Pro produces best results with CLEAN text.
Every ... or ، we inject creates artifacts (hard cuts, over-articulation).

This processor does ONLY what genuinely helps:
1. Numbers → Arabic words (Fish Speech can't read digits)
2. Abbreviations → Arabic words
3. Protect idafa (مضاف+مضاف إليه) — don't let anything break these

Everything else: LEAVE THE TEXT ALONE. Let Fish Speech handle pacing naturally.
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
# Main processor — MINIMAL
# ════════════════════════════════════════════════════════════════

def process_arabic_for_tts(text: str) -> str:
    """
    MINIMAL preprocessing — only what genuinely helps.
    
    DO: numbers, abbreviations
    DON'T: inject pauses, add diacritics, modify punctuation
    """
    if not text or not text.strip():
        return text

    # 1. Expand abbreviations
    for abbr, expansion in ABBREVIATIONS.items():
        text = re.sub(rf'\b{re.escape(abbr)}\b', expansion, text)

    # 2. Convert numbers to words (Fish Speech can't read digits)
    def _replace_number(m):
        try:
            return _number_to_arabic(int(m.group(0)))
        except ValueError:
            return m.group(0)

    text = re.sub(r'\b\d+\b', _replace_number, text)

    # 3. Percentage
    text = re.sub(r'(\d+)\s*%', lambda m: _number_to_arabic(int(m.group(1))) + " بالمئة", text)

    # 4. Normalize em-dash (Fish Speech reads it weird)
    text = text.replace('—', '،')
    text = text.replace('–', '،')

    # 5. Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text
