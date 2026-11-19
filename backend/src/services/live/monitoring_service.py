"""Live stream monitoring service: detects when streamers go live or offline."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import MonitoredChannel, LiveStreamSession
from .models import LiveStatusResult
from .providers import get_stream_provider

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 45


class LiveMonitoringService:
    """Service that scans monitored channels and reconciles active live stream sessions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def poll_active_channels(
        self,
        force: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Scan active monitored channels whose last check is older than the interval."""
        cutoff = datetime.utcnow() - timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS)
        stmt = (
            select(MonitoredChannel)
            .where(MonitoredChannel.is_active == True)
        )
        if not force:
            stmt = stmt.where(
                (MonitoredChannel.last_checked_at == None)
                | (MonitoredChannel.last_checked_at <= cutoff)
            )

        stmt = stmt.order_by(MonitoredChannel.last_checked_at.asc().nullsfirst()).limit(limit)
        channels = (await self.db.execute(stmt)).scalars().all()

        if not channels:
            return []

        logger.info("Polling %d monitored channels for live status", len(channels))
        results = []

        for ch in channels:
            try:
                res = await self.check_and_update_channel(ch)
                results.append(res)
            except Exception as exc:
                logger.exception("Error checking channel %s (%s): %s", ch.channel_identifier, ch.platform, exc)
                ch.status = "error"
                ch.last_error = str(exc)
                ch.last_checked_at = datetime.utcnow()
                await self.db.commit()
                results.append({
                    "channel_id": ch.id,
                    "platform": ch.platform,
                    "channel_identifier": ch.channel_identifier,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    async def check_and_update_channel(self, channel: MonitoredChannel) -> Dict[str, Any]:
        """Check a single channel and reconcile live stream session status."""
        provider = get_stream_provider(channel.platform)
        live_result = await provider.check_channel_live(channel.channel_identifier)

        now = datetime.utcnow()
        channel.last_checked_at = now
        previous_status = channel.status

        if live_result.error and not live_result.is_live:
            channel.last_error = live_result.error
        else:
            channel.last_error = None

        if live_result.avatar_url:
            channel.avatar_url = live_result.avatar_url
        if live_result.display_name:
            channel.display_name = live_result.display_name

        action_taken = "none"

        if live_result.is_live:
            channel.status = "live"
            channel.last_live_at = now

            # Ensure active session exists
            active_session_stmt = select(LiveStreamSession).where(
                LiveStreamSession.channel_id == channel.id,
                LiveStreamSession.status == "active",
            )
            active_session = (await self.db.execute(active_session_stmt)).scalar_one_or_none()

            if not active_session:
                # Channel just transitioned to LIVE
                new_session = LiveStreamSession(
                    channel_id=channel.id,
                    stream_id=live_result.stream_id,
                    title=live_result.title,
                    game_name=live_result.game_name,
                    status="active",
                    started_at=live_result.started_at or now,
                    stream_url=live_result.stream_url,
                    session_metadata=live_result.raw_metadata,
                )
                self.db.add(new_session)
                action_taken = "session_started"
                logger.info(
                    "Streamer went LIVE: %s (%s) - Session %s",
                    channel.display_name,
                    channel.platform,
                    live_result.title,
                )
            else:
                # Update session metadata if changed
                if live_result.title and active_session.title != live_result.title:
                    active_session.title = live_result.title
                if live_result.game_name and active_session.game_name != live_result.game_name:
                    active_session.game_name = live_result.game_name
                action_taken = "session_active"
        else:
            # Channel is offline
            channel.status = "offline"

            # Close any open active session
            active_session_stmt = select(LiveStreamSession).where(
                LiveStreamSession.channel_id == channel.id,
                LiveStreamSession.status == "active",
            )
            active_session = (await self.db.execute(active_session_stmt)).scalar_one_or_none()
            if active_session:
                active_session.status = "ended"
                active_session.ended_at = now
                action_taken = "session_ended"
                logger.info(
                    "Streamer went OFFLINE: %s (%s) - Session ended",
                    channel.display_name,
                    channel.platform,
                )

        await self.db.commit()
        await self.db.refresh(channel)

        if action_taken == "session_started" and channel.is_active:
            try:
                from .capture.capture_manager import LiveCaptureManager
                asyncio.create_task(
                    LiveCaptureManager.get_instance().start_capture(
                        channel_id=channel.id,
                        session_id=new_session.id,
                        stream_url=live_result.stream_url or channel.channel_identifier,
                        segment_duration=5.0,
                        max_buffer_duration=float(channel.max_clip_duration + 30),
                    )
                )
            except Exception as e:
                logger.warning("Could not launch capture for channel %s: %s", channel.id, e)

        elif action_taken == "session_ended":
            try:
                from .capture.capture_manager import LiveCaptureManager
                await LiveCaptureManager.get_instance().stop_capture(channel.id)
            except Exception as e:
                logger.warning("Could not stop capture for channel %s: %s", channel.id, e)

        return {
            "channel_id": channel.id,
            "platform": channel.platform,
            "channel_identifier": channel.channel_identifier,
            "status": channel.status,
            "is_live": live_result.is_live,
            "title": live_result.title,
            "action": action_taken,
        }
