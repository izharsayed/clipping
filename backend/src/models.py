from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    CheckConstraint,
    ARRAY,
    Boolean,
    Float,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
import uuid

from .database import Base


def generate_uuid_string():
    """Generate a UUID as a string for compatibility with Prisma"""
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    emailVerified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=func.now(),
    )

    # Additional fields for backend compatibility
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    default_clip_length: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=sql_text("'auto'")
    )
    create_settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )

    # Billing fields
    notify_on_completion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'true'")
    )
    product_updates_unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'false'")
    )
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'free'")
    )
    subscription_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'inactive'")
    )
    subscription_provider: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    billing_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_cancel_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Pro subscribers from before the 720p change keep 1080p while subscribed.
    legacy_hd: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'false'")
    )
    # Higher tier chosen in the billing portal, granted only after its invoice is paid.
    pending_plan: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pending_plan_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # Relationships
    tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="user", cascade="all, delete-orphan"
    )
    monitored_channels: Mapped[List["MonitoredChannel"]] = relationship(
        "MonitoredChannel", back_populates="user", cascade="all, delete-orphan"
    )
    token_usages: Mapped[List["ApiTokenUsage"]] = relationship(
        "ApiTokenUsage", back_populates="user", cascade="all, delete-orphan"
    )


class EmailDelivery(Base):
    """SES acceptance metadata for correlating bounce and complaint reports."""

    __tablename__ = "email_deliveries"

    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    prefer_admin_value: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'false'")
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RevenueCatWebhookEvent(Base):
    __tablename__ = "revenuecat_webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    generated_clips_ids: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(36)), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), server_default=sql_text("'pending'"), nullable=False
    )
    progress: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'0'")
    )
    progress_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Font customization fields
    font_family: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, server_default=sql_text("'TikTokSans-Regular'")
    )
    font_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'24'")
    )
    font_color: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, server_default=sql_text("'#FFFFFF'")
    )  # Hex color code

    # Caption template and B-roll options
    caption_template: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, server_default=sql_text("'default'")
    )
    include_broll: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default=sql_text("'false'")
    )
    processing_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'fast'")
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cache_hit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'false'")
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    stage_timings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    # Source length charged against the monthly minute allowance.
    source_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    completion_notification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    share_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    share_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'false'")
    )
    # What the task makes (highlights, series, topic, recap, trailer), its
    # validated options and the plan persisted before rendering.
    workflow: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'highlights'")
    )
    workflow_options: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    workflow_plan: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "workflow IN ('highlights', 'series', 'topic', 'recap', 'trailer')",
            name="tasks_workflow_check",
        ),
        Index("idx_tasks_user_workflow", "user_id", "workflow"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="tasks")
    generated_clips: Mapped[List["GeneratedClip"]] = relationship(
        "GeneratedClip", back_populates="task", cascade="all, delete-orphan"
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Add check constraint for type enum
    __table_args__ = (
        CheckConstraint(
            "type IN ('youtube', 'video_url', 'twitch', 'kick')",
            name="check_source_type",
        ),
    )

    # Relationships - Source can have multiple tasks
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="source")

    def decide_source_type(self, source_url: str) -> str:
        """Decide which type of source this is."""
        if "youtube" in source_url:
            return "youtube"
        else:
            return "video_url"


class GeneratedClip(Base):
    __tablename__ = "generated_clips"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    start_time: Mapped[str] = mapped_column(String(20), nullable=False)  # MM:SS format
    end_time: Mapped[str] = mapped_column(String(20), nullable=False)  # MM:SS format
    duration: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # Duration in seconds
    text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # Transcript text for this clip
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # AI reasoning for selection
    clip_order: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Order within the task

    # Virality score breakdown
    virality_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'0'")
    )
    hook_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'0'")
    )
    engagement_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'0'")
    )
    value_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'0'")
    )
    shareability_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=sql_text("'0'")
    )
    hook_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Workflow clips: part | topic | recap | trailer, the series part number
    # and the planned ranges and labels (empty for highlights).
    workflow_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    part_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    workflow_meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="generated_clips")


class ProcessingCache(Base):
    __tablename__ = "processing_cache"

    cache_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    video_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MonitoredChannel(Base):
    __tablename__ = "monitored_channels"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'true'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'offline'")
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_live_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_clips_per_stream: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'5'")
    )
    min_clip_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'20'")
    )
    max_clip_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'60'")
    )
    preferred_categories: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    auto_publish: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("'false'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "platform IN ('twitch', 'youtube', 'kick')",
            name="check_monitored_channel_platform",
        ),
        CheckConstraint(
            "status IN ('monitoring', 'live', 'offline', 'processing', 'error')",
            name="check_monitored_channel_status",
        ),
        UniqueConstraint(
            "user_id", "platform", "channel_identifier",
            name="uq_monitored_channels_user_platform_identifier",
        ),
        Index("idx_monitored_channels_user", "user_id", "is_active"),
        Index("idx_monitored_channels_active_poll", "is_active", "status", "last_checked_at"),
    )

    user: Mapped["User"] = relationship("User", back_populates="monitored_channels")
    sessions: Mapped[List["LiveStreamSession"]] = relationship(
        "LiveStreamSession", back_populates="channel", cascade="all, delete-orphan"
    )


class LiveStreamSession(Base):
    __tablename__ = "live_stream_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("monitored_channels.id", ondelete="CASCADE"), nullable=False
    )
    stream_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    game_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stream_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    clips_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'0'")
    )
    session_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'ended', 'error')",
            name="check_live_stream_session_status",
        ),
        Index("idx_live_stream_sessions_channel", "channel_id", "status"),
        Index("idx_live_stream_sessions_active", "status", "started_at"),
    )

    channel: Mapped["MonitoredChannel"] = relationship("MonitoredChannel", back_populates="sessions")
    moments: Mapped[List["LiveClipMoment"]] = relationship(
        "LiveClipMoment", back_populates="session", cascade="all, delete-orphan"
    )


class LiveClipMoment(Base):
    __tablename__ = "live_clip_moments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid_string
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("live_stream_sessions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    clip_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("generated_clips.id", ondelete="SET NULL"), nullable=True
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=sql_text("'highlight'")
    )
    confidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=sql_text("'0.8'")
    )
    audio_energy_score: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=sql_text("'0.0'")
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'published', 'failed')",
            name="check_live_clip_moment_status",
        ),
        Index("idx_live_clip_moments_session", "session_id", "status"),
        Index("idx_live_clip_moments_status", "status", "created_at"),
    )

    session: Mapped["LiveStreamSession"] = relationship("LiveStreamSession", back_populates="moments")


class ApiTokenUsage(Base):
    __tablename__ = "api_token_usages"

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=generate_uuid_string
    )
    user_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'0'")
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'0'")
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("'0'")
    )
    cost_usd: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=sql_text("'0.0'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_api_token_usages_user_id", "user_id"),
        Index("idx_api_token_usages_created_at", "created_at"),
        Index("idx_api_token_usages_provider", "provider"),
        Index("idx_api_token_usages_feature", "feature"),
    )

    user: Mapped["User"] = relationship("User", back_populates="token_usages")


