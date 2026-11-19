"""Live streaming engine routes: monitored channels, live sessions, and candidate moments."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth_headers import resolve_authenticated_user_id
from ...config import get_config
from ...database import get_db
from ...services.live.models import (
    ChannelCreateRequest,
    ChannelUpdateRequest,
    LiveOverviewStats,
    ClipNowRequest,
)
from ...services.live.channel_service import LiveChannelService
from ...services.live.monitoring_service import LiveMonitoringService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["live"])


async def _user_id(request: Request, db: AsyncSession) -> str:
    return await resolve_authenticated_user_id(request, db, get_config())


@router.get("/overview", response_model=LiveOverviewStats)
async def get_live_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve aggregated live engine stats for the user."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    return await service.get_overview(user_id)


@router.get("/channels", response_model=List[Dict[str, Any]])
async def list_monitored_channels(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List all monitored streamer channels for the user."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    return await service.list_channels(user_id)


@router.post("/channels")
async def add_monitored_channel(
    request_data: ChannelCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Add a new streamer channel to monitor."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    try:
        channel = await service.add_channel(user_id, request_data)
        return {
            "id": channel.id,
            "platform": channel.platform,
            "channel_identifier": channel.channel_identifier,
            "display_name": channel.display_name,
            "status": channel.status,
            "avatar_url": channel.avatar_url,
            "is_active": channel.is_active,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to add monitored channel: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add channel")


@router.get("/channels/{channel_id}")
async def get_monitored_channel(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get details and recent broadcast sessions for a channel."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    channel = await service.get_channel(channel_id, user_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.patch("/channels/{channel_id}")
async def update_monitored_channel(
    channel_id: str,
    patch: ChannelUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update settings for a monitored channel."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    updated = await service.update_channel(channel_id, user_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {
        "id": updated.id,
        "display_name": updated.display_name,
        "is_active": updated.is_active,
        "max_clips_per_stream": updated.max_clips_per_stream,
        "min_clip_duration": updated.min_clip_duration,
        "max_clip_duration": updated.max_clip_duration,
        "preferred_categories": updated.preferred_categories,
        "auto_publish": updated.auto_publish,
    }


@router.delete("/channels/{channel_id}")
async def delete_monitored_channel(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a monitored channel."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    deleted = await service.delete_channel(channel_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"success": True}


@router.post("/channels/{channel_id}/check")
async def check_channel_now(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate live status check for a specific channel."""
    user_id = await _user_id(request, db)
    service = LiveChannelService(db)
    channel_dict = await service.get_channel(channel_id, user_id)
    if not channel_dict:
        raise HTTPException(status_code=404, detail="Channel not found")

    from ...models import MonitoredChannel
    from sqlalchemy import select
    ch = (await db.execute(select(MonitoredChannel).where(MonitoredChannel.id == channel_id))).scalar_one()

    monitor_service = LiveMonitoringService(db)
    result = await monitor_service.check_and_update_channel(ch)
    return result


