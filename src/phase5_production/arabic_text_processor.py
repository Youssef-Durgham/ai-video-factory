"""
Arabic Text Processor for TTS — improves pronunciation quality.

Fish Speech S2-Pro struggles with Arabic because:
1. No diacritics (tashkeel) → wrong vowelization → wrong pronunciation
2. Numbers/dates not converted to Arabic words
3. Abbreviations not expanded
4. Punctuation not optimized for TTS pauses

This module preprocesses Arabic text to maximize TTS accuracy.
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
# Common abbreviations and symbols
# ════════════════════════════════════════════════════════════════

ABBREVIATIONS = {
    "km": "كيلومتر",
    "km²": "كيلومتر مربع",
    "m": "متر",
    "cm": "سنتيمتر",
    "mm": "مليمتر",
    "kg": "كيلوغرام",
    "g": "غرام",
    "°C": "درجة مئوية",
    "°F": "درجة فهرنهايت",
    "%": "بالمئة",
    "$": "دولار",
    "€": "يورو",
    "£": "جنيه",
    "AD": "ميلادي",
    "BC": "قبل الميلاد",
    "CEO": "الرئيس التنفيذي",
    "AI": "الذكاء الاصطناعي",
    "USA": "الولايات المتحدة",
    "UK": "المملكة المتحدة",
    "UN": "الأمم المتحدة",
    "NASA": "ناسا",
    "DNA": "الحمض النووي",
}

# ════════════════════════════════════════════════════════════════
# Common mispronunciation fixes
# ════════════════════════════════════════════════════════════════

# Words that Fish Speech commonly mispronounces — add phonetic hints
PRONUNCIATION_FIXES = {
    # Hamza issues
    "إلى": "إِلَى",
    # Note: أن/إن have multiple forms — leave without tashkeel
    # to let Fish Speech use context. Adding wrong tashkeel is worse
    # than none. Only add tashkeel to unambiguous words.
    # Diacritics disabled — Fish Speech handles context better without them
    # Adding wrong diacritics makes pronunciation WORSE not better
    # Common documentary words
    "العلماء": "العُلَمَاءُ",
    "الأرض": "الأَرْضِ",
    "المحيط": "المُحِيطِ",
    "الجزيرة": "الجَزِيرَةِ",
    "القرن": "القَرْنِ",
    "تاريخ": "تَارِيخِ",
    "اكتشاف": "اكْتِشَافِ",
    "الحضارة": "الحَضَارَةِ",
    "الطبيعة": "الطَّبِيعَةِ",
    "الحقيقة": "الحَقِيقَةِ",
    "المعرفة": "المَعْرِفَةِ",
}


# ════════════════════════════════════════════════════════════════
# Main processor
# ════════════════════════════════════════════════════════════════

def process_arabic_for_tts(text: str) -> str:
    """
    Preprocess Arabic text for optimal TTS pronunciation.
    
    Steps:
    1. Expand abbreviations and symbols
    2. Convert numbers to Arabic words
    3. Apply pronunciation fixes (common words with diacritics)
    4. Normalize punctuation for natural pauses
    5. Add breath marks for long sentences
    6. Clean up whitespace
    """
    if not text or not text.strip():
        return text

    original = text

    # 1. Expand abbreviations
    for abbr, expansion in ABBREVIATIONS.items():
        # Word boundary matching
        text = re.sub(rf'\b{re.escape(abbr)}\b', expansion, text)

    # 2. Convert numbers to words
    # Year patterns: keep as-is if 4 digits (e.g., 2024)
    def _replace_number(m):
        num_str = m.group(0)
        try:
            n = int(num_str)
            # Years: say as number
            if 1000 <= n <= 2100:
                return _number_to_arabic(n)
            # Percentages are handled separately
            return _number_to_arabic(n)
        except ValueError:
            return num_str

    # Replace standalone numbers
    text = re.sub(r'\b\d+\b', _replace_number, text)

    # 3. Percentage: "50%" → "خمسون بالمئة"
    text = re.sub(r'(\d+)\s*%', lambda m: _number_to_arabic(int(m.group(1))) + " بالمئة", text)

    # 4. Apply pronunciation fixes (add diacritics to common words)
    # Only apply to words without existing diacritics
    DIACRITICS = '\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0653\u0654\u0655'
    for word, fixed in PRONUNCIATION_FIXES.items():
        # Only replace if the word doesn't already have diacritics
        pattern = rf'\b{re.escape(word)}\b'
        def _fix_word(m):
            matched = m.group(0)
            if any(c in DIACRITICS for c in matched):
                return matched  # Already has diacritics
            return fixed
        text = re.sub(pattern, _fix_word, text)

    # 5. Normalize punctuation for TTS pauses
    # Double period → single with pause
    text = re.sub(r'\.{2,}', '...', text)
    # Em-dash → comma (pause)
    text = text.replace('—', '،')
    text = text.replace('–', '،')
    # Don't auto-insert commas — can cause unnatural pauses

    # 6. Add breath marks for long sentences (split at 30+ words without punctuation)
    sentences = text.split('.')
    processed = []
    for sent in sentences:
        words = sent.split()
        if len(words) > 25:
            # Insert comma every ~15 words at a natural break
            result_words = []
            for i, w in enumerate(words):
                result_words.append(w)
                if (i + 1) % 15 == 0 and i < len(words) - 3:
                    if not w.endswith(('،', '؟', '!', '.')):
                        result_words.append('،')
            processed.append(' '.join(result_words))
        else:
            processed.append(sent)
    text = '.'.join(processed)

    # 7. Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove double punctuation
    text = re.sub(r'،\s*،', '،', text)
    text = re.sub(r'\.\s*\.', '.', text)

    if text != original:
        logger.debug(f"Arabic TTS preprocessing applied ({len(original)} → {len(text)} chars)")

    return text
