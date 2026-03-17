"""
Phase 1: Google Trends + RSS news feed scanner.
Uses pytrends (Google Trends) and feedparser (RSS).
"""

import logging
from typing import Optional
from datetime import datetime

import feedparser

logger = logging.getLogger(__name__)

# Arabic news RSS feeds
DEFAULT_RSS_FEEDS = [
    {"name": "الجزيرة", "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4571-a233-01a4a5f21e3e/73d0e1b4-532f-45ef-b135-bba0e87b82b6"},
    {"name": "BBC عربي", "url": "https://feeds.bbci.co.uk/arabic/rss.xml"},
    {"name": "سكاي نيوز عربية", "url": "https://www.skynewsarabia.com/web/rss"},
    {"name": "Reuters عربي", "url": "https://www.reuters.com/rssFeed/worldNews/"},
    {"name": "Google News AR", "url": "https://news.google.com/rss?hl=ar&gl=EG&ceid=EG:ar"},
]


class WebTrends:
    """Scan Google Trends and news RSS for trending topics."""

    def __init__(self, config: dict):
        self.config = config

    def get_google_trends(
        self,
        keywords: list[str],
        regions: list[str] = None,
        timeframe: str = "now 7-d",
    ) -> list[dict]:
        """
        Get Google Trends interest over time for keywords.
        Uses pytrends — unofficial but widely used, low risk.
        """
        if regions is None:
            regions = ["IQ", "SA", "EG", "AE", "MA"]

        results = []
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="ar", tz=180)  # UTC+3

            for region in regions:
                try:
                    pytrends.build_payload(
                        keywords[:5],  # Max 5 per request
                        cat=0,
                        timeframe=timeframe,
                        geo=region,
                    )
                    df = pytrends.interest_over_time()

                    if df.empty:
                        continue

                    for kw in keywords[:5]:
                        if kw in df.columns:
                            values = df[kw].tolist()
                            avg_interest = sum(values) / len(values) if values else 0
                            # Trend direction: compare last 2 days vs first 2
                            if len(values) >= 4:
                                recent = sum(values[-2:]) / 2
                                early = sum(values[:2]) / 2
                                trend = "rising" if recent > early * 1.2 else (
                                    "falling" if recent < early * 0.8 else "stable"
                                )
                            else:
                                trend = "unknown"

                            results.append({
                                "keyword": kw,
                                "region": region,
                                "interest_score": avg_interest,
                                "peak_score": max(values) if values else 0,
                                "trend_direction": trend,
                                "source": "google_trends",
                            })
                except Exception as e:
                    logger.warning(f"Google Trends failed for {region}: {e}")

        except ImportError:
            logger.warning("pytrends not installed — skipping Google Trends")

        return results

    def get_google_trending_searches(
        self, regions: list[str] = None
    ) -> list[dict]:
        """Get real-time trending searches from Google Trends."""
        if regions is None:
            regions = ["iraq", "saudi_arabia", "egypt"]

        results = []
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="ar", tz=180)

            for region in regions:
                try:
                    trending = pytrends.trending_searches(pn=region)
                    for _, row in trending.iterrows():
                        results.append({
                            "keyword": row[0],
                            "region": region,
                            "source": "google_trending_searches",
                        })
                except Exception as e:
                    logger.debug(f"Trending searches failed for {region}: {e}")

        except ImportError:
            logger.warning("pytrends not installed")

        return results

    def get_news_topics(
        self, rss_feeds: list[dict] = None, max_per_feed: int = 20
    ) -> list[dict]:
        """
        Fetch news headlines from Arabic RSS feeds.
        Uses feedparser — public feeds, zero risk.
        """
        if rss_feeds is None:
            rss_feeds = DEFAULT_RSS_FEEDS

        results = []
        for feed_info in rss_feeds:
            try:
                feed = feedparser.parse(feed_info["url"])
                for entry in feed.entries[:max_per_feed]:
                    published = ""
                    if hasattr(entry, "published"):
                        published = entry.published
                    elif hasattr(entry, "updated"):
                        published = entry.updated

                    results.append({
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", "")[:500],
                        "source": feed_info["name"],
                        "link": entry.get("link", ""),
                        "published": published,
                        "source_type": "news_rss",
                    })
            except Exception as e:
                logger.warning(f"RSS feed failed for {feed_info['name']}: {e}")

        return results
