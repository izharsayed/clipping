"""Twitch live stream provider."""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
import httpx

from .base import BaseStreamProvider
from ..models import LiveStatusResult
from ....utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)

TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
TWITCH_GQL_URL = "https://gql.twitch.tv/gql"


class TwitchStreamProvider(BaseStreamProvider):
    """Twitch channel live status and stream provider."""

    @property
    def platform_name(self) -> str:
        return "twitch"

    def parse_channel_identifier(self, input_text: str) -> str:
        clean = input_text.strip()
        if clean.startswith(("http://", "https://")):
            parsed = urlparse(clean)
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if path_parts:
                return path_parts[0].lower()
        return clean.lstrip("@").lower()

    async def check_channel_live(self, channel_identifier: str) -> LiveStatusResult:
        login = self.parse_channel_identifier(channel_identifier)
        query = {
            "query": """
            query GetChannelStreamStatus($login: String!) {
                user(login: $login) {
                    id
                    login
                    displayName
                    profileImageURL(width: 300)
                    stream {
                        id
                        title
                        viewersCount
                        createdAt
                        game {
                            name
                        }
                    }
                }
            }
            """,
            "variables": {"login": login},
        }

        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(TWITCH_GQL_URL, json=query, headers=headers)
                if res.status_code == 200:
                    data = res.json().get("data", {}).get("user")
                    if not data:
                        return LiveStatusResult(
                            is_live=False,
                            platform=self.platform_name,
                            channel_identifier=login,
                            display_name=login,
                            error="Channel not found",
                        )

                    display_name = data.get("displayName") or login
                    avatar_url = data.get("profileImageURL")
                    stream = data.get("stream")

                    if stream:
                        started_at = None
                        if stream.get("createdAt"):
                            try:
                                started_at = datetime.fromisoformat(
                                    stream["createdAt"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass

                        return LiveStatusResult(
                            is_live=True,
                            platform=self.platform_name,
                            channel_identifier=login,
                            display_name=display_name,
                            stream_id=str(stream.get("id")),
                            title=stream.get("title") or "Live Stream",
                            game_name=(stream.get("game") or {}).get("name"),
                            viewer_count=stream.get("viewersCount"),
                            stream_url=f"https://www.twitch.tv/{login}",
                            avatar_url=avatar_url,
                            started_at=started_at,
                            raw_metadata=stream,
                        )

                    return LiveStatusResult(
                        is_live=False,
                        platform=self.platform_name,
                        channel_identifier=login,
                        display_name=display_name,
                        avatar_url=avatar_url,
                        stream_url=f"https://www.twitch.tv/{login}",
                    )
        except Exception as exc:
            logger.warning("Twitch GQL probe failed for %s: %s; falling back to ytdl probe", login, exc)

        # Fallback to probe via yt-dlp
        return await self._fallback_ytdl_probe(login)

    async def _fallback_ytdl_probe(self, login: str) -> LiveStatusResult:
        stream_url = f"https://www.twitch.tv/{login}"

        def probe():
            import yt_dlp
            ydl_opts = {
                "skip_download": True,
                "extract_flat": False,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(stream_url, download=False)
                    return info
                except Exception as e:
                    return None

        info = await run_in_thread(probe)
        if info and info.get("is_live"):
            return LiveStatusResult(
                is_live=True,
                platform=self.platform_name,
                channel_identifier=login,
                display_name=info.get("uploader") or login,
                stream_id=str(info.get("id")),
                title=info.get("title") or "Live Stream",
                game_name=info.get("genre") or info.get("category"),
                viewer_count=info.get("view_count"),
                stream_url=stream_url,
                avatar_url=info.get("thumbnail"),
                raw_metadata=info,
            )

        return LiveStatusResult(
            is_live=False,
            platform=self.platform_name,
            channel_identifier=login,
            display_name=login,
            stream_url=stream_url,
        )

    async def get_stream_playback_url(self, channel_identifier: str) -> Optional[str]:
        login = self.parse_channel_identifier(channel_identifier)
        return f"https://www.twitch.tv/{login}"
