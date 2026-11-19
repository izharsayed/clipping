"""Channel management service for monitored streamers."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment, GeneratedClip
from .models import ChannelCreateRequest, ChannelUpdateRequest, LiveOverviewStats
from .providers import get_stream_provider

logger = logging.getLogger(__name__)


class LiveChannelService:
    """Service for managing monitored streamer channels."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_channel(
        self, user_id: str, request: ChannelCreateRequest
    ) -> MonitoredChannel:
        provider = get_stream_provider(request.platform)
        channel_identifier = provider.parse_channel_identifier(request.channel)

        # Check for existing channel for this user
        existing_stmt = select(MonitoredChannel).where(
            MonitoredChannel.user_id == user_id,
            MonitoredChannel.platform == request.platform.lower(),
            MonitoredChannel.channel_identifier == channel_identifier,
        )
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            # Re-activate if was deactivated
            if not existing.is_active:
                existing.is_active = True
                await self.db.commit()
                await self.db.refresh(existing)
            return existing

        # Preflight live check to get display name and avatar
        display_name = request.display_name or channel_identifier
        avatar_url = None
        status = "offline"
        last_live_at = None

        try:
            live_result = await provider.check_channel_live(channel_identifier)
            if live_result.display_name:
                display_name = live_result.display_name
            if live_result.avatar_url:
                avatar_url = live_result.avatar_url
            if live_result.is_live:
                status = "live"
                last_live_at = datetime.utcnow()
        except Exception as exc:
            logger.warning("Initial channel check failed: %s", exc)

        channel = MonitoredChannel(
            user_id=user_id,
            platform=request.platform.lower(),
            channel_identifier=channel_identifier,
            display_name=display_name,
            avatar_url=avatar_url,
            is_active=True,
            status=status,
            last_checked_at=datetime.utcnow(),
            last_live_at=last_live_at,
            max_clips_per_stream=request.max_clips_per_stream,
            min_clip_duration=request.min_clip_duration,
            max_clip_duration=request.max_clip_duration,
            preferred_categories=request.preferred_categories,
            auto_publish=request.auto_publish,
        )

        self.db.add(channel)
        await self.db.commit()
        await self.db.refresh(channel)

        # If live at creation, create an active session
        if status == "live" and 'live_result' in locals() and live_result.is_live:
            session = LiveStreamSession(
                channel_id=channel.id,
                stream_id=live_result.stream_id,
                title=live_result.title,
                game_name=live_result.game_name,
                status="active",
                stream_url=live_result.stream_url,
                session_metadata=live_result.raw_metadata,
            )
            self.db.add(session)
            await self.db.commit()

        return channel

    async def list_channels(self, user_id: str) -> List[Dict[str, Any]]:
        stmt = (
            select(MonitoredChannel)
            .where(MonitoredChannel.user_id == user_id)
            .order_by(MonitoredChannel.created_at.desc())
        )
        channels = (await self.db.execute(stmt)).scalars().all()

        results = []
        for ch in channels:
            # Count total clips generated for this channel
            clips_stmt = (
                select(func.count(LiveClipMoment.id))
                .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
                .where(LiveStreamSession.channel_id == ch.id)
            )
            clips_count = (await self.db.execute(clips_stmt)).scalar() or 0

            # Get latest active session if any
            session_stmt = (
                select(LiveStreamSession)
                .where(LiveStreamSession.channel_id == ch.id, LiveStreamSession.status == "active")
                .order_by(LiveStreamSession.started_at.desc())
                .limit(1)
            )
            active_session = (await self.db.execute(session_stmt)).scalar_one_or_none()

            results.append({
                "id": ch.id,
                "platform": ch.platform,
                "channel_identifier": ch.channel_identifier,
                "display_name": ch.display_name,
                "avatar_url": ch.avatar_url,
                "is_active": ch.is_active,
                "status": ch.status,
                "last_checked_at": ch.last_checked_at.isoformat() if ch.last_checked_at else None,
                "last_live_at": ch.last_live_at.isoformat() if ch.last_live_at else None,
                "last_error": ch.last_error,
                "max_clips_per_stream": ch.max_clips_per_stream,
                "min_clip_duration": ch.min_clip_duration,
                "max_clip_duration": ch.max_clip_duration,
                "preferred_categories": ch.preferred_categories,
                "auto_publish": ch.auto_publish,
                "clips_count": clips_count,
                "active_session": {
                    "id": active_session.id,
                    "title": active_session.title,
                    "game_name": active_session.game_name,
                    "started_at": active_session.started_at.isoformat(),
                    "stream_url": active_session.stream_url,
                } if active_session else None,
            })
        return results

    async def get_channel(self, channel_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(MonitoredChannel).where(
            MonitoredChannel.id == channel_id, MonitoredChannel.user_id == user_id
        )
        ch = (await self.db.execute(stmt)).scalar_one_or_none()
        if not ch:
            return None

        # Fetch recent sessions
        sessions_stmt = (
            select(LiveStreamSession)
            .where(LiveStreamSession.channel_id == ch.id)
            .order_by(LiveStreamSession.started_at.desc())
            .limit(10)
        )
        sessions = (await self.db.execute(sessions_stmt)).scalars().all()
        active_session = next((s for s in sessions if s.status == "active"), None)

        return {
            "id": ch.id,
            "platform": ch.platform,
            "channel_identifier": ch.channel_identifier,
            "display_name": ch.display_name,
            "avatar_url": ch.avatar_url,
            "is_active": ch.is_active,
            "status": ch.status,
            "last_checked_at": ch.last_checked_at.isoformat() if ch.last_checked_at else None,
            "last_live_at": ch.last_live_at.isoformat() if ch.last_live_at else None,
            "last_error": ch.last_error,
            "max_clips_per_stream": ch.max_clips_per_stream,
            "min_clip_duration": ch.min_clip_duration,
            "max_clip_duration": ch.max_clip_duration,
            "preferred_categories": ch.preferred_categories,
            "auto_publish": ch.auto_publish,
            "active_session": {
                "id": active_session.id,
                "title": active_session.title,
                "game_name": active_session.game_name,
                "started_at": active_session.started_at.isoformat() if active_session.started_at else None,
                "stream_url": active_session.stream_url,
            } if active_session else None,
            "sessions": [
                {
                    "id": s.id,
                    "title": s.title,
                    "game_name": s.game_name,
                    "status": s.status,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "clips_count": s.clips_count,
                }
                for s in sessions
            ],
        }

    async def update_channel(
        self, channel_id: str, user_id: str, patch: ChannelUpdateRequest
    ) -> Optional[MonitoredChannel]:
        stmt = select(MonitoredChannel).where(
            MonitoredChannel.id == channel_id, MonitoredChannel.user_id == user_id
        )
        ch = (await self.db.execute(stmt)).scalar_one_or_none()
        if not ch:
            return None

        if patch.display_name is not None:
            ch.display_name = patch.display_name
        if patch.is_active is not None:
            ch.is_active = patch.is_active
        if patch.max_clips_per_stream is not None:
            ch.max_clips_per_stream = patch.max_clips_per_stream
        if patch.min_clip_duration is not None:
            ch.min_clip_duration = patch.min_clip_duration
        if patch.max_clip_duration is not None:
            ch.max_clip_duration = patch.max_clip_duration
        if patch.preferred_categories is not None:
            ch.preferred_categories = patch.preferred_categories
        if patch.auto_publish is not None:
            ch.auto_publish = patch.auto_publish

        ch.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(ch)
        return ch

    async def delete_channel(self, channel_id: str, user_id: str) -> bool:
        stmt = select(MonitoredChannel).where(
            MonitoredChannel.id == channel_id, MonitoredChannel.user_id == user_id
        )
        ch = (await self.db.execute(stmt)).scalar_one_or_none()
        if not ch:
            return False

        await self.db.delete(ch)
        await self.db.commit()
        return True

    async def get_overview(self, user_id: str) -> LiveOverviewStats:
        # Monitored count
        total_stmt = select(func.count(MonitoredChannel.id)).where(
            MonitoredChannel.user_id == user_id, MonitoredChannel.is_active == True
        )
        monitored_count = (await self.db.execute(total_stmt)).scalar() or 0

        # Currently live count
        live_stmt = select(func.count(MonitoredChannel.id)).where(
            MonitoredChannel.user_id == user_id,
            MonitoredChannel.is_active == True,
            MonitoredChannel.status == "live",
        )
        live_count = (await self.db.execute(live_stmt)).scalar() or 0

        # Streams processed count
        sessions_stmt = (
            select(func.count(LiveStreamSession.id))
            .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
            .where(MonitoredChannel.user_id == user_id)
        )
        sessions_count = (await self.db.execute(sessions_stmt)).scalar() or 0

        # Total clips
        clips_stmt = (
            select(func.count(LiveClipMoment.id))
            .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
            .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
            .where(MonitoredChannel.user_id == user_id)
        )
        total_clips = (await self.db.execute(clips_stmt)).scalar() or 0

        # Pending approval
        pending_stmt = (
            select(func.count(LiveClipMoment.id))
            .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
            .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
            .where(MonitoredChannel.user_id == user_id, LiveClipMoment.status == "pending")
        )
        pending_count = (await self.db.execute(pending_stmt)).scalar() or 0

        # Errors
        error_stmt = select(func.count(MonitoredChannel.id)).where(
            MonitoredChannel.user_id == user_id, MonitoredChannel.status == "error"
        )
        error_count = (await self.db.execute(error_stmt)).scalar() or 0

        return LiveOverviewStats(
            monitored_channels_count=monitored_count,
            currently_live_count=live_count,
            streams_processed_count=sessions_count,
            total_clips_count=total_clips,
            clips_awaiting_approval=pending_count,
            processing_errors_count=error_count,
        )
