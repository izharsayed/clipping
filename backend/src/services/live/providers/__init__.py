from .base import BaseStreamProvider
from .twitch import TwitchStreamProvider
from .kick import KickStreamProvider
from .youtube import YouTubeLiveProvider


def get_stream_provider(platform: str) -> BaseStreamProvider:
    """Factory to retrieve the appropriate platform provider."""
    platform_lower = platform.lower()
    if platform_lower == "twitch":
        return TwitchStreamProvider()
    if platform_lower == "kick":
        return KickStreamProvider()
    if platform_lower == "youtube":
        return YouTubeLiveProvider()
    raise ValueError(f"Unsupported live platform: {platform}")


__all__ = [
    "BaseStreamProvider",
    "TwitchStreamProvider",
    "KickStreamProvider",
    "YouTubeLiveProvider",
    "get_stream_provider",
]
