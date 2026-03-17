"""
Phase 8 — Subtitle Generation: SRT from scene narration text + timing.

Reads scenes from DB, builds SRT entries using each scene's
start_time_sec / end_time_sec / narration_text, with proper
Arabic text segmentation for readable subtitle lines.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum characters per subtitle line (Arabic is ~40 chars for readability)
MAX_CHARS_PER_LINE = 42
MAX_LINES_PER_CUE = 2


class SubtitleGenerator:
    """
    Generates SRT subtitle files from scene narration data.
    Handles Arabic text segmentation and timing alignment.
    """

    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        self.output_base = Path(config["settings"].get("output_dir", "output"))

    def generate_srt(self, job_id: str) -> str:
        """
        Generate an SRT subtitle file for a job.

        Args:
            job_id: The job to generate subtitles for.

        Returns:
            Path to the generated .srt file.
        """
        scenes = self.db.get_scenes(job_id)
        if not scenes:
            logger.warning(f"No scenes found for {job_id}")
            return ""

        srt_dir = self.output_base / job_id / "subtitles"
        srt_dir.mkdir(parents=True, exist_ok=True)
        srt_path = srt_dir / f"{job_id}.srt"

        cue_index = 1
        entries = []

        for scene in scenes:
            narration = scene.get("narration_text", "").strip()
            if not narration:
                continue

            start_sec = scene.get("start_time_sec", 0) or 0
            end_sec = scene.get("end_time_sec") or (start_sec + (scene.get("duration_sec") or 10))

            # Segment long narration into subtitle cues
            segments = self._segment_text(narration)
            if not segments:
                continue

            # Distribute timing evenly across segments
            total_duration = end_sec - start_sec
            seg_duration = total_duration / len(segments)

            for i, segment in enumerate(segments):
                seg_start = start_sec + (i * seg_duration)
                seg_end = seg_start + seg_duration

                entries.append(
                    f"{cue_index}\n"
                    f"{self._format_timestamp(seg_start)} --> {self._format_timestamp(seg_end)}\n"
                    f"{segment}\n"
                )
                cue_index += 1

        srt_content = "\n".join(entries)
        srt_path.write_text(srt_content, encoding="utf-8")

        # Save to DB
        word_count = sum(len(s.get("narration_text", "").split()) for s in scenes)
        self.db.conn.execute(
            "INSERT INTO subtitles (job_id, language, srt_path, word_count) VALUES (?, ?, ?, ?)",
            (job_id, "ar", str(srt_path), word_count),
        )
        self.db.conn.commit()

        logger.info(f"SRT generated: {srt_path} ({cue_index - 1} cues)")
        return str(srt_path)

    def _segment_text(self, text: str) -> list[str]:
        """
        Split narration text into subtitle-sized segments.
        Prefers splitting at sentence boundaries (. ، ؟ !),
        then at commas, then by word count.
        """
        # Split at Arabic/standard sentence boundaries
        sentences = re.split(r"(?<=[.؟!،\n])\s*", text)
        segments = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = f"{current} {sentence}".strip() if current else sentence

            if len(candidate) <= MAX_CHARS_PER_LINE * MAX_LINES_PER_CUE:
                current = candidate
            else:
                if current:
                    segments.append(self._wrap_lines(current))
                # If single sentence is too long, force-wrap it
                if len(sentence) > MAX_CHARS_PER_LINE * MAX_LINES_PER_CUE:
                    segments.extend(self._force_split(sentence))
                    current = ""
                else:
                    current = sentence

        if current:
            segments.append(self._wrap_lines(current))

        return segments

    def _wrap_lines(self, text: str) -> str:
        """Wrap text into max 2 lines for subtitle display."""
        if len(text) <= MAX_CHARS_PER_LINE:
            return text

        words = text.split()
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        return f"{line1}\n{line2}"

    def _force_split(self, text: str) -> list[str]:
        """Force-split very long text into subtitle-sized chunks."""
        words = text.split()
        chunks = []
        current_words = []
        current_len = 0

        for word in words:
            if current_len + len(word) + 1 > MAX_CHARS_PER_LINE * MAX_LINES_PER_CUE:
                if current_words:
                    chunks.append(self._wrap_lines(" ".join(current_words)))
                current_words = [word]
                current_len = len(word)
            else:
                current_words.append(word)
                current_len += len(word) + 1

        if current_words:
            chunks.append(self._wrap_lines(" ".join(current_words)))
        return chunks

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds to SRT timestamp: HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
