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

    async def on_segment_arrived(self, segment: SegmentInfo) -> None:
        """Called whenever a new .ts segment is flushed to disk."""
        try:
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
                if actual_slice_dur > target_duration + 1.5:
                    trim_offset = max(0.0, actual_slice_dur - target_duration)
                    trimmed_slice_path = self.buffer.buffer_dir / f"slice_trim_{slice_id}.mp4"
                    trim_cmd = [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        str(round(trim_offset, 3)),
                        "-i",
                        str(temp_slice_path),
                        "-t",
                        str(round(target_duration, 3)),
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

                        # Re-align transcript word timestamps to trimmed start
                        adjusted_words = []
                        for w in transcript_data.get("words", []):
                            w_start = w.get("start", 0.0)
                            w_end = w.get("end", 0.0)
                            if w_end > trim_offset and w_start < actual_slice_dur:
                                adjusted_words.append({
                                    **w,
                                    "start": max(0.0, round(w_start - trim_offset, 3)),
                                    "end": max(0.0, round(w_end - trim_offset, 3)),
                                })
                        transcript_data["words"] = adjusted_words
                        if adjusted_words:
                            transcript_data["text"] = " ".join(w.get("word", "") for w in adjusted_words)
                            transcript_text = transcript_data["text"]

                final_start_seconds = max(0.0, current_end - target_duration)
                final_end_seconds = current_end

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