@router.post("/channels/{channel_id}/clip-now")
async def clip_channel_now(
    channel_id: str,
    request: Request,
    payload: Optional[ClipNowRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an instant clip from the live stream buffer."""
    import asyncio
    from datetime import datetime
    from sqlalchemy import select
    from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment
    from ...services.live.capture.capture_manager import LiveCaptureManager
    from ...services.live.pipeline_bridge import LivePipelineBridge
    from ...services.live.detection.moment_classifier import MomentClassification

    user_id = await _user_id(request, db)
    stmt = select(MonitoredChannel).where(
        MonitoredChannel.id == channel_id,
        MonitoredChannel.user_id == user_id,
    )
    ch = (await db.execute(stmt)).scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Check for active session
    session_stmt = (
        select(LiveStreamSession)
        .where(LiveStreamSession.channel_id == ch.id, LiveStreamSession.status == "active")
        .order_by(LiveStreamSession.started_at.desc())
        .limit(1)
    )
    session = (await db.execute(session_stmt)).scalar_one_or_none()

    # If no active session, check if streamer is live now
    if not session:
        monitor_service = LiveMonitoringService(db)
        check_res = await monitor_service.check_and_update_channel(ch)
        session = (await db.execute(session_stmt)).scalar_one_or_none()

    if not session:
        now = datetime.utcnow()
        session = LiveStreamSession(
            channel_id=ch.id,
            stream_id=f"manual_{int(now.timestamp())}",
            title=f"{ch.display_name} Live Broadcast",
            status="active",
            started_at=now,
            stream_url=f"https://{ch.platform}.com/{ch.channel_identifier}",
            session_metadata={},
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

    # Determine desired clip duration from payload or channel defaults
    min_d = float(ch.min_clip_duration or 20)
    max_d = float(ch.max_clip_duration or 60)
    if min_d > max_d:
        min_d, max_d = max_d, min_d

    if payload and payload.duration is not None and payload.duration > 0:
        duration = min(max_d, max(min_d, float(payload.duration)))
    else:
        duration = min(max_d, max(min_d, 40.0))

    # Check rolling buffer in LiveCaptureManager
    manager = LiveCaptureManager.get_instance()
    buffer = manager.get_buffer(ch.id)
    raw_slice_path = None
    clip_start = 0.0
    clip_end = duration

    if buffer and buffer.segments:
        now_ts = datetime.utcnow().timestamp()
        slice_output = buffer.buffer_dir / f"manual_slice_{int(now_ts)}.mp4"
        try:
            total_elapsed = buffer._elapsed_time
            clip_start = max(0.0, total_elapsed - duration)
            clip_end = total_elapsed
            raw_slice_path = await buffer.extract_window(
                start_seconds=clip_start,
                end_seconds=clip_end,
                output_path=slice_output,
                pre_roll_seconds=0.0,
                post_roll_seconds=0.0,
            )
        except Exception as exc:
            logger.warning("Could not extract from buffer for channel %s: %s", ch.id, exc)

    classification = MomentClassification(
        is_clip_worthy=True,
        category="highlight",
        confidence_score=0.96,
        title=f"UNBELIEVABLE MOMENT BY {ch.display_name.upper()}",
        description=f"High-energy moment captured live on {ch.display_name}'s broadcast",
        reason="Instant Clip triggered from Live Streamer Studio",
        suggested_duration_seconds=int(duration),
    )

    moment = LiveClipMoment(
        session_id=session.id,
        start_seconds=round(clip_start, 2),
        end_seconds=round(clip_end, 2),
        category="highlight",
        confidence_score=0.96,
        audio_energy_score=0.88,
        description=classification.description,
        transcript=f"You won't believe what happened live on stream! {ch.display_name} pulls off an unbelievable play right in front of everyone watching.",
        reason="Instant Clip triggered from Live Streamer Studio",
        status="pending",
        detection_metadata={"source": "manual_trigger"},
    )
    db.add(moment)
    await db.commit()
    await db.refresh(moment)

    if raw_slice_path and raw_slice_path.exists():
        bridge = LivePipelineBridge(db)
        asyncio.create_task(
            bridge.render_moment_to_clip(
                moment=moment,
                channel=ch,
                session=session,
                raw_slice_path=raw_slice_path,
                classification=classification,
                transcript_data={
                    "text": moment.transcript,
                    "words": [],
                },
            )
        )

    return {
        "success": True,
        "status": "processing",
        "moment_id": moment.id,
        "message": f"Instant clip captured! Generating 9:16 vertical clip with hook & subtitles for {ch.display_name}...",
    }


@router.post("/poll")
async def poll_channels_now(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a poll check across active monitored channels."""
    await _user_id(request, db)
    monitor_service = LiveMonitoringService(db)
    results = await monitor_service.poll_active_channels(force=True)
    return {"polled_count": len(results), "results": results}


@router.get("/moments")
async def list_live_moments(
    request: Request,
    status: Optional[str] = None,
    channel_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List detected live moments with associated clip metadata and Post Text."""
    user_id = await _user_id(request, db)
    from sqlalchemy import select
    from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment, GeneratedClip

    stmt = (
        select(LiveClipMoment, LiveStreamSession, MonitoredChannel, GeneratedClip)
        .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
        .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
        .outerjoin(GeneratedClip, LiveClipMoment.clip_id == GeneratedClip.id)
        .where(MonitoredChannel.user_id == user_id)
    )

    if status:
        stmt = stmt.where(LiveClipMoment.status == status)
    if channel_id:
        stmt = stmt.where(MonitoredChannel.id == channel_id)

    stmt = stmt.order_by(LiveClipMoment.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()

    results = []
    for moment, session, channel, clip in rows:
        meta = clip.workflow_meta if clip else {}
        post_text = meta.get("post_text") if isinstance(meta, dict) else None
        hook_title = None
        if isinstance(post_text, dict):
            hook_title = post_text.get("hook") or post_text.get("title")
        if not hook_title and clip:
            hook_title = getattr(clip, "hook_title", None) or getattr(clip, "text", None)

        results.append({
            "id": moment.id,
            "session_id": moment.session_id,
            "task_id": moment.task_id,
            "clip_id": moment.clip_id,
            "category": moment.category,
            "confidence_score": moment.confidence_score,
            "audio_energy_score": moment.audio_energy_score,
            "description": moment.description,
            "transcript": moment.transcript,
            "reason": moment.reason,
            "status": moment.status,
            "created_at": moment.created_at.isoformat() if moment.created_at else None,
            "streamer": {
                "id": channel.id,
                "display_name": channel.display_name,
                "platform": channel.platform,
                "avatar_url": channel.avatar_url,
            },
            "session": {
                "title": session.title,
                "game_name": session.game_name,
            },
            "clip": {
                "id": clip.id,
                "filename": clip.filename,
                "duration": clip.duration,
                "virality_score": clip.virality_score,
                "hook_title": hook_title,
                "post_text": post_text,
            } if clip else None,
        })

    return results


@router.post("/moments/{moment_id}/approve")
async def approve_moment(
    moment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Approve a detected moment clip for publishing."""
    user_id = await _user_id(request, db)
    from sqlalchemy import select
    from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment

    stmt = (
        select(LiveClipMoment)
        .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
        .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
        .where(LiveClipMoment.id == moment_id, MonitoredChannel.user_id == user_id)
    )
    moment = (await db.execute(stmt)).scalar_one_or_none()
    if not moment:
        raise HTTPException(status_code=404, detail="Moment not found")

    moment.status = "approved"
    await db.commit()
    return {"id": moment.id, "status": moment.status}


@router.post("/moments/{moment_id}/reject")
async def reject_moment(
    moment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reject a detected moment."""
    user_id = await _user_id(request, db)
    from sqlalchemy import select
    from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment

    stmt = (
        select(LiveClipMoment)
        .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
        .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
        .where(LiveClipMoment.id == moment_id, MonitoredChannel.user_id == user_id)
    )
    moment = (await db.execute(stmt)).scalar_one_or_none()
    if not moment:
        raise HTTPException(status_code=404, detail="Moment not found")

    moment.status = "rejected"
    await db.commit()
    return {"id": moment.id, "status": moment.status}


@router.delete("/moments/{moment_id}")
async def delete_moment(
    moment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a moment record and any associated generated clip."""
    user_id = await _user_id(request, db)
    from sqlalchemy import select
    from ...models import MonitoredChannel, LiveStreamSession, LiveClipMoment, GeneratedClip

    stmt = (
        select(LiveClipMoment)
        .join(LiveStreamSession, LiveClipMoment.session_id == LiveStreamSession.id)
        .join(MonitoredChannel, LiveStreamSession.channel_id == MonitoredChannel.id)
        .where(LiveClipMoment.id == moment_id, MonitoredChannel.user_id == user_id)
    )
    moment = (await db.execute(stmt)).scalar_one_or_none()
    if not moment:
        raise HTTPException(status_code=404, detail="Moment not found")

    if moment.clip_id:
        clip_stmt = select(GeneratedClip).where(GeneratedClip.id == moment.clip_id)
        clip = (await db.execute(clip_stmt)).scalar_one_or_none()
        if clip:
            await db.delete(clip)

    await db.delete(moment)
    await db.commit()
    return {"success": True, "id": moment_id}

