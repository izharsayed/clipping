"""Abstract base class for platform live stream providers."""

from abc import ABC, abstractmethod
from typing import Optional
from ..models import LiveStatusResult


class BaseStreamProvider(ABC):
    """Interface for platform-specific live stream checkers."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Name of the platform (e.g. 'twitch', 'youtube', 'kick')."""
        pass

    @abstractmethod
    def parse_channel_identifier(self, input_text: str) -> str:
        """Normalize URL or username to standard channel identifier/slug."""
        pass

    @abstractmethod
    async def check_channel_live(self, channel_identifier: str) -> LiveStatusResult:
        """Check whether the channel is currently live and retrieve metadata."""
        pass

    @abstractmethod
    async def get_stream_playback_url(self, channel_identifier: str) -> Optional[str]:
        """Get live stream playback URL for capture tools (e.g. HLS or direct stream)."""
        pass
