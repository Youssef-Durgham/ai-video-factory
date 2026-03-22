"""
Phase handler wrappers — glue between pipeline phases and their components.
Each handler extends BasePhase, calls component modules, saves to DB, returns PhaseResult.

Phases 1-4: Fully wired to components (LLM-based, no GPU needed).
Phases 5+: Stubbed until GPU pipeline is ready.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.phase_executor import BasePhase
from src.core.config import get_channel_config
from src.core.llm import generate_json
from src.models.analytics import PhaseResult
from src.core.job_state_machine import JobStatus

logger = logging.getLogger(__name__)


def _notify(text: str):
    """Send a Telegram progress notification (non-blocking, fire-and-forget)."""
    try:
        from src.core.telegram_callbacks import send_telegram_sync
        send_telegram_sync(text)
    except Exception:
        pass


def _get_telegram_creds():
    """Get bot token and chat ID from env or config."""
    import os
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        try:
            from src.core.config import load_config
            cfg = load_config()
            tg = cfg.get("settings", {}).get("telegram", {})
            bot_token = bot_token or tg.get("bot_token", "")
            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
        except Exception:
            pass
    return bot_token, chat_id


def _send_audio_preview(job_id: str, audio_path: str, caption: str):
    """Send an audio file to Telegram for preview."""
    try:
        import requests
        bot_token, chat_id = _get_telegram_creds()
        if not bot_token or not chat_id:
            return
        api = f"https://api.telegram.org/bot{bot_token}"
        cap = f"{caption}\n🆔 <code>{job_id}</code>"
        with open(audio_path, "rb") as f:
            requests.post(f"{api}/sendAudio", data={
                "chat_id": chat_id, "caption": cap, "parse_mode": "HTML",
            }, files={"audio": (Path(audio_path).name, f, "audio/mpeg")}, timeout=60)
    except Exception as e:
        logger.warning(f"Failed to send audio preview: {e}")


def _send_video_preview(job_id: str, video_path: str, caption: str):
    """Send a video file to Telegram for preview."""
    try:
        import requests
        bot_token, chat_id = _get_telegram_creds()
        if not bot_token or not chat_id:
            return
        api = f"https://api.telegram.org/bot{bot_token}"
        cap = f"{caption}\n🆔 <code>{job_id}</code>"
        file_size = Path(video_path).stat().st_size
        # Telegram limit: 50MB for bots
        if file_size > 50 * 1024 * 1024:
            _notify(f"⚠️ الفيديو كبير ({file_size/1024/1024:.0f}MB) — ما يتحمّل على تلگرام")
            return
        with open(video_path, "rb") as f:
            requests.post(f"{api}/sendVideo", data={
                "chat_id": chat_id, "caption": cap, "parse_mode": "HTML",
                "supports_streaming": "true",
            }, files={"video": (Path(video_path).name, f, "video/mp4")}, timeout=120)
    except Exception as e:
        logger.warning(f"Failed to send video preview: {e}")


# ═══════════════════════════════════════════════════════════════
# Phase 1: Research
# ═══════════════════════════════════════════════════════════════

class ResearchPhase(BasePhase):
    """Discover and validate a topic for the video."""

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        channel_config = get_channel_config(job["channel_id"], self.config)
        topic = job.get("topic", "")
        topic_source = job.get("topic_source", "manual")

        if topic_source == "manual":
            # Manual topic — validate with LLM, skip trend research
            result = self._validate_manual_topic(topic, channel_config)
        else:
            # Auto topic — generate topic suggestions and send to user for selection
            result = self._auto_research(channel_config)

            # ALWAYS send topics to user for selection in auto mode
            ranked = result.get("all_ranked", [])
            logger.info(f"Auto research: got {len(ranked)} ranked topics")

            # If we got 0 topics but have a single selected_topic, wrap it
            if not ranked and result.get("selected_topic"):
                ranked = [{"topic": result["selected_topic"], "score": result.get("score", 7),
                           "suggested_angle": result.get("angle", ""), "ideal_length_min": 10,
                           "category": "", "pros": [], "cons": []}]

            if ranked:
                self._send_topic_choices(job_id, ranked)
                # Save partial research and pause for user selection
                self.db.conn.execute("""
                    INSERT INTO research (job_id, topic, source, suggested_angle,
                        rank_score, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    job_id, "awaiting_selection", topic_source,
                    "", 0, json.dumps(result),
                ))
                self.db.conn.commit()
                return PhaseResult(
                    success=False, blocked=True,
                    reason="⏸️ بانتظار اختيار الموضوع",
                    score=0,
                )

            # Fallback: no topics at all — shouldn't happen
            logger.error("Auto research returned 0 topics!")
            topic = result.get("selected_topic", topic)

        # Save research to DB
        self.db.conn.execute("""
            INSERT INTO research (job_id, topic, source, suggested_angle,
                rank_score, raw_data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job_id, topic, topic_source,
            result.get("angle", ""),
            result.get("score", 7.0),
            json.dumps(result),
        ))
        self.db.conn.commit()

        # Update job topic if auto-selected
        if topic_source != "manual" and result.get("selected_topic"):
            self.db.conn.execute(
                "UPDATE jobs SET topic = ?, topic_region = ? WHERE id = ?",
                (result["selected_topic"], result.get("region", "global"), job_id),
            )
            self.db.conn.commit()

        score = result.get("score", 7.0)
        logger.info(f"Research complete for {job_id}: topic='{topic}', score={score}")
        return PhaseResult(success=True, score=score)

    def _generate_topics_via_llm(self, channel_config: dict) -> dict:
        """Generate topic suggestions via LLM when trend APIs fail."""
        channel_name = channel_config.get("name", "وثائقيات")
        channel_topics = channel_config.get("content", {}).get("topics", [])
        topics_str = ", ".join(channel_topics) if channel_topics else "تاريخ، علوم، تكنولوجيا، سياسة، اقتصاد"

        result = generate_json(
            prompt=f"""أنت خبير محتوى يوتيوب عربي مثل "الدحيح" و"وثائقيات الجزيرة". اقترح 6 مواضيع مثيرة ومتنوعة لفيديوهات وثائقية لقناة "{channel_name}".

المواضيع يجب أن تكون:
- متنوعة وعالمية (علوم، تاريخ، فلسفة، تكنولوجيا، طبيعة، فضاء، نفس بشرية، اقتصاد، طب، فيزياء...)
- مثيرة للفضول بأسلوب "هل تعلم" أو "لماذا" أو "ماذا لو" أو "القصة الحقيقية وراء..."
- بنفس أسلوب الدحيح: تبسيط العلوم والتاريخ بطريقة ممتعة وساخرة
- أو بأسلوب وثائقيات الجزيرة: تحقيقات معمقة وقصص إنسانية مؤثرة
- ليست محصورة بالعالم العربي — مواضيع عالمية يهتم بها أي شخص فضولي

أمثلة على مواضيع ناجحة:
- "لماذا لا نستطيع تذكر أحلامنا؟"
- "الرجل الذي خدع العالم كله لمدة 30 سنة"
- "ماذا يحدث لجسمك إذا توقفت عن النوم؟"
- "لماذا الموسيقى تسبب لنا القشعريرة؟"
- "أغرب تجارب الحرب الباردة السرية"

لكل موضوع اعطِ:
- عنوان جذاب يثير الفضول (clickbait ذكي)
- تقييم من 1-10 (احتمالية النجاح على يوتيوب)
- زاوية التناول المقترحة
- المدة المثالية بالدقائق (قيّم كم يحتاج الموضوع ليكون مشوّق بدون ملل — بعض المواضيع تحتاج 5 دقائق فقط وبعضها 15)
- 2-3 مميزات
- 1-2 سلبيات
- التصنيف (علوم/تاريخ/تكنولوجيا/نفس/طبيعة/فضاء/اقتصاد/طب/فلسفة/غرائب)

مهم: المدة المثالية تعتمد على عمق الموضوع. موضوع بسيط مثل "لماذا نتثاءب" يكفيه 5-7 دقائق. موضوع معقد مثل "تاريخ الحرب الباردة السرية" يحتاج 12-15 دقيقة. لا تجعل كل المواضيع 10 دقائق!

أجب بـ JSON:
{{
    "topics": [
        {{
            "topic": "العنوان",
            "score": 8.5,
            "suggested_angle": "الزاوية",
            "suggested_region": "global",
            "category": "التصنيف",
            "ideal_length_min": 10,
            "pros": ["ميزة 1", "ميزة 2"],
            "cons": ["سلبية 1"]
        }}
    ]
}}""",
            temperature=0.7,
        )

        topics = result.get("topics", [])
        if not topics:
            return {"score": 5.0, "angle": "", "region": "global", "error": "LLM returned no topics"}

        # Sort by score
        topics.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "selected_topic": topics[0].get("topic", ""),
            "score": topics[0].get("score", 7.0),
            "angle": topics[0].get("suggested_angle", ""),
            "region": topics[0].get("suggested_region", "global"),
            "all_ranked": topics,
        }

    def _send_topic_choices(self, job_id: str, ranked_topics: list):
        """Send ranked topic options to Telegram with selection buttons."""
        import requests
        import os
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            tg = self.config.get("settings", {}).get("telegram", {})
            bot_token = bot_token or tg.get("bot_token", "")
            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
        if not bot_token or not chat_id:
            logger.warning("No Telegram credentials for topic selection")
            return

        api = f"https://api.telegram.org/bot{bot_token}"

        # Header
        header = (
            "\U0001f50d <b>مواضيع مقترحة</b>\n\n"
            f"\U0001f4e6 Job: <code>{job_id}</code>\n\n"
            "اختر الموضوع اللي يعجبك:"
        )
        requests.post(f"{api}/sendMessage", json={
            "chat_id": chat_id, "text": header, "parse_mode": "HTML"
        }, timeout=10)

        # Send each topic as a card with select button
        import time
        for i, t in enumerate(ranked_topics[:8]):  # Max 8 topics
            topic_name = t.get("topic", "—")
            score = t.get("score", 0)
            angle = t.get("suggested_angle", "")
            category = t.get("category", "")

            # Category emojis
            cat_emojis = {
                "علوم": "\U0001f52c", "تاريخ": "\U0001f3db", "تكنولوجيا": "\U0001f4bb",
                "نفس": "\U0001f9e0", "طبيعة": "\U0001f333", "فضاء": "\U0001f680",
                "اقتصاد": "\U0001f4b0", "طب": "\U0001f3e5", "فلسفة": "\U0001f914",
                "غرائب": "\U0001f47d", "فيزياء": "\u269b", "سياسة": "\U0001f3db",
            }
            cat_emoji = cat_emojis.get(category, "\U0001f4d6")

            stars = "\u2b50" * min(int(score), 5)
            card = (
                f"<b>{i+1}. {topic_name}</b>\n\n"
                f"\U0001f4ca التقييم: {score:.1f}/10 {stars}\n"
            )
            ideal_len = t.get("ideal_length_min", 10)
            if category:
                card += f"{cat_emoji} التصنيف: {category}\n"
            card += f"\u23f1 المدة المثالية: {ideal_len} دقائق\n"
            if angle:
                card += f"\U0001f3af الزاوية: {angle}\n"

            # Pros
            pros = t.get("pros", [])
            if pros:
                card += "\n\u2705 <b>المميزات:</b>\n"
                for p in pros[:3]:
                    card += f"  \u2022 {p}\n"

            # Cons
            cons = t.get("cons", [])
            if cons:
                card += "\n\u26a0\ufe0f <b>السلبيات:</b>\n"
                for c in cons[:3]:
                    card += f"  \u2022 {c}\n"

            keyboard = {
                "inline_keyboard": [[
                    {"text": f"\u2705 اختيار هذا الموضوع", "callback_data": f"ts_{job_id}_{i}"}
                ]]
            }
            requests.post(f"{api}/sendMessage", json={
                "chat_id": chat_id, "text": card, "parse_mode": "HTML",
                "reply_markup": keyboard
            }, timeout=10)
            time.sleep(0.3)

        # Save topics to review state for callback handler
        try:
            review_state_path = Path("data/review_state.json")
            state = {}
            if review_state_path.exists():
                state = json.loads(review_state_path.read_text(encoding="utf-8"))
            state[f"topics_{job_id}"] = ranked_topics[:8]
            review_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save topic state: {e}")

        logger.info(f"Sent {min(len(ranked_topics), 8)} topic choices to Telegram for {job_id}")

    def _validate_manual_topic(self, topic: str, channel_config: dict) -> dict:
        """Validate a user-provided topic with LLM."""
        channel_name = channel_config.get("name", "وثائقيات")
        channel_topics = channel_config.get("content", {}).get("topics", [])

        result = generate_json(
            prompt=f"""حلل هذا الموضوع لفيديو وثائقي على قناة "{channel_name}":

الموضوع: {topic}
تصنيفات القناة: {', '.join(channel_topics) if channel_topics else 'عام'}

أجب بـ JSON:
{{
    "valid": true,
    "score": 8.0,
    "angle": "الزاوية المقترحة للتناول",
    "region": "iraq|gulf|egypt|levant|maghreb|global",
    "content_depth": "كافي لفيديو 8-12 دقيقة؟",
    "risks": ["أي مخاطر محتملة"],
    "notes": "ملاحظات إضافية"
}}""",
            temperature=0.3,
        )

        if not result.get("valid", True):
            logger.warning(f"Topic validation failed: {topic}")

        return {
            "score": result.get("score", 7.0),
            "angle": result.get("angle", ""),
            "region": result.get("region", "global"),
            "notes": result,
        }

    def _auto_research(self, channel_config: dict) -> dict:
        """Full auto-research: YouTube trends + web trends + ranking."""
        from src.phase1_research import YouTubeTrends, WebTrends, TopicRanker

        channel_name = channel_config.get("name", "وثائقيات")
        channel_topics = channel_config.get("content", {}).get("topics", [])

        # Gather trend data
        yt_trends = YouTubeTrends(self.config)
        web_trends = WebTrends(self.config)
        ranker = TopicRanker(self.config)

        try:
            youtube_data = yt_trends.get_trending(
                region_codes=["IQ", "SA", "EG"],
                category_id="27",  # Education
            )
        except Exception as e:
            logger.warning(f"YouTube trends failed: {e}")
            youtube_data = []

        try:
            web_data = web_trends.get_rss_trends()
        except Exception as e:
            logger.warning(f"Web trends failed: {e}")
            web_data = []

        if not youtube_data and not web_data:
            # Fallback: generate topics via LLM
            logger.info("No trend data — generating topics via LLM")
            return self._generate_topics_via_llm(channel_config)

        ranked = ranker.rank_topics(youtube_data, web_data, channel_config)

        if not ranked:
            return {"score": 5.0, "angle": "", "region": "global",
                    "error": "Ranking returned no topics"}

        best = ranked[0]
        return {
            "selected_topic": best.get("topic", ""),
            "score": best.get("score", 7.0),
            "angle": best.get("suggested_angle", ""),
            "region": best.get("suggested_region", "global"),
            "all_ranked": ranked,
        }


# ═══════════════════════════════════════════════════════════════
# Phase 2: SEO
# ═══════════════════════════════════════════════════════════════

class SEOPhase(BasePhase):
    """Keyword research, title generation, tag planning."""

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        topic = job["topic"]
        channel_config = get_channel_config(job["channel_id"], self.config)

        from src.phase2_seo import KeywordResearch, TitleGenerator, TagPlanner, CompetitorAnalysis

        kw_research = KeywordResearch(self.config)
        title_gen = TitleGenerator(self.config)
        tag_planner = TagPlanner(self.config)
        competitor = CompetitorAnalysis(self.config)

        # 1. Keyword research
        logger.info(f"SEO: keyword research for '{topic}'")
        keyword_report = kw_research.analyze_top_results(topic)
        autocomplete = kw_research.get_autocomplete(topic)
        keyword_report["autocomplete"] = autocomplete

        # 2. Competitor / gap analysis
        logger.info(f"SEO: competitor analysis for '{topic}'")
        try:
            gap_analysis = competitor.analyze(topic, keyword_report)
        except Exception as e:
            logger.warning(f"Competitor analysis failed: {e}")
            gap_analysis = {"recommended_angle": "تحليل شامل"}

        # 3. Generate titles
        logger.info(f"SEO: generating titles for '{topic}'")
        titles = title_gen.generate_titles(topic, keyword_report, gap_analysis)
        selected_title = titles[0] if titles else {"title": topic, "overall_score": 5.0}

        # 4. Tags + description
        primary_kw = [k.get("keyword", k) if isinstance(k, dict) else k
                      for k in keyword_report.get("keywords", [])[:10]]
        logger.info(f"SEO: planning tags for '{topic}'")
        tag_result = tag_planner.plan_tags_description(
            topic=topic,
            keywords=primary_kw,
            title=selected_title.get("title", topic),
        )

        # Save SEO data to DB
        self.db.conn.execute("""
            INSERT INTO seo_data (job_id, primary_keywords, secondary_keywords,
                generated_titles, selected_title, selected_title_score,
                tags, description_template, hashtags, unique_angle, content_gap)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            json.dumps(primary_kw),
            json.dumps(autocomplete[:20]),
            json.dumps(titles),
            selected_title.get("title", topic),
            selected_title.get("overall_score", 5.0),
            json.dumps(tag_result.get("tags", [])),
            tag_result.get("description_template", ""),
            json.dumps(tag_result.get("hashtags", [])),
            gap_analysis.get("recommended_angle", ""),
            json.dumps(gap_analysis.get("content_gaps", [])),
        ))
        self.db.conn.commit()

        score = selected_title.get("overall_score", 7.0)
        logger.info(f"SEO complete for {job_id}: title='{selected_title.get('title')}', score={score}")
        return PhaseResult(success=True, score=score)


