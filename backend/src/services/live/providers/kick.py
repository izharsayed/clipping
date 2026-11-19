"""Kick live stream provider."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
import httpx

from .base import BaseStreamProvider
from ..models import LiveStatusResult
from ....utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)

KICK_CHANNEL_API_URL = "https://kick.com/api/v2/channels/{slug}"


class KickStreamProvider(BaseStreamProvider):
    """Kick channel live status and stream provider."""

    @property
    def platform_name(self) -> str:
        return "kick"

    def parse_channel_identifier(self, input_text: str) -> str:
        clean = input_text.strip()
        if clean.startswith(("http://", "https://")):
            parsed = urlparse(clean)
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if path_parts:
                return path_parts[0].lower()
        return clean.lstrip("@").lower()

    async def check_channel_live(self, channel_identifier: str) -> LiveStatusResult:
        slug = self.parse_channel_identifier(channel_identifier)
        url = KICK_CHANNEL_API_URL.format(slug=slug)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    user = data.get("user") or {}
                    display_name = user.get("username") or slug
                    avatar_url = user.get("profile_pic")
                    livestream = data.get("livestream")

                    if livestream:
                        categories = livestream.get("categories") or []
                        game_name = categories[0].get("name") if categories else None
                        started_at = None
                        if livestream.get("created_at"):
                            try:
                                started_at = datetime.fromisoformat(
                                    livestream["created_at"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass

                        return LiveStatusResult(
                            is_live=True,
                            platform=self.platform_name,
                            channel_identifier=slug,
                            display_name=display_name,
                            stream_id=str(livestream.get("id")),
                            title=livestream.get("session_title") or "Kick Live Stream",
                            game_name=game_name,
                            viewer_count=livestream.get("viewer_count"),
                            stream_url=f"https://kick.com/{slug}",
                            avatar_url=avatar_url,
                            started_at=started_at,
                            raw_metadata=livestream,
                        )

                    return LiveStatusResult(
                        is_live=False,
                        platform=self.platform_name,
                        channel_identifier=slug,
                        display_name=display_name,
                        avatar_url=avatar_url,
                        stream_url=f"https://kick.com/{slug}",
                    )
        except Exception as exc:
            logger.warning("Kick API check failed for %s: %s; trying ytdl fallback", slug, exc)

        return await self._fallback_ytdl_probe(slug)

    async def _fallback_ytdl_probe(self, slug: str) -> LiveStatusResult:
        stream_url = f"https://kick.com/{slug}"

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
                except Exception:
                    return None

        info = await run_in_thread(probe)
        if info and info.get("is_live"):
            return LiveStatusResult(
                is_live=True,
                platform=self.platform_name,
                channel_identifier=slug,
                display_name=info.get("uploader") or slug,
                stream_id=str(info.get("id")),
                title=info.get("title") or "Kick Live Stream",
                game_name=info.get("genre") or info.get("category"),
                viewer_count=info.get("view_count"),
                stream_url=stream_url,
                avatar_url=info.get("thumbnail"),
                raw_metadata=info,
            )

        return LiveStatusResult(
            is_live=False,
            platform=self.platform_name,
            channel_identifier=slug,
            display_name=slug,
            stream_url=stream_url,
        )

    async def get_stream_playback_url(self, channel_identifier: str) -> Optional[str]:
        slug = self.parse_channel_identifier(channel_identifier)
        return f"https://kick.com/{slug}"
