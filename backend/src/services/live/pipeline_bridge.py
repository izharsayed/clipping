"""Bridge connecting detected live stream moments to SupoClip's rendering & Post Text pipeline."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment, Task, Source
from ...repositories.clip_repository import ClipRepository
from ..post_text_service import generate_post_text_with_ai, tidy_post_text
from ...media.ffmpeg import ffprobe_duration
from ...media.transcription import cache_transcript_data
from ...video_utils import create_optimized_clip
from ...config import get_config
from .detection.moment_classifier import MomentClassification
from ...utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)


class LivePipelineBridge:
    """Takes a raw live stream slice and renders it into a complete short-form vertical clip."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.config = get_config()

    async def get_or_create_session_task(
        self, channel: MonitoredChannel, session: LiveStreamSession
    ) -> Task:
        """Find or create a parent Task representing this live broadcast."""
        # Check if session metadata already has a task_id
        task_id = session.session_metadata.get("task_id")
        if task_id:
            stmt = select(Task).where(Task.id == task_id)
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing

        # Create source
        stream_url = session.stream_url or f"https://twitch.tv/{channel.channel_identifier}"
        source = Source(
            type="video_url",
            title=f"Live: {channel.display_name} - {session.title or 'Broadcast'}",
            url=stream_url,
        )
        self.db.add(source)
        await self.db.flush()

        task = Task(
            user_id=channel.user_id,
            source_id=source.id,
            status="completed",
            progress=100,
            workflow="highlights",
            caption_template="default",
            font_family="TikTokSans-Regular",
            font_size=24,
            font_color="#FFFFFF",
            source_metadata={
                "live": True,
                "channel_id": channel.id,
                "session_id": session.id,
                "platform": channel.platform,
            },
        )
        self.db.add(task)
        await self.db.flush()

        # Update session metadata
        meta = dict(session.session_metadata or {})
        meta["task_id"] = task.id
        session.session_metadata = meta
        await self.db.commit()

        return task

    async def render_moment_to_clip(
        self,
        moment: LiveClipMoment,
        channel: MonitoredChannel,
        session: LiveStreamSession,
        raw_slice_path: Path,
        classification: MomentClassification,
        transcript_data: Dict[str, Any],
    ) -> Optional[str]:
        """
        Executes the full rendering:
        1. Prepares word-level timings
        2. Generates PeakCut Post Text (Hook, CTR Title, Description, Hashtags)
        3. Renders 9:16 vertical crop with active speaker framing & animated subtitles
        4. Saves to PostgreSQL generated_clips
        5. Updates LiveClipMoment
        """
        task = await self.get_or_create_session_task(channel, session)
        clips_output_dir = Path(self.config.temp_dir) / "clips"
        clips_output_dir.mkdir(parents=True, exist_ok=True)

        clip_id = str(uuid4())
        final_clip_filename = f"live_{clip_id[:12]}.mp4"
        final_clip_path = clips_output_dir / final_clip_filename

        raw_duration = await run_in_thread(ffprobe_duration, raw_slice_path)
        if raw_duration <= 1.0:
            logger.warning("Raw slice duration too short: %.2f", raw_duration)
            return None

        # 1. Cache word timings sidecar so captions engine can read it
        if transcript_data.get("words"):
            await run_in_thread(cache_transcript_data, raw_slice_path, transcript_data)

        # 2. Generate PeakCut Post Text with AI
        transcript_text = transcript_data.get("text") or classification.description
        post_text_dict = await generate_post_text_with_ai(
            clip_text=transcript_text,
            clip_title=classification.title,
            source_title=session.title or channel.display_name,
        )

        hook_text = post_text_dict.get("hook") or "CHECK THIS OUT"

        # 3. Render 9:16 vertical video using existing SupoClip video_utils
        logger.info(
            "Rendering live moment clip: %s (duration: %.1fs, hook: %s)",
            final_clip_filename,
            raw_duration,
            hook_text,
        )

        def do_render():
            return create_optimized_clip(
                video_path=raw_slice_path,
                start_time=0.0,
                end_time=raw_duration,
                output_path=final_clip_path,
                add_subtitles=True,
                output_format="vertical",
                hook_title=hook_text,
                extend_to_sentence=True,
            )

        rendered_success = await run_in_thread(do_render)
        if not rendered_success or not final_clip_path.exists():
            logger.error("Failed to render vertical clip for moment %s", moment.id)
            moment.status = "failed"
            await self.db.commit()
            return None

        final_duration = await run_in_thread(ffprobe_duration, final_clip_path)

        # 4. Insert into generated_clips table
        clip_order = session.clips_count + 1
        virality_score = int(classification.confidence_score * 100)

        workflow_meta = {
            "post_text": post_text_dict,
            "category": classification.category,
            "live_session_id": session.id,
            "channel_id": channel.id,
            "platform": channel.platform,
        }

        created_clip_id = await ClipRepository.create_clip(
            db=self.db,
            task_id=task.id,
            filename=final_clip_filename,
            file_path=str(final_clip_path),
            start_time="00:00",
            end_time=f"00:{int(final_duration):02d}",
            duration=round(final_duration, 2),
            text=transcript_text,
            relevance_score=round(classification.confidence_score, 2),
            reasoning=classification.reason,
            clip_order=clip_order,
            virality_score=virality_score,
            hook_score=min(25, int(virality_score * 0.25)),
            engagement_score=min(25, int(virality_score * 0.25)),
            value_score=min(25, int(virality_score * 0.25)),
            shareability_score=min(25, int(virality_score * 0.25)),
            hook_type=classification.category,
            hook_title=hook_text,
            clip_id=clip_id,
            workflow_role="highlight",
            workflow_meta=workflow_meta,
        )

        # 5. Update LiveClipMoment
        moment.task_id = task.id
        moment.clip_id = created_clip_id
        moment.status = "pending"  # Ready for user approval
        session.clips_count += 1

        await self.db.commit()
        logger.info(
            "Live clip created successfully: %s (id=%s) for streamer %s",
            final_clip_filename,
            created_clip_id,
            channel.display_name,
        )
        return created_clip_id
