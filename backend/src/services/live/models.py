"""Pydantic models for live stream providers, monitoring, and moments."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LiveStatusResult(BaseModel):
    """Result of querying a streaming platform for a channel's live status."""

    is_live: bool
    platform: str
    channel_identifier: str
    display_name: str
    stream_id: Optional[str] = None
    title: Optional[str] = None
    game_name: Optional[str] = None
    viewer_count: Optional[int] = None
    stream_url: Optional[str] = None
    avatar_url: Optional[str] = None
    started_at: Optional[datetime] = None
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ChannelCreateRequest(BaseModel):
    """Payload to add a new monitored streamer channel."""

    platform: str
    channel: str
    display_name: Optional[str] = None
    max_clips_per_stream: int = 5
    min_clip_duration: int = 20
    max_clip_duration: int = 60
    preferred_categories: List[str] = Field(default_factory=list)
    auto_publish: bool = False


class ChannelUpdateRequest(BaseModel):
    """Payload to update an existing monitored channel."""

    display_name: Optional[str] = None
    is_active: Optional[bool] = None
    max_clips_per_stream: Optional[int] = None
    min_clip_duration: Optional[int] = None
    max_clip_duration: Optional[int] = None
    preferred_categories: Optional[List[str]] = None
    auto_publish: Optional[bool] = None


class LiveOverviewStats(BaseModel):
    """Aggregated stats for the live clipping dashboard overview."""

    monitored_channels_count: int = 0
    currently_live_count: int = 0
    streams_processed_count: int = 0
    total_clips_count: int = 0
    clips_awaiting_approval: int = 0
    processing_errors_count: int = 0
