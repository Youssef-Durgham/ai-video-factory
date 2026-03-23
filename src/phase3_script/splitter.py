"""
Phase 3: Split script into scenes JSON with visual prompts.
visual_prompt is in ENGLISH (for FLUX). Narration stays Arabic.
"""

import json
import logging
from src.core.llm import generate_json
from src.models.scene import Scene, TextOverlay

logger = logging.getLogger(__name__)

SPLITTER_SYSTEM = """أنت مخرج أفلام وثائقية ومصمم مشاهد محترف.
مهمتك: تقسيم السكربت إلى مشاهد، وكتابة وصف بصري بالإنجليزية لكل مشهد (لمحرك FLUX).

## التعليمات الإخراجية في السكربت
السكربت قد يحتوي على تعليمات بين أقواس مربعة:
- [بصري: وصف اللقطة] ← استخدمه كأساس لكتابة visual_prompt بالإنجليزية
- [صوتي: وصف الموسيقى/المؤثرات] ← استخدمه لتحديد music_mood و sfx

إذا وجدت [بصري: لقطة جوية بطيئة لمدينة مهجورة عند الفجر، ضباب خفيف]:
→ visual_prompt: "Aerial slow drone shot of an abandoned city at dawn, light fog, cold blue tones..."
→ camera_movement: "slow_pan_right"

إذا وجدت [صوتي: موسيقى توتر متصاعدة، صوت رياح]:
→ music_mood: "tense"
→ sfx: ["wind", "tension_strings"]

## الدقة الإقليمية
- عمارة عراقية ≠ عمارة سعودية ≠ عمارة مصرية
- ملابس وعادات مختلفة حسب البلد
- مناظر طبيعية حسب المنطقة (ليس كل الشرق الأوسط صحراء)"""

SPLITTER_PROMPT = """
قسّم السكربت التالي إلى مشاهد:

═══ السكربت ═══
{script_text}

═══ معلومات الفيديو ═══
الموضوع: {topic}
المنطقة: {region}
النمط البصري: {visual_style}
نمط القناة: {channel_style}

═══ قواعد التقسيم ═══
1. كل مشهد = 5-15 ثانية عند القراءة
2. visual_prompt يجب أن يكون بالإنجليزية (لمحرك FLUX)
3. visual_prompt يجب أن يتضمن:
   - وصف دقيق لما يجب أن يظهر
   - أسلوب التصوير: photorealistic, documentary photography, cinematic
   - الإضاءة والألوان
   - دقة إقليمية: Iraqi/Saudi/Egyptian/etc. specific details
   - لا يتضمن أي نص أو كتابة
4. expected_visual_elements: العناصر التي يجب التحقق منها في Phase 6
5. music_mood: المزاج الموسيقي للمشهد
6. voice_emotion: نبرة الصوت المطلوبة
7. transition_to_next: نوع الانتقال للمشهد التالي

═══ أنماط الانتقال المتاحة ═══
cut, crossfade, dissolve, fade_black, fade_white, wipe_left, slide_up, zoom_in, zoom_out, glitch_cut

═══ أنماط حركة الكاميرا ═══
static, slow_zoom_in, slow_zoom_out, slow_pan_left, slow_pan_right, ken_burns, parallax, dolly_forward

مهم جداً: اكتب الـ JSON مباشرة بدون شرح أو تحليل مطول. ابدأ فوراً بكتابة الـ JSON:
أجب بـ JSON:
{{
    "scenes": [
        {{
            "scene_index": 0,
            "narration_text": "النص العربي الذي يُقرأ في هذا المشهد",
            "duration_seconds": 10,
            "visual_prompt": "Detailed English prompt for FLUX image generation. Photorealistic documentary style. Regional accuracy...",
            "visual_style": "photorealistic_cinematic",
            "camera_movement": "slow_zoom_in",
            "music_mood": "dramatic",
            "sfx": ["ambient_city", "wind"],
            "text_overlay": null,
            "expected_visual_elements": ["element1", "element2"],
            "transition_to_next": "crossfade",
            "presenter_mode": "none",
            "voice_emotion": "calm"
        }}
    ]
}}

لبعض المشاهد الرئيسية أضف text_overlay:
"text_overlay": {{"text": "١٩٦٩", "style": "fact_date", "position": "bottom_center", "animation": "fade_slide"}}

أنماط text_overlay: fact_date, section_header, quote, stat"""

# Region-specific prompt enhancers
REGION_ENHANCERS = {
    "iraq": ", Iraqi setting, Mesopotamian architecture, Tigris river area, Baghdad urban landscape",
    "gulf": ", Gulf state setting, modern Arabian architecture, white marble, glass towers",
    "egypt": ", Egyptian setting, Nile delta, Cairo urban, Islamic Cairo architecture",
    "levant": ", Levantine setting, stone buildings, Mediterranean hills, olive groves",
    "maghreb": ", North African setting, Moroccan architecture, Atlas mountains backdrop",
    "global": ", international documentary style, diverse settings",
}

STYLE_SUFFIX = ", photorealistic, documentary photography, cinematic lighting, 8k quality, no text, no writing, no letters, no watermark"

NEGATIVE_PROMPT = "text, writing, letters, words, watermark, subtitle, cartoon, anime, orientalist, stereotypical, fantasy, Aladdin-style, deformed, blurry, low quality"


