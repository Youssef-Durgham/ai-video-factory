"""
Phase 3: Deep web research on topic.
Gathers information from multiple sources and synthesizes into a research document.
"""

import logging
import requests
from typing import Optional

from src.core.llm import generate

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM = """أنت باحث أكاديمي متخصص في إعداد المواد البحثية للأفلام الوثائقية العربية.
مهمتك: جمع وتحليل وتوثيق المعلومات من مصادر متعددة.
اكتب بالعربية الفصحى. وثّق كل معلومة بمصدرها."""

SYNTHESIS_PROMPT = """
اكتب مستند بحثي شامل عن الموضوع التالي:

الموضوع: {topic}
الزاوية: {angle}

المعلومات المتوفرة من مصادر مختلفة:
{raw_sources}

المطلوب:
1. ملخص تنفيذي (فقرة واحدة)
2. الخلفية التاريخية والسياق
3. الحقائق والأرقام الرئيسية (مع مصادرها)
4. وجهات النظر المختلفة
5. التطورات الأخيرة
6. أسئلة مهمة لم تُجَب
7. قائمة المصادر

اكتب 2000-4000 كلمة بالعربية الفصحى.
كل ادعاء يجب أن يُنسب لمصدره: "وفقاً لـ [المصدر]..."
"""


class Researcher:
    """Deep web research agent for documentary content."""

    def __init__(self, config: dict):
        self.config = config
        self.brave_api_key = config.get("settings", {}).get("brave", {}).get("api_key", "")

    def research_topic(self, topic: str, angle: str = "") -> dict:
        """
        Research a topic thoroughly using web search + synthesis.
        Returns dict with research_text and sources list.
        """
        # Step 1: Gather raw information from multiple searches
        raw_sources = []

        # Search queries in Arabic and English
        queries = [
            topic,
            f"{topic} تحليل",
            f"{topic} حقائق وأرقام",
            f"{topic} analysis",
            f"{topic} facts statistics",
        ]
        if angle:
            queries.append(f"{topic} {angle}")

        for query in queries:
            results = self._web_search(query)
            raw_sources.extend(results)

        if not raw_sources:
            logger.warning(f"No web results found for '{topic}' — using LLM knowledge only")
            raw_sources = [{"title": "No web sources available", "snippet": "Using model knowledge."}]

        # Step 2: Synthesize into research document using LLM
        sources_text = self._format_sources(raw_sources)

        prompt = SYNTHESIS_PROMPT.format(
            topic=topic,
            angle=angle or "تحليل شامل",
            raw_sources=sources_text,
        )

        try:
            research_text = generate(
                prompt=prompt,
                system=SYNTHESIS_SYSTEM,
                temperature=0.4,
                max_tokens=8192,
            )

            word_count = len(research_text.split())
            logger.info(f"Research complete for '{topic}': {word_count} words, {len(raw_sources)} sources")

            return {
                "topic": topic,
                "angle": angle,
                "research_text": research_text,
                "word_count": word_count,
                "sources": [
                    {"title": s.get("title", ""), "url": s.get("url", "")}
                    for s in raw_sources
                    if s.get("url")
                ],
                "source_count": len(raw_sources),
            }

        except Exception as e:
            logger.error(f"Research synthesis failed: {e}")
            return {
                "topic": topic,
                "angle": angle,
                "research_text": f"فشل البحث التفصيلي. الموضوع: {topic}",
                "word_count": 0,
                "sources": [],
                "source_count": 0,
            }

    def _web_search(self, query: str, count: int = 5) -> list[dict]:
        """Search the web using Brave Search API."""
        if not self.brave_api_key:
            logger.debug("No Brave API key — skipping web search")
            return []

        try:
            resp = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": count},
                headers={"X-Subscription-Token": self.brave_api_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                    "source": "brave_search",
                })
            return results

        except Exception as e:
            logger.debug(f"Web search failed for '{query}': {e}")
            return []

    def _format_sources(self, sources: list[dict], max_chars: int = 8000) -> str:
        """Format raw sources for LLM context window."""
        lines = []
        total = 0
        for s in sources:
            line = f"[{s.get('source', 'web')}] {s.get('title', '')}\n{s.get('snippet', '')}\nURL: {s.get('url', '')}\n"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n---\n".join(lines) if lines else "لا توجد مصادر خارجية متاحة."
