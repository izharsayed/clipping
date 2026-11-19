-- Live Streaming Engine: monitored streamer channels, active/historical broadcast sessions,
-- and AI-detected candidate moments.

CREATE TABLE IF NOT EXISTS monitored_channels (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL CHECK (platform IN ('twitch', 'youtube', 'kick')),
    channel_identifier VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(20) NOT NULL DEFAULT 'offline' CHECK (
        status IN ('monitoring', 'live', 'offline', 'processing', 'error')
    ),
    last_checked_at TIMESTAMPTZ,
    last_live_at TIMESTAMPTZ,
    last_error TEXT,
    max_clips_per_stream INTEGER NOT NULL DEFAULT 5,
    min_clip_duration INTEGER NOT NULL DEFAULT 20,
    max_clip_duration INTEGER NOT NULL DEFAULT 60,
    preferred_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    auto_publish BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_monitored_channels_user_platform_identifier UNIQUE (user_id, platform, channel_identifier)
);

CREATE INDEX IF NOT EXISTS idx_monitored_channels_user
    ON monitored_channels (user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_monitored_channels_active_poll
    ON monitored_channels (is_active, status, last_checked_at);


CREATE TABLE IF NOT EXISTS live_stream_sessions (
    id VARCHAR(36) PRIMARY KEY,
    channel_id VARCHAR(36) NOT NULL REFERENCES monitored_channels(id) ON DELETE CASCADE,
    stream_id VARCHAR(255),
    title VARCHAR(500),
    game_name VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'ended', 'error')
    ),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    stream_url VARCHAR(1000),
    clips_count INTEGER NOT NULL DEFAULT 0,
    session_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_stream_sessions_channel
    ON live_stream_sessions (channel_id, status);

CREATE INDEX IF NOT EXISTS idx_live_stream_sessions_active
    ON live_stream_sessions (status, started_at);


CREATE TABLE IF NOT EXISTS live_clip_moments (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES live_stream_sessions(id) ON DELETE CASCADE,
    task_id VARCHAR(36) REFERENCES tasks(id) ON DELETE SET NULL,
    clip_id VARCHAR(36) REFERENCES generated_clips(id) ON DELETE SET NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'highlight',
    confidence_score REAL NOT NULL DEFAULT 0.8,
    audio_energy_score REAL NOT NULL DEFAULT 0.0,
    description TEXT,
    transcript TEXT,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'approved', 'rejected', 'published', 'failed')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_clip_moments_session
    ON live_clip_moments (session_id, status);

CREATE INDEX IF NOT EXISTS idx_live_clip_moments_status
    ON live_clip_moments (status, created_at);
