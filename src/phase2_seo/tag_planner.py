"""
Phase 2: Tags + description template generation.
"""

import logging
from src.core.llm import generate_json

logger = logging.getLogger(__name__)

TAG_PROMPT = """أنت خبير SEO لقنوات YouTube العربية.

الموضوع: {topic}
العنوان المختار: {title}
الكلمات المفتاحية: {keywords}

أنشئ:
1. قائمة 30 تاق (عربي + إنجليزي مختلط) مرتبة حسب الأهمية
2. قالب وصف الفيديو (أول سطرين = hook مع كلمات مفتاحية)
3. 3-5 هاشتاقات

أجب بـ JSON:
{{
    "tags": ["تاق1", "تاق2", "tag3_en", ...],
    "description_template": "أول سطرين هوك...\\n\\nالوصف الكامل...\\n\\n📌 المصادر:\\n-\\n\\n🔔 اشترك بالقناة\\n#هاشتاق",
    "hashtags": ["#هاشتاق1", "#هاشتاق2", "#hashtag3"],
    "first_two_lines": "السطران الأولان المرئيان قبل 'عرض المزيد'"
}}"""


class TagPlanner:
    """Generate tags + description template for YouTube SEO."""

    def __init__(self, config: dict):
        self.config = config

    def plan_tags_description(
        self,
        topic: str,
        keywords: list[str],
        title: str,
    ) -> dict:
        """
        Generate 30 tags + description template using Qwen 3.5.
        """
        prompt = TAG_PROMPT.format(
            topic=topic,
            title=title,
            keywords=", ".join(keywords[:15]) if keywords else topic,
        )

        try:
            result = generate_json(prompt=prompt, temperature=0.5)

            # Validate tags
            tags = result.get("tags", [])
            # Ensure we have enough tags
            if len(tags) < 10:
                # Add basic tags
                tags.extend([topic, title.split()[0], "وثائقي", "documentary"])
            # YouTube max: 500 chars total for tags
            tags = self._trim_tags(tags, max_chars=500)

            result["tags"] = tags
            logger.info(f"Generated {len(tags)} tags for '{topic}'")
            return result

        except Exception as e:
            logger.error(f"Tag planning failed: {e}")
            return self._fallback_tags(topic, title, keywords)

    def _trim_tags(self, tags: list[str], max_chars: int = 500) -> list[str]:
        """Trim tags to fit YouTube's 500 character limit."""
        trimmed = []
        total_chars = 0
        for tag in tags:
            tag = tag.strip()
            if not tag:
                continue
            # Each tag + comma separator
            needed = len(tag) + 1
            if total_chars + needed > max_chars:
                break
            trimmed.append(tag)
            total_chars += needed
        return trimmed

    def _fallback_tags(
        self, topic: str, title: str, keywords: list[str]
    ) -> dict:
        """Fallback tags without LLM."""
        base_tags = [topic, title]
        base_tags.extend(keywords[:10])
        base_tags.extend([
            "وثائقي", "وثائقيات", "documentary", "عربي",
            "تحليل", "حقائق", "معلومات",
        ])

        # Deduplicate
        seen = set()
        unique_tags = []
        for t in base_tags:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique_tags.append(t)

        return {
            "tags": unique_tags[:30],
            "description_template": (
                f"{title}\n"
                f"في هذا الفيديو نتناول {topic} بالتفصيل.\n\n"
                f"📌 المصادر:\n- \n\n"
                f"🔔 لا تنسوا الاشتراك بالقناة وتفعيل الجرس\n"
                f"#وثائقي #{topic.replace(' ', '_')}"
            ),
            "hashtags": [f"#{topic.replace(' ', '_')}", "#وثائقي", "#معلومات"],
            "first_two_lines": f"{title}\nفي هذا الفيديو نتناول {topic} بالتفصيل.",
        }