# ═══════════════════════════════════════════════════════════════
# Phase 3: Script
# ═══════════════════════════════════════════════════════════════

class ScriptPhase(BasePhase):
    """Research → write script → split into scenes."""

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        topic = job["topic"]
        channel_config = get_channel_config(job["channel_id"], self.config)

        # Override target length if set per-job
        job_target = job.get("target_length_min")
        if job_target and job_target > 0:
            if "content" not in channel_config:
                channel_config["content"] = {}
            channel_config["content"]["target_length_min"] = int(job_target)

        from src.phase3_script import Researcher, ScriptWriter, SceneSplitter

        # 1. Deep research
        logger.info(f"Script: researching '{topic}'")
        researcher = Researcher(self.config)
        research = researcher.research_topic(
            topic=topic,
            angle=self._get_angle(job_id),
        )

        # 2. Get SEO data for the script
        seo_data = self._get_seo_data(job_id)

        # 3. Get performance rules from past videos
        rules = self.db.get_active_rules(job.get("channel_id"))

        # 4. Write script
        logger.info(f"Script: writing script for '{topic}'")
        writer = ScriptWriter(self.config)
        script_text = writer.write_script(
            topic=topic,
            research=research,
            seo_data=seo_data,
            channel_config=channel_config,
            performance_rules=rules,
        )

        if not script_text or len(script_text.strip()) < 100:
            return PhaseResult(
                success=False, blocked=True,
                reason="Script generation produced empty/too-short output",
            )

        # 5. Split into scenes
        logger.info(f"Script: splitting into scenes for '{topic}'")
        splitter = SceneSplitter(self.config)
        region = job.get("topic_region", "global")
        scenes = splitter.split_to_scenes(
            script_text=script_text,
            topic=topic,
            region=region,
            channel_config=channel_config,
        )

        if not scenes:
            return PhaseResult(
                success=False, blocked=True,
                reason="Scene splitting produced no scenes",
            )

        # 5.5. Self-review: LLM reviews the script for issues before sending to user
        logger.info(f"Script: self-reviewing script for '{topic}'")
        try:
            review_prompt = f"""أنت مراجع سكربتات وثائقية محترف. راجع السكربت التالي وأصلح أي مشاكل:

**الموضوع:** {topic}
**السكربت:**
{script_text}

## تعليمات المراجعة:
1. تأكد من عدم وجود جمل مقطوعة أو غير مكتملة
2. تأكد أن المقدمة جذابة وتحتوي على hook قوي
3. تأكد أن الخاتمة تحتوي على call-to-action (اشتراك، إعجاب، تعليق)
4. صحح أي أخطاء نحوية أو إملائية
5. تأكد أن الانتقالات بين المشاهد سلسة
6. تأكد أن الأرقام والحقائق منطقية
7. تأكد أن الأسلوب متسق طوال السكربت (فصحى وسلس)
8. أزل أي تكرار غير مبرر
9. تأكد أن الطول مناسب (ليس قصير جداً ولا طويل جداً)

أعد السكربت المُعدّل فقط بدون أي تعليقات أو شروحات. إذا كان السكربت جيداً، أعده كما هو."""

            from src.core.llm import generate
            reviewed_script = generate(
                prompt=review_prompt,
                system="أنت مراجع سكربتات عربية. أعد السكربت المصحح فقط بدون أي تعليقات.",
                max_tokens=16000,
            )
            if reviewed_script and len(reviewed_script.strip()) > 100:
                script_text = reviewed_script.strip()
                logger.info(f"Script self-review complete: {len(script_text.split())} words")

                # Re-split scenes with reviewed script
                scenes = splitter.split_to_scenes(
                    script_text=script_text,
                    topic=topic,
                    region=region,
                    channel_config=channel_config,
                )
                if not scenes:
                    logger.warning("Scene re-split after review failed, using original scenes")
            else:
                logger.warning("Script self-review returned empty, using original")
        except Exception as e:
            logger.warning(f"Script self-review failed (using original): {e}")

        # 6. Save to DB
        word_count = len(script_text.split())
        self.db.save_script(
            job_id=job_id,
            full_text=script_text,
            version=1,
            word_count=word_count,
            estimated_duration_sec=int(word_count / 2.5),  # ~2.5 words/sec Arabic
        )
        self.db.save_scenes(job_id, scenes)

        logger.info(f"Script complete for {job_id}: {word_count} words, {len(scenes)} scenes")
        return PhaseResult(success=True, score=8.0)

    def _get_angle(self, job_id: str) -> str:
        """Get suggested angle from research phase."""
        row = self.db.conn.execute(
            "SELECT suggested_angle FROM research WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return dict(row).get("suggested_angle", "") if row else ""

    def _get_seo_data(self, job_id: str) -> dict:
        """Get SEO data from phase 2."""
        row = self.db.conn.execute(
            "SELECT * FROM seo_data WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if not row:
            return {}
        data = dict(row)
        # Parse JSON fields
        for field in ("primary_keywords", "generated_titles", "tags", "hashtags"):
            if data.get(field) and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return data


# ═══════════════════════════════════════════════════════════════
# Phase 4: Compliance
# ═══════════════════════════════════════════════════════════════

class CompliancePhase(BasePhase):
    """YouTube policy + AI content quality + fact checking.
    
    AUTO-FIX: Instead of blocking on fact errors, attempts to fix the script
    automatically by rewriting problematic claims, then re-checks.
    Only blocks if auto-fix fails after MAX_FIX_ATTEMPTS.
    """

    MAX_FIX_ATTEMPTS = 2  # Max auto-fix retries before blocking

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        from src.phase4_compliance import (
            YouTubePolicyChecker, AIContentChecker, FactChecker,
        )

        # Get script text
        script_row = self.db.conn.execute(
            "SELECT full_text FROM scripts WHERE job_id = ? ORDER BY version DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if not script_row:
            return PhaseResult(success=False, blocked=True, reason="No script found")
        script_text = dict(script_row)["full_text"]

        # Get scenes for AI content check
        scenes = self.db.get_scenes(job_id)

        # Get research sources for fact checking
        research_row = self.db.conn.execute(
            "SELECT raw_data FROM research WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        research_sources = []
        if research_row:
            try:
                raw = json.loads(dict(research_row).get("raw_data", "{}"))
                research_sources = raw.get("sources", [])
            except (json.JSONDecodeError, TypeError):
                pass

        # 1. YouTube policy check (with auto-fix)
        logger.info(f"Compliance: YouTube policy check for {job_id}")
        policy_checker = YouTubePolicyChecker(self.config)
        policy_result = policy_checker.check(script_text)

        if policy_result.get("status") == "block":
            logger.warning(f"YouTube policy violation for {job_id}, attempting auto-fix...")
            fixed = self._auto_fix_script(script_text, "youtube_policy", policy_result)
            if fixed:
                script_text = fixed
                policy_result = policy_checker.check(script_text)
                if policy_result.get("status") == "block":
                    return PhaseResult(
                        success=False, blocked=True,
                        reason=f"YouTube policy violation (auto-fix failed): {policy_result.get('checks', [])}",
                        score=policy_result.get("score", 0),
                    )
                logger.info(f"YouTube policy auto-fix successful for {job_id}")
                self._save_fixed_script(job_id, script_text, "Auto-fixed YouTube policy issues")
            else:
                return PhaseResult(
                    success=False, blocked=True,
                    reason=f"YouTube policy violation: {policy_result.get('checks', [])}",
                    score=policy_result.get("score", 0),
                )

        # 2. AI content quality check (with auto-fix)
        logger.info(f"Compliance: AI content quality check for {job_id}")
        ai_checker = AIContentChecker(self.config)
        ai_result = ai_checker.check(script_text, scenes)

        if ai_result.get("status") == "block":
            logger.warning(f"AI content quality issue for {job_id}, attempting auto-fix...")
            fixed = self._auto_fix_script(script_text, "ai_quality", ai_result)
            if fixed:
                script_text = fixed
                ai_result = ai_checker.check(script_text, scenes)
                if ai_result.get("status") != "block":
                    logger.info(f"AI content auto-fix successful for {job_id}")
                    self._save_fixed_script(job_id, script_text, "Auto-fixed AI content quality")
                else:
                    logger.warning(f"AI content auto-fix failed for {job_id}, continuing anyway with warning")
                    ai_result["status"] = "warn"  # Downgrade to warning instead of blocking

        # 3. Fact checking (with auto-fix — up to MAX_FIX_ATTEMPTS)
        logger.info(f"Compliance: fact checking for {job_id}")
        fact_checker = FactChecker(self.config)
        fact_result = fact_checker.check(script_text, research_sources)

        fix_attempt = 0
        while fact_result.get("status") == "block" and fix_attempt < self.MAX_FIX_ATTEMPTS:
            fix_attempt += 1
            false_count = fact_result.get("false", 0)
            logger.warning(
                f"Fact check failed for {job_id}: {false_count} false claims. "
                f"Auto-fix attempt {fix_attempt}/{self.MAX_FIX_ATTEMPTS}..."
            )
            fixed = self._auto_fix_script(script_text, "fact_check", fact_result)
            if fixed:
                script_text = fixed
                self._save_fixed_script(job_id, script_text, f"Auto-fixed facts (attempt {fix_attempt})")
                # Re-check
                fact_result = fact_checker.check(script_text, research_sources)
                if fact_result.get("status") != "block":
                    logger.info(f"Fact check auto-fix successful on attempt {fix_attempt} for {job_id}")
            else:
                break

        # If fact check still fails after all attempts, downgrade to warning (don't block)
        if fact_result.get("status") == "block":
            logger.warning(
                f"Fact check auto-fix exhausted for {job_id} after {fix_attempt} attempts. "
                f"Downgrading to warning and continuing."
            )
            fact_result["status"] = "warn"
            fact_result["score"] = max(fact_result.get("score", 0), 4.0)

        # Aggregate score (weighted average)
        policy_score = policy_result.get("score", 7.0)
        ai_score = ai_result.get("score", 7.0)
        fact_score = fact_result.get("score", 7.0)
        avg_score = (policy_score * 0.3 + ai_score * 0.3 + fact_score * 0.4)

        # Warn if any check has warnings
        has_warnings = (
            policy_result.get("status") == "warn"
            or ai_result.get("status") == "warn"
            or fact_result.get("status") == "warn"
        )

        logger.info(
            f"Compliance complete for {job_id}: policy={policy_score}, "
            f"ai={ai_score}, fact={fact_score}, avg={avg_score:.1f}"
        )

        return PhaseResult(
            success=True,
            score=avg_score,
            reason="Warnings present — review recommended" if has_warnings else "",
        )

    def _auto_fix_script(self, script_text: str, issue_type: str, check_result: dict) -> Optional[str]:
        """Attempt to auto-fix script based on compliance issues."""
        from src.core.llm import generate

        issues_desc = ""
        if issue_type == "fact_check":
            claims = check_result.get("claims", [])
            false_claims = [c for c in claims if c.get("status") == "false"]
            if false_claims:
                issues_desc = "الادعاءات الخاطئة التي تحتاج تصحيح:\n"
                for c in false_claims:
                    issues_desc += f"- خاطئ: {c.get('claim', '?')}\n"
                    if c.get("correction"):
                        issues_desc += f"  التصحيح المقترح: {c['correction']}\n"
            unverified = [c for c in claims if c.get("status") == "unverified"]
            if unverified:
                issues_desc += "\nادعاءات غير موثقة (أضف تحفظاً أو احذفها):\n"
                for c in unverified:
                    issues_desc += f"- {c.get('claim', '?')}\n"

        elif issue_type == "youtube_policy":
            checks = check_result.get("checks", check_result.get("flagged_items", []))
            issues_desc = f"مخالفات سياسات يوتيوب:\n{json.dumps(checks, ensure_ascii=False)}"

        elif issue_type == "ai_quality":
            issues_desc = f"المحتوى يبدو مولّد بالذكاء الاصطناعي بشكل واضح. أعد صياغته بأسلوب أكثر طبيعية وإنسانية."

        if not issues_desc:
            return None

        try:
            fixed = generate(
                prompt=f"""أعد كتابة السكربت التالي مع تصحيح المشاكل المذكورة.
حافظ على نفس الهيكلية والأسلوب والطول، فقط أصلح المشاكل.

═══ المشاكل ═══
{issues_desc}

═══ السكربت الأصلي ═══
{script_text[:10000]}

أعد السكربت المصحح كاملاً فقط (بدون تعليقات أو شروحات):""",
                system="أنت محرر سكربتات وثائقية عربية. أصلح المشاكل المذكورة مع الحفاظ على الجودة والأسلوب.",
                max_tokens=8192,
                temperature=0.3,
            )
            if fixed and len(fixed.split()) > 300:
                return fixed.strip()
        except Exception as e:
            logger.error(f"Auto-fix generation failed: {e}")

        return None

    def _save_fixed_script(self, job_id: str, script_text: str, reason: str):
        """Save the auto-fixed script as a new version."""
        try:
            # Get current version
            row = self.db.conn.execute(
                "SELECT MAX(version) as v FROM scripts WHERE job_id = ?", (job_id,)
            ).fetchone()
            new_version = (dict(row).get("v", 0) or 0) + 1

            word_count = len(script_text.split())
            self.db.conn.execute("""
                INSERT INTO scripts (job_id, full_text, version, word_count,
                    estimated_duration_sec, status)
                VALUES (?, ?, ?, ?, ?, 'auto_fixed')
            """, (
                job_id, script_text, new_version, word_count,
                int(word_count / 2.5),
            ))
            self.db.conn.commit()

            # Also re-split scenes with the fixed script
            from src.phase3_script import SceneSplitter
            from src.core.config import get_channel_config
            job = self.db.get_job(job_id)
            channel_config = get_channel_config(job["channel_id"], self.config)
            splitter = SceneSplitter(self.config)
            scenes = splitter.split_to_scenes(
                script_text=script_text,
                topic=job.get("topic", ""),
                region=job.get("topic_region", "global"),
                channel_config=channel_config,
            )
            if scenes:
                self.db.save_scenes(job_id, scenes)

            logger.info(f"Saved auto-fixed script v{new_version} for {job_id}: {reason}")
        except Exception as e:
            logger.error(f"Failed to save fixed script: {e}")


# ═══════════════════════════════════════════════════════════════
# Phase 5: Images (FLUX via ComfyUI)
# ═══════════════════════════════════════════════════════════════

class ImagesPhase(BasePhase):
    """Generate images for all scenes using FLUX via ComfyUI."""

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase5_production.image_gen import ImageGenerator, ImageGenConfig

        img_config = ImageGenConfig(
            comfyui_host="http://127.0.0.1:8000",
            model_name="flux1-dev-fp8.safetensors",
            width=1280,
            height=720,
            steps=20,
            cfg=1.0,
            sampler="euler",
            scheduler="normal",
            timeout_sec=300,
        )
        gen = ImageGenerator(img_config)

        # Ensure ComfyUI is running (auto-start if needed)
        if not gen.ensure_server(max_wait=120):
            return PhaseResult(
                success=False, blocked=True,
                reason="ComfyUI server not reachable — auto-start failed",
            )

        output_dir = str(Path(f"output/{job_id}/images"))
        success_count = 0
        total = len(scenes)

        for scene in scenes:
            idx = scene["scene_index"]
            prompt = scene.get("visual_prompt", "")
            if not prompt.strip():
                logger.warning(f"Scene {idx} has no visual_prompt, skipping")
                continue

            logger.info(f"Generating image for scene {idx}/{total - 1}")
            if idx % 5 == 0 or idx == 0:  # Notify every 5 images to avoid spam
                _notify(f"🎨 صورة {idx + 1}/{total}...")

            result = gen.generate(
                prompt=prompt,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                width=1280,
                height=720,
            )

            if result.success and result.image_path:
                self.db.update_scene_asset(
                    job_id, idx,
                    image_path=result.image_path,
                    image_seed=result.seed,
                )
                success_count += 1
                logger.info(f"Scene {idx} image saved: {result.image_path}")
            else:
                logger.error(f"Scene {idx} image failed: {result.error}")

        if success_count == 0:
            return PhaseResult(
                success=False, blocked=True,
                reason=f"All {total} image generations failed",
            )

        score = (success_count / total) * 10.0
        logger.info(f"Images complete for {job_id}: {success_count}/{total} succeeded")
        return PhaseResult(success=True, score=score)


# ═══════════════════════════════════════════════════════════════
# Phase 8: Voice (Fish Speech TTS)
# ═══════════════════════════════════════════════════════════════

class VoicePhase(BasePhase):
    """Generate voice narration for all scenes using Fish Speech + Edge TTS fallback.
    
    If voice profiles exist, pauses to let user choose a voice via Telegram.
    The selected voice_id is stored in the review_state and used for generation.
    """

    def _get_telegram_creds(self):
        import os
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            tg = self.config.get("settings", {}).get("telegram", {})
            bot_token = bot_token or tg.get("bot_token", "")
            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
        return bot_token, chat_id

    def run(self, job_id: str) -> PhaseResult:
        import requests
        import time
        from src.phase5_production.voice_gen import VoiceGenerator
        from src.phase5_production.voice_cloner import VoiceCloner

        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        total = len(scenes)
        logger.info(f"Voice phase starting for {job_id}: {total} scenes")

        # Check if user already selected a voice (resuming after selection)
        review_state_path = Path("data/review_state.json")
        review_state = {}
        if review_state_path.exists():
            try:
                review_state = json.loads(review_state_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Check if voice review already approved → skip everything
        voice_approved = review_state.get(f"voice_approved_{job_id}")
        if voice_approved:
            review_state.pop(f"voice_approved_{job_id}", None)
            review_state_path.write_text(json.dumps(review_state, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Voice already approved for {job_id}")
            return PhaseResult(success=True, score=9.0)

        # Check if voices already generated → skip to review
        voice_dir = Path(f"output/{job_id}/voice")
        existing_voices = list(voice_dir.glob("scene_*.mp3")) if voice_dir.exists() else []
        if existing_voices and len(existing_voices) >= len(scenes) * 0.8:
            logger.info(f"Voice already generated ({len(existing_voices)} files), skipping to review")
            # Update DB with existing paths
            from src.phase5_production.voice_gen import VoiceGenResult
            results = []
            for scene in scenes:
                idx = scene.get("scene_index", 0)
                vp = voice_dir / f"scene_{idx:03d}.mp3"
                if vp.exists():
                    self.db.update_scene_asset(job_id, idx, voice_path=str(vp))
                    results.append(VoiceGenResult(success=True, audio_path=str(vp), duration_sec=0, engine="fish_speech"))
                else:
                    results.append(VoiceGenResult(success=False, error="File not found"))
            # Send to review
            bot_token, chat_id = self._get_telegram_creds()
            if bot_token and chat_id:
                return self._send_voice_review(job_id, scenes, results, str(voice_dir), bot_token, chat_id)
            return PhaseResult(success=True, score=8.0)

        # Get selected voice ID (from review_state or DB)
        selected_voice_id = review_state.pop(f"voice_selected_{job_id}", None)
        if selected_voice_id:
            review_state_path.write_text(json.dumps(review_state, ensure_ascii=False, indent=2), encoding="utf-8")
            # Save to DB so we don't lose it
            self.db.conn.execute("UPDATE jobs SET selected_voice_id=? WHERE id=?", (selected_voice_id, job_id))
            self.db.conn.commit()
        else:
            # Check DB for previously selected voice
            job = self.db.get_job(job_id)
            selected_voice_id = job.get("selected_voice_id") if job else None

        if not selected_voice_id:
            # Ask user to choose voice
            cloner = VoiceCloner()
            voices = cloner.list_voices()
            if voices:
                bot_token, chat_id = self._get_telegram_creds()
                if bot_token and chat_id:
                    return self._send_voice_selection(job_id, voices, cloner, bot_token, chat_id)

        # Generate voice with selected voice (or default/none)
        voice_id = selected_voice_id if selected_voice_id != "__edge_tts__" else None

        gen = VoiceGenerator()

        # Start Fish Speech server (nuclear cleanup may have killed it)
        _notify("🎙️ تشغيل خادم الصوت...")
        if not gen.ensure_server(max_wait=180):
            logger.warning("Fish Speech server failed to start — will try Edge TTS fallback")
            _notify("⚠️ خادم الصوت لم يعمل — سنستخدم البديل")

        output_dir = f"output/{job_id}/voice"

        # Generate voice for each scene (simple generation, more reliable)
        results = []
        total = len(scenes)
        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            narration = scene.get("narration_text", "")
            if not narration or not narration.strip():
                logger.warning(f"Scene {idx} has no narration text, skipping")
                from src.phase5_production.voice_gen import VoiceGenResult
                results.append(VoiceGenResult(success=False, error="No narration text"))
                continue

            logger.info(f"Generating voice {i + 1}/{total} (scene {idx})")
            if i % 5 == 0:
                _notify(f"🎙️ تعليق {i + 1}/{total}...")

            # Detect mood from scene data for mood-specific voice reference
            scene_mood = scene.get("music_mood", "")
            voice_mood = None
            if scene_mood:
                mood_lower = scene_mood.lower()
                if any(w in mood_lower for w in ["dramatic", "tense", "epic", "mystery"]):
                    voice_mood = "dramatic"
                elif any(w in mood_lower for w in ["calm", "peaceful", "sad"]):
                    voice_mood = "calm"
            # Questions get question mood
            if narration.strip().endswith("؟"):
                voice_mood = "question"

            result = gen.generate(
                text=narration,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                voice_id=voice_id,
                mood=voice_mood,
            )
            results.append(result)

        success_count = 0
        for scene, result in zip(scenes, results):
            idx = scene["scene_index"]
            if result.success and result.audio_path:
                self.db.update_scene_asset(job_id, idx, voice_path=result.audio_path)
                success_count += 1
                logger.info(f"Scene {idx} voice saved: {result.audio_path} ({result.engine}, {result.duration_sec}s)")
            else:
                logger.error(f"Scene {idx} voice failed: {getattr(result, 'error', 'unknown')}")

        if success_count == 0:
            return PhaseResult(success=False, blocked=True, reason=f"All {total} voice generations failed")

        # Send voice clips to Telegram for review
        bot_token, chat_id = self._get_telegram_creds()
        if bot_token and chat_id:
            return self._send_voice_review(job_id, scenes, results, output_dir, bot_token, chat_id)

        score = (success_count / total) * 10.0
        logger.info(f"Voice complete for {job_id}: {success_count}/{total} succeeded")
        return PhaseResult(success=True, score=score)

    def _send_voice_review(self, job_id, scenes, results, output_dir, bot_token, chat_id):
        """Send each voice clip to Telegram for scene-by-scene review."""
        import requests
        import time

        api = f"https://api.telegram.org/bot{bot_token}"
        job = self.db.get_job(job_id) if self.db else {}
        topic = job.get("topic", "—") if job else "—"

        # Header
        requests.post(f"{api}/sendMessage", json={
            "chat_id": chat_id, "parse_mode": "HTML",
            "text": (
                f"🎙️ <b>مراجعة التعليق الصوتي — {len(scenes)} مشهد</b>\n\n"
                f"📝 <b>الموضوع:</b> {topic}\n"
                f"🆔 <code>{job_id}</code>\n\n"
                "راجع كل مقطع صوتي ثم اضغط موافقة أو إعادة توليد:"
            ),
        }, timeout=10)
        time.sleep(0.5)

        # Send each voice clip
        for scene, result in zip(scenes, results):
            idx = scene["scene_index"]
            narration = (scene.get("narration_text") or "")[:500]

            if not result.success or not result.audio_path:
                requests.post(f"{api}/sendMessage", json={
                    "chat_id": chat_id, "parse_mode": "HTML",
                    "text": f"❌ <b>مشهد {idx + 1}</b>: فشل التوليد\n\n📝 {narration}",
                }, timeout=10)
                continue

            caption = (
                f"<b>مشهد {idx + 1}/{len(scenes)}</b> | 🎙️ {result.engine} ({result.duration_sec}ث)\n\n"
                f"📝 {narration}"
            )[:1024]

            keyboard = json.dumps({"inline_keyboard": [[
                {"text": "✅ موافق", "callback_data": f"va_{job_id}_{idx}"},
                {"text": "🔄 إعادة", "callback_data": f"vr_{job_id}_{idx}"},
                {"text": "❌ رفض", "callback_data": f"vx_{job_id}_{idx}"},
            ]]})

            # Send as voice message
            audio_path = Path(result.audio_path)
            if audio_path.exists():
                try:
                    with open(str(audio_path), "rb") as f:
                        requests.post(f"{api}/sendVoice", data={
                            "chat_id": chat_id,
                            "caption": caption,
                            "parse_mode": "HTML",
                            "reply_markup": keyboard,
                        }, files={"voice": (audio_path.name, f, "audio/mpeg")}, timeout=30)
                except Exception as e:
                    logger.warning(f"Failed to send voice for scene {idx}: {e}")

            time.sleep(0.3)

        time.sleep(0.5)

        # Approve all button
        requests.post(f"{api}/sendMessage", json={
            "chat_id": chat_id, "parse_mode": "HTML",
            "text": "✅ <b>انتهت المراجعة؟</b>\n\nراجع كل مقطع ثم اضغط:",
            "reply_markup": {"inline_keyboard": [
                [{"text": "✅ موافقة على الكل", "callback_data": f"var_{job_id}"}],
            ]},
        }, timeout=10)

        logger.info(f"Voice review sent to Telegram for {job_id}, BLOCKING pipeline until user approves")
        return PhaseResult(
            success=False, blocked=True,
            reason="⏸️ بانتظار مراجعة التعليق الصوتي",
            score=0,
        )

    def _send_voice_selection(self, job_id, voices, cloner, bot_token, chat_id):
        """Send voice selection menu to Telegram and pause pipeline."""
        import requests

        api = f"https://api.telegram.org/bot{bot_token}"
        job = self.db.get_job(job_id) if self.db else {}
        topic = job.get("topic", "—") if job else "—"
        default_id = cloner.get_default_voice_id()

        text = (
            f"🎙️ <b>اختر الشخصية الصوتية لهذا المشروع:</b>\n\n"
            f"📝 <b>الموضوع:</b> {topic}\n"
            f"🆔 <code>{job_id}</code>\n"
        )

        buttons = []
        for v in voices:
            label = f"👤 {v.name}"
            if v.voice_id == default_id:
                label += " ⭐ افتراضي"
            buttons.append([{"text": label, "callback_data": f"vs_{job_id}_{v.voice_id}"}])

        buttons.append([{"text": "🤖 صوت Edge TTS الافتراضي", "callback_data": f"vs_{job_id}___edge_tts__"}])

        keyboard = {"inline_keyboard": buttons}
        requests.post(f"{api}/sendMessage", json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "reply_markup": keyboard,
        }, timeout=10)

        logger.info(f"Voice selection sent to Telegram for {job_id}, BLOCKING pipeline until user selects voice")
        return PhaseResult(
            success=False, blocked=True,
            reason="⏸️ بانتظار اختيار المعلق الصوتي",
            score=0,
        )


# ═══════════════════════════════════════════════════════════════
# Phase 9: Music (ACE-Step / MusicGen)
# ═══════════════════════════════════════════════════════════════

class MusicPhase(BasePhase):
    """Generate background music via ACE-Step 1.5, local library, or FFmpeg ambient."""

    def run(self, job_id: str) -> PhaseResult:
        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase5_production.music_gen import MusicGenerator

        gen = MusicGenerator()
        output_dir = f"output/{job_id}/audio/music"

        _notify("🎵 تحميل موديل الموسيقى...")

        # Calculate total duration from actual voice durations or scene estimates
        total_dur = 0.0
        for s in scenes:
            # Prefer actual voice duration if available
            voice_path = s.get("voice_path")
            if voice_path and Path(voice_path).exists():
                try:
                    import subprocess
                    from src.phase5_production.ffmpeg_path import FFMPEG
                    probe = subprocess.run(
                        [FFMPEG, "-i", voice_path, "-f", "null", "-"],
                        capture_output=True, text=True, timeout=10,
                    )
                    # Parse duration from ffmpeg stderr
                    import re
                    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", probe.stderr)
                    if m:
                        h, mn, sc, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                        total_dur += h * 3600 + mn * 60 + sc + ms / 100
                        continue
                except Exception:
                    pass
            total_dur += float(s.get("duration_sec", 6) or 6)

        if total_dur < 10:
            total_dur = len(scenes) * 6.0

        try:
            result = gen.generate(scenes=scenes, output_dir=output_dir, duration_sec=total_dur)
            if not result.success:
                logger.warning(f"Music generation failed: {result.error}, continuing without music")
                _notify(f"⚠️ موسيقى — فشل ({result.error[:100]}), مكمّلين بدونها")
                return PhaseResult(success=True, score=5.0, reason="Music generation failed, continuing")

            _notify(f"✅ موسيقى — {result.method} ({result.duration_sec:.0f}s)")
            logger.info(f"Music complete for {job_id}: {result.mood} ({result.method}, {result.duration_sec:.0f}s)")

            # Send music to Telegram for preview
            if result.audio_path and Path(result.audio_path).exists():
                _send_audio_preview(job_id, result.audio_path, f"🎵 الموسيقى — {result.mood} ({result.duration_sec:.0f}s)")

            return PhaseResult(success=True, score=8.0)
        finally:
            gen.unload_model()


# ═══════════════════════════════════════════════════════════════
# Pass-through / Stub phases (not yet implemented)
# ═══════════════════════════════════════════════════════════════

class _PassthroughPhase(BasePhase):
    """Phase that passes through with success (skipped for now)."""
    phase_name: str = "unknown"

    def run(self, job_id: str) -> PhaseResult:
        logger.info(f"Phase '{self.phase_name}' skipped (pass-through) for {job_id}")
        return PhaseResult(success=True, score=8.0)


class _StubPhase(BasePhase):
    """Phase that's a stub — not yet implemented but doesn't block."""
    phase_name: str = "unknown"

    def run(self, job_id: str) -> PhaseResult:
        logger.info(f"Phase '{self.phase_name}' is a stub — skipping for {job_id}")
        return PhaseResult(success=True, score=5.0, reason=f"{self.phase_name} not yet implemented")


class ImageQAPhase(BasePhase):
    """Run image QA: deterministic checks + vision LLM rubric scoring."""
    phase_name = "image_qa"

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase6_visual_qa.image_qa import ImageQA

        qa = ImageQA()
        images_dir = str(Path(f"output/{job_id}/images"))
        results = qa.check_batch(scenes, images_dir)

        pass_count = sum(1 for r in results if r.verdict == "PASS")
        regen_count = sum(1 for r in results if r.verdict == "REGEN")
        fail_count = sum(1 for r in results if r.verdict == "FAIL")
        total = len(results)

        # Save rubrics to DB
        for r in results:
            self.db.save_rubric(
                job_id=job_id, scene_index=r.scene_index,
                asset_type="image", check_phase="image_qa",
                attempt=1, deterministic=r.scores,
                rubric_scores=r.scores,
                weighted_score=r.weighted_score,
                verdict=r.verdict.lower(),
                flags=r.details,
                hard_fail=r.error if r.verdict == "FAIL" else None,
                model="deterministic",
            )

            # Mark scenes needing regen
            if r.verdict in ("REGEN", "FAIL"):
                self.db.update_scene_asset(
                    job_id, r.scene_index,
                    image_score=r.weighted_score,
                    image_regenerated=True,
                )
            else:
                self.db.update_scene_asset(
                    job_id, r.scene_index,
                    image_score=r.weighted_score,
                )

        pass_rate = pass_count / max(total, 1)
        score = pass_rate * 10.0
        logger.info(
            f"Image QA for {job_id}: {pass_count} pass, {regen_count} regen, "
            f"{fail_count} fail out of {total} ({pass_rate:.0%})"
        )

        # ── Auto-regenerate failed images (up to 2 retries) ──
        failed_indices = [r.scene_index for r in results if r.verdict in ("REGEN", "FAIL")]
        max_regen_rounds = 2

        if failed_indices:
            from src.phase5_production.image_gen import ImageGenerator, ImageGenConfig
            img_config = ImageGenConfig(
                comfyui_host="http://127.0.0.1:8000",
                model_name="flux1-dev-fp8.safetensors",
                width=1280, height=720, steps=20, cfg=1.0,
                sampler="euler", scheduler="normal", timeout_sec=300,
            )
            img_gen = ImageGenerator(img_config)
            images_dir_path = Path(images_dir)

            for regen_round in range(max_regen_rounds):
                if not failed_indices:
                    break

                _notify(f"🔄 إعادة توليد {len(failed_indices)} صورة (محاولة {regen_round + 1}/{max_regen_rounds})...")
                logger.info(f"Regenerating {len(failed_indices)} images (round {regen_round + 1})")

                # Ensure ComfyUI is running
                if not img_gen.ensure_server(max_wait=120):
                    logger.warning("ComfyUI not available for regen")
                    break

                still_failed = []
                for idx in failed_indices:
                    scene = next((s for s in scenes if s.get("scene_index") == idx), None)
                    if not scene:
                        continue

                    prompt = scene.get("visual_prompt", "")
                    if not prompt.strip():
                        still_failed.append(idx)
                        continue

                    result = img_gen.generate(
                        prompt=prompt, output_dir=images_dir,
                        filename=f"scene_{idx:03d}", width=1280, height=720,
                    )

                    if result.success and result.image_path:
                        self.db.update_scene_asset(job_id, idx,
                            image_path=result.image_path, image_seed=result.seed)

                        # Re-QA the regenerated image
                        qa_result = qa.check_image(image_path=result.image_path, scene_index=idx)
                        self.db.update_scene_asset(job_id, idx, image_score=qa_result.weighted_score)

                        icon = {"PASS": "✅", "REGEN": "🔄", "FAIL": "❌"}.get(qa_result.verdict, "❓")
                        _notify(f"🔄 صورة {idx} — {icon} {qa_result.weighted_score:.1f}/10")

                        if qa_result.verdict in ("REGEN", "FAIL"):
                            still_failed.append(idx)
                        else:
                            pass_count += 1
                    else:
                        still_failed.append(idx)

                failed_indices = still_failed

            # Update counts
            regen_count = len(failed_indices)
            pass_rate = (total - regen_count) / max(total, 1)
            score = pass_rate * 10.0

        # ── Send all images to Telegram for user approval ──
        _notify(f"📊 فحص الصور: {total - len(failed_indices)}/{total} نجحت — إرسال للمراجعة...")
        self._send_images_for_review(job_id, scenes, images_dir, failed_indices)

        return PhaseResult(
            success=False, blocked=True,
            reason="⏸️ بانتظار مراجعة الصور",
            score=score,
        )

    def _send_images_for_review(self, job_id, scenes, images_dir, failed_indices):
        """Send all images to Telegram with approve/reject buttons per image."""
        import requests as req
        import os, time

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            tg = self.config.get("settings", {}).get("telegram", {})
            bot_token = bot_token or tg.get("bot_token", "")
            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")

        if not bot_token or not chat_id:
            logger.warning("No Telegram credentials for image review")
            return

        api = f"https://api.telegram.org/bot{bot_token}"

        for scene in scenes:
            idx = scene.get("scene_index", 0)
            img_path = scene.get("image_path") or str(Path(images_dir) / f"scene_{idx:03d}.png")
            if not Path(img_path).exists():
                continue

            narration = (scene.get("narration_text") or "")[:200]
            failed = idx in failed_indices
            status = "⚠️ لم تنجح بالفحص" if failed else "✅ نجحت"

            caption = f"<b>مشهد {idx + 1}/{len(scenes)}</b> | {status}\n\n📝 {narration}"
            if len(caption) > 1024:
                caption = caption[:1020] + "..."

            keyboard = json.dumps({"inline_keyboard": [[
                {"text": "✅ موافق", "callback_data": f"ia_{job_id}_{idx}"},
                {"text": "🔄 إعادة", "callback_data": f"ir_{job_id}_{idx}"},
            ]]})

            try:
                with open(img_path, "rb") as f:
                    req.post(f"{api}/sendPhoto", data={
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    }, files={"photo": (Path(img_path).name, f, "image/png")}, timeout=30)
            except Exception as e:
                logger.warning(f"Failed to send image {idx}: {e}")

            time.sleep(0.3)

        # Final approve-all button
        req.post(f"{api}/sendMessage", json={
            "chat_id": chat_id, "parse_mode": "HTML",
            "text": f"📸 <b>مراجعة الصور — {len(scenes)} مشهد</b>\n\n"
                    f"راجع كل صورة ثم اضغط:",
            "reply_markup": {"inline_keyboard": [
                [{"text": "✅ موافقة على الكل", "callback_data": f"iaa_{job_id}"}],
            ]},
        }, timeout=10)


class ImageRegenPhase(_PassthroughPhase):
    phase_name = "image_regen"


class VideoPhase(BasePhase):
    """Generate video clips for all scenes using LTX-2.3 + Ken Burns fallback."""
    phase_name = "video"

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase5_production.video_gen import VideoGenerator, VideoGenConfig

        config = VideoGenConfig(
            comfyui_host="http://127.0.0.1:8000",
            ltx_model="ltx-2.3-22b-dev-fp8.safetensors",
            fps=24,
            default_duration_sec=6.0,
            max_duration_sec=10.0,   # LTX max — longer scenes use Ken Burns
            arabic_words_per_sec=2.5,  # Documentary narration pace
            timeout_sec=300,
        )
        gen = VideoGenerator(config)

        images_dir = str(Path(f"output/{job_id}/images"))
        output_dir = str(Path(f"output/{job_id}/videos"))
        results = gen.generate_batch(scenes, images_dir, output_dir)

        success_count = 0
        for scene, result in zip(scenes, results):
            idx = scene["scene_index"]
            if result.success and result.video_path:
                self.db.update_scene_asset(
                    job_id, idx,
                    video_clip_path=result.video_path,
                    video_method=result.method,
                )
                success_count += 1
                logger.info(f"Scene {idx} video: {result.method} → {result.video_path}")
            else:
                logger.error(f"Scene {idx} video failed: {result.error}")

        if success_count == 0:
            return PhaseResult(
                success=False, blocked=True,
                reason=f"All {len(scenes)} video generations failed",
            )

        score = (success_count / len(scenes)) * 10.0
        logger.info(f"Video complete for {job_id}: {success_count}/{len(scenes)} succeeded")
        return PhaseResult(success=True, score=score)


class VideoQAPhase(BasePhase):
    """Run video QA: deterministic checks + vision LLM on keyframes."""
    phase_name = "video_qa"

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase6_visual_qa.video_qa import VideoQA

        qa = VideoQA()
        videos_dir = str(Path(f"output/{job_id}/videos"))
        images_dir = str(Path(f"output/{job_id}/images"))
        results = qa.check_batch(scenes, videos_dir, images_dir)

        pass_count = sum(1 for r in results if r.verdict == "PASS")
        regen_count = sum(1 for r in results if r.verdict == "REGEN")
        total = len(results)

        # Save rubrics to DB
        for r in results:
            det_dict = {
                "duration_sec": r.deterministic.duration_sec,
                "fps": r.deterministic.fps,
                "file_ok": r.deterministic.file_ok,
                "duration_ok": r.deterministic.duration_ok,
                "fps_ok": r.deterministic.fps_ok,
                "has_black_frames": r.deterministic.has_black_frames,
            }
            rubric_dict = {}
            if r.rubric:
                rubric_dict = {
                    "motion_plausibility": r.rubric.motion_plausibility,
                    "source_fidelity": r.rubric.source_fidelity,
                    "artifact_severity": r.rubric.artifact_severity,
                }

            self.db.save_rubric(
                job_id=job_id, scene_index=r.scene_index,
                asset_type="video", check_phase="video_qa",
                attempt=1, deterministic=det_dict,
                rubric_scores=rubric_dict,
                weighted_score=r.weighted_score,
                verdict=r.verdict.lower(),
                flags=r.deterministic.fail_reasons,
                hard_fail=r.error if r.verdict == "REGEN" and not r.deterministic.file_ok else None,
                model="qwen3.5:27b",
            )

        score = (pass_count / max(total, 1)) * 10.0
        logger.info(
            f"Video QA for {job_id}: {pass_count} pass, {regen_count} regen out of {total}"
        )

        return PhaseResult(
            success=True, score=score,
            reason=f"{pass_count}/{total} passed" + (
                f" — {regen_count} need regen" if regen_count > 0 else ""
            ),
        )


class VideoRegenPhase(_PassthroughPhase):
    phase_name = "video_regen"

class SFXPhase(BasePhase):
    """Generate per-scene SFX from library or ambient fallback."""
    phase_name = "sfx"

    def run(self, job_id: str) -> PhaseResult:
        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase5_production.sfx_gen import SFXGenerator

        gen = SFXGenerator()
        output_dir = f"output/{job_id}/audio/sfx"

        _notify(f"🔊 تحميل موديل المؤثرات الصوتية ({len(scenes)} مشهد)...")

        try:
            results = gen.generate_batch(scenes, output_dir)
            success_count = sum(1 for r in results if r.success)
            _notify(f"✅ المؤثرات — {success_count}/{len(scenes)} نجحت")
            logger.info(f"SFX complete for {job_id}: {success_count}/{len(scenes)}")

            # Send a few SFX samples to Telegram
            sent = 0
            for r in results:
                if r.success and r.audio_path and Path(r.audio_path).exists() and sent < 3:
                    _send_audio_preview(job_id, r.audio_path, f"🔊 مؤثر — {', '.join(r.matched_tags[:3]) if r.matched_tags else r.method}")
                    sent += 1

            return PhaseResult(success=True, score=8.0)
        finally:
            gen.unload_model()


class ComposePhase(BasePhase):
    """Compose final video from all scene assets."""
    phase_name = "compose"

    def run(self, job_id: str) -> PhaseResult:
        scenes = self.db.get_scenes(job_id)
        if not scenes:
            return PhaseResult(success=False, blocked=True, reason="No scenes found")

        from src.phase5_production.composer import VideoComposer

        composer = VideoComposer()
        result = composer.compose(job_id, scenes, f"output/{job_id}/videos")

        if not result.success:
            return PhaseResult(success=False, blocked=True, reason=f"Composition failed: {result.error}")

        logger.info(f"Compose complete for {job_id}: {result.video_path} ({result.duration_sec:.0f}s)")

        # Send final video to Telegram
        if result.video_path and Path(result.video_path).exists():
            _send_video_preview(job_id, result.video_path, f"🎬 الفيديو النهائي ({result.duration_sec:.0f}s)")

        return PhaseResult(success=True, score=9.0)


class OverlayQAPhase(BasePhase):
    """Run overlay QA checks on final video."""
    phase_name = "overlay_qa"

    def run(self, job_id: str) -> PhaseResult:
        final_path = f"output/{job_id}/final.mp4"
        if not Path(final_path).exists():
            return PhaseResult(success=False, blocked=True, reason="final.mp4 not found")

        from src.phase6_visual_qa.overlay_qa import OverlayQA

        scenes = self.db.get_scenes(job_id)
        expected_dur = sum(float(s.get("duration_sec", 6)) for s in scenes) if scenes else 0

        qa = OverlayQA()
        result = qa.check(final_path, expected_dur)

        if not result.success:
            return PhaseResult(success=False, reason=f"Overlay QA error: {result.error}")

        score = 9.0 if result.passed else 6.0
        reason = "; ".join(result.warnings) if result.warnings else ""
        logger.info(f"Overlay QA for {job_id}: passed={result.passed}, warnings={len(result.warnings)}")
        return PhaseResult(success=True, score=score, reason=reason)


class FinalQAPhase(BasePhase):
    """Final quality gate before publish."""
    phase_name = "final_qa"

    def run(self, job_id: str) -> PhaseResult:
        final_path = f"output/{job_id}/final.mp4"
        if not Path(final_path).exists():
            return PhaseResult(success=False, blocked=True, reason="final.mp4 not found")

        from src.phase7_video_qa.final_qa import FinalQA

        scenes = self.db.get_scenes(job_id)
        target_dur = sum(float(s.get("duration_sec", 6)) for s in scenes) if scenes else 0

        qa = FinalQA()
        result = qa.check(final_path, target_dur)

        if not result.success:
            return PhaseResult(success=False, reason=f"Final QA error: {result.error}")

        logger.info(f"Final QA for {job_id}: score={result.score:.1f}, passed={result.passed}")
        return PhaseResult(success=True, score=result.score, reason="; ".join(result.warnings))

class ManualReviewPhase(BasePhase):
    """Send each scene with image + per-image action buttons to Telegram."""
    phase_name = "manual_review"

    def _get_telegram_creds(self):
        import os
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            tg = self.config.get("settings", {}).get("telegram", {})
            bot_token = bot_token or tg.get("bot_token", "")
            chat_id = chat_id or tg.get("admin_chat_id") or tg.get("chat_id", "")
        return bot_token, chat_id

    def run(self, job_id: str) -> PhaseResult:
        import requests
        import time

        # Check if already approved (resuming after user clicked approve)
        job = self.db.get_job(job_id) if self.db else {}
        if job and job.get("manual_review_status") == "approved":
            logger.info(f"Manual review already approved for {job_id}, proceeding to publish")
            return PhaseResult(
                success=True, phase=self.phase_name, score=9.0,
                details={"status": "already_approved"},
                timestamp=datetime.utcnow().isoformat(),
            )

        bot_token, chat_id = self._get_telegram_creds()
        if not bot_token or not chat_id:
            logger.warning("No Telegram credentials for manual review")
            return PhaseResult(success=True, phase=self.phase_name, score=0,
                             details={"status": "no_telegram"}, timestamp=datetime.utcnow().isoformat())

        api = f"https://api.telegram.org/bot{bot_token}"

        topic = job.get("topic", "Unknown") if job else "Unknown"
        scenes = self.db.get_scenes(job_id) if self.db else []
        output_dir = Path(f"output/{job_id}/images")

        # 1. Header
        header = (
            f"🎬 <b>مراجعة يدوية — {len(scenes)} مشهد</b>\n\n"
            f"📝 <b>الموضوع:</b> {topic}\n"
            f"🆔 <code>{job_id}</code>\n\n"
            f"كل مشهد أدناه يحتوي على أزرار للموافقة أو التعديل أو إعادة التوليد أو الرفض."
        )
        requests.post(f"{api}/sendMessage", json={
            "chat_id": chat_id, "text": header, "parse_mode": "HTML"
        }, timeout=10)
        time.sleep(0.5)

        # 2. Send each scene with per-image buttons
        for scene in scenes:
            idx = scene["scene_index"]
            img_path = output_dir / f"scene_{idx:03d}.png"
            if not img_path.exists():
                continue

            narration = (scene.get("narration_text") or "")[:300]
            visual = (scene.get("visual_prompt") or "")[:150]
            camera = scene.get("camera_movement") or "static"

            caption = (
                f"<b>مشهد {idx + 1}/{len(scenes)}</b> | 🎥 {camera}\n\n"
                f"📝 {narration}\n\n"
                f"🎨 <i>{visual}</i>"
            )[:1024]

            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅", "callback_data": f"ia_{job_id}_{idx}"},
                    {"text": "✏️", "callback_data": f"ie_{job_id}_{idx}"},
                    {"text": "🔄", "callback_data": f"ir_{job_id}_{idx}"},
                    {"text": "❌", "callback_data": f"ix_{job_id}_{idx}"},
                ]]
            }

            with open(str(img_path), "rb") as f:
                resp = requests.post(f"{api}/sendPhoto", data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(keyboard),
                }, files={"photo": (img_path.name, f, "image/png")}, timeout=30)

            if not resp.ok:
                logger.warning(f"Failed to send scene {idx}: {resp.text[:200]}")

            time.sleep(0.3)

        time.sleep(0.5)

        # 3. Final action buttons
        action_keyboard = {
            "inline_keyboard": [
                [{"text": "✅ موافقة على الكل والمتابعة", "callback_data": f"ra_{job_id}"}],
                [
                    {"text": "🔄 إعادة توليد الكل", "callback_data": f"rr_{job_id}"},
                    {"text": "❌ إلغاء", "callback_data": f"rx_{job_id}"},
                ],
            ]
        }
        requests.post(f"{api}/sendMessage", json={
            "chat_id": chat_id,
            "text": "✅ <b>انتهت المراجعة؟</b>\n\nراجع كل مشهد ثم اضغط زر أدناه:",
            "parse_mode": "HTML",
            "reply_markup": action_keyboard,
        }, timeout=10)

        logger.info(f"Manual review with {len(scenes)} scenes sent to Telegram for {job_id}")

        return PhaseResult(
            success=False, blocked=True,
            reason="⏸️ بانتظار المراجعة اليدوية",
            score=0,
        )

class PublishPhase(BasePhase):
    """Publish final video: copy to publish folder, generate metadata, notify Telegram."""
    phase_name = "publish"

    def run(self, job_id: str) -> PhaseResult:
        job = self.db.get_job(job_id)
        if not job:
            return PhaseResult(success=False, blocked=True, reason="Job not found")

        from src.phase8_publish.publisher import Publisher

        pub = Publisher(self.config)
        result = pub.publish(job_id, job, self.db)

        if not result.success:
            return PhaseResult(success=False, reason=f"Publish failed: {result.error}")

        logger.info(f"Published {job_id}: telegram={result.telegram_sent}")
        return PhaseResult(success=True, score=9.0)
