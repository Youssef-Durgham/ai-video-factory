"""
Phase 1: Topic ranking using LLM analysis.
Combines YouTube trends + web trends → scored & ranked topic list.
"""

import json
import logging
from typing import Optional

from src.core.llm import generate_json

logger = logging.getLogger(__name__)

RANKING_SYSTEM_PROMPT = """أنت محلل محتوى عربي متخصص في YouTube.
مهمتك: تحليل بيانات الترند وترتيب المواضيع حسب إمكانية نجاحها كفيديو وثائقي عربي على YouTube.

معايير التقييم:
1. حجم البحث (search_volume): كل ما أكبر = أفضل
2. المنافسة (competition): كل ما أقل = أفضل (فرصة أكبر)
3. سرعة الترند (trend_velocity): ارتفاع سريع = فرصة ذهبية
4. ملاءمة القناة (category_match): هل يناسب نوع المحتوى؟
5. عمق المحتوى (content_depth): هل يكفي لفيديو 8-12 دقيقة؟

أجب بـ JSON فقط."""

RANKING_PROMPT_TEMPLATE = """
حلل المواضيع التالية ورتبها:

=== بيانات YouTube الترند ===
{youtube_data}

=== بيانات الويب والأخبار ===
{web_data}

=== إعدادات القناة ===
اسم القناة: {channel_name}
التصنيفات المسموحة: {channel_topics}
النبرة: {channel_tone}

رتّب أفضل 10 مواضيع بالصيغة التالية:
{{
    "ranked_topics": [
        {{
            "topic": "عنوان الموضوع بالعربي",
            "topic_en": "Topic title in English",
            "score": 8.5,
            "search_volume_score": 8,
            "competition_score": 7,
            "trend_velocity_score": 9,
            "category_match_score": 8,
            "content_depth_score": 9,
            "suggested_angle": "الزاوية المقترحة للتناول",
            "suggested_region": "iraq|gulf|egypt|levant|maghreb|global",
            "why": "سبب اختيار هذا الموضوع",
            "sources": ["مصدر1", "مصدر2"]
        }}
    ]
}}
"""


class TopicRanker:
    """Score and rank topics using LLM analysis."""

    def __init__(self, config: dict):
        self.config = config

    def rank_topics(
        self,
        youtube_data: list[dict],
        web_data: list[dict],
        channel_config: dict,
    ) -> list[dict]:
        """
        Combine all trend data and rank topics using Qwen 3.5.

        Scoring formula:
        score = search_volume * 0.3 + competition_inv * 0.25 +
                trend_velocity * 0.25 + category_match * 0.2

        Returns ranked list of topic dicts.
        """
        # Prepare data summaries for LLM (trim to avoid token limits)
        yt_summary = self._summarize_youtube(youtube_data)
        web_summary = self._summarize_web(web_data)

        prompt = RANKING_PROMPT_TEMPLATE.format(
            youtube_data=yt_summary,
            web_data=web_summary,
            channel_name=channel_config.get("name", "وثائقيات"),
            channel_topics=", ".join(channel_config.get("topics", ["history", "science"])),
            channel_tone=channel_config.get("content", {}).get("tone", "educational, engaging"),
        )

        try:
            result = generate_json(
                prompt=prompt,
                system=RANKING_SYSTEM_PROMPT,
                temperature=0.4,
            )

            topics = result.get("ranked_topics", [])

            # Validate and normalize scores
            for t in topics:
                t["score"] = min(10.0, max(0.0, float(t.get("score", 0))))

            # Sort by score descending
            topics.sort(key=lambda x: x["score"], reverse=True)

            logger.info(f"Ranked {len(topics)} topics. Top: {topics[0]['topic'] if topics else 'none'}")
            return topics[:10]

        except Exception as e:
            logger.error(f"Topic ranking failed: {e}")
            # Fallback: return raw YouTube trending titles
            return self._fallback_ranking(youtube_data, web_data)

    def _summarize_youtube(self, data: list[dict], max_items: int = 30) -> str:
        """Summarize YouTube data for LLM context."""
        lines = []
        for item in data[:max_items]:
            lines.append(
                f"- [{item.get('region', '?')}] {item['title']} "
                f"(views: {item.get('views', 0):,}, channel: {item.get('channel', '?')})"
            )
        return "\n".join(lines) if lines else "لا توجد بيانات YouTube متاحة"

    def _summarize_web(self, data: list[dict], max_items: int = 30) -> str:
        """Summarize web/news data for LLM context."""
        lines = []
        for item in data[:max_items]:
            source_type = item.get("source_type", item.get("source", ""))
            lines.append(
                f"- [{source_type}] {item.get('title', item.get('keyword', '?'))} "
                f"({item.get('source', '')})"
            )
        return "\n".join(lines) if lines else "لا توجد بيانات ويب متاحة"

    def _fallback_ranking(
        self, youtube_data: list[dict], web_data: list[dict]
    ) -> list[dict]:
        """Fallback: simple view-based ranking without LLM."""
        logger.warning("Using fallback ranking (no LLM)")
        topics = []
        seen = set()

        for item in sorted(youtube_data, key=lambda x: x.get("views", 0), reverse=True):
            title = item["title"]
            if title not in seen:
                seen.add(title)
                topics.append({
                    "topic": title,
                    "topic_en": title,
                    "score": min(10, item.get("views", 0) / 100000),
                    "suggested_angle": "تحليل شامل",
                    "suggested_region": "global",
                    "why": f"ترند على YouTube — {item.get('views', 0):,} مشاهدة",
                    "sources": [f"https://youtube.com/watch?v={item.get('video_id', '')}"],
                })
                if len(topics) >= 10:
                    break

        return topics
