"""
Phase 5 — Image Prompt Enhancer for Arabic/Middle-Eastern documentary content.

Enhances raw visual prompts with:
  • Regional accuracy (Iraq, Gulf, Egypt, Levant, Maghreb)
  • Documentary style modifiers
  • Content-appropriate LoRA triggers
  • Arabic content optimization rules
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# REGIONAL CONTEXT TAGS
# ════════════════════════════════════════════════════════════════

REGION_TAGS: dict[str, dict] = {
    "iraq": {
        "architecture": (
            "Iraqi architecture, Abbasid-era buildings, Baghdadi mashrabiya, "
            "Tigris riverbank, Mesopotamian landscape, Iraqi brick buildings"
        ),
        "people": (
            "Iraqi man in dishdasha, olive skin tone, Iraqi street scene, "
            "Mesopotamian marshlands in background"
        ),
        "landscape": (
            "Mesopotamian marshlands, Tigris and Euphrates, palm groves, "
            "Iraqi desert plateau, ziggurat ruins"
        ),
        "negative_extra": "Saudi style, Egyptian style, Moroccan style",
    },
    "gulf": {
        "architecture": (
            "modern Gulf architecture, glass skyscrapers, Arabian geometric patterns, "
            "Dubai-style skyline, futuristic Gulf city, white marble mosque"
        ),
        "people": (
            "Gulf Arab man in white thobe and ghutra, dark skin tone, "
            "modern Gulf office setting, pearl diving heritage"
        ),
        "landscape": (
            "Arabian desert dunes, Gulf coast turquoise water, "
            "date palm oasis, modern Gulf port"
        ),
        "negative_extra": "poverty, slum, Iraqi style, Egyptian style",
    },
    "egypt": {
        "architecture": (
            "Egyptian architecture, Cairo old town, Islamic Cairo mosques, "
            "Nile corniche, Egyptian baladi buildings, Khan el-Khalili bazaar"
        ),
        "people": (
            "Egyptian man in gallabiya, Mediterranean skin tone, "
            "Cairo street vendor, Egyptian countryside farmer"
        ),
        "landscape": (
            "Nile delta farmland, Egyptian desert, Sinai mountains, "
            "Alexandria coastline, Aswan landscape"
        ),
        "negative_extra": "Gulf style, Iraqi style, Moroccan style",
    },
    "levant": {
        "architecture": (
            "Levantine stone buildings, Ottoman-era architecture, "
            "Damascus old city, Beirut French colonial, Jerusalem limestone"
        ),
        "people": (
            "Levantine man in suit, light olive skin, "
            "Levantine woman in modest modern dress"
        ),
        "landscape": (
            "Levantine hills, olive orchards, Mediterranean coast, "
            "cedar forest, terraced agriculture"
        ),
        "negative_extra": "Gulf style, Egyptian style, desert only",
    },
    "maghreb": {
        "architecture": (
            "North African architecture, Moroccan zellige tilework, "
            "Tunisian blue-white buildings, Algerian casbah, riad courtyard"
        ),
        "people": (
            "North African man in djellaba, Berber features, "
            "Moroccan market seller, Tunisian café scene"
        ),
        "landscape": (
            "Atlas mountains, Sahara edge, Moroccan coast, "
            "olive groves, Mediterranean North Africa"
        ),
        "negative_extra": "Gulf style, Iraqi style, Egyptian style",
    },
    "global": {
        "architecture": "",
        "people": "",
        "landscape": "",
        "negative_extra": "",
    },
}

# ════════════════════════════════════════════════════════════════
# DOCUMENTARY STYLE MODIFIERS
# ════════════════════════════════════════════════════════════════

STYLE_MODIFIERS: dict[str, str] = {
    "cinematic_photorealistic": (
        "photorealistic, cinematic lighting, dramatic shadows, "
        "shallow depth of field, documentary photography, "
        "golden hour warm light, film grain, 35mm lens"
    ),
    "editorial_clean": (
        "editorial photography, clean lighting, sharp focus, "
        "professional photo, neutral color palette, even exposure"
    ),
    "archival_historical": (
        "archival photograph style, slightly desaturated, "
        "historical documentary still, aged film look, "
        "warm sepia undertone, vintage photography"
    ),
    "dramatic_noir": (
        "dramatic noir lighting, high contrast, deep shadows, "
        "moody atmosphere, chiaroscuro, cinematic still"
    ),
    "illustrated_educational": (
        "detailed illustration, infographic style, clean lines, "
        "educational diagram, explainer visual, flat design"
    ),
}

# Default style if none specified
DEFAULT_STYLE = "cinematic_photorealistic"

# ════════════════════════════════════════════════════════════════
# TOPIC-CATEGORY SPECIFIC MODIFIERS
# ════════════════════════════════════════════════════════════════

CATEGORY_MODIFIERS: dict[str, dict] = {
    "politics": {
        "style_hint": "photojournalism, press conference, government building",
        "negative_extra": "violent imagery, gore, graphic content, propaganda",
    },
    "history": {
        "style_hint": "historical photograph style, aged film, documentary still",
        "negative_extra": "modern objects, smartphones, modern cars",
    },
    "military": {
        "style_hint": "military photography, war documentary, harsh lighting",
        "negative_extra": "gore, graphic violence, disrespectful depictions",
    },
    "science": {
        "style_hint": "scientific visualization, lab setting, clean modern",
        "negative_extra": "fantasy, magic, supernatural",
    },
    "technology": {
        "style_hint": "modern technology, digital, futuristic clean",
        "negative_extra": "steampunk, fantasy, medieval",
    },
    "economics": {
        "style_hint": "business photography, stock market, modern office",
        "negative_extra": "poverty porn, exaggerated wealth stereotypes",
    },
    "culture": {
        "style_hint": "cultural photography, traditional setting, vibrant",
        "negative_extra": "orientalist, stereotypical, Aladdin-style",
    },
    "religion": {
        "style_hint": "respectful, elegant, warm golden tones, sacred spaces",
        "negative_extra": "disrespectful, caricature, mockery",
    },
    "mysteries": {
        "style_hint": "mysterious atmosphere, dark, fog, dramatic lighting",
        "negative_extra": "cartoon, silly, comedic",
    },
}

# ════════════════════════════════════════════════════════════════
# MAIN ENHANCER
# ════════════════════════════════════════════════════════════════


def enhance_prompt(
    raw_prompt: str,
    region: str = "global",
    visual_style: str = DEFAULT_STYLE,
    topic_category: Optional[str] = None,
    lora_name: Optional[str] = None,
    extra_negative: Optional[str] = None,
) -> tuple[str, str]:
    """
    Enhance a raw visual prompt with regional accuracy and style.

    Args:
        raw_prompt: Base visual description (English, from scene splitter).
        region: Target region ("iraq", "gulf", "egypt", "levant", "maghreb", "global").
        visual_style: Style key from STYLE_MODIFIERS.
        topic_category: Optional content category for extra modifiers.
        lora_name: LoRA trigger word to append (if applicable).
        extra_negative: Additional negative prompt terms.

    Returns:
        Tuple of (enhanced_prompt, negative_prompt).
    """
    parts: list[str] = []

    # 1. Original prompt (cleaned)
    clean = raw_prompt.strip().rstrip(",. ")
    parts.append(clean)

    # 2. Regional context
    region_key = region.lower() if region else "global"
    region_data = REGION_TAGS.get(region_key, REGION_TAGS["global"])

    # Detect which regional sub-tag is relevant
    prompt_lower = raw_prompt.lower()
    if any(w in prompt_lower for w in ("building", "city", "street", "mosque", "architecture", "town")):
        if region_data["architecture"]:
            parts.append(region_data["architecture"])
    elif any(w in prompt_lower for w in ("person", "man", "woman", "people", "crowd", "leader")):
        if region_data["people"]:
            parts.append(region_data["people"])
    elif any(w in prompt_lower for w in ("landscape", "desert", "mountain", "river", "coast", "field")):
        if region_data["landscape"]:
            parts.append(region_data["landscape"])
    else:
        # Generic — add architecture tags as the most common need
        if region_data["architecture"]:
            parts.append(region_data["architecture"])

    # 3. Documentary style
    style_str = STYLE_MODIFIERS.get(visual_style, STYLE_MODIFIERS[DEFAULT_STYLE])
    parts.append(style_str)

    # 4. Category-specific hints
    if topic_category:
        cat_data = CATEGORY_MODIFIERS.get(topic_category.lower(), {})
        if cat_data.get("style_hint"):
            parts.append(cat_data["style_hint"])

    # 5. LoRA trigger
    if lora_name:
        # LoRA trigger words are typically the filename stem
        trigger = lora_name.replace(".safetensors", "").replace("_", " ")
        parts.append(trigger)

    # 6. Quality boosters
    parts.append("masterpiece, best quality, highly detailed, 8k uhd")

    enhanced = ", ".join(p for p in parts if p)

    # ─── Negative prompt ───────────────────────────────
    neg_parts: list[str] = [
        "text, writing, letters, words, watermark, subtitle, caption, "
        "logo, signature, stamp, label, number overlay, "
        "blurry, low quality, distorted, deformed, ugly, "
        "extra fingers, extra limbs, mutated hands, bad anatomy, "
        "cartoon, anime, 3d render, painting, sketch, "
        "orientalist, stereotypical, fantasy, Aladdin-style"
    ]

    if region_data.get("negative_extra"):
        neg_parts.append(region_data["negative_extra"])

    if topic_category:
        cat_neg = CATEGORY_MODIFIERS.get(topic_category.lower(), {}).get("negative_extra", "")
        if cat_neg:
            neg_parts.append(cat_neg)

    if extra_negative:
        neg_parts.append(extra_negative)

    negative = ", ".join(neg_parts)

    logger.debug(f"Enhanced prompt ({region}): {enhanced[:120]}...")
    return enhanced, negative


def enhance_scenes(
    scenes: list[dict],
    region: str = "global",
    topic_category: Optional[str] = None,
    channel_lora: Optional[str] = None,
) -> list[dict]:
    """
    Enhance visual prompts for a batch of scenes in-place.
    Adds 'enhanced_prompt' and 'negative_prompt' keys.
    """
    for scene in scenes:
        style = scene.get("visual_style", DEFAULT_STYLE)
        enhanced, negative = enhance_prompt(
            raw_prompt=scene.get("visual_prompt", ""),
            region=region,
            visual_style=style,
            topic_category=topic_category,
            lora_name=channel_lora,
        )
        scene["enhanced_prompt"] = enhanced
        scene["negative_prompt"] = negative
    return scenes
