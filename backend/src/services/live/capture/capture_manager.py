"""Capture Manager: coordinates active stream captures and buffers across channels."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from .stream_capture import LiveStreamCaptureEngine
from .rolling_buffer import RollingBuffer
from ....config import get_config

logger = logging.getLogger(__name__)


class LiveCaptureManager:
    """Singleton manager tracking all active live capture engines."""

    _instance: Optional["LiveCaptureManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._captures: Dict[str, LiveStreamCaptureEngine] = {}
        config = get_config()
        self.base_buffer_dir = Path(config.temp_dir) / "live_buffers"
        self.base_buffer_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "LiveCaptureManager":
        if cls._instance is None:
            cls._instance = LiveCaptureManager()
        return cls._instance

    async def start_capture(
        self,
        channel_id: str,
        session_id: str,
        stream_url: str,
        segment_duration: float = 5.0,
        max_buffer_duration: float = 90.0,
    ) -> bool:
        """Launch or return existing capture engine for a channel."""
        async with self._lock:
            existing = self._captures.get(channel_id)
            if existing and existing._running:
                logger.info("Capture engine already active for channel %s", channel_id)
                return True

            channel_buffer_dir = self.base_buffer_dir / channel_id / session_id
            engine = LiveStreamCaptureEngine(
                channel_id=channel_id,
                session_id=session_id,
                stream_url=stream_url,
                buffer_dir=channel_buffer_dir,
                segment_duration=segment_duration,
                max_buffer_duration=max_buffer_duration,
            )

            started = await engine.start()
            if started:
                self._captures[channel_id] = engine
                return True
            return False

    async def stop_capture(self, channel_id: str, cleanup_disk: bool = True) -> None:
        """Stop capture engine for a channel and optionally purge buffer."""
        async with self._lock:
            engine = self._captures.pop(channel_id, None)
            if engine:
                if cleanup_disk:
                    await engine.cleanup()
                else:
                    await engine.stop()

    def get_capture(self, channel_id: str) -> Optional[LiveStreamCaptureEngine]:
        return self._captures.get(channel_id)

    def get_buffer(self, channel_id: str) -> Optional[RollingBuffer]:
        engine = self._captures.get(channel_id)
        return engine.buffer if engine else None

    def is_capturing(self, channel_id: str) -> bool:
        engine = self._captures.get(channel_id)
        return engine._running if engine else False

    async def stop_all(self) -> None:
        """Stop and cleanup all captures (e.g. during shutdown)."""
        async with self._lock:
            for channel_id, engine in list(self._captures.items()):
                try:
                    await engine.cleanup()
                except Exception as e:
                    logger.warning("Error stopping capture %s: %s", channel_id, e)
            self._captures.clear()
