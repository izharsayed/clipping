"""YouTube Live stream provider."""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from .base import BaseStreamProvider
from ..models import LiveStatusResult
from ....utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)


class YouTubeLiveProvider(BaseStreamProvider):
    """YouTube Live stream status and playback provider."""

    @property
    def platform_name(self) -> str:
        return "youtube"

    def parse_channel_identifier(self, input_text: str) -> str:
        clean = input_text.strip()
        if clean.startswith(("http://", "https://")):
            parsed = urlparse(clean)
            path = parsed.path.strip("/")
            # Handle @handle or channel/id or c/name
            if path.startswith("@"):
                return path.split("/")[0]
            if "/@" in parsed.path:
                return "@" + parsed.path.split("/@")[1].split("/")[0]
            parts = path.split("/")
            if parts and parts[0] in {"channel", "c", "user"} and len(parts) > 1:
                return parts[1]
            if parts and parts[0] == "live" and len(parts) > 1:
                return parts[1]
            if "v=" in parsed.query:
                from urllib.parse import parse_qs
                v = parse_qs(parsed.query).get("v")
                if v:
                    return v[0]
            if parsed.netloc == "youtu.be" and parts:
                return parts[0]
            if parts:
                return parts[0]
        if not clean.startswith("@") and not clean.startswith("UC"):
            return f"@{clean}"
        return clean

    async def check_channel_live(self, channel_identifier: str) -> LiveStatusResult:
        identifier = self.parse_channel_identifier(channel_identifier)
        if identifier.startswith("@"):
            live_url = f"https://www.youtube.com/{identifier}/live"
        elif identifier.startswith("UC"):
            live_url = f"https://www.youtube.com/channel/{identifier}/live"
        elif len(identifier) == 11 and not identifier.startswith("@"):
            live_url = f"https://www.youtube.com/watch?v={identifier}"
        else:
            live_url = f"https://www.youtube.com/@{identifier}/live"

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
                    info = ydl.extract_info(live_url, download=False)
                    return info
                except Exception as e:
                    # Not live or error
                    return None

        info = await run_in_thread(probe)
        if info and info.get("is_live"):
            return LiveStatusResult(
                is_live=True,
                platform=self.platform_name,
                channel_identifier=identifier,
                display_name=info.get("channel") or info.get("uploader") or identifier,
                stream_id=str(info.get("id")),
                title=info.get("title") or "YouTube Live Stream",
                game_name=info.get("genre") or info.get("category"),
                viewer_count=info.get("view_count") or info.get("concurrent_view_count"),
                stream_url=info.get("webpage_url") or live_url,
                avatar_url=info.get("thumbnail"),
                raw_metadata={"id": info.get("id"), "title": info.get("title")},
            )

        return LiveStatusResult(
            is_live=False,
            platform=self.platform_name,
            channel_identifier=identifier,
            display_name=identifier,
            stream_url=live_url,
        )

    async def get_stream_playback_url(self, channel_identifier: str) -> Optional[str]:
        identifier = self.parse_channel_identifier(channel_identifier)
        if identifier.startswith("@"):
            return f"https://www.youtube.com/{identifier}/live"
        elif identifier.startswith("UC"):
            return f"https://www.youtube.com/channel/{identifier}/live"
        return f"https://www.youtube.com/@{identifier}/live"
