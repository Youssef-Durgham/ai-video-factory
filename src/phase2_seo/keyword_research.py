"""
Phase 2: YouTube keyword research.
Autocomplete suggestions + top results analysis.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"


class KeywordResearch:
    """YouTube keyword analysis — autocomplete + top results."""

    def __init__(self, config: dict):
        from googleapiclient.discovery import build

        api_key = config["settings"]["youtube"]["api_key"]
        self.youtube = build("youtube", "v3", developerKey=api_key)

    def get_autocomplete(self, query: str, language: str = "ar") -> list[str]:
        """
        Get YouTube search autocomplete suggestions.
        Semi-official endpoint — widely used, low risk.
        """
        params = {
            "client": "youtube",
            "q": query,
            "hl": language,
            "ds": "yt",
        }
        try:
            resp = requests.get(SUGGEST_URL, params=params, timeout=10)
            # Response is JSONP-like, parse it
            text = resp.text
            # Extract suggestions from response
            import json
            # Format: window.google.ac.h([...])
            start = text.find("[")
            if start >= 0:
                data = json.loads(text[start:])
                if len(data) > 1 and isinstance(data[1], list):
                    return [s[0] for s in data[1] if isinstance(s, list)]
            return []
        except Exception as e:
            logger.warning(f"Autocomplete failed for '{query}': {e}")
            return []

    def analyze_top_results(
        self, query: str, limit: int = 20
    ) -> dict:
        """
        Search YouTube for the query and analyze top results.
        Extracts: title patterns, tags, view counts, descriptions.
        Uses search.list (100 quota units).
        """
        try:
            # Search for videos
            search_request = self.youtube.search().list(
                part="snippet",
                q=query,
                order="viewCount",
                maxResults=min(limit, 50),
                type="video",
                relevanceLanguage="ar",
            )
            search_response = search_request.execute()

            video_ids = [
                item["id"]["videoId"]
                for item in search_response.get("items", [])
            ]

            if not video_ids:
                return {"keywords": [], "title_patterns": [], "avg_views": 0}

            # Get detailed video info (tags, stats)
            details_request = self.youtube.videos().list(
                part="snippet,statistics",
                id=",".join(video_ids),
            )
            details_response = details_request.execute()

            titles = []
            all_tags = []
            view_counts = []
            descriptions = []

            for item in details_response.get("items", []):
                snippet = item["snippet"]
                stats = item.get("statistics", {})

                titles.append(snippet["title"])
                all_tags.extend(snippet.get("tags", []))
                view_counts.append(int(stats.get("viewCount", 0)))
                descriptions.append(snippet.get("description", "")[:300])

            # Extract keyword frequencies from tags
            from collections import Counter
            tag_freq = Counter(all_tags)
            top_keywords = [
                {"keyword": kw, "frequency": count}
                for kw, count in tag_freq.most_common(30)
            ]

            # Analyze title patterns
            title_patterns = self._extract_title_patterns(titles)

            avg_views = sum(view_counts) / len(view_counts) if view_counts else 0

            return {
                "keywords": top_keywords,
                "title_patterns": title_patterns,
                "avg_views": int(avg_views),
                "total_results": len(titles),
                "top_titles": titles[:10],
                "descriptions": descriptions[:5],
            }

        except Exception as e:
            logger.error(f"Top results analysis failed: {e}")
            return {"keywords": [], "title_patterns": [], "avg_views": 0}

    def get_full_keyword_report(self, topic: str) -> dict:
        """Complete keyword research: autocomplete + top results."""
        # Get autocomplete suggestions
        suggestions = self.get_autocomplete(topic)

        # Analyze top results for the topic
        top_analysis = self.analyze_top_results(topic)

        # Also get suggestions for variations
        extended_suggestions = []
        prefixes = ["لماذا", "كيف", "حقيقة", "أسرار", "قصة"]
        for prefix in prefixes:
            extended_suggestions.extend(
                self.get_autocomplete(f"{prefix} {topic}")
            )

        return {
            "topic": topic,
            "autocomplete": suggestions,
            "extended_suggestions": list(set(extended_suggestions)),
            "top_results": top_analysis,
        }

    def _extract_title_patterns(self, titles: list[str]) -> list[str]:
        """Extract common patterns from competitor titles."""
        patterns = []
        pattern_markers = {
            "question": ["لماذا", "كيف", "هل", "ما هو", "ما هي", "من هو"],
            "list": ["أفضل", "أسوأ", "أخطر", "أغرب", "أقوى"],
            "revelation": ["الحقيقة", "السر", "ما لا تعرفه", "المخفي"],
            "dramatic": ["انهيار", "كارثة", "صدمة", "مفاجأة", "خطير"],
        }

        for title in titles:
            for pattern_type, markers in pattern_markers.items():
                for marker in markers:
                    if marker in title:
                        patterns.append(f"{pattern_type}:{marker}")
                        break

        from collections import Counter
        pattern_freq = Counter(patterns)
        return [
            {"pattern": p, "count": c}
            for p, c in pattern_freq.most_common(10)
        ]