class SceneSplitter:
    """Split approved script into scenes JSON with English visual prompts."""

    def __init__(self, config: dict):
        self.config = config

    def split_to_scenes(
        self,
        script_text: str,
        topic: str,
        region: str = "global",
        channel_config: dict = None,
    ) -> list[dict]:
        """
        Split script into scenes with visual prompts.
        Returns list of scene dicts matching the Scene model schema.
        """
        if channel_config is None:
            channel_config = {}

        visual_style = channel_config.get("style", {}).get(
            "visual", "cinematic_photorealistic"
        )

        # Split script into paragraphs and process each separately
        # This prevents thinking from exhausting tokens on the full script
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip() and len(p.strip()) > 20]
        
        if not paragraphs:
            paragraphs = [script_text]

        logger.info(f"Splitting {len(paragraphs)} paragraphs into scenes")

        all_scenes = []
        scene_idx = 0
        
        try:
            for pi, para in enumerate(paragraphs):
                para_prompt = f"""قسّم هذه الفقرة إلى مشهد أو مشهدين:

الفقرة:
{para}

الموضوع: {topic}
المنطقة: {region}
النمط البصري: {visual_style}

مهم جداً: اكتب JSON مباشرة:
{{"scenes": [{{"scene_index": {scene_idx}, "narration_text": "...", "duration_seconds": 10, "visual_prompt": "English FLUX prompt...", "visual_style": "photorealistic_cinematic", "camera_movement": "slow_zoom_in", "music_mood": "dramatic", "sfx": [], "text_overlay": null, "expected_visual_elements": [], "transition_to_next": "crossfade", "voice_emotion": "calm"}}]}}"""

                result = generate_json(
                    prompt=para_prompt,
                    system=SPLITTER_SYSTEM,
                    temperature=0.5,
                )

                para_scenes = result.get("scenes", []) if result else []
                
                if not para_scenes:
                    # Fallback: create a simple scene from the paragraph
                    logger.warning(f"  Paragraph {pi+1}: JSON failed, creating basic scene")
                    para_scenes = [{
                        "scene_index": scene_idx,
                        "narration_text": para,
                        "duration_seconds": max(5, min(15, len(para.split()) // 3)),
                        "visual_prompt": f"Documentary scene about {topic}, photorealistic, cinematic lighting",
                        "visual_style": "photorealistic_cinematic",
                        "camera_movement": "slow_zoom_in",
                        "music_mood": "dramatic",
                        "sfx": [],
                        "text_overlay": None,
                        "expected_visual_elements": [],
                        "transition_to_next": "crossfade",
                        "voice_emotion": "calm",
                    }]
                
                for s in para_scenes:
                    s["scene_index"] = scene_idx
                    scene_idx += 1
                all_scenes.extend(para_scenes)
                logger.info(f"  Paragraph {pi+1}/{len(paragraphs)}: {len(para_scenes)} scenes")

            scenes = all_scenes

            # Post-process: enhance visual prompts with regional accuracy
            for scene in scenes:
                scene["visual_prompt"] = self._enhance_visual_prompt(
                    scene.get("visual_prompt", ""),
                    region,
                )
                # Ensure scene_index is sequential
                scene["scene_index"] = scenes.index(scene)
                # Validate duration
                dur = scene.get("duration_seconds", 10)
                scene["duration_seconds"] = max(3, min(20, dur))

            # Validate scenes
            scenes = self._validate_scenes(scenes)

            logger.info(
                f"Split into {len(scenes)} scenes. "
                f"Total duration: {sum(s['duration_seconds'] for s in scenes):.0f}s"
            )
            return scenes

        except Exception as e:
            logger.error(f"Scene splitting failed: {e}")
            raise

    def _enhance_visual_prompt(self, prompt: str, region: str) -> str:
        """Add regional accuracy tags and style modifiers to visual prompt."""
        if not prompt:
            return "Documentary scene, cinematic lighting" + STYLE_SUFFIX

        # Add regional context
        region_suffix = REGION_ENHANCERS.get(region, REGION_ENHANCERS["global"])

        # Add documentary style if not present
        enhanced = prompt.strip()
        if "photorealistic" not in enhanced.lower():
            enhanced += region_suffix + STYLE_SUFFIX
        else:
            enhanced += region_suffix

        return enhanced

    def _validate_scenes(self, scenes: list[dict]) -> list[dict]:
        """Validate and fix scene data."""
        valid_scenes = []
        for i, scene in enumerate(scenes):
            # Required fields
            if not scene.get("narration_text"):
                logger.warning(f"Scene {i} missing narration — skipping")
                continue
            if not scene.get("visual_prompt"):
                scene["visual_prompt"] = (
                    "Documentary scene, cinematic lighting" + STYLE_SUFFIX
                )

            # Fix scene index
            scene["scene_index"] = len(valid_scenes)

            # Defaults for optional fields
            scene.setdefault("visual_style", "photorealistic_cinematic")
            scene.setdefault("camera_movement", "slow_zoom_in")
            scene.setdefault("music_mood", "dramatic")
            scene.setdefault("sfx", [])
            scene.setdefault("text_overlay", None)
            scene.setdefault("expected_visual_elements", [])
            scene.setdefault("transition_to_next", "crossfade")
            scene.setdefault("presenter_mode", "none")
            scene.setdefault("voice_emotion", "calm")

            valid_scenes.append(scene)

        return valid_scenes

    def get_negative_prompt(self) -> str:
        """Return the standard negative prompt for FLUX."""
        return NEGATIVE_PROMPT
