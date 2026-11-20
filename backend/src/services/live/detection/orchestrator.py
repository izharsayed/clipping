"""Orchestrator for real-time moment detection and automated clipping."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from .audio_energy import AudioEnergyDetector, AudioEnergyResult
from .transcription import RollingTranscriber
from .moment_classifier import MomentClassifier, MomentClassification
from ..capture.rolling_buffer import RollingBuffer, SegmentInfo
from ....database import AsyncSessionLocal
from ....models import MonitoredChannel, LiveStreamSession, LiveClipMoment
from ....media.ffmpeg import ffprobe_duration
from ....utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)

DEFAULT_MOMENT_COOLDOWN_SECONDS = 45.0


def find_optimal_speech_cut_points(
    words: list[dict],
    target_start: float,
    target_end: float,
    total_duration: float,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> tuple[float, float]:
    """
    Snaps raw cut points to natural conversational boundaries (pauses or sentence starts/ends)
    using word-level timestamps, avoiding abrupt mid-word cutoffs.
    """
    if not words:
        return max(0.0, target_start), min(total_duration, target_end)

    best_start = target_start
    best_start_score = -1.0

    for i, w in enumerate(words):
        w_start = float(w.get("start", 0.0))
        dist = abs(w_start - target_start)
        if dist > 3.5:
            continue

        score = 10.0 - dist
        if i > 0:
            prev_end = float(words[i - 1].get("end", 0.0))
            pause = w_start - prev_end
            if pause >= 0.35:
                score += 5.0
            elif pause >= 0.15:
                score += 2.0
        else:
            score += 4.0

        word_text = str(w.get("word", "")).strip()
        if word_text and word_text[0].isupper():
            score += 2.0

        if score > best_start_score:
            best_start_score = score
            best_start = w_start

    best_end = target_end
    best_end_score = -1.0

    for i, w in enumerate(words):
        w_end = float(w.get("end", 0.0))
        dist = abs(w_end - target_end)
        if dist > 3.0:
            continue

        score = 10.0 - dist
        word_text = str(w.get("word", "")).strip()
        if word_text.endswith((".", "!", "?")):
            score += 5.0

        if i < len(words) - 1:
            next_start = float(words[i + 1].get("start", 0.0))
            if (next_start - w_end) >= 0.3:
                score += 3.0

        if score > best_end_score:
            best_end_score = score
            best_end = w_end

    actual_dur = best_end - best_start
    if actual_dur < min_duration:
        best_start = max(0.0, best_end - min_duration)
    elif actual_dur > max_duration:
        best_start = max(0.0, best_end - max_duration)

    return max(0.0, round(best_start, 3)), min(total_duration, round(best_end, 3))


class LiveMomentOrchestrator:
    """Listens to recorded segments, analyzes excitement, and coordinates clipping."""

    def __init__(
        self,
        channel_id: str,
        session_id: str,
        buffer: RollingBuffer,
        cooldown_seconds: float = DEFAULT_MOMENT_COOLDOWN_SECONDS,
    ):
        self.channel_id = channel_id
        self.session_id = session_id
        self.buffer = buffer
        self.cooldown_seconds = cooldown_seconds

        self.energy_detector = AudioEnergyDetector()
        self.transcriber = RollingTranscriber(whisper_model="base")
        self.classifier = MomentClassifier()

        self._last_clip_time: float = 0.0
        self._processing_moment: bool = False
        self._last_settings_refresh: float = 0.0

    async def _sync_channel_settings(self) -> None:
        """Fetch channel's configured virality threshold and radar mode to tune detector sensitivity."""
        now = time.time()
        if (now - self._last_settings_refresh) < 30.0:
            return
        self._last_settings_refresh = now

        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                ch_stmt = select(MonitoredChannel).where(MonitoredChannel.id == self.channel_id)
                channel = (await db.execute(ch_stmt)).scalar_one_or_none()
                if not channel:
                    return

                threshold = 80
                mode = "Balanced Hype"
                for cat in (channel.preferred_categories or []):
                    if cat.startswith("threshold:"):
                        try:
                            threshold = int(cat.split(":", 1)[1])
                        except ValueError:
                            pass
                    elif cat.startswith("radar_mode:"):
                        mode = cat.split(":", 1)[1]

                self.energy_detector.set_sensitivity(threshold, mode)
        except Exception as e:
            logger.debug("Could not refresh channel settings for %s: %s", self.channel_id, e)

    async def on_segment_arrived(self, segment: SegmentInfo) -> None:
        """Called whenever a new .ts segment is flushed to disk."""
        try:
            await self._sync_channel_settings()
            energy_res: AudioEnergyResult = await self.energy_detector.analyze_segment(segment.file_path)

            now = time.time()
            if not energy_res.is_spike:
                return

            if (now - self._last_clip_time) < self.cooldown_seconds:
                logger.debug(
                    "Spike detected (%.1fx) for %s but within cooldown (%.1fs remaining)",
                    energy_res.spike_ratio,
                    self.channel_id,
                    self.cooldown_seconds - (now - self._last_clip_time),
                )
                return

            if self._processing_moment:
                return

            logger.info(
                "🔥 Excitement spike detected (%.1fx baseline) on channel %s at stream time %.1fs!",
                energy_res.spike_ratio,
                self.channel_id,
                segment.start_time,
            )

            # Process candidate in background task to avoid blocking the segment watcher
            asyncio.create_task(self._evaluate_and_clip(segment, energy_res))

        except Exception as e:
            logger.warning("Error analyzing segment %s: %s", segment.file_path.name, e)

    async def _evaluate_and_clip(self, segment: SegmentInfo, energy: AudioEnergyResult) -> None:
        """Extract candidate window, transcribe, classify with AI, and render clip."""
        self._processing_moment = True
        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                ch_stmt = select(MonitoredChannel).where(MonitoredChannel.id == self.channel_id)
                channel = (await db.execute(ch_stmt)).scalar_one_or_none()
                sess_stmt = select(LiveStreamSession).where(LiveStreamSession.id == self.session_id)
                session = (await db.execute(sess_stmt)).scalar_one_or_none()

                if not channel or not session:
                    return

                # Check max clips per stream cap
                if session.clips_count >= channel.max_clips_per_stream:
                    logger.info("Session %s reached max clips cap (%d)", session.id, channel.max_clips_per_stream)
                    return

                # 1. Determine candidate window from channel configuration
                min_duration = float(channel.min_clip_duration or 20)
                max_duration = float(channel.max_clip_duration or 60)
                if min_duration > max_duration:
                    min_duration, max_duration = max_duration, min_duration

                # Segment ends at current stream time
                current_end = segment.start_time + segment.duration
                # Extract candidate context up to max_clip_duration (default 60s) for AI transcription
                candidate_context_sec = min(max_duration, 60.0)
                candidate_start = max(0.0, current_end - candidate_context_sec)

                slice_id = uuid4().hex[:8]
                temp_slice_path = self.buffer.buffer_dir / f"slice_{slice_id}.mp4"

                # Extract raw candidate window from rolling buffer (bounded to existing history)
                await self.buffer.extract_window(
                    start_seconds=candidate_start,
                    end_seconds=current_end,
                    output_path=temp_slice_path,
                    pre_roll_seconds=0.0,
                    post_roll_seconds=0.0,
                )

                if not temp_slice_path.exists():
                    logger.warning("Slice file does not exist: %s", temp_slice_path)
                    return

                # 2. Transcribe candidate window
                transcript_data = await self.transcriber.transcribe_media(temp_slice_path)
                transcript_text = transcript_data.get("text", "")

                # 3. Classify with AI agent
                classification: MomentClassification = await self.classifier.classify_moment(
                    transcript=transcript_text,
                    streamer_name=channel.display_name,
                    game_or_category=session.game_name,
                    audio_spike_ratio=energy.spike_ratio,
                    radar_mode=self.energy_detector.current_mode,
                )

                logger.info(
                    "AI evaluation for %s: clip_worthy=%s, category=%s, score=%.2f, suggested_duration=%ss, title='%s'",
                    channel.display_name,
                    classification.is_clip_worthy,
                    classification.category,
                    classification.confidence_score,
                    classification.suggested_duration_seconds,
                    classification.title,
                )

                if not classification.is_clip_worthy:
                    temp_slice_path.unlink(missing_ok=True)
                    return

                # 4. Determine final target clip duration dynamically based on AI recommendation and channel boundaries
                suggested_sec = getattr(classification, "suggested_duration_seconds", None)
                if suggested_sec is None or suggested_sec <= 0:
                    target_duration = min(max_duration, max(min_duration, 40.0))
                else:
                    target_duration = min(max_duration, max(min_duration, float(suggested_sec)))

                # Check actual extracted slice duration
                actual_slice_dur = await run_in_thread(ffprobe_duration, temp_slice_path)
                words = transcript_data.get("words", [])

                target_start = max(0.0, actual_slice_dur - target_duration)
                target_end = actual_slice_dur

                optimal_start, optimal_end = find_optimal_speech_cut_points(
                    words=words,
                    target_start=target_start,
                    target_end=target_end,
                    total_duration=actual_slice_dur,
                    min_duration=min_duration,
                    max_duration=max_duration,
                )

                optimal_dur = optimal_end - optimal_start
                if optimal_dur > 0 and (optimal_start > 0.5 or (actual_slice_dur - optimal_end) > 0.5):
                    trimmed_slice_path = self.buffer.buffer_dir / f"slice_trim_{slice_id}.mp4"
                    trim_cmd = [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        str(round(optimal_start, 3)),
                        "-i",
                        str(temp_slice_path),
                        "-t",
                        str(round(optimal_dur, 3)),
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(trimmed_slice_path),
                    ]
                    proc = await asyncio.create_subprocess_exec(
                        *trim_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                    if proc.returncode == 0 and trimmed_slice_path.exists():
                        temp_slice_path.unlink(missing_ok=True)
                        temp_slice_path = trimmed_slice_path

                        # Re-align transcript word timestamps to natural speech boundary
                        adjusted_words = []
                        for w in words:
                            w_start = float(w.get("start", 0.0))
                            w_end = float(w.get("end", 0.0))
                            if w_end > optimal_start and w_start < optimal_end:
                                adjusted_words.append({
                                    **w,
                                    "start": max(0.0, round(w_start - optimal_start, 3)),
                                    "end": max(0.0, round(w_end - optimal_start, 3)),
                                })
                        transcript_data["words"] = adjusted_words
                        if adjusted_words:
                            transcript_data["text"] = " ".join(w.get("word", "") for w in adjusted_words)
                            transcript_text = transcript_data["text"]

                final_start_seconds = max(0.0, candidate_start + optimal_start)
                final_end_seconds = min(current_end, candidate_start + optimal_end)

                # 5. Save LiveClipMoment record
                moment = LiveClipMoment(
                    session_id=session.id,
                    start_seconds=round(final_start_seconds, 2),
                    end_seconds=round(final_end_seconds, 2),
                    category=classification.category,
                    confidence_score=round(classification.confidence_score, 2),
                    audio_energy_score=round(energy.spike_ratio, 2),
                    description=classification.description,
                    transcript=transcript_text,
                    reason=classification.reason,
                    status="pending",
                )
                db.add(moment)
                await db.commit()
                await db.refresh(moment)

                # 5. Trigger SupoClip rendering pipeline
                from ..pipeline_bridge import LivePipelineBridge
                bridge = LivePipelineBridge(db)
                clip_id = await bridge.render_moment_to_clip(
                    moment=moment,
                    channel=channel,
                    session=session,
                    raw_slice_path=temp_slice_path,
                    classification=classification,
                    transcript_data=transcript_data,
                )

                if clip_id:
                    self._last_clip_time = time.time()

        except Exception as exc:
            logger.exception("Failed during live moment evaluation: %s", exc)
        finally:
            self._processing_moment = False
