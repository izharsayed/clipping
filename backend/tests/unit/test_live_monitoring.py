"""Unit tests for Live Streaming Engine: providers, channel management, and monitoring."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.live.models import (
    LiveStatusResult,
    ChannelCreateRequest,
    ChannelUpdateRequest,
)
from src.services.live.providers.twitch import TwitchStreamProvider
from src.services.live.providers.kick import KickStreamProvider
from src.services.live.providers.youtube import YouTubeLiveProvider
from src.services.live.providers import get_stream_provider
from src.services.live.channel_service import LiveChannelService
from src.services.live.monitoring_service import LiveMonitoringService
from src.models import MonitoredChannel, LiveStreamSession, User


def test_provider_identifier_parsing():
    twitch = TwitchStreamProvider()
    assert twitch.parse_channel_identifier("shroud") == "shroud"
    assert twitch.parse_channel_identifier("@tarik") == "tarik"
    assert twitch.parse_channel_identifier("https://www.twitch.tv/ninja") == "ninja"
    assert twitch.parse_channel_identifier("https://twitch.tv/pokimane/") == "pokimane"

    kick = KickStreamProvider()
    assert kick.parse_channel_identifier("xqc") == "xqc"
    assert kick.parse_channel_identifier("https://kick.com/adinross") == "adinross"

    youtube = YouTubeLiveProvider()
    assert youtube.parse_channel_identifier("mrbeast") == "@mrbeast"
    assert youtube.parse_channel_identifier("@mkbhd") == "@mkbhd"
    assert youtube.parse_channel_identifier("https://www.youtube.com/@veritasium") == "@veritasium"
    assert youtube.parse_channel_identifier("https://www.youtube.com/channel/UC12345/live") == "UC12345"
    assert youtube.parse_channel_identifier("https://www.youtube.com/live/LMbea5SozeM") == "LMbea5SozeM"
    assert youtube.parse_channel_identifier("https://www.youtube.com/watch?v=LMbea5SozeM") == "LMbea5SozeM"


def test_get_stream_provider_factory():
    assert isinstance(get_stream_provider("twitch"), TwitchStreamProvider)
    assert isinstance(get_stream_provider("kick"), KickStreamProvider)
    assert isinstance(get_stream_provider("youtube"), YouTubeLiveProvider)
    with pytest.raises(ValueError):
        get_stream_provider("facebook")


@pytest.mark.asyncio
async def test_twitch_provider_gql_mock():
    provider = TwitchStreamProvider()
    fake_response = {
        "data": {
            "user": {
                "id": "123",
                "login": "shroud",
                "displayName": "shroud",
                "profileImageURL": "https://avatar.png",
                "stream": {
                    "id": "999",
                    "title": "Ranked Grinding",
                    "viewersCount": 15000,
                    "createdAt": "2026-11-19T05:00:00Z",
                    "game": {"name": "VALORANT"},
                },
            }
        }
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = MagicMock(status_code=200, json=lambda: fake_response)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value = mock_client
        res = await provider.check_channel_live("shroud")

        assert res.is_live is True
        assert res.channel_identifier == "shroud"
        assert res.display_name == "shroud"
        assert res.stream_id == "999"
        assert res.title == "Ranked Grinding"
        assert res.game_name == "VALORANT"
        assert res.viewer_count == 15000
        assert res.avatar_url == "https://avatar.png"


@pytest.mark.asyncio
async def test_kick_provider_api_mock():
    provider = KickStreamProvider()
    fake_response = {
        "user": {
            "username": "xQc",
            "profile_pic": "https://kick-avatar.png",
        },
        "livestream": {
            "id": 888,
            "session_title": "DAY 1 GAMING",
            "categories": [{"name": "Just Chatting"}],
            "viewer_count": 42000,
            "created_at": "2026-11-19T04:30:00Z",
        },
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = MagicMock(status_code=200, json=lambda: fake_response)

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value = mock_client
        res = await provider.check_channel_live("xqc")

        assert res.is_live is True
        assert res.channel_identifier == "xqc"
        assert res.display_name == "xQc"
        assert res.stream_id == "888"
        assert res.title == "DAY 1 GAMING"
        assert res.game_name == "Just Chatting"
        assert res.viewer_count == 42000


@pytest.mark.asyncio
async def test_channel_service_crud():
    mock_db = AsyncMock()

    # Mock no existing channel
    mock_execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_execute.return_value = mock_result
    mock_db.execute = mock_execute

    service = LiveChannelService(mock_db)

    # Add channel with mocked live check
    with patch.object(
        TwitchStreamProvider,
        "check_channel_live",
        return_value=LiveStatusResult(
            is_live=False,
            platform="twitch",
            channel_identifier="tarik",
            display_name="tarik",
            avatar_url="https://avatar.png",
        ),
    ):
        req = ChannelCreateRequest(
            platform="twitch",
            channel="tarik",
            max_clips_per_stream=3,
        )
        channel = await service.add_channel("user-1", req)

        assert channel.channel_identifier == "tarik"
        assert channel.display_name == "tarik"
        assert channel.platform == "twitch"
        assert channel.max_clips_per_stream == 3
        assert mock_db.add.called
        assert mock_db.commit.called


@pytest.mark.asyncio
async def test_monitoring_service_transitions():
    mock_db = AsyncMock()
    service = LiveMonitoringService(mock_db)

    # 1. Streamer goes from offline to LIVE
    channel = MonitoredChannel(
        id="ch-1",
        user_id="u-1",
        platform="twitch",
        channel_identifier="tarik",
        display_name="tarik",
        status="offline",
    )

    live_res = LiveStatusResult(
        is_live=True,
        platform="twitch",
        channel_identifier="tarik",
        display_name="tarik",
        stream_id="stream-101",
        title="VCT Watch Party",
        game_name="VALORANT",
    )

    # No existing active session
    mock_session_query = MagicMock()
    mock_session_query.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_session_query

    with patch.object(TwitchStreamProvider, "check_channel_live", return_value=live_res):
        update = await service.check_and_update_channel(channel)
        assert update["status"] == "live"
        assert update["action"] == "session_started"
        assert channel.status == "live"
        assert mock_db.add.called
        assert mock_db.commit.called

    # 2. Streamer goes from LIVE to OFFLINE
    channel.status = "live"
    offline_res = LiveStatusResult(
        is_live=False,
        platform="twitch",
        channel_identifier="tarik",
        display_name="tarik",
    )

    active_session = LiveStreamSession(
        id="sess-1",
        channel_id="ch-1",
        status="active",
    )
    mock_session_query.scalar_one_or_none.return_value = active_session

    with patch.object(TwitchStreamProvider, "check_channel_live", return_value=offline_res):
        update = await service.check_and_update_channel(channel)
        assert update["status"] == "offline"
        assert update["action"] == "session_ended"
        assert channel.status == "offline"
        assert active_session.status == "ended"
        assert active_session.ended_at is not None
        assert mock_db.commit.called
