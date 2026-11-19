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

                # Desired clip duration: default 30-40s centered around the spike
                clip_duration = float(channel.min_clip_duration or 30)
                start_seconds = max(0.0, segment.start_time - (clip_duration * 0.65))
                end_seconds = segment.start_time + segment.duration + (clip_duration * 0.35)

                slice_id = uuid4().hex[:8]
                temp_slice_path = self.buffer.buffer_dir / f"slice_{slice_id}.mp4"

                # 1. Extract raw window from rolling buffer
                await self.buffer.extract_window(
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    output_path=temp_slice_path,
                    pre_roll_seconds=2.0,
                    post_roll_seconds=3.0,
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
                    "AI evaluation for %s: clip_worthy=%s, category=%s, score=%.2f, title='%s'",
                    channel.display_name,
                    classification.is_clip_worthy,
                    classification.category,
                    classification.confidence_score,
                    classification.title,
                )

                if not classification.is_clip_worthy:
                    temp_slice_path.unlink(missing_ok=True)
                    return

                # 4. Save LiveClipMoment record
                moment = LiveClipMoment(
                    session_id=session.id,
                    start_seconds=round(start_seconds, 2),
                    end_seconds=round(end_seconds, 2),
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
